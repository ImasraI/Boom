"""The displayed weekly plan must retain valid times and concrete practice sources."""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.auth.database import Base, BookCatalog, TaskProgress, User
from app.planner import adaptive, resources
from app.routers.boom_ai import _chat_plan_update_is_safe
from app.routers.profile import ProgressIn, save_progress


@pytest.fixture
def db(tmp_path, monkeypatch):
    settings = SimpleNamespace(RAW_DIR=str(tmp_path / "raw"), OCR_DIR=str(tmp_path / "ocr"))
    monkeypatch.setattr(resources, "get_settings", lambda: settings)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([User(id=1, username="one", hashed_password="x"), User(id=2, username="two", hashed_password="x")])
        session.commit()
        yield session


@pytest.mark.parametrize("student", [
    {"wakeTime": "06:30"},
    {"wakeTime": "07:15", "breakStyle": "تمرکز ۴۵ دقیقه"},
    {"wakeTime": "06:30", "breakStyle": "پومودورو ۲۵ دقیقه"},
])
def test_weekly_blocks_preserve_validated_minutes(db, monkeypatch, student):
    week = date(2099, 4, 4)
    fixed = [{"day": 0, "startHour": 8.5, "duration": 1, "title": "کلاس"}]
    generated = []
    original = adaptive.generate_plan
    def capture(inp):
        result = original(inp)
        generated.extend(result.items)
        return result
    monkeypatch.setattr(adaptive, "generate_plan", capture)
    result = adaptive.build_week(db, 1, student, 4, week, fixed, now=datetime(2099, 4, 3))
    assert result["blocks"]
    for item, block in zip(generated, result["blocks"]):
        hour, minute = map(int, item["start"].split(":"))
        assert block["startHour"] == pytest.approx(hour + minute / 60)
    for day in range(7):
        rows = sorted([b for b in result["blocks"] if b["day"] == day], key=lambda b: b["startHour"])
        assert all(a["startHour"] + a["duration"] <= b["startHour"] + 1e-9 for a, b in zip(rows, rows[1:]))
    assert all(b["day"] != 0 or b["startHour"] + b["duration"] <= 8.5 or b["startHour"] >= 9.5 for b in result["blocks"])


def _test_block(count=20, topic="مرور مباحث"):
    return {"task_type": "test", "subject": "شیمی", "topic": topic, "count": count, "description": "تمرین"}


def test_processed_ocr_alone_restores_numbered_practice_without_raw_pdfs(db, tmp_path):
    pages = tmp_path / "ocr" / "شیمی 3 خیلی سبز" / "pages"
    pages.mkdir(parents=True)
    record = {"page": 18, "data": {"lesson_title": "تعادل", "questions": [
        {"number": n, "text": "سوال", "options": ["الف", "ب", "ج", "د"]}
        for n in range(30, 80)]}}
    (pages / "page_0018.json").write_text(json.dumps(record), encoding="utf-8")
    blocks = [_test_block(20, "تعادل")]
    resources.assign_test_resources(db, {"grade": "دوازدهم"}, blocks, [])
    assert blocks[0]["resource"] == "شیمی 3 خیلی سبز"
    assert (blocks[0]["question_start"], blocks[0]["question_end"], blocks[0]["count"]) == (30, 49, 20)
    assert "تست‌های ۳۰ تا ۴۹" in blocks[0]["title"]
    assert resources.available_books(db, {"grade": "دهم"}) == []
    week = adaptive.build_week(db, 1, {"grade": "دوازدهم"}, 4, date(2099, 4, 4), [], now=datetime(2099, 4, 3))
    practice = [b for b in week["blocks"] if b.get("resource") == "شیمی 3 خیلی سبز" and b.get("question_start")]
    assert practice
    assert all(b["type"] == "test" and b["count"] == b["question_end"] - b["question_start"] + 1 for b in practice)


