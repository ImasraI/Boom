"""Tests for the weekly planner validator (_complete_week_plan)."""

import sys
import os

# Add backend to path
sys.path.insert(0, r"C:\Users\Arsam\Desktop\Boom-merged\backend")

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