"""Durable draft booklets with independent drafting and blind-solving workers."""
import json
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update, text
from fastapi import HTTPException

from app.auth.database import PoolDraftJob, BankQuestion, SessionLocal
from app.config import get_settings
from app.rag import mock_generation, pool_core, question_bank, exam_blueprint
from app.rag.llm import get_pool_verifier_client
from app.rag.provider_quota import pool_generation_status, pool_verification_status, is_terminal_provider_error
from app.utils.logger import get_logger

logger = get_logger(__name__)
_OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
_VERIFY_WAKE = threading.Event()
_ASSEMBLE_LOCK = threading.Lock()
_OPEN = ("drafting", "pending", "verifying")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _lease():
    return _now() + timedelta(minutes=30)


def snapshot(scope=None):
    with SessionLocal() as db:
        query = select(PoolDraftJob.status, func.count(),
            func.sum(PoolDraftJob.question_count), func.sum(PoolDraftJob.verified_count),
            func.sum(PoolDraftJob.rejected_count)).group_by(PoolDraftJob.status)
        if scope:
            query = query.where(func.json_extract(PoolDraftJob.config, '$.weekly_scope') == scope)
        rows = db.execute(query).all()
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


def _weekly_draft_plan(db, config, major, plan, *, include_pending=True):
    """Spend the next draft on the least stocked subject/branch, not math again.

    Verified unused stock and saved pending candidates both contribute. Pending
    questions only guide drafting; they are never playable until reviewed.
    Each durable job is a small tranche, not necessarily a complete paper.
    """
    reserved = pool_core._reserved_stock_ids(db)
    candidates = [json.loads(q.content) for q in db.scalars(select(BankQuestion).where(
        BankQuestion.owner_id == 0, BankQuestion.verified == True,
        BankQuestion.status == 'active', BankQuestion.uses == 0,
        BankQuestion.major == pool_core.CANONICAL_MAJOR[major], BankQuestion.difficulty == 'konkur',
        BankQuestion.grade_level <= question_bank.grade_number(config.get('grade', '')),
        BankQuestion.id.not_in(reserved),
        func.json_extract(BankQuestion.content, '$.weekly_ranked_scope') == config['weekly_scope']))]
    pending = db.scalars(select(PoolDraftJob).where(PoolDraftJob.status.in_(_OPEN),
        PoolDraftJob.major == major, PoolDraftJob.difficulty == pool_core.DUEL_DIFFICULTY,
        func.json_extract(PoolDraftJob.config, '$.weekly_scope') == config['weekly_scope']))
    if include_pending:
        for job in pending:
            candidates.extend(q for q in json.loads(job.questions) if q.get('_queue_status') == 'pending')
    seen = set()
    unique = []
    for question in candidates:
        identity = question_bank._fingerprint(question, 0)
        if identity not in seen:
            seen.add(identity); unique.append(question)
    options = []
    for row in exam_blueprint.coverage_rows(plan):
        eligible = [q for q in unique if q.get('subject') == row['name'] and
            (not row.get('branch') or q.get('branch') == row['branch']) and
            q.get('weekly_ranked_scope') == config['weekly_scope'] and
            q.get('curriculum_id') in row.get('curriculum_ids', []) and
            (not row.get('full_mock') or (q.get('grounding_status') == 'book_ocr' and
             q.get('book') and type(q.get('page')) is int and q.get('source_quote')))]
        represented = {q['curriculum_id'] for q in eligible}
        nodes = exam_blueprint.lessons_for(row, config.get('grade', ''))
        expected = min(row['questions'], len(nodes))
        count = len(eligible)
        if len(represented) < expected:
            count = min(count, len(represented))
        options.append((count / row['questions'], count, row, represented, expected, nodes))
    subject_counts = {}
    for _, count, row, *_ in options:
        subject_counts[row['name']] = subject_counts.get(row['name'], 0) + count
    quotas = {row['name']: row['questions'] for row in plan}
    _, count, row, represented, expected, nodes = min(options, key=lambda option: (
        option[0], subject_counts[option[2]['name']] / quotas[option[2]['name']]))
    needed = row['questions'] - count % row['questions']
    drafted = {**row, 'branches': {}, 'questions': needed}
    if len(represented) < expected:
        # New chapter coverage takes priority over more copies of one lesson.
        ids = [node['id'] for node in nodes if node['id'] not in represented]
        if ids: drafted['curriculum_ids'] = ids
    return [drafted]


