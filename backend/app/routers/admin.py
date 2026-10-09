"""Admin-only management endpoints (gated by deps.require_admin).

Sections:
  - Signup allowlist CRUD: numbers allowed to bypass the (not yet approved)
    SMS verification template using the shared SIGNUP_BYPASS_CODE.
  - User overview + per-user AI usage (today's feature counts + tokens) and
    a quota reset button (clears the user's in-memory daily counters).
  - Mock pool levels (pending_use stock per major/difficulty shelf) + a
    manual restock trigger that runs one pool_core.sweep inline.
  - SMS credit (remaining sms.ir panel balance) for the verification codes.

Everything here is server-side gated: 403 for any non-admin token, no
endpoint can create or promote admins (that's scripts/manage_admin.py only).
"""

import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import limits
from ..auth.database import BankQuestion, QuestionReport, GeneratedMock, SignupAllowlist, User, get_db
from ..auth.deps import require_admin
from ..rag import pool_core, question_bank, pool_service, pool_usage
from ..rag.provider_quota import pool_quota_status, require_pool_available
from ..utils.logger import get_logger
from ..utils.metrics import snapshot

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


@router.get("/metrics")
def runtime_metrics():
    """Return process-local request/error counters for the admin dashboard."""
    return snapshot()


class AllowlistAdd(BaseModel):
    phone: str
    note: str = ""


def _normalize_or_400(phone: str) -> str:
    """Reuse the SMS normalizer so the allowlist matches what signup sends."""
    from ..auth.sms import normalize_ir_mobile

    try:
        return normalize_ir_mobile(phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="شماره موبایل معتبر نیست")


@router.get("/allowlist")
def list_allowlist(db: Session = Depends(get_db)):
    rows = db.execute(
        select(SignupAllowlist).order_by(SignupAllowlist.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": r.id,
            "phone": r.phone,
            "note": r.note or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/allowlist")
def add_allowlist(payload: AllowlistAdd, db: Session = Depends(get_db)):
    mobile = _normalize_or_400(payload.phone)
    existing = db.query(SignupAllowlist).filter(
        SignupAllowlist.phone == mobile).first()
    if existing:
        raise HTTPException(status_code=409, detail="این شماره قبلاً اضافه شده است")
    row = SignupAllowlist(phone=mobile, note=(payload.note or "").strip()[:200])
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Admin allowlisted %s for bypass signup.", mobile)
    return {"id": row.id, "phone": row.phone, "note": row.note or ""}


@router.delete("/allowlist/{entry_id}")
def delete_allowlist(entry_id: int, db: Session = Depends(get_db)):
    row = db.get(SignupAllowlist, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="مورد پیدا نشد")
    db.delete(row)
    db.commit()
    logger.info("Admin removed allowlist entry %d (%s).", entry_id, row.phone)
    return {"ok": True}


@router.get("/users")
def users_overview(db: Session = Depends(get_db)):
    """Quick who's-registered view, enriched with today's AI usage and
    per-feature limits so the panel renders usage inline per user."""
    usage = limits.all_usage()
    by_uid = {u["user_id"]: u for u in usage["users"]}
    rows = db.execute(
        select(User).order_by(User.created_at.desc()).limit(200)
    ).scalars().all()
    return {
        "day": usage["day"],
        "token_budget": usage["token_budget"],
        "limits": usage["limits"],
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "phone": u.phone,
                "phone_verified": bool(u.phone_verified),
                "is_admin": bool(u.is_admin),
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "usage": by_uid.get(u.id, {"features": {}, "tokens_used_today": 0}),
            }
            for u in rows
        ],
    }


