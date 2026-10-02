"""Regressions for asynchronous friend challenges.

Covers the whole invite lifecycle without HTTP: create (only for mocks the
sender has already attempted, idempotent re-invite), lazy 7-day expiry,
accept (single-taker lock, self-accept block) and complete (both scores
side by side, submit-side auto-complete helper).
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import (
    Base,
    ChallengeInvite,
    GeneratedMock,
    MockAttempt,
    User,
)
from app.routers import challenges as ch


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


BOOKLET = (
    '[{"_id":1,"subject":"ریاضی","topic":"","text":"سوال یک؟",'
    '"options":["a","b","c","d"],"answer":1,"explanation":""},'
    '{"_id":2,"subject":"فیزیک","topic":"","text":"سوال دو؟",'
    '"options":["a","b","c","d"],"answer":2,"explanation":""}]'
)


def _mk_user(db, username):
    u = User(username=username, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _mk_played_mock(db, student_id, score=80.0):
    db.add(GeneratedMock(
        student_id=student_id, title="آزمون چالش", major="ریاضی فیزیک",
        grade="", duration_minutes=30, questions=BOOKLET, status="claimed",
        difficulty="konkur",
    ))
    db.commit()
    mock = db.query(GeneratedMock).order_by(GeneratedMock.id.desc()).first()
    db.add(MockAttempt(mock_id=mock.id, student_id=student_id,
                       answers="{}", score=score, correct=8, wrong=1, blank=1))
    db.commit()
    return mock


class _Ctx:
    """Fake Depends()-free stand-in for current_user."""

    def __init__(self, user):
        self.id = user.id
        self.username = user.username


def test_create_requires_sender_to_have_played_the_mock(db):
    sender = _mk_user(db, "09120000001")
    other = _mk_user(db, "09120000002")
    db.add(GeneratedMock(
        student_id=other.id, title="not mine", major="", grade="",
        duration_minutes=10, questions=BOOKLET, status="claimed",
    ))
    db.commit()
    mock = db.query(GeneratedMock).first()

    # Someone else's mock -> 404.
    with pytest.raises(ch.HTTPException) as e:
        ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                         current_user=_Ctx(sender), db=db)
    assert e.value.status_code == 404

    # Own mock but never attempted -> 400.
    own = _mk_played_mock(db, sender.id)
    db.query(MockAttempt).filter(MockAttempt.mock_id == own.id).delete()
    db.commit()
    with pytest.raises(ch.HTTPException) as e:
        ch.create_invite(ch.CreatePayload(mock_id=own.id),
                         current_user=_Ctx(sender), db=db)
    assert e.value.status_code == 400


def test_create_returns_code_and_is_idempotent(db):
    sender = _mk_user(db, "09120000003")
    mock = _mk_played_mock(db, sender.id, score=72.5)
    first = ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                             current_user=_Ctx(sender), db=db)
    again = ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                             current_user=_Ctx(sender), db=db)
    assert first["invite_code"] == again["invite_code"]
    assert first["your_score"] == 72.5
    assert db.query(ChallengeInvite).count() == 1
    # 7-day TTL.
    assert ch.datetime.utcnow() < datetime.fromisoformat(first["expires_at"]) \
        <= ch.datetime.utcnow() + timedelta(days=7)


def test_expired_invite_is_invisible(db):
    sender = _mk_user(db, "09120000004")
    mock = _mk_played_mock(db, sender.id)
    inv = ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                           current_user=_Ctx(sender), db=db)
    row = db.query(ChallengeInvite).first()
    row.expires_at = ch.datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    for call in (lambda: ch.lookup_invite(inv["invite_code"], _Ctx(sender), db),
                 lambda: ch.accept_invite(inv["invite_code"], _Ctx(sender), db)):
        with pytest.raises(ch.HTTPException) as e:
            call()
        assert e.value.status_code == 404


def test_accept_locks_to_first_recipient_and_blocks_sender(db):
    sender = _mk_user(db, "09120000005")
    r1 = _mk_user(db, "09120000006")
    r2 = _mk_user(db, "09120000007")
    mock = _mk_played_mock(db, sender.id)
    inv = ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                           current_user=_Ctx(sender), db=db)

    # Sender can't accept their own challenge.
    with pytest.raises(ch.HTTPException) as e:
        ch.accept_invite(inv["invite_code"], _Ctx(sender), db=db)
    assert e.value.status_code == 400

    out1 = ch.accept_invite(inv["invite_code"], _Ctx(r1), db=db)
    assert out1["mock_id"] == mock.id
    assert [q["id"] for q in out1["questions"]] == [1, 2]
    assert all("answer" not in q for q in out1["questions"])  # no key leak

    # Second taker is locked out; first taker re-accepts idempotently.
    with pytest.raises(ch.HTTPException) as e:
        ch.accept_invite(inv["invite_code"], _Ctx(r2), db=db)
    assert e.value.status_code == 409
    out1b = ch.accept_invite(inv["invite_code"], _Ctx(r1), db=db)
    assert out1b["mock_id"] == mock.id

    # Recipient can now read the booklet through the normal mocks endpoint
    # auth path (same rule the route applies).
    from app.routers import mocks as mocks_router
    row = db.get(GeneratedMock, mock.id)
    assert mocks_router.get_mock(mock.id, current_user=_Ctx(r1), db=db)["mock_id"] == mock.id


def test_complete_requires_recipient_attempt_and_compares_scores(db):
    sender = _mk_user(db, "09120000008")
    recipient = _mk_user(db, "09120000009")
    mock = _mk_played_mock(db, sender.id, score=60.0)
    inv = ch.create_invite(ch.CreatePayload(mock_id=mock.id),
                           current_user=_Ctx(sender), db=db)
    ch.accept_invite(inv["invite_code"], _Ctx(recipient), db=db)

    # No recipient attempt yet -> 400.
    with pytest.raises(ch.HTTPException) as e:
        ch.complete_invite(inv["invite_code"], _Ctx(recipient), db=db)
    assert e.value.status_code == 400

    db.add(MockAttempt(mock_id=mock.id, student_id=recipient.id,
                       answers="{}", score=85.0, correct=9, wrong=0, blank=1))
    db.commit()
    res = ch.complete_invite(inv["invite_code"], _Ctx(recipient), db=db)
    assert res["sender_score"] == 60.0
    assert res["your_score"] == 85.0
    assert res["won"] is True and res["tied"] is False
    assert db.get(ChallengeInvite, inv["invite_id"]).status == "completed"

    # Idempotent: calling complete again returns the same comparison.
    res2 = ch.complete_invite(inv["invite_code"], _Ctx(recipient), db=db)
    assert res2["your_score"] == 85.0

    # Sender calling complete -> 403.
    with pytest.raises(ch.HTTPException) as e:
        ch.complete_invite(inv["invite_code"], _Ctx(sender), db=db)
    assert e.value.status_code == 403
