"""Regressions for two fixed logic bugs.

1. pad_booklet used to shift the answer INDEX without moving option text,
   pointing answer keys at the wrong option. The fix swaps option strings.
2. _complete_week_plan's backfill passed an always-empty occupied list, so
   default blocks could land on top of the user's protected static slots.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

from app.rag.mock_generation import pad_booklet
from app.routers import boom_ai
from app.routers.boom_ai import _complete_week_plan, _default_week_plan


def test_pad_booklet_keeps_key_on_correct_text():
    """Spreading answer keys must swap option TEXT, not just the index."""
    # All three questions answer=0 -> clumping triggers the spread.
    questions = [
        {"text": f"q{i}", "options": ["صحیح", "غلط الف", "غلط ب", "غلط ج"],
         "answer": 0, "explanation": "", "subject": "ریاضی", "topic": ""}
        for i in range(3)
    ]
    out = pad_booklet([dict(q, options=list(q["options"])) for q in questions])
    # Every question's answer index must still point at the original correct
    # string "صحیح", wherever it moved to.
    for q in out:
        assert q["options"][q["answer"]] == "صحیح", (
            f"answer key points at wrong option text: {q}")
    # And the keys should actually be spread (not all 0 anymore).
    assert len({q["answer"] for q in out}) > 1


def test_pad_booklet_no_spread_when_not_clumped():
    """A balanced booklet must pass through untouched."""
    questions = [
        {"text": "q0", "options": ["a", "b", "c", "d"], "answer": 1,
         "explanation": "", "subject": "ریاضی", "topic": ""},
        {"text": "q1", "options": ["a", "b", "c", "d"], "answer": 2,
         "explanation": "", "subject": "ریاضی", "topic": ""},
    ]
    out = pad_booklet([dict(q, options=list(q["options"])) for q in questions])
    assert [q["answer"] for q in out] == [1, 2]


def test_backfill_respects_protected_statics():
    """Default-plan backfill must not place blocks over protected slots."""
    books = ["کتاب فیزیک"]
    student = {"weakSubjects": []}

    # A protected class slot covering the whole study window on EVERY day:
    # 06:00-24:00. Nothing should be scheduled over it.
    statics = [{"day": d, "startHour": 6, "duration": 18, "title": "کلاس"}
               for d in range(7)]

    result = _complete_week_plan([], books, 4.0, student,
                                 statics=[], protected_statics=statics)
    study = [b for b in result if b["type"] == "study"]
    assert not study, (
        f"backfill placed study blocks inside protected slots: {study}")


def test_default_week_plan_resolves_weak_topic_ranges(monkeypatch):
    """Weak topics must resolve into real page/question ranges.

    Regression: the range-resolution block referenced current_user.id inside
    this plain helper - NameError on every call, swallowed by the surrounding
    except, so every test block silently fell back to the generic
    «N تست از کتاب منبع کنکور» title with no real ranges."""
    canned = [{"subject": "فیزیک", "topic": "اثر داپلر", "book": "فیزیک خیلی سبز",
               "page_from": 154, "page_to": 162, "q_from": 41, "q_to": 56}]
    seen_user_ids = []

    def fake_resolve(user_id, subject, topics, wanted=6):
        seen_user_ids.append(user_id)
        return [dict(canned[0], subject=subject, topic=topics[0] if topics else "")]

    monkeypatch.setattr(boom_ai, "_resolve_topic_ranges", fake_resolve)

    blocks = _default_week_plan(
        ["کتاب فیزیک"], 4.0, {"weakSubjects": []},
        weak_topics=["فیزیک: اثر داپلر"], user_id=42,
    )
    assert seen_user_ids and seen_user_ids[0] == 42, (
        "range resolution never ran - the silent failure is back")
    test_blocks = [b for b in blocks if b["type"] == "test"]
    assert test_blocks, "no test blocks produced"
    # The concrete range must surface in the title instead of the generic one.
    assert any("۴۱ تا ۵۶" in b["title"] for b in test_blocks), \
        [b["title"] for b in test_blocks]


if __name__ == "__main__":
    test_pad_booklet_keeps_key_on_correct_text()
    test_pad_booklet_no_spread_when_not_clumped()
    test_backfill_respects_protected_statics()
    print("\nAll regression tests passed!")