def create_job(config, major, difficulty):
    from app.rag.weekly_ranked import prepare_config
    config = prepare_config(config)
    plan = config.get('weekly_plan') or pool_core.generation_plan(major, ranked=difficulty == pool_core.DUEL_DIFFICULTY,
        subjects=config.get("subjects"), **({"total_questions": config.get("total_questions", 0)}
            if difficulty != pool_core.DUEL_DIFFICULTY else {}))
    with SessionLocal() as db:
        # Reserve a queue slot atomically, including across API processes.
        db.execute(text("BEGIN IMMEDIATE"))
        slots = select(func.count()).select_from(PoolDraftJob).where(PoolDraftJob.status.in_(_OPEN))
        if config.get('weekly_scope'):
            slots = slots.where(func.json_extract(PoolDraftJob.config, '$.weekly_scope') == config['weekly_scope'])
        count = db.scalar(slots)
        if count >= max(1, get_settings().POOL_DRAFT_QUEUE_CAPACITY):
            return None
        if config.get('weekly_scope'):
            plan = _weekly_draft_plan(db, config, major, plan)
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
            scoped_rows = [r for r in json.loads(job.plan) if r.get('weekly_ranked_scope')]
            scoped = next((r for r in scoped_rows if r['name'] == q.get('subject') and
                q.get('curriculum_id') in r['curriculum_ids'] and
                (not r.get('branch') or r['branch'] == q.get('branch'))), None)
            if scoped_rows and not scoped:
                continue
            if scoped:
                clean['weekly_ranked_scope'] = scoped['weekly_ranked_scope']
                clean['maze_scope'] = scoped.get('maze_scope', {}).get(q['curriculum_id'], [])
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


