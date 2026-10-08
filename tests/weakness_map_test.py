"""Actual wrong answers, verified provenance, curriculum and account isolation."""
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
from app.auth.database import GeneratedMock, MockAttempt
import json


class _Ctx:
    def __init__(self, user):
        self.id = user.id
        self.username = user.username


@pytest.fixture()
def db(monkeypatch):
    from app.rag import knowledge_graph
    topics = {"ریاضی": ["مشتق", "حد"], "فیزیک": ["حرکت‌شناسی", "نسبت به شتاب"],
              "شیمی": ["استوکیومتری"], "عربی": ["قواعد"]}
    monkeypatch.setattr(knowledge_graph, "load_catalog", lambda: {"nodes": [
        {"id": subject + topic, "subject": subject, "title": topic, "majors": ["riazi"]}
        for subject, titles in topics.items() for topic in titles]})
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
            was_blank=blank, student_answer=None if blank else "1", correct_answer="0", source="practice",
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
    assert subjects["ریاضی"]["wrong_count"] == 4
    assert subjects["فیزیک"]["wrong_count"] == 2
    riazi_topics = {t["topic"]: t for t in subjects["ریاضی"]["topics"]}
    assert riazi_topics["مشتق"]["wrong_count"] == 3
    assert riazi_topics["مشتق"]["blanks"] == 0
    assert riazi_topics["مشتق"]["wrongness"] == 1.0  # worst in subject
    assert riazi_topics["حد"]["wrong_count"] == 1
    assert riazi_topics["حد"]["wrongness"] == 0.33
    # Subjects sorted by total wrong count desc.
    assert out["subjects"][0]["subject"] == "ریاضی"
    assert out["total_wrong"] == 6


def test_days_window_excludes_old_rows(db):
    u = _mk_user(db, "09130000002")
    _wrong(db, u.id, "شیمی", "استوکیومتری", n=2, days_ago=5)
    _wrong(db, u.id, "شیمی", "استوکیومتری_قدیمی", n=3, days_ago=400)

    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 2  # 400-day-old rows excluded
    assert out["days"] == 90


def test_topicless_and_out_of_book_rows_are_not_invented_lessons(db):
    u = _mk_user(db, "09130000003")
    _wrong(db, u.id, "ریاضی", "", n=2)
    _wrong(db, u.id, "ریاضی", "انتگرال معین", n=1)
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["subjects"] == [] and out["total_wrong"] == 0
    assert db.query(WrongAnswer).count() == 3  # Historical data remains intact.


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


def _attempt(db, uid, answers, *, verified=True, topic="مشتق", bank_id=None):
    questions = [{"_id": i, "subject": "ریاضی", "topic": topic, "answer": 0,
                  "verification_status": "verified" if verified else "unverified",
                  **({"bank_id": bank_id} if bank_id else {})} for i in range(1, 4)]
    mock = GeneratedMock(student_id=uid, title="evidence", questions=json.dumps(questions))
    db.add(mock); db.flush()
    db.add(MockAttempt(student_id=uid, mock_id=mock.id, answers=json.dumps(answers)))
    db.commit()
    return mock


def test_verified_blank_exam_does_not_create_weakness_or_mastery(db):
    u = _mk_user(db, "blank-user")
    _attempt(db, u.id, {})
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 0 and out["subjects"] == []
    assert out["total_answered"] == 0 and out["total_blank"] == 3
    graph = insights.knowledge_graph(_Ctx(u), db)
    assert all(n["accuracy"] is None and not n["opened"] for n in graph["nodes"])


def test_verified_actual_wrong_and_zero_option_with_blanks(db):
    u = _mk_user(db, "answer-user")
    _attempt(db, u.id, {"1": 0, "2": 1})
    # The submit endpoint also saves copies; they must not count twice.
    db.add(WrongAnswer(student_id=u.id, subject="ریاضی", topic="مشتق", source="mock",
                       was_blank=False, student_answer="1", correct_answer="0"))
    db.commit()
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 1 and out["total_answered"] == 2
    assert out["subjects"][0]["topics"][0]["blanks"] == 1
    graph = insights.knowledge_graph(_Ctx(u), db)
    node = next(n for n in graph["nodes"] if n["kind"] == "lesson" and n["title"] == "مشتق")
    assert node["accuracy"] == .5 and node["attempted"] == 2
    assert node["wrong"] == 1 and node["correct"] == 1


