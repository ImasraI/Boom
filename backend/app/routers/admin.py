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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import limits
from ..auth.database import GeneratedMock, SignupAllowlist, User, get_db
from ..auth.deps import require_admin
from ..rag import pool_core
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


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


@router.get("/pool")
def pool_levels(db: Session = Depends(get_db)):
    """pending_use stock per (major, difficulty) shelf + the target the
    worker/restock button aims for.

    ``running`` tells the UI whether the admin-triggered sweep is still
    producing; ``cancel_requested`` covers the short window after a cancel
    while the current booklet finishes (shelves may still tick up once).
    """
    from ..config import get_settings

    return {
        "target": get_settings().MOCK_POOL_TARGET,
        "shelves": pool_core.pool_levels(db),
        "running": _restock_running,
        "cancel_requested": pool_core.cancel_requested(),
    }


@router.post("/pool/restock")
def pool_restock(db: Session = Depends(get_db)):
    """Run ONE pool sweep inline (targeted at shelves below target).

    Each booklet = one LLM call per subject + one verification call per
    question, so a sweep of several empty shelves can take minutes - the
    request runs the sweep in a background thread and returns immediately;
    poll GET /api/admin/pool to watch the shelves fill.
    """
    with _restock_lock:
        if _restock_running:
            raise HTTPException(status_code=409,
                                detail="یک restock در حال اجرا است؛ صبر کنید")
        globals()['_restock_running'] = True
    # A previous run may have been canceled just before it exited; a fresh
    # start must not inherit that flag.
    pool_core.clear_cancel()

    def _run() -> None:
        global _restock_running
        # The request's session is closed by get_db as soon as this endpoint
        # returns - the background thread MUST open its own (like the worker).
        from ..auth.database import SessionLocal
        sweep_db = SessionLocal()
        try:
            produced = pool_core.sweep(sweep_db, _pool_target(),
                                       pool_core.POOL_MAJORS,
                                       pool_core.POOL_DIFFICULTIES)
            produced += pool_core.sweep_duels(sweep_db, _pool_target(),
                                              pool_core.POOL_MAJORS)
            logger.info("Admin-triggered restock produced %d row(s).", produced)
        except Exception:
            logger.exception("Admin-triggered restock failed.")
        finally:
            sweep_db.close()
            globals()['_restock_running'] = False

    threading.Thread(target=_run, daemon=True, name="admin-restock").start()
    return {"ok": True, "started": True}


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
        WrongAnswer,
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
    with _restock_lock:
        running = _restock_running
    if not running:
        raise HTTPException(status_code=409,
                            detail="restock در حال اجرا نیست")
    pool_core.request_cancel()
    logger.info("Admin requested pool-restock cancel.")
    return {"ok": True, "cancel_requested": True}