def claim_job(scope=None):
    with SessionLocal() as db:
        query = select(PoolDraftJob.id).where(PoolDraftJob.status == "pending",
            (PoolDraftJob.retry_at.is_(None) | (PoolDraftJob.retry_at <= _now())))
        if scope:
            query = query.where(func.json_extract(PoolDraftJob.config, '$.weekly_scope') == scope)
        job_id = db.scalar(query.order_by(PoolDraftJob.id).limit(1))
        if scope and job_id is not None:
            first = db.get(PoolDraftJob, job_id)
            config = json.loads(first.config)
            if config.get('weekly_plan'):
                wanted = _weekly_draft_plan(db, config, first.major,
                                           config['weekly_plan'], include_pending=False)[0]
                # Complete the weakest shelf first; old extra math candidates
                # remain durable and will be reviewed when their turn comes.
                for candidate in db.scalars(select(PoolDraftJob).where(PoolDraftJob.id.in_(query)).order_by(PoolDraftJob.id)):
                    if any(q.get('_queue_status') == 'pending' and
                           q.get('_review_after', '') <= _now().isoformat() and
                           q.get('subject') == wanted['name'] and
                           q.get('curriculum_id') in wanted['curriculum_ids'] and
                           (not wanted.get('branch') or q.get('branch') == wanted['branch'])
                           for q in json.loads(candidate.questions)):
                        job_id = candidate.id; break
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
        positions = [i for i, q in enumerate(rows) if q.get("_queue_status") == "pending"
                     and q.get("_review_after", "") <= _now().isoformat()][:mock_generation._VERIFY_BATCH_SIZE]
    client = client if client is not None else get_pool_verifier_client()
    verdicts = mock_generation._verify_batch(client, [rows[i] for i in positions], 60)
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        if job.status != "verifying" or job.lease_owner != _OWNER:
            return False
        if verdicts is None:
            # A terminal quota/access refusal is remembered by the provider
            # client. Never discard candidates because a provider is unavailable.
            for position in positions:
                rows[position]["validation"] = {"version": 1, "status": "pending", "reason": "verifier_provider_or_protocol_error"}
            job.questions = json.dumps(rows, ensure_ascii=False)
            job.status = "pending"; job.retry_at = _now() + timedelta(seconds=60)
            job.lease_owner = ""; job.lease_until = None
            db.commit()
            return False
        accepted = []
        for index, position in enumerate(positions, start=1):
            q = rows[position]
            if index in getattr(verdicts, "details", {}):
                q["validation"] = verdicts.details[index]
            if index in getattr(verdicts, "deferred", set()):
                q["_review_retries"] = q.get("_review_retries", 0) + 1
                q["_review_after"] = (_now() + timedelta(seconds=min(
                    21600, 60 * 2 ** min(q["_review_retries"], 8)))).isoformat()
                continue
            valid = (verdicts.get(index) == q["answer"]
                     and not mock_generation._missing_visible_reference(q))
            q["_queue_status"] = "verified" if valid else "rejected"
            q["verification_status"] = "verified" if valid else "rejected"
            if valid:
                accepted.append({k: v for k, v in q.items() if not k.startswith("_review") and k != "_queue_status"})
                job.verified_count += 1
            else:
                job.rejected_count += 1
        if accepted:
            pool_core._harvest_questions(db, accepted, job.major, job.difficulty, job.grade, commit=False)
        job.questions = json.dumps(rows, ensure_ascii=False)
        job.status = ("pending" if any(q.get("_queue_status") == "pending" for q in rows)
                      else "completed" if job.verified_count else "rejected")
        # An uncertain question waits without blocking the remaining questions
        # in the same draft booklet. Only due reviews compete for this lease.
        pending_times = [datetime.fromisoformat(q["_review_after"]) if q.get("_review_after") else _now()
                         for q in rows if q.get("_queue_status") == "pending"]
        earliest = min(pending_times, default=_now())
        job.retry_at = earliest if earliest > _now() else None
        job.lease_owner = ""; job.lease_until = None
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
        if config.get('kind')=='weekly_ranked':
            from app.rag.weekly_ranked import prepare_config
            config = prepare_config(config)
            if state.get('weekly_scope') != config['weekly_scope']:
                state = service._update(weekly_scope=config['weekly_scope'], produced=0)
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
                if config.get('weekly_plan'):
                    kwargs['plan'] = config['weekly_plan']
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
            config = service.snapshot()['config']
            scope = None
            if config.get('kind') == 'weekly_ranked':
                from app.rag.weekly_ranked import prepare_config
                scope = prepare_config(config)['weekly_scope']
            job_id = claim_job(scope)
            if job_id is None:
                _worker_state("verification", "waiting_for_drafts", health)
                _VERIFY_WAKE.wait(5); _VERIFY_WAKE.clear(); continue
            _worker_state("verification", "verifying", health)
            verify_step(job_id)
            if not stop.is_set():
                _assemble()
            service._wake.set()
        except HTTPException:
            _worker_state('verification', 'waiting_for_schedule')
            _VERIFY_WAKE.wait(60); _VERIFY_WAKE.clear()
        except Exception:
            logger.exception("Queued verification failed; saved candidates retained")
            _worker_state("verification", "error")
            _VERIFY_WAKE.wait(60); _VERIFY_WAKE.clear()


class _Interrupted(Exception):
    pass


def _draft_failure(failures, error):
    """Quota refusals are availability waits, not malformed draft strikes."""
    from app.rag import pool_service as service
    health = pool_generation_status()
    unavailable = health['blocked'] or is_terminal_provider_error(error)
    failures = 0 if unavailable else failures + 1
    if unavailable or failures >= 3:
        seconds = max(60, int(health.get('retry_after') or (60 if unavailable else 900)))
        retry = (_now() + timedelta(seconds=seconds)).replace(tzinfo=timezone.utc).isoformat()
        # Persist only our own messages, never arbitrary provider response text.
        message = ('سرویس تولید موقتاً در دسترس نیست؛ پس از بازنشانی سهمیه ادامه می‌یابد.'
                   if unavailable else 'سه تولید متوالی سؤال قابل ذخیره نساخت؛ ۱۵ دقیقه دیگر دوباره بررسی می‌شود.')
        status = 'waiting_for_quota' if unavailable else 'waiting_for_retry'
        service._update(status=status, last_error=message, retry_at=retry,
            drafting_paused=True, drafting_retry_at=retry,
            drafting={'status': status, 'retry_at': retry, 'provider': health.get('provider')})
    return failures