def test_processed_book_with_pdf_suffix_and_joined_grade_name(db, tmp_path):
    pages = tmp_path / "ocr" / "شیمی3خیلی سبز.pdf" / "pages"
    pages.mkdir(parents=True)
    (pages / "page_0001.json").write_text(json.dumps({"page": 1, "questions": [
        {"number": 30, "text": "سوال", "options": ["الف", "ب"]}]}), encoding="utf-8")
    assert resources.available_books(db, {"grade": "دهم"}) == []
    books = resources.available_books(db, {"grade": "دوازدهم"})
    assert books[0]["ranges"][0]["q_from"] == 30


def test_processed_ocr_does_not_reintroduce_raw_books_excluded_by_track(db, tmp_path):
    pdf = tmp_path / "raw/test-books/riazi/10/فیزیک خیلی سبز.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.touch()
    pages = tmp_path / "ocr" / pdf.stem / "pages"
    pages.mkdir(parents=True)
    (pages / "page_0001.json").write_text(json.dumps({"page": 1, "questions": [
        {"number": 30, "text": "سوال", "options": ["الف", "ب"]}]}), encoding="utf-8")
    assert resources.available_books(db, {"grade": "دهم", "major": "تجربی"}) == []


def test_processed_ocr_books_respect_science_track_without_raw_pdfs(db, tmp_path):
    for track in ("ریاضی", "تجربی"):
        pages = tmp_path / "ocr" / f"فیزیک 1 {track} خیلی سبز" / "pages"
        pages.mkdir(parents=True)
        (pages / "page_0001.json").write_text(json.dumps({"page": 1, "questions": [
            {"number": 30, "text": "سوال", "options": ["الف", "ب"]}]}), encoding="utf-8")
    books = resources.available_books(db, {"major": "تجربی", "grade": "دهم"})
    assert [b["book"] for b in books] == ["فیزیک 1 تجربی خیلی سبز"]


def test_catalog_ranges_are_split_without_repeating_questions(db):
    db.add(BookCatalog(book_id="شیمی خیلی سبز", subject="شیمی", chapter="استوکیومتری",
                       question_range_start=30, question_range_end=110))
    db.commit()
    blocks = [_test_block() for _ in range(3)]
    books, warnings = resources.assign_test_resources(db, {}, blocks, [])
    assert books == ["شیمی خیلی سبز"] and not warnings
    assert [(b["question_start"], b["question_end"]) for b in blocks] == [(30, 49), (50, 69), (70, 89)]
    assert blocks[0]["title"].startswith("تست‌های ۳۰ تا ۴۹ کتاب شیمی خیلی سبز")


def test_ocr_ranges_never_bridge_missing_question_numbers(db, tmp_path):
    pdf = tmp_path / "raw/test-books/Common/12/شیمی 3 خیلی سبز.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.touch()
    pages = tmp_path / "ocr" / pdf.stem / "pages"
    pages.mkdir(parents=True)
    data = {"page": 18, "data": {"lesson_title": "استوکیومتری", "questions": [
        {"number": number, "text": "سوال", "options": ["الف", "ب", "ج", "د"]}
        for number in [30, 31, 32, 35, 36]
    ]}}
    (pages / "page_0018.json").write_text(json.dumps(data), encoding="utf-8")
    blocks = [_test_block(20, "استوکیومتری") for _ in range(2)]
    books, warnings = resources.assign_test_resources(db, {"grade": "دوازدهم"}, blocks, [])
    assert not warnings
    assert [(b["question_start"], b["question_end"]) for b in blocks] == [(30, 32), (35, 36)]
    assert [b["count"] for b in blocks] == [3, 2]
    assert blocks[0]["page_start"] == 18
    assert books == [pdf.name]


