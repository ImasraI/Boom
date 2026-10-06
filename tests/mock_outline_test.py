"""A student's next mock must match their provider, grade and its own date."""
import json
from datetime import date
from types import SimpleNamespace

from app.planner import mock_outline


def _cache(tmp_path, monkeypatch, entries):
    directory = tmp_path / "cache"
    directory.mkdir()
    (directory / "mock_extraction.json").write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(mock_outline, "get_settings", lambda: SimpleNamespace(RAW_DIR=str(tmp_path / "raw")))


def test_topics_are_bound_to_their_exam_date(tmp_path, monkeypatch):
    text = """ماز – دوازدهم ریاضی ۱۴۰۵
| ۱۸ مهر | آزمون اول |
| ۲۵ مهر | آزمون دوم |
### آزمون ۱۸ مهر
- **شیمی**
  - مباحث: تعادل
### آزمون ۲۵ مهر
- **شیمی**
  - مباحث: ساختار اتم
"""
    _cache(tmp_path, monkeypatch, {"norm2|maz-1405.pdf": text})
    result = mock_outline.next_mock_outline({"major": "ریاضی", "grade": "دوازدهم", "testExams": ["ماز"]}, date(2026, 10, 10))
    assert result["date"] == date(2026, 10, 10)
    assert result["topics"] == {"شیمی": ["تعادل"]}


def test_another_provider_and_grade_are_not_silently_used(tmp_path, monkeypatch):
    text = "ماز – دوازدهم ریاضی ۱۴۰۵\n| ۱۸ مهر | آزمون |\n### دفترچه هر تاریخ\n- **شیمی**\n  - مباحث: تعادل"
    _cache(tmp_path, monkeypatch, {"norm2|maz-1405.pdf": text})
    assert mock_outline.next_mock_outline({"testExams": ["سنجش"]}, date(2026, 10, 10)) is None
    assert mock_outline.next_mock_outline({"testExams": ["ماز"], "grade": "یازدهم"}, date(2026, 10, 10)) is None


def test_multiple_exam_dates_without_topic_date_binding_are_ambiguous(tmp_path, monkeypatch):
    text = "ماز – دوازدهم ریاضی ۱۴۰۵\n| ۱۸ مهر | آزمون |\n| ۲۵ مهر | آزمون |\n### دفترچه اول\n- **شیمی**\n  - مباحث: تعادل"
    _cache(tmp_path, monkeypatch, {"norm2|maz-1405.pdf": text})
    assert mock_outline.next_mock_outline({}, date(2026, 10, 10)) is None
