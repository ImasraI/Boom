"""Asynchronous friend challenges on AI-generated mocks.

Unlike the ranked arena (matchmaking, both players online at once, Elo on
the line), a challenge is a shareable link with no simultaneity:

  1. POST /api/challenges/create            -> invite (code) for a mock the
                                               sender has already played.
  2. GET  /api/challenges/{invite_code}     -> preview: sender, their score,
                                               subjects/duration. Recipient
                                               sees what they are accepting.
  3. POST /api/challenges/{invite_code}/accept -> claim the invite; returns
                                               the booklet in the exact shape
                                               GET /api/mocks/{id} returns, so
                                               the frontend mock-taking flow
                                               works unchanged.
  4. POST /api/challenges/{invite_code}/complete -> after the recipient
                                               submits (through the normal
                                               /api/mocks/{id}/submit), mark
                                               the invite completed and
                                               return both scores side by side.

Scoring itself is never duplicated here: the recipient's attempt goes
through mocks.submit_mock (konkur negative marking, weakness memory); this
router only orchestrates invite state and reads the stored MockAttempt
scores for the comparison.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.database import ChallengeInvite, GeneratedMock, MockAttempt, User
from app.auth.deps import get_current_user, get_db
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/challenges", tags=["challenges"])
logger = get_logger(__name__)

# Invite lifetime: stale links die after a week (checked lazily on every
# touch - no cleanup job). Fresh codes stay 15 chars long (unambiguous).
INVITE_TTL_DAYS = 7
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/L/1/O/0 lookalikes


def _new_invite_code(db: Session) -> str:
    """Short unique shareable code (6 chars -> ~1B combinations)."""
    for _ in range(20):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not db.execute(
            select(ChallengeInvite.id)
            .where(ChallengeInvite.invite_code == code)
            .limit(1)
        ).scalar_one_or_none():
            return code
    raise HTTPException(status_code=500, detail="خطا در ساخت کد دعوت")


def _fresh_invite(db: Session, invite_code: str) -> ChallengeInvite:
    """Load an invite by code, 404 when unknown or expired.

    Expired invites 404 (indistinguishable from a made-up code) so stale
    links simply stop working; the row stays for sender bookkeeping.
    """
    invite = db.execute(
        select(ChallengeInvite).where(ChallengeInvite.invite_code == invite_code)
    ).scalar_one_or_none()
    if not invite or datetime.utcnow() >= invite.expires_at:
        raise HTTPException(status_code=404, detail="دعوت پیدا نشد یا منقضی شده")
    return invite


def _visible_questions(db: Session, mock: GeneratedMock) -> list:
    """Booklet rows without answers, placeholders dropped (same filtering
    GET /api/mocks/{id} applies, so previews and accepts never leak keys)."""
    if not mock:
        return []
    from app.routers.mocks import _load_questions  # late: avoids import cycle

    return [
        {
            "id": q.get("_id") or q.get("id"),
            "subject": q.get("subject"),
            "topic": q.get("topic"),
            "text": q.get("text"),
            "options": q.get("options"),
        }
        for q in _load_questions(mock)
        if (q.get("text") or "").strip()
    ]


class CreatePayload(BaseModel):
    mock_id: int


@router.post("/create")
def create_invite(
    payload: CreatePayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Challenge friends with a mock the caller has ALREADY played.

    The invite reuses the sender's existing GeneratedMock - the recipient
    takes the identical booklet, so the comparison is fair. Re-inviting the
    same mock returns the existing pending invite (same code) instead of
    piling up duplicate rows.
    """
    mock = db.get(GeneratedMock, payload.mock_id)
    if not mock or mock.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    sender_attempt = db.execute(
        select(MockAttempt)
        .where(MockAttempt.mock_id == mock.id)
        .where(MockAttempt.student_id == current_user.id)
        .order_by(MockAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not sender_attempt:
        raise HTTPException(
            status_code=400,
            detail="اول خودت این آزمون را داده باش تا بتوانی دوستانت را به چالش بکشی",
        )

    existing = db.execute(
        select(ChallengeInvite)
        .where(ChallengeInvite.mock_id == mock.id)
        .where(ChallengeInvite.sender_id == current_user.id)
        .where(ChallengeInvite.status == "pending")
        .limit(1)
    ).scalar_one_or_none()
    if existing:
        invite = existing
    else:
        invite = ChallengeInvite(
            mock_id=mock.id,
            sender_id=current_user.id,
            invite_code=_new_invite_code(db),
            expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
        logger.info("Challenge invite %s created by user %d on mock %d",
                    invite.invite_code, current_user.id, mock.id)

    return {
        "invite_id": invite.id,
        "invite_code": invite.invite_code,
        "expires_at": invite.expires_at.isoformat(),
        "mock_id": mock.id,
        "mock_title": mock.title,
        "your_score": sender_attempt.score,
    }


@router.get("/{invite_code}")
def lookup_invite(
    invite_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview an invite before accepting (login required, no claim yet)."""
    invite = _fresh_invite(db, invite_code)
    sender = db.get(User, invite.sender_id)
    sender_attempt = db.execute(
        select(MockAttempt)
        .where(MockAttempt.mock_id == invite.mock_id)
        .where(MockAttempt.student_id == invite.sender_id)
        .order_by(MockAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    mock = db.get(GeneratedMock, invite.mock_id)
    questions = _visible_questions(db, mock)
    subjects: list = []
    for q in questions:
        if q["subject"] and q["subject"] not in subjects:
            subjects.append(q["subject"])
    accepted_by_me = invite.recipient_id == current_user.id
    return {
        "invite_code": invite.invite_code,
        "status": invite.status,
        "accepted_by_me": accepted_by_me,
        "sender_name": (sender.username if sender else "") or "دانش‌آموز بوم",
        "sender_score": sender_attempt.score if sender_attempt else None,
        "mock_title": mock.title if mock else "",
        "duration_minutes": mock.duration_minutes if mock else 0,
        "question_count": len(questions),
        "subjects": subjects,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/{invite_code}/accept")
def accept_invite(
    invite_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Claim an invite and get the booklet (same shape as GET /api/mocks).

    The sender can't accept their own challenge; the first taker wins -
    a pending invite accepts exactly one recipient, then it is locked to
    them (idempotent re-accept returns the same booklet).
    """
    invite = _fresh_invite(db, invite_code)
    if invite.sender_id == current_user.id:
        raise HTTPException(status_code=400, detail="نمی‌توانی چالش خودت را بپذیری")
    if invite.recipient_id is not None and invite.recipient_id != current_user.id:
        raise HTTPException(status_code=409, detail="این چالش قبلاً توسط دانش‌آموز دیگری پذیرفته شده")
    if invite.recipient_id != current_user.id:
        invite.recipient_id = current_user.id
        invite.status = "accepted"
        db.commit()
        logger.info("Challenge invite %s accepted by user %d",
                    invite.invite_code, current_user.id)

    mock = db.get(GeneratedMock, invite.mock_id)
    if not mock:
        raise HTTPException(status_code=404, detail="دفترچه آزمون پیدا نشد")
    # Same booklet serialization GET /api/mocks/{id} uses - the frontend
    # mock-taking flow works on this unchanged.
    questions = _visible_questions(db, mock)
    return {
        "mock_id": mock.id,
        "title": mock.title,
        "duration_minutes": mock.duration_minutes,
        "questions": questions,
        "invite_code": invite.invite_code,
    }


@router.post("/{invite_code}/complete")
def complete_invite(
    invite_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finish an accepted invite; returns both scores for the comparison UI.

    The recipient's score comes from the MockAttempt their submit already
    wrote (mocks.submit_mock did the konkur scoring). Called by the frontend
    right after that submit; idempotent so a retry is harmless.
    """
    invite = _fresh_invite(db, invite_code)
    if invite.recipient_id != current_user.id:
        raise HTTPException(status_code=403, detail="این چالش مال تو نیست")
    if invite.status != "completed":
        recipient_attempt = db.execute(
            select(MockAttempt)
            .where(MockAttempt.mock_id == invite.mock_id)
            .where(MockAttempt.student_id == current_user.id)
            .order_by(MockAttempt.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if not recipient_attempt:
            raise HTTPException(
                status_code=400,
                detail="هنوز آزمون را ارسال نکرده‌ای",
            )
        invite.status = "completed"
        db.commit()
        logger.info("Challenge invite %s completed (users %d vs %d)",
                    invite.invite_code, invite.sender_id, current_user.id)

    sender = db.get(User, invite.sender_id)
    sender_attempt = db.execute(
        select(MockAttempt)
        .where(MockAttempt.mock_id == invite.mock_id)
        .where(MockAttempt.student_id == invite.sender_id)
        .order_by(MockAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    recipient_attempt = db.execute(
        select(MockAttempt)
        .where(MockAttempt.mock_id == invite.mock_id)
        .where(MockAttempt.student_id == current_user.id)
        .order_by(MockAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    sender_score = sender_attempt.score if sender_attempt else None
    recipient_score = recipient_attempt.score if recipient_attempt else None
    return {
        "invite_code": invite.invite_code,
        "mock_id": invite.mock_id,
        "status": invite.status,
        "sender_name": (sender.username if sender else "") or "دانش‌آموز بوم",
        "sender_score": sender_score,
        "your_score": recipient_score,
        "won": (
            recipient_score is not None and sender_score is not None
            and recipient_score > sender_score
        ),
        "tied": (
            recipient_score is not None and sender_score is not None
            and recipient_score == sender_score
        ),
    }
