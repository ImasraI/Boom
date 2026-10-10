"""Durable draft booklets with independent drafting and blind-solving workers."""
import json
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update, text

from app.auth.database import PoolDraftJob, SessionLocal
from app.config import get_settings
from app.rag import mock_generation, pool_core, question_bank
from app.rag.llm import get_pool_verifier_client
from app.rag.provider_quota import pool_generation_status, pool_verification_status
from app.utils.logger import get_logger

logger = get_logger(__name__)
_OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
_VERIFY_WAKE = threading.Event()
_ASSEMBLE_LOCK = threading.Lock()
_OPEN = ("drafting", "pending", "verifying")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _lease():
    return _now() + timedelta(minutes=10)


def snapshot():
    with SessionLocal() as db:
        rows = db.execute(select(PoolDraftJob.status, func.count(),
            func.sum(PoolDraftJob.question_count), func.sum(PoolDraftJob.verified_count),
            func.sum(PoolDraftJob.rejected_count)).group_by(PoolDraftJob.status)).all()
    pending = sum(count for status, count, *_ in rows if status in _OPEN)
    return {"enabled": get_settings().POOL_DRAFT_QUEUE_ENABLED,
        "capacity": max(1, get_settings().POOL_DRAFT_QUEUE_CAPACITY),
        "pending_booklets": pending,
        "pending_questions": sum((qs or 0) - (verified or 0) - (rejected or 0)
            for status, _, qs, verified, rejected in rows if status in _OPEN),
        "drafting_booklets": sum(count for status, count, *_ in rows if status == "drafting"),
        "verifying_booklets": sum(count for status, count, *_ in rows if status == "verifying"),
        "completed_booklets": sum(count for status, count, *_ in rows if status == "completed"),
        "rejected_booklets": sum(count for status, count, *_ in rows if status == "rejected"),
        "verified_questions": sum(verified or 0 for _, _, _, verified, _ in rows),
        "rejected_questions": sum(rejected or 0 for _, _, _, _, rejected in rows)}


def create_job(config, major, difficulty):
    plan = pool_core.generation_plan(major, ranked=difficulty == pool_core.DUEL_DIFFICULTY,
        subjects=config.get("subjects"), **({"total_questions": config.get("total_questions", 0)}
            if difficulty != pool_core.DUEL_DIFFICULTY else {}))
    with SessionLocal() as db:
        # Reserve a queue slot atomically, including across API processes.
        db.execute(text("BEGIN IMMEDIATE"))
        count = db.scalar(select(func.count()).select_from(PoolDraftJob).where(PoolDraftJob.status.in_(_OPEN)))
        if count >= max(1, get_settings().POOL_DRAFT_QUEUE_CAPACITY):
            return None
        job = PoolDraftJob(config=json.dumps(config, ensure_ascii=False), major=major,
            difficulty=difficulty, grade=config.get("grade", ""), plan=json.dumps(plan, ensure_ascii=False),
            status="drafting", lease_owner=_OWNER, lease_until=_lease())
        db.add(job); db.commit(); db.refresh(job)
        return job.id


def append_batch(job_id, batch):
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        if job.status != "drafting" or job.lease_owner != _OWNER:
            raise RuntimeError("Draft lease lost")
        rows = json.loads(job.questions)
        seen = {(q["subject"], mock_generation._norm_qtext(q["text"])) for q in rows}
        for q in batch:
            if not question_bank._valid(q):
                continue
            identity = (q.get("subject"), mock_generation._norm_qtext(q["text"]))
            if identity in seen:
                continue
            seen.add(identity)
            clean = {k: v for k, v in q.items() if k not in ("bank_id", "id", "_queue_status")}
            rows.append({**clean, "_id": len(rows) + 1, "verification_status": "pending", "_queue_status": "pending"})
        job.questions = json.dumps(rows, ensure_ascii=False)
        job.question_count = len(rows)
        job.lease_until = _lease()
        db.commit()


def finish_draft(job_id):
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        if job and job.status == "drafting" and job.lease_owner == _OWNER:
            job.status = "pending" if job.question_count else "rejected"
            job.lease_owner = ""; job.lease_until = None
            db.commit()
    _VERIFY_WAKE.set()


