"""Growth-readiness projects 1 + 4: server-side state regressions.

- profile: auto-provision, PATCH with optimistic concurrency (stale
  version -> 409 + server state, no silent lost-update)
- study sessions: quick-log persists real-vs-planned data, ownership
  enforced on list/delete
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import Base, StudentProfile, StudySession, User
from app.routers import profile as profile_router


class _Ctx:
    def __init__(self, user):
        self.id = user.id
        self.username = user.username


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


def _user(db, phone):
    u = User(username=phone, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_profile_get_autoprovisions(db):
    u = _user(db, "09140000001")
    out = profile_router.get_profile(current_user=_Ctx(u), db=db)
    assert out["profile"]["version"] == 1
    assert db.query(StudentProfile).filter_by(user_id=u.id).count() == 1


def test_profile_patch_increments_version(db):
    u = _user(db, "09140000002")
    profile_router.patch_profile(profile_router.ProfileIn(major="ریاضی فیزیک"),
                                 current_user=_Ctx(u), db=db)
    out = profile_router.patch_profile(
        profile_router.ProfileIn(version=2, target_rank="زیر ۱۰۰"),
        current_user=_Ctx(u), db=db)
    assert out["profile"]["major"] == "ریاضی فیزیک"
    assert out["profile"]["target_rank"] == "زیر ۱۰۰"
    assert out["profile"]["version"] == 3


def test_profile_stale_version_gets_409_not_lost_update(db):
    """THE concurrency regression: device A reads v1, device B writes v2,
    device A's write with version=1 must be REJECTED with the server state
    returned - never a silent overwrite."""
    u = _user(db, "09140000003")
    profile_router.patch_profile(profile_router.ProfileIn(name="آ"),
                                 current_user=_Ctx(u), db=db)  # v2
    with pytest.raises(HTTPException) as e:
        profile_router.patch_profile(
            profile_router.ProfileIn(version=1, name="ب"),
            current_user=_Ctx(u), db=db)
    assert e.value.status_code == 409
    assert e.value.detail["profile"]["name"] == "آ"  # server state won


def test_profile_blind_write_allowed_when_no_version_sent(db):
    """First save from a fresh device (no version cached yet) works."""
    u = _user(db, "09140000004")
    out = profile_router.patch_profile(
        profile_router.ProfileIn(availability={"wake": "06:30", "sleep": "23:00"}),
        current_user=_Ctx(u), db=db)
    assert out["profile"]["availability"]["wake"] == "06:30"


def test_quick_session_log_roundtrip(db):
    u = _user(db, "09140000005")
    out = profile_router.create_session(
        profile_router.SessionIn(
            subject="حسابان", topic="مشتق", actual_minutes=45,
            attempted_questions=20, correct_count=14, wrong_count=4,
            blank_count=2, perceived_difficulty=3,
            completion_status="partially_completed", logged_via="quick"),
        current_user=_Ctx(u), db=db)
    assert out["logged"] is True and out["actual_minutes"] == 45
    listed = profile_router.list_sessions(current_user=_Ctx(u), db=db)
    s = listed["sessions"][0]
    assert s["subject"] == "حسابان" and s["actual_minutes"] == 45
    assert s["completion_status"] == "partially_completed"
    assert s["correct_count"] == 14


def test_session_list_and_delete_are_scoped_to_owner(db):
    """One student can never see or delete another's sessions."""
    u1 = _user(db, "09140000006")
    u2 = _user(db, "09140000007")
    profile_router.create_session(
        profile_router.SessionIn(subject="فیزیک", actual_minutes=30),
        current_user=_Ctx(u1), db=db)
    assert profile_router.list_sessions(current_user=_Ctx(u2), db=db)["count"] == 0
    row = db.query(StudySession).filter_by(student_id=u1.id).first()
    with pytest.raises(HTTPException):
        profile_router.delete_session(row.id, current_user=_Ctx(u2), db=db)
    profile_router.delete_session(row.id, current_user=_Ctx(u1), db=db)
    assert db.query(StudySession).filter_by(student_id=u1.id).count() == 0
