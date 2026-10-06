"""The displayed weekly plan must retain valid times and concrete practice sources."""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.auth.database import Base, BookCatalog, TaskProgress, User, StudentProfile, Assessment
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


def _write_questions(directory, page, questions, topic=""):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"page_{page:04d}.json").write_text(json.dumps({"page": page,
        "data": {"lesson_title": topic, "questions": questions}}), encoding="utf-8")


def _question(number, text="سوال معتبر"):
    return {"number": number, "text": text, "options": ["گزینه اول", "گزینه دوم", "گزینه سوم", "گزینه چهارم"]}


def test_empty_legacy_directory_does_not_hide_populated_pdf_ocr(db, tmp_path):
    (tmp_path / "ocr/شیمی 3 خیلی سبز/pages").mkdir(parents=True)
    _write_questions(tmp_path / "ocr/شیمی 3 خیلی سبز.pdf/pages", 18, [_question(30), _question(31)], "تعادل")
    blocks = [_test_block(topic="تعادل")]
    _, warnings = resources.assign_test_resources(db, {"grade": "دوازدهم"}, blocks, [])
    assert not warnings
    assert (blocks[0]["question_start"], blocks[0]["question_end"]) == (30, 31)


def test_duplicate_ocr_layouts_do_not_repeat_a_printed_page(db, tmp_path):
    for directory in ("شیمی 3 خیلی سبز", "شیمی 3 خیلی سبز.pdf"):
        _write_questions(tmp_path / "ocr" / directory / "pages", 18, [_question(30), _question(31)], "تعادل")
    assert len(resources.available_books(db, {})[0]["ranges"]) == 1


def test_missing_lesson_heading_matches_only_actual_question_text(db, tmp_path):
    _write_questions(tmp_path / "ocr/شیمی 3 خیلی سبز/pages", 18,
        [_question(30, "تعادل شیمیایی را مشخص کنید"), _question(31, "ساختار اتم را مشخص کنید"),
         _question(32, "ثابت تعادل را محاسبه کنید"), _question(33, "تعادل واکنش چیست؟")])
    blocks = [_test_block(topic="تعادل") for _ in range(2)]
    _, warnings = resources.assign_test_resources(db, {}, blocks, [])
    assert not warnings
    assert [(b["question_start"], b["question_end"]) for b in blocks] == [(32, 33), (30, 30)]


def test_placeholder_choice_labels_are_not_usable_book_questions(db, tmp_path):
    invalid = {"number": 30, "text": "کلاس آنلاین", "options": ["(A)", "(B)", "(C)", "(D)"]}
    _write_questions(tmp_path / "ocr/شیمی 3 خیلی سبز/pages", 18, [invalid, _question(31)], "تعادل")
    blocks = [_test_block(topic="تعادل")]
    resources.assign_test_resources(db, {}, blocks, [])
    assert (blocks[0]["question_start"], blocks[0]["question_end"]) == (31, 31)


def test_generic_ocr_subject_heading_does_not_displace_real_chapter(db, tmp_path):
    directory = tmp_path / "ocr/ریاضی 1 خیلی سبز/pages"
    _write_questions(directory, 1, [_question(1)], "ریاضی")
    _write_questions(directory, 18, [_question(n) for n in range(30, 200)], "تابع")
    result = adaptive.build_week(db, 1, {}, 4, date(2099, 4, 4), [], now=datetime(2099, 4, 3))
    math = [b for b in result["blocks"] if b["subject"] == "ریاضی"]
    assert math and all(b["topic"] == "تابع" for b in math)
    assert any(b.get("question_start") for b in math)
    assert all("ریاضی 1 خیلی سبز" in b["description"] for b in math)


def test_saved_exam_selection_is_loaded_and_empty_provisioned_row_keeps_request(db):
    db.add(StudentProfile(user_id=1, version=1, test_exams=json.dumps(["ماز"]), exam_year="۱۴۰۵"))
    db.add(StudentProfile(user_id=2, version=0))
    db.commit()
    assert adaptive.student_state(db, 1, {"testExams": ["سنجش"]})["testExams"] == ["ماز"]
    assert adaptive.student_state(db, 1)["examYear"] == "۱۴۰۵"
    assert adaptive.student_state(db, 2, {"testExams": ["سنجش"]})["testExams"] == ["سنجش"]


def test_registered_mock_topic_can_find_questions_without_a_heading(db, tmp_path):
    week = date(2099, 4, 4)
    db.add(Assessment(student_id=1, title="آزمون بعدی", date=week + timedelta(days=6),
        results=json.dumps({"subjects": [{"name": "شیمی", "topics": ["تعادل"]}]})))
    db.commit()
    _write_questions(tmp_path / "ocr/شیمی 3 خیلی سبز/pages", 18,
        [_question(n, "تعادل واکنش را مشخص کنید") for n in range(30, 300)])
    result = adaptive.build_week(db, 1, {}, 4, week, [], now=datetime(2099, 4, 3))
    practice = [b for b in result["blocks"] if b.get("question_start")]
    assert practice and all(b["topic"] == "تعادل" for b in practice)
    assert all("آزمون ثبت‌شده" in b["description"] for b in practice)


def test_missing_topic_and_exhausted_ranges_have_different_warnings(db):
    db.add(BookCatalog(book_id="شیمی خیلی سبز", subject="شیمی", chapter="تعادل",
        question_range_start=30, question_range_end=31))
    db.commit()
    blocks = [_test_block(topic="تعادل"), _test_block(topic="تعادل"), _test_block(topic="ساختار اتم")]
    _, warnings = resources.assign_test_resources(db, {}, blocks, [])
    assert any("تست جدید باقی نمانده" in w for w in warnings)
    assert any("در دادهٔ OCR پیدا نشد" in w for w in warnings)


def test_indexed_question_text_is_scoped_and_placeholder_chunks_are_excluded(db, tmp_path, monkeypatch):
    from app.rag import vector_store
    from app.rag.question_chunks import build_chunks_for_page
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(
        CHROMA_DIR=str(chroma), DEMO_USER_ID=1))
    records = build_chunks_for_page("شیمی 3 خیلی سبز", 18, {"questions": [
        _question(30, "تعادل واکنش چیست؟"),
        {"number": 31, "text": "متن خراب", "options": ["(A)", "(B)", "(C)", "(D)"]}]})
    class Collection:
        def count(self): return len(records)
        def get(self, **kwargs):
            assert kwargs["where"]["$and"][0]["user_id"]["$in"] == [1, 2]
            assert "documents" in kwargs["include"]
            return {"metadatas": [r["metadata"] for r in records], "documents": [r["text"] for r in records]}
    monkeypatch.setattr(vector_store, "get_question_vector_store", lambda: SimpleNamespace(collection=Collection()))
    runs = resources._indexed_ranges(2)["شیمی 3 خیلی سبز"]
    assert [(r["q_from"], r["q_to"]) for r in runs] == [(30, 30)]
    assert resources._matching_runs("تعادل", runs[0])[0][1]["q_from"] == 30