@router.post("/users/{user_id}/reset-quota")
def reset_quota(user_id: int, db: Session = Depends(get_db)):
    """Clear one user's daily AI counters (features + tokens) immediately.

    Counters are process-local and reset at UTC midnight anyway; this just
    gives the user their full budget back right now.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    limits.reset_user_quota(user_id)
    logger.info("Admin reset daily AI quota for user %d (%s).",
                user_id, user.username)
    return {"ok": True, "user_id": user_id}


@router.get("/sms-credit")
def sms_credit_view():
    """Remaining sms.ir credit (each verification SMS costs ~1 unit).
    Fetched live from sms.ir; never raises - reports 0 + a reason instead."""
    from ..auth.sms import sms_credit
    from ..config import get_settings

    result = sms_credit()
    result["bypass_active"] = bool(
        (get_settings().SIGNUP_BYPASS_CODE or "").strip())
    return result


@router.get("/sms-delivery/{message_id}")
def sms_delivery_view(message_id: int):
    """Admin-only provider timing report; excludes OTPs and recipient details."""
    if message_id <= 0:
        raise HTTPException(status_code=400, detail="شناسه پیامک معتبر نیست")
    from ..auth.sms import sms_delivery_report
    try:
        return sms_delivery_report(message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/pool")
def pool_levels(db: Session = Depends(get_db)):
    """pending_use stock per (major, difficulty) shelf + the target the
    worker/restock button aims for.

    ``running`` tells the UI whether the admin-triggered sweep is still
    producing; ``cancel_requested`` covers the short window after a cancel
    while the current booklet finishes (shelves may still tick up once).

    ``progress`` carries what a progress bar needs: the run state (active,
    booklets produced/planned, the shelf being generated right now, elapsed
    seconds) plus the aggregate fill of every shelf against the target.
    """
    from ..config import get_settings

    target = get_settings().MOCK_POOL_TARGET
    shelves = pool_core.pool_levels(db)
    available = sum(s["available"] for s in shelves)
    # Duel stock is generated by the same restock run but lives on separate
    # shelves (difficulty="duel"), so it gets its own headline number.
    duel_available = pool_core.ready_count(db, difficulty=pool_core.DUEL_DIFFICULTY)
    progress = pool_core.progress_snapshot()
    progress.update(
        available=available,
        capacity=None,
        percent=None,
        duel_available=duel_available,
        duel_capacity=None,
    )
    run = pool_service.snapshot()
    return {
        "target": target,
        "shelves": shelves,
        "running": run.get('enabled', False) or _restock_running or progress["active"],
        "run": run,
        "catalog": pool_core.catalog(),
        "inventory": pool_core.stock_inventory(db),
        "token_usage": pool_usage.summary(),
        "provider_health": pool_quota_status(),
        "question_bank": question_bank.counts(db),
        "unlimited_storage": True,
        "cancel_requested": pool_core.cancel_requested(),
        "progress": progress,
    }


class PoolRunIn(BaseModel):
    kind: str = Field(default="mock", pattern="^(mock|ranked|both)$")
    major: str = "riazi"
    difficulty: str = Field(default="konkur", pattern="^(easy|konkur|hard)$")
    count: int = Field(default=0, ge=0)  # 0: until canceled/provider stops
    grade: str = Field(default="دوازدهم", pattern="^(دهم|یازدهم|دوازدهم)$")
    total_questions: int = Field(default=10, ge=0, le=200)  # 0: official full mock.
    subjects: list[str] = Field(default_factory=list, max_length=15)
    topics: list[str] = Field(default_factory=list, max_length=20)


@router.post("/pool/restock")
def pool_restock(db: Session = Depends(get_db), payload: PoolRunIn | None = None):
    """Generate the selected shelves independently of existing inventory.

    Each booklet uses paced draft batches and independent solver batches,
    so a sweep of several empty shelves can take minutes - the
    request runs the sweep in a background thread and returns immediately;
    poll GET /api/admin/pool to watch the shelves fill.
    """
    payload = payload or PoolRunIn()
    if payload.major not in pool_core.POOL_MAJORS and payload.major != "all":
        raise HTTPException(422, detail="رشته معتبر نیست")
    majors = pool_core.POOL_MAJORS if payload.major == "all" else [payload.major]
    for major in majors:
        allowed = {s['name'] for s in pool_core.generation_plan(major, ranked=payload.kind=='ranked')}
        if payload.subjects and not set(payload.subjects).issubset(allowed):
            raise HTTPException(422, detail="درس‌های انتخابی با رشته و نوع آزمون هماهنگ نیستند.")
        if payload.kind == 'both' and payload.subjects and not set(payload.subjects).issubset(
                {s['name'] for s in pool_core.generation_plan(major, ranked=True)}):
            raise HTTPException(422, detail="این درس در قالب رنکینگ نیست؛ تولید آزمون آزمایشی را انتخاب کن.")
    if any(not t.strip() or len(t) > 200 for t in payload.topics):
        raise HTTPException(422, detail="هر مبحث باید بین ۱ تا ۲۰۰ نویسه باشد.")
    health = pool_quota_status()
    if health['blocked'] and not health.get('retry_at'):
        require_pool_available()
    return pool_service.start({'kind':payload.kind, 'majors':majors,
        'difficulties':[payload.difficulty], 'count':payload.count, 'grade':payload.grade,
        'total_questions':payload.total_questions, 'subjects':payload.subjects, 'topics':payload.topics})


@router.get("/questions/corrupt")
def corrupt_questions(db: Session = Depends(get_db), offset: int = 0, limit: int = 30, status: str = "corrupt"):
    import json
    from sqlalchemy import func
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    if status not in ("corrupt", "deleted"):
        raise HTTPException(422, detail="وضعیت معتبر نیست")
    rows = db.execute(select(BankQuestion).where(BankQuestion.status == status)
        .order_by(BankQuestion.id.desc()).offset(offset).limit(limit)).scalars().all()
    total = db.scalar(select(func.count(BankQuestion.id)).where(BankQuestion.status == status))
    return {"total": total, "items": [{"id": q.id, "major": q.major, "grade": q.grade, "status": q.status,
        "difficulty": q.difficulty, "content": json.loads(q.content), "note": q.admin_note,
        "reports": [{"id": r.id, "reason": r.reason, "mock_id": r.mock_id,
                     "created_at": r.created_at.isoformat()} for r in db.execute(select(QuestionReport)
            .where(QuestionReport.question_id == q.id).order_by(QuestionReport.id.desc())).scalars()]} for q in rows]}


class QuestionReviewIn(BaseModel):
    action: str = Field(pattern="^(restore|delete|note|correct)$")
    note: str = Field(default="", max_length=4000)
    text: str | None = Field(default=None, min_length=1, max_length=12000)
    options: list[str] | None = None
    answer: int | None = Field(default=None, ge=0, le=3)
    explanation: str | None = Field(default=None, max_length=12000)


@router.post("/questions/{question_id}/review")
def review_question(question_id: int, payload: QuestionReviewIn, db: Session = Depends(get_db)):
    import json
    q = db.get(BankQuestion, question_id)
    if not q:
        raise HTTPException(404, detail="سوال یافت نشد")
    if q.status != "corrupt":
        raise HTTPException(409, detail="این سوال دیگر در صف بررسی نیست")
    q.admin_note = payload.note
    new_id = None
    if payload.action == "restore":
        if not q.verified:
            raise HTTPException(409, detail="پاسخ این سوال تایید نشده است؛ ابتدا نسخه اصلاح‌شده ثبت کنید")
        q.status = "active"
    elif payload.action == "delete":
        q.status = "deleted"  # Retain evidence and every other question.
    elif payload.action == "correct":
        content = json.loads(q.content)
        for name in ("text", "options", "answer", "explanation"):
            value = getattr(payload, name)
            if value is not None:
                content[name] = value
        if not question_bank._valid(content):
            raise HTTPException(422, detail="متن، چهار گزینه و پاسخ صحیح باید معتبر باشند")
        fingerprint = question_bank._fingerprint(content, q.owner_id, "assessment" if q.difficulty == "assessment" else "mock")
        if fingerprint == q.fingerprint:
            raise HTTPException(422, detail="نسخه اصلاح‌شده باید متن، گزینه‌ها یا پاسخ متفاوتی داشته باشد")
        replacement = db.execute(select(BankQuestion).where(BankQuestion.fingerprint == fingerprint)).scalar_one_or_none()
        if replacement is not None:
            raise HTTPException(409, detail="این نسخه از سوال قبلاً در بانک ثبت شده است")
        content["verification_status"] = "verified"
        content["replaces_bank_id"] = q.id
        replacement = BankQuestion(fingerprint=fingerprint, owner_id=q.owner_id, major=q.major,
            grade=q.grade, grade_level=q.grade_level, difficulty=q.difficulty, subject=q.subject, topic=q.topic,
            content=json.dumps(content, ensure_ascii=False), verified=True, status="active", uses=0,
            admin_note=payload.note)
        db.add(replacement)
        q.status = "deleted"
        db.flush()
        new_id = replacement.id
    db.commit()
    return {"ok": True, "status": q.status, "replacement_id": new_id}


# Restock single-flight guard (per process; the worker script is the other
# producer and SQLite serializes the inserts themselves).
_restock_running = False
_restock_lock = threading.Lock()


class WipeUserData(BaseModel):
    # Must equal the user's username (phone) - a type-to-confirm guard
    # against wiping the wrong account from the panel.
    confirm: str


@router.delete("/users/{user_id}/data")
def wipe_user_data(user_id: int, body: WipeUserData,
                   db: Session = Depends(get_db)):
    """Permanently erase one user's data (GDPR-style full wipe).

    Removes: account row, conversations, daily tasks, study tasks/sessions,
    assessments, wrong answers, claimed mocks + attempts, arena queue/match
    entries, SMS codes for their phone, uploaded files, rendered page images
    and every vector-store chunk in all three collections.

    Deliberately NOT touched: the shared mock pool (pool rows are owned by
    the student_id=0 sentinel) and the admin-managed signup allowlist.
    Admin accounts cannot be wiped from here.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    if user.is_admin:
        raise HTTPException(status_code=403,
                            detail="حساب مدیر از این طریق حذف نمیشود")
    if (body.confirm or "").strip() != user.username:
        raise HTTPException(status_code=400,
                            detail="متن تایید با نام کاربری مطابقت ندارد")

    counts = _wipe_user_data(user_id, user.phone, db)
    logger.warning(
        "Admin wiped ALL data for user %d (%s): %s", user_id, user.username,
        counts,
    )
    return {"ok": True, "user_id": user_id, "deleted": counts}


