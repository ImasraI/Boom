import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import json
from datetime import date, datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.auth.database import Base, User, StudentProfile, TaskProgress, GeneratedMock, MockAttempt, WrongAnswer
from app.planner.adaptive import build_week, topic_evidence
from app.routers.profile import ProgressIn, save_progress
from app.routers.mocks import submit_mock, SubmitPayload

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([User(id=1, username="student1", hashed_password="x"), User(id=2, username="student2", hashed_password="x")])
        db.commit()
        yield db


def test_saved_availability_overrides_request_and_isolated_by_student(db):
    db.add(StudentProfile(user_id=1, availability=json.dumps({"daily_hours": {"*": 0}})))
    db.commit()
    assert not build_week(db, 1, {}, 4, date.today(), [])["blocks"]
    assert build_week(db, 2, {}, 4, date.today(), [])["blocks"]


def test_partial_work_is_carried_with_only_remaining_minutes(db):
    save_progress(ProgressIn(client_ref="p1", date=date.today(), subject="math", topic="limits",
        planned_minutes=120, actual_minutes=45, status="partially_completed"), SimpleNamespace(id=1), db)
    result = build_week(db, 1, {}, 4, date.today(), [])
    backlog = [b for b in result["blocks"] if b["id"].startswith("backlog-p1#")]
    assert sum(round(b["duration"] * 60) for b in backlog) == 75


def test_progress_retries_and_undo_replace_same_record(db):
    data = dict(client_ref="p1", date=date.today(), subject="math", planned_minutes=60,
                actual_minutes=60, status="completed")
    for _ in range(2): save_progress(ProgressIn(**data), SimpleNamespace(id=1), db)
    assert db.query(TaskProgress).count() == 1
    data.update(status="planned", actual_minutes=0)
    save_progress(ProgressIn(**data), SimpleNamespace(id=1), db)
    db.expire_all()
    assert db.query(TaskProgress).one().status == "planned"


def test_repeated_mock_submit_does_not_inflate_weakness_or_change_score(db):
    qs = [{"_id": 1, "subject": "math", "topic": "limits", "text": "q", "options": ["a","b","c","d"], "answer": 0}]
    mock = GeneratedMock(student_id=1, title="test", questions=json.dumps(qs), duration_minutes=10)
    db.add(mock); db.commit()
    a = submit_mock(mock.id, SubmitPayload(answers={"1": 1}), SimpleNamespace(id=1), db)
    b = submit_mock(mock.id, SubmitPayload(answers={"1": 0}), SimpleNamespace(id=1), db)
    assert a == b
    assert a["score"] == -33.3
    assert db.query(MockAttempt).count() == 1
    assert db.query(WrongAnswer).count() == 1
    ev = topic_evidence(db, 1)
    assert ev[0]["attempted"] == 1 and ev[0]["accuracy"] == 0
    assert topic_evidence(db, 2) == []


def test_correct_answers_contribute_to_strength_evidence(db):
    qs = [{"_id": i, "subject": "math", "topic": "limits", "answer": 0} for i in range(1, 11)]
    mock = GeneratedMock(student_id=1, title="test", questions=json.dumps(qs), duration_minutes=10)
    db.add(mock); db.flush()
    db.add(MockAttempt(student_id=1, mock_id=mock.id, answers=json.dumps({str(i): 0 if i < 10 else 1 for i in range(1,11)})))
    db.commit()
    assert topic_evidence(db, 1)[0]["accuracy"] == 0.9


def test_unverified_question_is_dropped(monkeypatch):
    from app.rag import mock_generation as mg
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: object())
    # The solver verifies in batches now; this stub is "solved none of them".
    monkeypatch.setattr(mg, "_verify_batch", lambda *a: {1: None})
    monkeypatch.setattr(mg, "_verify_question", lambda *a: None)
    monkeypatch.setattr(mg, "_generate_replacement", lambda *a: None)
    q = {"_id":1, "subject":"math", "text":"q", "answer":0, "options":["a","b","c","d"]}
    assert mg.verify_and_repair_booklet([q], 1, max_regens=1) == []


def test_verified_question_has_persisted_status(monkeypatch):
    from app.rag import mock_generation as mg
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: object())
    # Batch solver agrees with the stored key on question 1.
    monkeypatch.setattr(mg, "_verify_batch", lambda *a: {1: 0})
    monkeypatch.setattr(mg, "_verify_question", lambda *a: 0)
    q = {"_id":1, "subject":"math", "text":"q", "answer":0, "options":["a","b","c","d"]}
    result = mg.verify_and_repair_booklet([q], 1)
    assert result[0]["verification_status"] == "verified"


def test_completed_recovery_does_not_create_backlog_again(db):
    save_progress(ProgressIn(client_ref="original", date=date.today(), subject="math", topic="limits",
        planned_minutes=120, actual_minutes=45, status="partially_completed"), SimpleNamespace(id=1), db)
    save_progress(ProgressIn(client_ref="recovery", source_ref="backlog-original", date=date.today(),
        subject="math", topic="limits", planned_minutes=75, actual_minutes=75, status="completed"), SimpleNamespace(id=1), db)
    result = build_week(db, 1, {}, 4, date.today(), [])
    assert not any(b["source_ref"].startswith("backlog-") for b in result["blocks"])