def test_legacy_unverified_mock_and_copied_errors_are_ignored_without_deletion(db):
    u = _mk_user(db, "legacy-user")
    _attempt(db, u.id, {"1": 1}, verified=False)
    db.add_all([WrongAnswer(student_id=u.id, subject="ریاضی", topic="مشتق", source="mock",
                           was_blank=i > 0, student_answer="1" if i == 0 else None)
                for i in range(13)])
    db.commit()
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 0 and out["total_answered"] == 0
    assert db.query(WrongAnswer).count() == 13 and db.query(MockAttempt).count() == 1
    assert all(not n["opened"] for n in insights.knowledge_graph(_Ctx(u), db)["nodes"])


def test_wrong_answers_for_another_user_or_unknown_lesson_are_not_shown(db):
    u = _mk_user(db, "scoped-user"); other = _mk_user(db, "other-user")
    _attempt(db, other.id, {"1": 1})
    _attempt(db, u.id, {"1": 1}, topic="انتگرال معین")
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 0 and out["subjects"] == []
    assert all(not n["opened"] for n in insights.knowledge_graph(_Ctx(u), db)["nodes"])


def test_missing_bank_question_and_malformed_answers_do_not_establish_weakness(db):
    u = _mk_user(db, "invalid-user")
    _attempt(db, u.id, {"1": 1}, bank_id=99999)
    _attempt(db, u.id, {"1": True, "2": 17, "3": "bogus"})
    out = insights.weakness_map(current_user=_Ctx(u), db=db)
    assert out["total_wrong"] == 0 and out["total_answered"] == 0


def test_manual_empty_or_correct_answers_do_not_count_as_wrong(db):
    u = _mk_user(db, "manual-user")
    insights.record_wrong_answers([
        insights.WrongAnswerIn(subject="ریاضی", topic="مشتق"),
        insights.WrongAnswerIn(subject="ریاضی", topic="مشتق", student_answer="0", correct_answer="0"),
    ], _Ctx(u), db)
    assert insights.weakness_map(current_user=_Ctx(u), db=db)["total_wrong"] == 0
    assert db.query(WrongAnswer).filter_by(student_answer=None).one().was_blank


def test_reported_question_stops_affecting_weakness_and_mastery(db):
    from app.auth.database import BankQuestion
    from app.rag.learning_evidence import confirmed_mistakes
    u = _mk_user(db, "reported-user")
    question = BankQuestion(fingerprint="verified-question", owner_id=0, major="riazi",
        subject="ریاضی", topic="مشتق", content="{}", verified=True, status="active")
    db.add(question); db.commit()
    _attempt(db, u.id, {"1": 1}, bank_id=question.id)
    assert insights.weakness_map(current_user=_Ctx(u), db=db)["total_wrong"] == 1
    assert len(confirmed_mistakes(db, u.id)) == 1
    question.status = "corrupt"; db.commit()
    assert insights.weakness_map(current_user=_Ctx(u), db=db)["total_wrong"] == 0
    assert confirmed_mistakes(db, u.id) == []
    assert all(n["accuracy"] is None for n in insights.knowledge_graph(_Ctx(u), db)["nodes"])


def test_trusted_planner_accuracy_ignores_blanks_and_preserves_diagnostic_history(db):
    from app.planner.adaptive import topic_evidence
    u = _mk_user(db, "planner-answer-user")
    _attempt(db, u.id, {"1": 0})
    evidence = topic_evidence(db, u.id, trusted_only=True)[0]
    assert evidence["accuracy"] == 1 and evidence["attempted"] == 1 and evidence["blank"] == 2
    other = _mk_user(db, "planner-blank-user")
    _attempt(db, other.id, {})
    assert topic_evidence(db, other.id, trusted_only=True) == []
    assert topic_evidence(db, other.id)[0]["accuracy"] is None


def test_missing_identity_never_falls_back_to_demo_user_memory():
    from app.routers.boom_ai import get_recent_wrong_answers
    assert get_recent_wrong_answers() == []
