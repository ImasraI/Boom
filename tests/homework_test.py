"""Homework must be student-reviewed, account-owned and calendar-backed."""
import json
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.auth.database import Base, User, Homework, StudentProfile, TaskProgress
from app.planner.homework import HomeworkIn, intake, schedule_homework
from app.planner.calendar import calendar_row, payload, write_calendar, protected_blocks, overlaps

WEEK = date(2099, 4, 4)
NOW = datetime(2099, 4, 4, 9)

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([User(id=i, username=str(i), hashed_password="x") for i in (1, 2)])
        session.add(StudentProfile(user_id=1, study_hours="۸", availability=json.dumps({"wake": "06:00"})))
        session.add(Homework(id="one", student_id=1, conversation_id="chat", details="{}", status="draft"))
        session.commit()
        yield session

def req(**changes):
    values = dict(title="تمرین معلم", subject="فیزیک", topic="میدان الکتریکی",
        workload="۲۰ سؤال از کتاب خیلی سبز", minutes=120, due_date=WEEK,
        activity="practice", familiarity="learning", calendar_version=0)
    return HomeworkIn(**{**values, **changes})

def block(id="generated", **changes):
    return {"id": id, "day": 0, "startHour": 10, "duration": 2, "title": "حل سؤال میدان",
        "origin": "generated", "type": "test", "task_type": "practice",
        "subject": "فیزیک", "topic": "میدان الکتریکی", **changes}

def save(db, blocks, statics=None):
    return write_calendar(db, calendar_row(db, 1), {WEEK.isoformat(): blocks}, statics or [], 0)

def assert_code(code, action):
    with pytest.raises(HTTPException) as error:
        action()
    assert error.value.status_code == code

def test_intake_asks_questions_without_creating_calendar_blocks(db, monkeypatch):
    from app.rag import llm
    monkeypatch.setattr(llm, "get_llm_client", lambda: SimpleNamespace(
        generate=lambda *a, **k: '{"subject":"فیزیک","topic":"میدان الکتریکی","workload":"۲۰ سؤال"}',
        last_usage=SimpleNamespace(total_tokens=0)))
    answer = intake(db, 1, "new-chat", "۲۰ سؤال فیزیک میدان دارم")
    draft = answer["homework_draft"]
    assert draft["status"] == "draft" and "minutes" not in draft["details"]
    assert "مهلت" in answer["answer"] and "ثبت در برنامه" in answer["answer"]
    assert payload(calendar_row(db, 1))["weeks"] == {}
    assert db.query(TaskProgress).count() == 0

def test_provider_failure_leaves_manual_intake_available(db, monkeypatch):
    from app.rag import llm
    def failed(*a, **k):
        raise RuntimeError("quota")
    monkeypatch.setattr(llm, "get_llm_client", lambda: SimpleNamespace(generate=failed))
    answer = intake(db, 1, "chat", "تکلیف دارم")
    assert answer["homework_draft"]["details"] == {"student_message": "تکلیف دارم"}

def test_drafts_are_scoped_to_account_and_conversation(db):
    assert_code(404, lambda: intake(db, 2, "chat", "یک ساعت", "one"))
    assert_code(404, lambda: intake(db, 1, "other-chat", "یک ساعت", "one"))
    assert_code(404, lambda: schedule_homework(db, 2, "one", req(), now=NOW))

def test_homework_fits_future_slots_and_persists_metadata_and_progress(db):
    saved = schedule_homework(db, 1, "one", req(), now=NOW)
    blocks = saved["calendar"]["weeks"][str(WEEK)]
    assert sum(round(b["duration"] * 60) for b in blocks) == 120
    assert all(b["startHour"] > 9 and b["origin"] == "manual" for b in blocks)
    assert all(b["subject"] == "فیزیک" and b["topic"] == "میدان الکتریکی" for b in blocks)
    assert all("۲۰ سؤال" in b["description"] for b in blocks)
    assert not overlaps(blocks)
    assert protected_blocks(blocks) == blocks  # Weekly rebuild preserves homework.
    assert db.query(TaskProgress).count() == len(blocks)
    assert all(p.status == "planned" and p.actual_minutes == 0 for p in db.query(TaskProgress))
    assert payload(calendar_row(db, 2))["weeks"] == {}

def test_duplicate_confirmation_never_adds_duplicate_homework(db):
    first = schedule_homework(db, 1, "one", req(), now=NOW)
    second = schedule_homework(db, 1, "one", req(), now=NOW)
    assert second["already_scheduled"]
    assert first["calendar"] == second["calendar"]
    assert db.query(TaskProgress).count() == len(first["blocks"])

def test_no_capacity_keeps_entire_plan_and_draft_unchanged(db):
    original = save(db, [block(duration=8)])
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(calendar_version=1), now=NOW))
    assert payload(calendar_row(db, 1)) == original
    assert db.get(Homework, "one").status == "draft"
    assert db.query(TaskProgress).count() == 0

def test_replacement_changes_only_equivalent_generated_session(db):
    matching = block()
    manual = block("manual", origin="manual", startHour=13)
    other = block("other", topic="حرکت", startHour=16, duration=4)
    save(db, [matching, manual, other])
    db.add(TaskProgress(student_id=1, client_ref=f"{WEEK}:generated", date=WEEK,
        subject="فیزیک", topic="میدان الکتریکی", task_type="practice", planned_minutes=120,
        actual_minutes=0, status="planned"))
    db.commit()
    result = schedule_homework(db, 1, "one", req(calendar_version=1, placement="replace_matching"), now=NOW)
    assert result["replaced"] == [matching]
    current = result["calendar"]["weeks"][str(WEEK)]
    assert manual in current and other in current and matching not in current
    assert not overlaps(current)
    assert db.get(TaskProgress, (1, f"{WEEK}:generated")).status == "rescheduled"

