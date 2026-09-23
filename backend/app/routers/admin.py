"""Admin-only management endpoints (gated by deps.require_admin).

Currently:
  - Signup allowlist CRUD: numbers allowed to bypass the (not yet approved)
    SMS verification template using the shared SIGNUP_BYPASS_CODE.
  - Read-only user overview for a quick who's-registered look.

Everything here is server-side gated: 403 for any non-admin token, no
endpoint can create or promote admins (that's scripts/manage_admin.py only).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.database import SignupAllowlist, User, get_db
from ..auth.deps import require_admin
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
    """Quick who's-registered view (read-only; no mutations over HTTP)."""
    rows = db.execute(
        select(User).order_by(User.created_at.desc()).limit(200)
    ).scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "phone": u.phone,
            "phone_verified": bool(u.phone_verified),
            "is_admin": bool(u.is_admin),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]