def test_book_selection_excludes_other_tracks_and_future_grades(db, tmp_path):
    for path in ["riazi/10/فیزیک 1 ریاضی.pdf", "tajrobi/10/فیزیک 1 تجربی.pdf", "Common/12/شیمی 3.pdf"]:
        pdf = tmp_path / "raw/test-books" / path
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.touch()
    rows = resources._raw_books({"major": "تجربی", "grade": "دهم"})
    assert [row["book"] for row in rows] == ["فیزیک 1 تجربی.pdf"]


def test_split_ranges_show_only_the_pages_for_the_assigned_questions(db, tmp_path):
    pdf = tmp_path / "raw/test-books/Common/12/شیمی 3 خیلی سبز.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.touch()
    pages = tmp_path / "ocr" / pdf.stem / "pages"
    pages.mkdir(parents=True)
    for page, start in ((18, 30), (19, 40)):
        data = {"page": page, "data": {"lesson_title": "تعادل", "questions": [
            {"number": number, "text": "سوال", "options": ["الف", "ب", "ج", "د"]}
            for number in range(start, start + 10)
        ]}}
        (pages / f"page_{page:04d}.json").write_text(json.dumps(data), encoding="utf-8")
    blocks = [_test_block(10, "تعادل") for _ in range(2)]
    resources.assign_test_resources(db, {}, blocks, [])
    assert [(block["page_start"], block["page_end"]) for block in blocks] == [(18, 18), (19, 19)]
    assert "صفحه ۱۸ تا ۱۸" in blocks[0]["title"]


def test_completed_assignments_are_retained_and_scoped_to_student(db):
    db.add(BookCatalog(book_id="شیمی خیلی سبز", subject="شیمی", question_range_start=30, question_range_end=1000))
    db.commit()
    week = date(2099, 4, 4)
    first = adaptive.build_week(db, 1, {}, 4, week, [], now=datetime(2099, 4, 3))
    block = next(b for b in first["blocks"] if b.get("resource"))
    row = db.query(TaskProgress).filter(TaskProgress.student_id == 1, TaskProgress.client_ref.endswith(block["id"])).one()
    save_progress(ProgressIn(client_ref=row.client_ref, source_ref=row.source_ref, date=row.date,
        subject=row.subject, topic=row.topic, task_type="test", planned_minutes=row.planned_minutes,
        actual_minutes=row.planned_minutes, status="completed"), SimpleNamespace(id=1), db)
    db.expire_all()
    completed = db.get(TaskProgress, (1, row.client_ref))
    assert completed.resource == "شیمی خیلی سبز" and completed.question_start == 30
    later = adaptive.build_week(db, 1, {}, 4, week, [], now=datetime(2099, 4, 3))
    assert all(b.get("question_start", 1001) > block["question_end"] for b in later["blocks"] if b.get("resource"))
    other = adaptive.build_week(db, 2, {}, 4, week, [], now=datetime(2099, 4, 3))
    assert next(b for b in other["blocks"] if b.get("resource"))["question_start"] == 30


def test_unrecorded_ranges_name_the_book_without_inventing_numbers(db, tmp_path):
    pdf = tmp_path / "raw/test-books/Common/12/شیمی خیلی سبز.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.touch()
    blocks = [_test_block(topic="تعادل")]
    books, warnings = resources.assign_test_resources(db, {}, blocks, [])
    assert books == [pdf.name] and warnings
    assert "شیمی خیلی سبز" in blocks[0]["title"]
    assert "question_start" not in blocks[0]


def test_chat_updates_cannot_overlap_retained_plan_or_classes():
    block = {"day": 0, "startHour": 13.5, "duration": 1.5, "title": "ریاضی", "type": "study"}
    proposed = {**block, "startHour": 14.5, "title": "شیمی"}
    assert not _chat_plan_update_is_safe({"blocks": [proposed]}, {"blocks": [block]}, {})
    assert _chat_plan_update_is_safe({"removed": [block], "blocks": [proposed]}, {"blocks": [block]}, {})
    assert not _chat_plan_update_is_safe({"blocks": [proposed]}, {"statics": [block]}, {})
