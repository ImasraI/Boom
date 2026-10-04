"""User commitments, realistic workload and calendar persistence regressions."""
import json
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.auth.database import Base, User, StudentProfile, BookCatalog, Assessment
from app.planner import resources, mock_outline
from app.planner.adaptive import build_week
from app.planner.calendar import occurrences, overlaps
from app.routers.profile import CalendarIn, get_calendar, patch_calendar
from app.routers.boom_ai import WeeklyPlanRequest, generate_weekly_plan

WEEK = date(2099, 4, 4)
USER = SimpleNamespace(id=1)

@pytest.fixture
def db(tmp_path, monkeypatch):
    settings = SimpleNamespace(RAW_DIR=str(tmp_path / "raw"), OCR_DIR=str(tmp_path / "ocr"))
    monkeypatch.setattr(resources, "get_settings", lambda: settings)
    monkeypatch.setattr(mock_outline, "get_settings", lambda: settings)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([User(id=i, username=str(i), hashed_password="x") for i in (1, 2)])
        db.commit()
        yield db

def block(**kwargs):
    return {"id": "manual", "day": 2, "startHour": 14, "duration": 2,
            "title": "کلاس من", "type": "class", "origin": "manual", **kwargs}

def test_eight_hours_target_fills_each_day_with_mixed_subjects(db):
    db.add(StudentProfile(user_id=1, study_hours="۸ ساعت", availability=json.dumps({"wake": "06:30"})))
    db.commit()
    result = build_week(db, 1, {}, 4, WEEK, [], now=datetime(2099, 4, 3))
    assert result["target_daily_minutes"] == 480
    assert all(450 <= minutes <= 480 for minutes in result["daily_minutes"]), result["daily_minutes"]
    assert sum(result["daily_minutes"]) >= 3300
    for day in range(7):
        assert len({b["subject"] for b in result["blocks"] if b["day"] == day}) >= 2
    assert not overlaps(result["blocks"])

def test_completed_and_manual_study_count_toward_goal(db):
    manual = block(type="study", duration=2, day=0)
    result = build_week(db, 1, {}, 8, WEEK, [], protected=[manual], now=datetime(2099, 4, 3))
    assert result["blocks"][0] == manual
    assert 450 <= result["daily_minutes"][0] <= 480

def test_capacity_shortfall_is_explained_and_does_not_overlap(db):
    fixed = [{"day": day, "startHour": 6, "duration": 15, "title": "مدرسه"} for day in range(7)]
    result = build_week(db, 1, {}, 8, WEEK, fixed, now=datetime(2099, 4, 3))
    assert result["unscheduled"]
    assert all(m < 480 for m in result["daily_minutes"])
    assert not overlaps(result["blocks"] + fixed)

def test_manual_blocks_survive_rebuild_and_accounts_load_separately(db):
    manual = block()
    initial = get_calendar(USER, db)
    saved = patch_calendar(CalendarIn(version=initial["version"], weeks={WEEK.isoformat(): [manual]}), USER, db)
    generated = generate_weekly_plan(WeeklyPlanRequest(week_start=WEEK.isoformat(), daily_hours=8,
                                                       calendar_version=saved["version"]), USER, db)
    assert manual in generated["blocks"]
    again = generate_weekly_plan(WeeklyPlanRequest(week_start=WEEK.isoformat(), daily_hours=8,
                         calendar_version=generated["calendar_version"]), USER, db)
    assert next(b for b in again["blocks"] if b["id"] == manual["id"]) == manual
    assert not overlaps(again["blocks"])
    assert get_calendar(SimpleNamespace(id=2), db)["weeks"] == {}
    assert get_calendar(USER, db)["weeks"][WEEK.isoformat()] == again["blocks"]

def test_stale_calendar_writes_and_rebuilds_do_not_erase_manual_blocks(db):
    patch_calendar(CalendarIn(version=0, weeks={WEEK.isoformat(): [block()]}), USER, db)
    with pytest.raises(HTTPException) as e:
        patch_calendar(CalendarIn(version=0, weeks={WEEK.isoformat(): []}), USER, db)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        generate_weekly_plan(WeeklyPlanRequest(week_start=WEEK.isoformat(), calendar_version=0), USER, db)
    assert e.value.status_code == 409
    assert get_calendar(USER, db)["weeks"][WEEK.isoformat()] == [block()]

@pytest.mark.parametrize("rule,expected", [
    ({"frequency": "daily", "interval": 2}, [0, 2, 4, 6]),
    ({"frequency": "daily", "interval": 1, "count": 3}, [0, 1, 2]),
    ({"frequency": "daily", "interval": 1, "until": "2099-04-06"}, [0, 1, 2]),
    ({"frequency": "weekly", "interval": 1, "weekdays": [0, 3]}, [0, 3]),
    ({"frequency": "monthly", "interval": 1}, [0]),
    ({"frequency": "yearly", "interval": 1}, [0]),
])
def test_recurrence_rules(rule, expected):
    template = block(date=WEEK.isoformat(), recurrence=rule)
    assert [b["day"] for b in occurrences([template], WEEK)] == expected