def test_regeneration_does_not_reuse_ids_or_reset_completed_work(db):
    first = build_week(db, 1, {}, 2, date.today(), [])
    block = first["blocks"][0]
    from datetime import timedelta
    day = date.today() + timedelta(days=block["day"])
    ref = f'{day}:{block["id"]}'
    save_progress(ProgressIn(client_ref=ref, source_ref=block["source_ref"], date=day,
        subject=block["subject"], topic=block["topic"], task_type=block["task_type"],
        planned_minutes=round(block["duration"]*60), actual_minutes=round(block["duration"]*60),
        status="completed"), SimpleNamespace(id=1), db)
    second = build_week(db, 1, {}, 2, date.today(), [])
    assert not {b["id"] for b in first["blocks"]} & {b["id"] for b in second["blocks"]}
    db.expire_all()
    assert db.get(TaskProgress, (1, ref)).status == "completed"
    scheduled = sum(round(b["duration"]*60) for b in second["blocks"] if b["day"] == block["day"])
    assert scheduled + round(block["duration"]*60) <= 120


def test_weekly_mock_and_correction_are_in_order(db):
    result = build_week(db, 1, {}, 2, date.today(), [])
    mocks = [b for b in result["blocks"] if b["source_ref"] == "weekly-mock"]
    correction = [b for b in result["blocks"] if b["source_ref"] == "weekly-correction"]
    assert sum(round(b["duration"] * 60) for b in mocks) == 60
    assert sum(round(b["duration"] * 60) for b in correction) == 30
    assert min((b["day"], b["startHour"]) for b in correction) >= max(
        (b["day"], b["startHour"] + b["duration"]) for b in mocks)


def test_pool_quarantines_unverified_stock_then_claims_verified(db):
    from app.routers.mocks import _claim_pool_mock
    from app.rag.pool_core import CANONICAL_MAJOR
    q = {"_id":1,"text":"q","options":["a","b","c","d"],"answer":0}
    old = GeneratedMock(student_id=0, title="old", questions=json.dumps([q]),
        status="pending_use", major=CANONICAL_MAJOR["riazi"], difficulty="easy")
    new = GeneratedMock(student_id=0, title="new", questions=json.dumps([{**q,"verification_status":"verified"}]),
        status="pending_use", major=CANONICAL_MAJOR["riazi"], difficulty="easy")
    db.add_all([old,new]); db.commit()
    assert _claim_pool_mock(db, 1, "riazi", "easy", "12").id == new.id
    db.refresh(old)
    assert old.status == "quarantined"
    assert _claim_pool_mock(db, 2, "riazi", "easy", "12") is None


def test_regeneration_does_not_schedule_elapsed_time(db):
    now = datetime.combine(date.today(), datetime.min.time()).replace(hour=14, minute=20)
    result = build_week(db, 1, {}, 4, date.today(), [], now=now)
    assert all(b["day"] > 0 or b["startHour"] >= 14 + 21/60 for b in result["blocks"])


@pytest.mark.parametrize("values", [
    {"started_at":"bad-date"},
    {"started_at":"2026-09-28T12:00:00", "ended_at":"2026-09-28T11:00:00"},
    {"attempted_questions":2,"correct_count":3},
    {"subject":"   "},
])
def test_invalid_session_is_rejected_without_writing(db, values):
    from app.routers.profile import SessionIn, create_session
    from app.auth.database import StudySession
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create_session(SessionIn(**{"subject":"math", **values}), SimpleNamespace(id=1), db)
    assert exc.value.status_code == 422
    assert db.query(StudySession).count() == 0


def test_session_normalizes_timezone_and_has_real_subject_foreign_key(db):
    from app.routers.profile import SessionIn, create_session
    from app.auth.database import StudySession, Subject
    result = create_session(SessionIn(subject="math", started_at="2026-09-28T12:00:00+03:30",
        ended_at="2026-09-28T09:30:00Z"), SimpleNamespace(id=1), db)
    assert result["actual_minutes"] == 60
    row = db.get(StudySession, result["id"])
    assert db.get(Subject, row.subject_id).name == "math"


def test_saved_exam_is_scoped_and_visible_in_overview(db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.planner import clock
    from app.routers.profile import ExamIn, add_exam
    from app.routers.boom_ai import plan_overview
    from app.auth.database import Assessment
    from fastapi import HTTPException
    # UTC hosts and Tehran students have different dates near midnight.
    now = datetime(2026, 10, 6, 21, 30, tzinfo=timezone.utc).astimezone(
        timezone(timedelta(hours=3, minutes=30))).replace(tzinfo=None)
    monkeypatch.setattr(clock, "planner_now", lambda: now)
    with pytest.raises(HTTPException) as error:
        add_exam(ExamIn(title="previous", date=date(2026, 10, 6), subjects=["math"]), SimpleNamespace(id=1), db)
    assert error.value.status_code == 422
    db.add(Assessment(student_id=1, title="previous", date=date(2026, 10, 6)))
    db.commit()
    add_exam(ExamIn(title="upcoming", date=now.date(), subjects=["math"]), SimpleNamespace(id=1), db)
    assert [exam["title"] for exam in plan_overview(SimpleNamespace(id=1), db)["exams"]] == ["upcoming"]
    assert not plan_overview(SimpleNamespace(id=2), db)["exams"]



def test_learning_and_break_preferences_change_the_schedule(db):
    from datetime import timedelta
    week = date.today() + timedelta(days=7)
    theory = build_week(db, 1, {"studyStyle":"بیشتر مطالعه نظری", "breakStyle":"پومودورو ۲۵ دقیقه"}, 4, week, [])
    practice = build_week(db, 2, {"studyStyle":"بیشتر تمرین"}, 4, week, [])
    assert all(round(b["duration"]*60) <= 25 for b in theory["blocks"])
    study_minutes = lambda result: sum(round(b["duration"]*60) for b in result["blocks"] if b["task_type"] == "study")
    assert study_minutes(theory) > study_minutes(practice)