def _draft_waiting(state):
    """Keep saved waits across restarts, then recheck the credential ledger."""
    from app.rag import pool_service as service
    if not state.get('drafting_paused'):
        return False
    retry = state.get('drafting_retry_at')
    if retry:
        until = datetime.fromisoformat(retry).replace(tzinfo=None)
        if until <= _now():
            service._update(drafting_paused=False, drafting_retry_at=None,
                            retry_at=None, last_error='')
            return False
    # Old runs had a permanent pause without a reason. Make it visible until
    # an explicit restart/credential change, instead of advertising progress.
    if not retry:
        service._update(status='drafting_paused', last_error=state.get('last_error') or
                        'تولید متوقف شده است؛ برای ادامه تولید را دوباره شروع کنید.')
        _worker_state('drafting', 'error')
    return True


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
            try:
                if _assemble(): continue
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail,dict) else {'message':str(exc.detail)}
                service._update(status='waiting_for_schedule',last_error=detail['message'])
                _worker_state('drafting','waiting_for_schedule')
                service._wake.wait(60);service._wake.clear();continue
            if _draft_waiting(state):
                service._wake.wait(60); service._wake.clear(); continue
            if state.get('drafting_paused'):
                failures = 0
            service._update(status="queue_running", last_error="", retry_at=None)
            if config.get('kind') == 'weekly_ranked':
                from app.rag.weekly_ranked import prepare_config
                try:
                    config = prepare_config(config)
                except HTTPException:
                    continue  # The next pass displays the missing schedule.
            stats = snapshot(config.get('weekly_scope'))
            if stats["pending_booklets"] >= stats["capacity"] or (config["count"] and not config.get('weekly_scope') and
                    state["produced"] + stats["pending_booklets"] >= config["count"]):
                _worker_state("drafting", "waiting_for_queue")
                service._wake.wait(5); service._wake.clear(); continue
            health = pool_generation_status()
            if health["blocked"]:
                _worker_state("drafting", "waiting_for_quota", health)
                service._update(status='waiting_for_quota', last_error=health['message'],
                                retry_at=health.get('retry_at'))
                service._wake.wait(60); service._wake.clear(); continue
            shelves = service._shelves(config)
            cursor = state.get("draft_cursor", state.get("cursor", 0))
            major, difficulty = shelves[cursor % len(shelves)]
            try:
                job_id = create_job(config, major, difficulty)
            except HTTPException:
                continue  # Schedule changed between reservation and drafting.
            if job_id is None:
                service._wake.wait(5); service._wake.clear(); continue
            service._update(draft_cursor=cursor + 1)
            _worker_state("drafting", "generating", health)
            pool_core.set_current(major, difficulty)
            pool_core.add_planned(1)
            with SessionLocal() as db:
                plan = json.loads(db.get(PoolDraftJob, job_id).plan)
            def save_batch(batch):
                append_batch(job_id, batch)
                if not _active(): raise _Interrupted()
            draft_error = ''
            progress_report = pool_core._progress_reporter()
            def report(event, data):
                nonlocal draft_error
                if event == 'provider_error':
                    draft_error = data.get('message', '')
                progress_report(event, data)
            try:
                mock_generation.generate_booklet(0, plan, topics=config.get("topics") or [],
                    difficulty="konkur" if difficulty == pool_core.DUEL_DIFFICULTY else difficulty,
                    grade=config["grade"], timeout=60, on_drafted=save_batch,
                    report=report)
            except _Interrupted:
                pass
            finally:
                finish_draft(job_id)
            with SessionLocal() as db:
                empty = db.get(PoolDraftJob, job_id).question_count == 0
            failures = _draft_failure(failures, draft_error) if empty else 0
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