def recover_interrupted():
    with SessionLocal() as db:
        for job in db.scalars(select(PoolDraftJob).where(PoolDraftJob.status.in_(("drafting", "verifying")))):
            dead = False
            try:
                host, pid, _ = job.lease_owner.split(":")
                # On Windows os.kill(pid, 0) sends CTRL_C_EVENT, not a liveness
                # probe. Other Windows processes recover on lease expiry.
                if host == socket.gethostname() and int(pid) != os.getpid() and os.name != "nt":
                    try: os.kill(int(pid), 0)
                    except ProcessLookupError: dead = True
                    except PermissionError: pass
            except (ValueError, OSError):
                dead = True
            if dead or not job.lease_until or job.lease_until <= _now():
                job.status = "pending" if job.question_count > job.verified_count + job.rejected_count else (
                    "completed" if job.verified_count else "rejected")
                job.lease_owner = ""; job.lease_until = None
        db.commit()


def claim_job():
    with SessionLocal() as db:
        job_id = db.scalar(select(PoolDraftJob.id).where(PoolDraftJob.status == "pending",
            (PoolDraftJob.retry_at.is_(None) | (PoolDraftJob.retry_at <= _now())))
            .order_by(PoolDraftJob.id).limit(1))
        if job_id is None:
            return None
        claimed = db.execute(update(PoolDraftJob).where(PoolDraftJob.id == job_id,
            PoolDraftJob.status == "pending").values(status="verifying", lease_owner=_OWNER, lease_until=_lease()))
        db.commit()
        return job_id if claimed.rowcount == 1 else None


def verify_step(job_id, client=None):
    """Commit each batch's decisions and bank inserts together; refusals keep drafts."""
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        if not job or job.status != "verifying" or job.lease_owner != _OWNER:
            return False
        rows = json.loads(job.questions)
        positions = [i for i, q in enumerate(rows) if q.get("_queue_status") == "pending"][:10]
    client = client if client is not None else get_pool_verifier_client()
    verdicts = mock_generation._verify_batch(client, [rows[i] for i in positions], 60)
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        if job.status != "verifying" or job.lease_owner != _OWNER:
            return False
        if verdicts is None:
            # A terminal quota/access refusal is remembered by the provider
            # client. Never discard candidates because a provider is unavailable.
            job.status = "pending"; job.retry_at = _now() + timedelta(seconds=60)
            job.lease_owner = ""; job.lease_until = None
            db.commit()
            return False
        accepted = []
        for index, position in enumerate(positions, start=1):
            q = rows[position]
            valid = (verdicts.get(index) == q["answer"]
                     and not mock_generation._missing_visible_reference(q))
            q["_queue_status"] = "verified" if valid else "rejected"
            q["verification_status"] = "verified" if valid else "rejected"
            if valid:
                accepted.append({k: v for k, v in q.items() if k != "_queue_status"})
                job.verified_count += 1
            else:
                job.rejected_count += 1
        if accepted:
            pool_core._harvest_questions(db, accepted, job.major, job.difficulty, job.grade, commit=False)
        job.questions = json.dumps(rows, ensure_ascii=False)
        job.status = ("pending" if any(q.get("_queue_status") == "pending" for q in rows)
                      else "completed" if job.verified_count else "rejected")
        job.retry_at = None; job.lease_owner = ""; job.lease_until = None
        db.commit()
        return bool(accepted)


def _active():
    from app.rag import pool_service as service
    state = service.snapshot()
    return not service._shutdown.is_set() and state.get("enabled", False)


def _assemble():
    from app.rag import pool_service as service
    with _ASSEMBLE_LOCK:
        if not _active(): return False
        state = service.snapshot(); config = state["config"]
        if config["count"] and state["produced"] >= config["count"]: return False
        shelves = service._shelves(config)
        cursor = state.get("assemble_cursor", 0)
        for offset in range(len(shelves)):
            index = (cursor + offset) % len(shelves)
            major, difficulty = shelves[index]
            with SessionLocal() as db:
                kwargs = dict(grade=config["grade"], subjects=config.get("subjects"), topics=config.get("topics"))
                if difficulty != pool_core.DUEL_DIFFICULTY:
                    kwargs["total_questions"] = config.get("total_questions", 0)
                success = pool_core.assemble_stock(db, major, difficulty, **kwargs)
            if success:
                with service._LOCK:
                    current = service.snapshot()
                    current["produced"] += 1
                    current["assemble_cursor"] = index + 1
                    service._save(current)
                pool_core.bump_produced()
                return True
        return False