def _wipe_user_data(user_id: int, phone: str | None, db: Session) -> dict:
    """Delete every trace of a user. Returns per-target deletion counts."""
    from sqlalchemy import or_

    from ..auth.database import (
        ArenaMatch, ArenaQueueEntry, Assessment, Conversation, DailyTask,
        GeneratedMock, MockAttempt, PhoneCode, StudySession, Task,
        WrongAnswer, TaskProgress, StudentProfile, BankQuestion, QuestionReport,
    )
    from ..rag import mock_generation  # noqa: F401  (import guard: stores wired)
    from ..rag.vector_store import (
        get_image_vector_store, get_question_vector_store, get_vector_store,
    )

    counts: dict[str, int] = {}

    # ---- Vector stores: all three collections, scoped by user_id --------
    for name, store in (
        ("vector_text_chunks", get_vector_store()),
        ("vector_image_chunks", get_image_vector_store()),
        ("vector_question_chunks", get_question_vector_store()),
    ):
        try:
            store.collection.delete(where={"user_id": user_id})
            counts[name] = -1  # Chroma does not report deleted counts
        except Exception:
            logger.exception("Wipe: vector purge failed (%s).", name)
    try:
        from ..rag.hybrid_search import get_hybrid_search
        get_hybrid_search().refresh(user_id)
    except Exception:
        logger.exception("Wipe: lexical index refresh failed.")

    # ---- Files: uploads and rendered page images ------------------------
    from ..config import get_settings
    settings = get_settings()
    for name, folder in (
        ("upload_files", Path(settings.UPLOAD_DIR) / str(user_id)),
        ("page_images", Path(settings.IMAGES_DIR) / str(user_id)),
    ):
        try:
            if folder.exists():
                shutil.rmtree(folder)
                counts[name] = -1
        except Exception:
            logger.exception("Wipe: could not remove %s.", folder)

    # ---- SQLite rows (FK-safe order; pool rows student_id=0 survive) ----
    def _delete(model, *filters, key: str) -> None:
        q = db.query(model)
        if filters:
            q = q.filter(*filters)
        counts[key] = q.delete(synchronize_session=False)

    # Children of generated_mocks first, then the user's claimed mocks.
    _delete(QuestionReport, or_(QuestionReport.student_id == user_id,
        QuestionReport.mock_id.in_(select(GeneratedMock.id).where(GeneratedMock.student_id == user_id)),
        QuestionReport.question_id.in_(select(BankQuestion.id).where(BankQuestion.owner_id == user_id))), key="question_reports")
    _delete(BankQuestion, BankQuestion.owner_id == user_id, key="private_bank_questions")
    _delete(MockAttempt, MockAttempt.student_id == user_id,
            key="mock_attempts")
    _delete(GeneratedMock, GeneratedMock.student_id == user_id,
            key="generated_mocks")
    _delete(ArenaMatch,
            or_(ArenaMatch.student_a_id == user_id,
                ArenaMatch.student_b_id == user_id,
                ArenaMatch.winner_id == user_id),
            key="arena_matches")
    _delete(ArenaQueueEntry, ArenaQueueEntry.student_id == user_id,
            key="arena_queue_entries")
    _delete(StudySession, StudySession.student_id == user_id,
            key="study_sessions")
    _delete(TaskProgress, TaskProgress.student_id == user_id, key="task_progress")
    _delete(StudentProfile, StudentProfile.user_id == user_id, key="student_profiles")
    _delete(Task, Task.student_id == user_id, key="tasks")
    _delete(Assessment, Assessment.student_id == user_id, key="assessments")
    _delete(WrongAnswer, WrongAnswer.student_id == user_id,
            key="wrong_answers")
    _delete(DailyTask, DailyTask.user_id == user_id, key="daily_tasks")
    _delete(Conversation, Conversation.user_id == user_id,
            key="conversations")
    if phone:
        _delete(PhoneCode, PhoneCode.phone == phone, key="phone_codes")

    user_row = db.get(User, user_id)
    if user_row is not None:
        db.delete(user_row)
        counts["user"] = 1
    db.commit()

    # ---- In-memory quota counters (features + tokens) -------------------
    try:
        limits.reset_user_quota(user_id)
    except Exception:
        logger.exception("Wipe: quota counter cleanup failed.")

    return counts


def _pool_target() -> int:
    from ..config import get_settings
    return get_settings().MOCK_POOL_TARGET


@router.post("/pool/cancel")
def pool_cancel():
    """Ask the running admin restock to stop after its current booklet.

    Cooperative: the in-flight booklet (several LLM calls) finishes and is
    KEPT - only the remaining work is skipped. Raises 409 when nothing is
    running; the UI can also poll /pool's cancel_requested to show the
    finishing state.
    """
    if pool_service.cancel():
        return {"ok": True, "cancel_requested": True}
    with _restock_lock:
        running = _restock_running or pool_core.progress_snapshot()["active"]
    if not running:
        raise HTTPException(status_code=409,
                            detail="restock در حال اجرا نیست")
    pool_core.request_cancel()
    logger.info("Admin requested pool-restock cancel.")
    return {"ok": True, "cancel_requested": True}