@pytest.mark.parametrize("changes", [
    {"origin": "manual"}, {"topic": "حرکت"}, {"subject": "شیمی"}, {"type": "study", "task_type": "study"},
])
def test_replacement_cannot_remove_manual_other_topics_or_initial_study(db, changes):
    original = save(db, [block(duration=8, **changes)])
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(calendar_version=1, placement="replace_matching"), now=NOW))
    assert payload(calendar_row(db, 1)) == original

def test_new_topic_or_completed_session_is_not_replaced(db):
    original = save(db, [block(duration=8)])
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(calendar_version=1,
        placement="replace_matching", familiarity="new", preparation_minutes=30), now=NOW))
    db.add(TaskProgress(student_id=1, client_ref=f"{WEEK}:generated", date=WEEK,
        subject="فیزیک", topic="میدان الکتریکی", task_type="practice", planned_minutes=480,
        actual_minutes=60, status="partially_completed"))
    db.commit()
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(calendar_version=1, placement="replace_matching"), now=NOW))
    assert payload(calendar_row(db, 1)) == original

def test_fixed_recurrence_and_deadline_are_respected_across_weeks(db):
    now = datetime(2099, 4, 10, 23)
    statics = [block("repeat", date="2099-04-11", day=None, type="class", startHour=6, duration=3,
                    recurrence={"frequency": "daily", "interval": 1})]
    save(db, [], statics)
    result = schedule_homework(db, 1, "one", req(calendar_version=1, due_date=WEEK + timedelta(days=7),
                               due_time="12:00"), now=now)
    for iso, blocks in result["calendar"]["weeks"].items():
        for b in blocks:
            actual = date.fromisoformat(iso) + timedelta(days=b["day"])
            assert actual >= now.date()
            assert b["startHour"] > 23 if actual == now.date() else b["startHour"] >= 9
            assert b["startHour"] + b["duration"] <= 12 if actual.day == 11 else True

def test_stale_version_and_invalid_deadline_do_not_change_calendar(db):
    save(db, [])
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(), now=NOW))
    assert_code(422, lambda: schedule_homework(db, 1, "one", req(calendar_version=1, due_time="08:00"), now=NOW))
    assert_code(422, lambda: schedule_homework(db, 1, "one", req(calendar_version=1, due_date=WEEK+timedelta(days=43)), now=NOW))
    assert payload(calendar_row(db, 1))["version"] == 1

def test_rest_day_and_study_goal_are_not_overridden(db):
    profile = db.query(StudentProfile).filter_by(user_id=1).one()
    profile.availability = json.dumps({"daily_hours": {"شنبه": 0}})
    db.commit()
    assert_code(409, lambda: schedule_homework(db, 1, "one", req(), now=NOW))


def test_unread_homework_topic_gets_study_before_practice_within_total_time(db):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        req(familiarity="new")
    result = schedule_homework(db, 1, "one", req(familiarity="new", preparation_minutes=30), now=NOW)
    blocks = result["blocks"]
    assert blocks[0]["task_type"] == "study"
    assert round(blocks[0]["duration"] * 60) == 30
    assert all(b["task_type"] == "practice" for b in blocks[1:])
    assert blocks[0]["startHour"] + blocks[0]["duration"] <= blocks[1]["startHour"]
    assert sum(round(b["duration"] * 60) for b in blocks) == 120


def test_weekly_rebuild_preserves_homework_without_inventing_mastery(db, monkeypatch):
    from app.planner import resources, mock_outline
    from app.planner.adaptive import build_week, topic_evidence
    monkeypatch.setattr(resources, "available_books", lambda *a, **k: [])
    monkeypatch.setattr(mock_outline, "next_mock_outline", lambda *a, **k: None)
    saved = schedule_homework(db, 1, "one", req(), now=NOW)
    old = saved["blocks"]
    result = build_week(db, 1, {}, 8, WEEK, [], protected=protected_blocks(old), now=NOW)
    assert all(b in result["blocks"] for b in old)
    assert not overlaps(result["blocks"])
    assert topic_evidence(db, 1) == []


def test_chat_homework_flow_skips_book_retrieval_and_retains_draft_on_followup(db, monkeypatch):
    from app.routers import boom_ai
    from app.rag import llm
    for name in ("check_ai_quota", "check_token_budget", "record_ai_use"):
        monkeypatch.setattr(boom_ai, name, lambda *a: None)
    monkeypatch.setattr(boom_ai, "answer_question", lambda **k: pytest.fail("Homework is not a book retrieval query"))
    answers = iter(['{"subject":"فیزیک","topic":"میدان الکتریکی","workload":"۲۰ سؤال"}',
                    '{"minutes":90,"familiarity":"learning"}'])
    monkeypatch.setattr(llm, "get_llm_client", lambda: SimpleNamespace(generate=lambda *a, **k: next(answers),
        last_usage=SimpleNamespace(total_tokens=0)))
    first = boom_ai.boom_chat(boom_ai.BoomChatRequest(question="تکلیف فیزیک دارم", conversation_id="chat"), SimpleNamespace(id=1), db)
    draft_id = first["homework_draft"]["id"]
    second = boom_ai.boom_chat(boom_ai.BoomChatRequest(question="خوانده‌ام، ۹۰ دقیقه وقت لازم دارد", conversation_id="chat", homework_id=draft_id), SimpleNamespace(id=1), db)
    assert second["homework_draft"]["id"] == draft_id
    assert second["homework_draft"]["details"]["subject"] == "فیزیک"
    assert second["homework_draft"]["details"]["minutes"] == 90
    assert "plan_update" not in second
    assert payload(calendar_row(db, 1))["weeks"] == {}