def _worker_state(stage, status, health=None):
    from app.rag import pool_service as service
    service._update(**{stage: {"status": status, **(health or {})}})


def _verify_loop(stop):
    from app.rag import pool_service as service
    while _active() and not stop.is_set():
        try:
            recover_interrupted()
            health = pool_verification_status()
            if health["blocked"]:
                _worker_state("verification", "waiting_for_quota", health)
                _VERIFY_WAKE.wait(60); _VERIFY_WAKE.clear(); continue
            job_id = claim_job()
            if job_id is None:
                _worker_state("verification", "waiting_for_drafts", health)
                _VERIFY_WAKE.wait(5); _VERIFY_WAKE.clear(); continue
            _worker_state("verification", "verifying", health)
            verify_step(job_id)
            if not stop.is_set():
                _assemble()
            service._wake.set()
        except Exception:
            logger.exception("Queued verification failed; saved candidates retained")
            _worker_state("verification", "error")
            _VERIFY_WAKE.wait(60); _VERIFY_WAKE.clear()


class _Interrupted(Exception):
    pass


def run():
    from app.rag import pool_service as service
    verifier = None
    stop = threading.Event()
    owned = False
    try:
        while _active() and not owned:
            owned = pool_core.begin_progress("selected:queue")
            if not owned:
                service._update(status="waiting_for_worker")
                service._wake.wait(30); service._wake.clear()
        if not owned: return
        pool_core.clear_cancel()
        recover_interrupted()
        _VERIFY_WAKE.clear()
        verifier = threading.Thread(target=_verify_loop, args=(stop,), daemon=True, name="pool-queue-verifier")
        verifier.start()
        failures = 0
        while _active():
            state = service.snapshot(); config = state["config"]
            if config["count"] and state["produced"] >= config["count"]:
                service._update(enabled=False, status="finished"); break
            service._update(status="queue_running", last_error="", retry_at=None)
            if _assemble(): continue
            if state.get("drafting_paused"):
                _worker_state("drafting", "error")
                service._wake.wait(60); service._wake.clear(); continue
            stats = snapshot()
            if stats["pending_booklets"] >= stats["capacity"] or (config["count"] and
                    state["produced"] + stats["pending_booklets"] >= config["count"]):
                _worker_state("drafting", "waiting_for_queue")
                service._wake.wait(5); service._wake.clear(); continue
            health = pool_generation_status()
            if health["blocked"]:
                _worker_state("drafting", "waiting_for_quota", health)
                service._wake.wait(60); service._wake.clear(); continue
            shelves = service._shelves(config)
            cursor = state.get("draft_cursor", state.get("cursor", 0))
            major, difficulty = shelves[cursor % len(shelves)]
            job_id = create_job(config, major, difficulty)
            if job_id is None: continue
            service._update(draft_cursor=cursor + 1)
            _worker_state("drafting", "generating", health)
            with SessionLocal() as db:
                plan = json.loads(db.get(PoolDraftJob, job_id).plan)
            def save_batch(batch):
                append_batch(job_id, batch)
                if not _active(): raise _Interrupted()
            try:
                mock_generation.generate_booklet(0, plan, topics=config.get("topics") or [],
                    difficulty="konkur" if difficulty == pool_core.DUEL_DIFFICULTY else difficulty,
                    grade=config["grade"], timeout=60, on_drafted=save_batch)
            except _Interrupted:
                pass
            finally:
                finish_draft(job_id)
            with SessionLocal() as db:
                empty = db.get(PoolDraftJob, job_id).question_count == 0
            failures = failures + 1 if empty else 0
            if failures >= 3 and not pool_generation_status()["blocked"]:
                _worker_state("drafting", "error")
                service._update(drafting_paused=True)
    except Exception:
        logger.exception("Queued drafting failed; saved candidates retained")
        service._update(enabled=False, status="failed", last_error="خطای تولید؛ پیش‌نویس‌های ذخیره‌شده حفظ شدند.")
    finally:
        stop.set()
        _VERIFY_WAKE.set()
        if verifier: verifier.join(timeout=5)
        if owned: pool_core.finish_progress()
        if service.snapshot().get("status") == "stopping": service._update(status="stopped")


def wake():
    _VERIFY_WAKE.set()