def test_monthly_skips_missing_day_and_weekly_interval_is_anchored():
    monthly = block(date="2026-01-31", recurrence={"frequency": "monthly", "interval": 1})
    assert occurrences([monthly], date(2026, 2, 28)) == []
    assert len(occurrences([monthly], date(2026, 3, 28))) == 1
    weekly = block(date=WEEK.isoformat(), recurrence={"frequency": "weekly", "interval": 2, "weekdays": [0, 3]})
    assert occurrences([weekly], WEEK + timedelta(days=7)) == []
    assert len(occurrences([weekly], WEEK + timedelta(days=14))) == 2

def test_recurring_activities_are_reserved_when_rebuilding(db):
    template = block(date=WEEK.isoformat(), recurrence={"frequency": "daily", "interval": 1})
    saved = patch_calendar(CalendarIn(version=0, statics=[template]), USER, db)
    result = generate_weekly_plan(WeeklyPlanRequest(week_start=WEEK.isoformat(), daily_hours=8,
                                    calendar_version=saved["version"]), USER, db)
    assert not overlaps(result["blocks"] + occurrences([template], WEEK))
    assert get_calendar(USER, db)["statics"] == [template]

def test_mock_topics_select_matching_book_ranges(db):
    db.add(Assessment(student_id=1, title="آزمون شیمی", date=WEEK + timedelta(days=6),
        results=json.dumps({"subjects": [{"name": "شیمی", "topics": ["تعادل"]}]})))
    db.add_all([BookCatalog(book_id="شیمی خیلی سبز " + topic, subject="شیمی", chapter=topic,
        question_range_start=start, question_range_end=start+1000) for topic, start in (("تعادل", 30), ("استوکیومتری", 2000))])
    db.commit()
    result = build_week(db, 1, {}, 8, WEEK, [], now=datetime(2099, 4, 3))
    chemistry = [b for b in result["blocks"] if b["subject"] == "شیمی"]
    assert chemistry and all(b["topic"] == "تعادل" for b in chemistry)
    tests = [b for b in chemistry if b["task_type"] == "test"]
    assert tests and all(30 <= b["question_start"] <= b["question_end"] <= 1030 for b in tests)


def test_missing_question_ranges_never_become_unspecified_test_assignments(db):
    result = build_week(db, 1, {}, 8, WEEK, [], now=datetime(2099, 4, 3))
    assert all(b.get("question_start") and b.get("question_end") and b.get("resource")
               for b in result["blocks"] if b["task_type"] == "test" and b["subject"] != "آزمون")
    practice = [b for b in result["blocks"] if b["task_type"] == "practice"]
    assert practice and all(b["count"] is None and "تمرین تشریحی" in b["title"] for b in practice)
    assert sum(result["daily_minutes"]) >= 3300


def test_cached_mock_outline_uses_upcoming_dates_and_skips_old_year(db, tmp_path):
    path = tmp_path / "cache/mock_extraction.json"
    path.parent.mkdir()
    text = "برنامه ماز ریاضی ۱۴۰۵\n| ۱۸ مهر | جامع |\n### دفترچه اول\n- **شیمی پایه** – ۲۰ سؤال\n  - مباحث: تعادل، استوکیومتری\n### دفترچه سوم (اختیاری)\n- **شیمی** – ۱۰ سؤال\n  - مباحث: موضوع اختیاری\n"
    path.write_text(json.dumps({"norm2|plan-1405.pdf": text}), encoding="utf-8")
    outline = mock_outline.next_mock_outline({"major": "ریاضی"}, date(2026, 10, 3))
    assert outline["date"] == date(2026, 10, 10)
    assert outline["topics"]["شیمی"] == ["تعادل", "استوکیومتری"]
    assert mock_outline.next_mock_outline({"major": "تجربی"}, date(2026, 10, 3)) is None
    assert mock_outline.next_mock_outline({"major": "ریاضی"}, date(2027, 10, 3)) is None


def test_indexed_user_uploads_supply_book_ranges_without_shared_raw_pdf(db, monkeypatch):
    monkeypatch.setattr(resources, "_indexed_ranges", lambda user_id: {"شیمی خیلی سبز": [{
        "q_from": 30, "q_to": 80, "topic": "تعادل", "page_from": 18, "page_to": 20}]})
    books = resources.available_books(db, {"major": "ریاضی", "grade": "دوازدهم"}, 1)
    blocks = [{"task_type":"test", "subject":"شیمی", "topic":"تعادل", "count":20, "description":"تمرین"}]
    resources.assign_test_resources(db, {}, blocks, [], books=books)
    assert blocks[0]["resource"] == "شیمی خیلی سبز"
    assert (blocks[0]["question_start"], blocks[0]["question_end"]) == (30,49)


def test_preserved_manual_test_ranges_are_not_reassigned_by_rebuild(db):
    db.add(BookCatalog(book_id="شیمی خیلی سبز", subject="شیمی", chapter="تعادل",
                       question_range_start=30, question_range_end=1030))
    db.commit()
    manual = block(type="test", resource="شیمی خیلی سبز", question_start=30, question_end=49)
    result = build_week(db, 1, {}, 8, WEEK, [], protected=[manual], now=datetime(2099,4,3))
    assert manual in result["blocks"]
    assert all(b["question_start"] > 49 for b in result["blocks"] if b.get("resource") == manual["resource"] and b["id"] != manual["id"] and b.get("question_start"))
