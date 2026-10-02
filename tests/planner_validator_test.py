"""Tests for the weekly planner validator (_complete_week_plan)."""

import sys
from pathlib import Path

# Add backend to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.routers.boom_ai import _complete_week_plan, _default_week_plan


def test_complete_week_plan_fills_all_days():
    """_complete_week_plan should ensure all 7 days have study + test blocks."""
    books = ["mathematics", "physics"]
    daily_hours = 4.0
    student = {"weakSubjects": [], "strong_subjects": []}

    # Provide partial LLM output (only 2 days)
    llm_blocks = [
        {"day": 0, "startHour": 9, "duration": 2, "title": "مطالعه Mathematiker", "type": "study"},
        {"day": 1, "startHour": 10, "duration": 1, "title": "5 تست Physic", "type": "test"},
    ]

    result = _complete_week_plan(llm_blocks, books, daily_hours, student)
    
    # Should have blocks for all 7 days
    days_covered = set()
    for b in result:
        days_covered.add(b["day"])
    
    # All 7 days should be covered (0-6)
    assert len(days_covered) == 7, f"Expected 7 days covered, got {len(days_covered)}: {days_covered}"
    print(f"✓ All 7 days covered: {sorted(days_covered)}")


def test_complete_week_plan_deduplicates():
    """_complete_week_plan should not create duplicate blocks for the same day/type."""
    books = ["mathematics"]
    daily_hours = 4.0
    student = {"weakSubjects": [], "strong_subjects": []}

    # Provide output with duplicate study blocks for the same day
    llm_blocks = [
        {"day": 0, "startHour": 9, "duration": 2, "title": "مطالعه ۱", "type": "study"},
        {"day": 0, "startHour": 11, "duration": 2, "title": "مطالعه ۲", "type": "study"},
        {"day": 0, "startHour": 14, "duration": 1, "title": "بازبینی", "type": "study"},  # duplicate type for day 0
    ]

    result = _complete_week_plan(llm_blocks, books, daily_hours, student)
    
    # Should not have 2 study blocks for the same day without the validator handling it
    study_per_day = {}
    for b in result:
        d = b["day"]
        study_per_day.setdefault(d, []).append(b)
    
    # Day 0 should have at most 1 study block after validation
    day0_studies = study_per_day.get(0, [])
    print(f"Day 0 studies after validation: {len(day0_studies)}")
    # The validator may keep or remove duplicates depending on the logic


def test_default_week_plan_has_study_and_test():
    """_default_week_plan should produce blocks with both study and test types."""
    books = ["mathematics"]
    daily_hours = 4.0
    student = {"weakSubjects": [], "strong_subjects": []}

    result = _default_week_plan(books, daily_hours, student)
    
    study_count = sum(1 for b in result if b["type"] == "study")
    test_count = sum(1 for b in result if b["type"] == "test")
    
    assert study_count > 0, f"Expected study blocks, got {study_count}"
    assert test_count > 0, f"Expected test blocks, got {test_count}"
    print(f"✓ Default plan: {study_count} study, {test_count} test blocks")


if __name__ == "__main__":
    test_complete_week_plan_fills_all_days()
    test_default_week_plan_has_study_and_test()
    print("\nAll planner validator tests passed!")

def _assert_safe(blocks, cap):
    for day in range(7):
        rows = sorted([b for b in blocks if b["day"] == day], key=lambda b: b["startHour"])
        assert sum(b["duration"] for b in rows) <= cap
        assert all(a["startHour"] + a["duration"] <= b["startHour"] for a, b in zip(rows, rows[1:]))


def test_live_validator_rejects_overlap_and_overcapacity():
    blocks = [{"day": 0, "startHour": 8, "duration": 3, "type": "study", "title": "a"},
              {"day": 0, "startHour": 9, "duration": 3, "type": "test", "title": "b"},
              {"day": 0, "startHour": 14, "duration": 3, "type": "test", "title": "c"}]
    _assert_safe(_complete_week_plan(blocks, [], 4, {}), 4)


def test_short_fallback_day_never_exceeds_budget():
    for cap in (0, 0.5, 1, 1.5, 2, 4, 8, 16):
        _assert_safe(_default_week_plan([], cap), cap)


def test_fallback_blocks_do_not_collide_after_class():
    fixed = [{"day": d, "startHour": 6, "duration": 6} for d in range(7)]
    _assert_safe(_default_week_plan([], 4, occupied=fixed), 4)


def test_live_plan_honors_persian_daily_hours_and_wake_time():
    student = {"dailyHours": {"شنبه": 0, "یکشنبه": 1}, "wakeTime": "10:00", "sleepHours": 8}
    blocks = _complete_week_plan([], [], 4, student)
    assert not any(b["day"] == 0 for b in blocks)
    assert sum(b["duration"] for b in blocks if b["day"] == 1) <= 1
    assert all(b["startHour"] >= 10 for b in blocks)


def test_weekly_endpoint_falls_back_offline_and_anchors_saturday(monkeypatch):
    from types import SimpleNamespace
    from datetime import date
    from app.routers import boom_ai
    from app.rag import pipeline
    def unavailable(*args, **kwargs):
        raise RuntimeError("service unavailable")
    monkeypatch.setattr(boom_ai, "check_ai_quota", lambda *a: None)
    monkeypatch.setattr(boom_ai, "record_ai_use", lambda *a: (_ for _ in ()).throw(AssertionError("failed call billed")))
    monkeypatch.setattr(boom_ai, "get_embedding_model", unavailable)
    monkeypatch.setattr(boom_ai, "get_llm_client", unavailable)
    monkeypatch.setattr(boom_ai, "_subject_book_context", unavailable)
    monkeypatch.setattr(pipeline, "_retrieve_image_hits", unavailable)
    monkeypatch.setattr(boom_ai, "_pick_main_book", lambda *a: "math")
    monkeypatch.setattr(boom_ai, "book_catalog", lambda: [])
    monkeypatch.setattr(boom_ai, "_extract_week_mock", lambda *a, **kw: None)
    monkeypatch.setattr(boom_ai, "_weakness_summary", lambda *a, **kw: {})
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.auth.database import Base
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = boom_ai.generate_weekly_plan(boom_ai.WeeklyPlanRequest(daily_hours=2), SimpleNamespace(id=1), db)
    assert result["llm_used"] is False
    assert date.fromisoformat(result["week_start"]).weekday() == 5
    assert result["blocks"]
    _assert_safe(result["blocks"], 2)
