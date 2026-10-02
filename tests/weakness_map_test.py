"""Regressions for GET /api/insights/weakness-map.

The endpoint groups the user's wrong_answers rows by (subject, topic) and
returns raw counts plus a normalized wrongness score (topic wrong count
relative to the user's worst topic within the same subject). No
attempts-per-topic tracking exists in the schema, so raw counts are the
honest denominator - tested explicitly.
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

from app.auth.database import Base, User, WrongAnswer
from app.routers import insights


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


def _mk_user(db, username):
    u = User(username=username, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _wrong(db, uid, subject, topic="", n=1, blank=False, days_ago=0):
    for _ in range(n):
        db.add(WrongAnswer(
            student_id=uid, subject=subject, topic=topic,
            was_blank=blank,
            created_at=datetime.utcnow() - timedelta(days=days_ago),
        ))
    db.commit()


def test_groups_by_subject_and_topic(db):
    u = _mk_user(db, "09130000001")
    _wrong(db, u.id, "ریاضی", "مشتق", n=3)
    _wrong(db, u.id, "ریاضی", "مشتق", n=1, blank=True)
    _wrong(db, u.id, "ریاضی", "حد", n=1)
    _wrong(db, u.id, "فیزیک", "حرکت‌شناسی", n=2)

    out = insights.weakness_map(current_user=_Ctx(u), db=db)

    subjects = {s["subject"]: s for s in out["subjects"]}
    assert subjects["ریاضی"]["wrong_count"] == 5
    assert subjects["فیزیک"]["wrong_count"] == 2
    riazi_topics = {t["topic"]: t for t in subjects["ریاضی"]["topics"]}
    assert riazi_topics["مشتق"]["wrong_count"] == 4
    assert riazi_topics["مشتق"]["blanks"] == 1
    assert riazi_topics["مشتق"]["wrongness"] == 1.0  # worst in subject
    assert riazi_topics["حد"]["wrong_count"] == 1
    assert riazi_topics["حد"]["wrongness"] == 0.25
    # Subjects sorted by total wrong count desc.
    assert out["subjects"][0]["subject"] == "ریاضی"
    assert out["total_wrong"] == 7


def test_days_window_excludes_old_rows(db):
    u = _mk_user(db, "09130000002")
    _wrong(db, u.id, "شیمی", "استوکیومتری", n=2, days_ago=5)
    _wrong(db, u.id, "شیمی", "استوکیومتری_قدیمی", n=3, days_ago=400)

    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 2  # 400-day-old rows excluded
    assert out["days"] == 90


def test_topicless_rows_bucketed(db):
    u = _mk_user(db, "09130000003")
    _wrong(db, u.id, "ادبیات", "", n=2)

    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    topics = out["subjects"][0]["topics"]
    assert topics[0]["topic"] == "بدون مبحث"
    assert topics[0]["wrong_count"] == 2
    assert topics[0]["wrongness"] == 1.0


def test_empty_state(db):
    u = _mk_user(db, "09130000004")
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["subjects"] == [] and out["total_wrong"] == 0


def test_per_subject_normalization(db):
    """Wrongness is relative WITHIN a subject, not global."""
    u = _mk_user(db, "09130000005")
    _wrong(db, u.id, "فیزیک", "نسبت به شتاب", n=4)
    _wrong(db, u.id, "عربی", "قواعد", n=2)

    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    subjects = {s["subject"]: s for s in out["subjects"]}
    # عربی's single topic is its own subject-peak even though فیزیک has more.
    assert subjects["عربی"]["topics"][0]["wrongness"] == 1.0


def test_days_param_clamped(db):
    u = _mk_user(db, "09130000006")
    out = insights.weakness_map(days=5000, current_user=_Ctx(u), db=db)
    assert out["days"] == 5000  # echoed as requested...
    _wrong(db, u.id, "دینی", "احکام", n=1, days_ago=370)
    # ...but the window itself never exceeds 365 days.
    out2 = insights.weakness_map(days=5000, current_user=_Ctx(u), db=db)
    assert out2["total_wrong"] == 0
