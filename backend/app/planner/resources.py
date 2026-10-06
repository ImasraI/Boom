"""Assign practice from real catalogue ranges and promoted OCR, without an LLM."""
import json
import re
from functools import lru_cache
from pathlib import Path

from app.auth.database import BookCatalog
from app.config import get_settings

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_SUBJECTS = {
    "شیمی": ("شیمی", "shimi", "chemistry"),
    "فیزیک": ("فیزیک", "physics"),
    "ریاضی": ("ریاضی", "حسابان", "هندسه", "گسسته", "آمار", "riazi", "math", "hendese"),
    "زیست": ("زیست", "zist", "biology"),
    "عربی": ("عربی", "arabi"), "ادبیات": ("ادبیات", "adabiat"),
    "تاریخ": ("تاریخ",), "جغرافیا": ("جغرافیا",), "فلسفه": ("فلسفه",),
    "منطق": ("منطق",), "اقتصاد": ("اقتصاد",), "جامعه شناسی": ("جامعه شناسی",),
    "زمین شناسی": ("زمین شناسی",),
}


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").translate(_DIGITS).replace("ي", "ی")
                  .replace("ك", "ک").replace("\u200c", " ").lower()).strip()


def _subject(value):
    value = _norm(value)
    return next((name for name, aliases in _SUBJECTS.items()
                 if any(alias in value for alias in aliases)), value)


def _grade(student):
    text = _norm(student.get("grade"))
    return next((number for number, word in ((12, "دوازدهم"), (11, "یازدهم"), (10, "دهم"))
                 if word in text or str(number) in text), 12)


def _raw_books(student):
    root = Path(get_settings().RAW_DIR) / "test-books"
    major = _norm(student.get("major"))
    branch = "tajrobi" if "تجربی" in major else "ensani" if "انسانی" in major else "riazi"
    books = []
    for pdf in sorted(root.rglob("*.pdf")):
        parts = pdf.relative_to(root).parts
        # Common books belong to both science tracks; branch-specific books
        # must match, even when their filenames contain the same subject.
        if any(p in ("riazi", "tajrobi", "ensani") and p != branch for p in parts):
            continue
        if "تجربی" in pdf.stem and branch != "tajrobi":
            continue
        if "ریاضی" in pdf.stem and "فیزیک" in pdf.stem and branch != "riazi":
            continue
        grade = next((int(p) for p in parts if p in ("10", "11", "12", "33")), 33)
        if grade != 33 and grade > _grade(student):
            continue
        books.append({"book": pdf.name, "subject": _subject(pdf.stem), "grade": grade, "ranges": []})
    return books


@lru_cache(maxsize=64)
def _read_question_runs(signature):
    """Only consecutive printed numbers form a range; never bridge OCR gaps."""
    runs = []
    for filename, _mtime, _size in signature:
        try:
            record = json.loads(Path(filename).read_text(encoding="utf-8"))
            if "error" in record:
                continue
            data = record.get("data", record)
            lesson = str(data.get("lesson_title") or "")
            if "پاسخ" in _norm(lesson) or "کلید" in _norm(lesson):
                continue
            page = int(record.get("page") or Path(filename).stem.split("_")[-1])
            for question in data.get("questions") or []:
                if not isinstance(question, dict):
                    continue
                if not question.get("text") or len(question.get("options") or []) < 2:
                    continue
                raw_number = _norm(question.get("number", question.get("question_number")))
                if not raw_number.isdigit():
                    continue
                number = int(raw_number)
                if number < 1:
                    continue
                previous = runs[-1] if runs else None
                if previous and number == previous["q_to"] + 1 and _norm(lesson) == _norm(previous["topic"]):
                    previous["q_to"] = number
                    previous["page_to"] = page
                    previous["question_pages"].append((number, page))
                else:
                    runs.append({"q_from": number, "q_to": number, "topic": lesson,
                                 "page_from": page, "page_to": page, "question_pages": [(number, page)]})
        except (OSError, ValueError, TypeError, AttributeError, IndexError):
            continue
    return runs


def _ocr_ranges(book):
    # Pending OCR has not been promoted and is intentionally not a source.
    stem = Path(book).stem.strip().rstrip(" .")
    root = Path(get_settings().OCR_DIR)
    directory = root / stem / "pages"
    if not directory.exists():
        directory = root / (stem + ".pdf") / "pages"
    signature = []
    for path in sorted(directory.glob("page_*.json")):
        try:
            stat = path.stat()
            signature.append((str(path.resolve()), stat.st_mtime_ns, stat.st_size))
        except OSError:
            continue
    return [dict(row) for row in _read_question_runs(tuple(signature))]


def _processed_books(student):
    """Discover promoted question OCR without requiring raw PDFs on the VM.

    Shared OCR is corpus data; private uploads stay scoped in _indexed_ranges.
    Plain OCR prose alone is not evidence of printed question numbers.
    """
    root = Path(get_settings().OCR_DIR)
    major = _norm(student.get("major"))
    branch = "tajrobi" if "تجربی" in major else "ensani" if "انسانی" in major else "riazi"
    books, seen = [], set()
    for directory in sorted(root.iterdir()) if root.exists() else []:
        if not directory.is_dir():
            continue
        name = directory.name.removesuffix(".pdf").strip().rstrip(" .")
        normalized = _norm(name)
        if name in seen or any(word in normalized for word in ("پاسخنامه", "کلید", "mock", "آزمون آزمایشی")):
            continue
        subject = _subject(name)
        if subject not in _SUBJECTS:
            continue
        if "تجربی" in normalized and branch != "tajrobi":
            continue
        if "فیزیک" in normalized and "ریاضی" in normalized and branch != "riazi":
            continue
        match = re.search(r"(?:شیمی|فیزیک|زیست|ریاضی|حسابان|هندسه)\s*([123])(?=\D|$)", normalized)
        grade = {1: 10, 2: 11, 3: 12}[int(match[1])] if match else 33
        if grade != 33 and grade > _grade(student):
            continue
        ranges = _ocr_ranges(name)
        if not ranges:
            continue
        seen.add(name)
        books.append({"book": name, "subject": subject, "grade": grade, "ranges": ranges})
    return books


def _topic_score(topic, source_topic):
    topic = _norm(topic)
    if not topic or topic == "مرور مباحث":
        return 1
    words = {word for word in topic.replace("،", " ").split()
             if len(word) > 2 and word not in ("مرور", "مباحث", "فصل", "بخش")}
    source = _norm(source_topic)
    return sum(word in source for word in words)


def _indexed_ranges(user_id):
    """Read RAG question metadata, scoped to the student and shared corpus.

    No embedding/LLM request is needed, and only individually indexed
    question numbers may form a range.
    """
    settings = get_settings()
    directory = getattr(settings, "CHROMA_DIR", None)
    if user_id is None or not directory or not Path(directory).exists():
        return {}
    try:
        from app.rag.vector_store import get_question_vector_store
        collection = get_question_vector_store().collection
        shared = getattr(settings, "DEMO_USER_ID", 1)
        where = {"$and": [{"user_id": {"$in": list({user_id, shared})}}, {"kind": "question"}]}
        records = []
        for offset in range(0, collection.count(), 1000):
            batch = collection.get(where=where, limit=1000, offset=offset, include=["metadatas"])
            metas = batch.get("metadatas") or []
            records.extend(metas)
            if len(metas) < 1000:
                break
        groups = {}
        for meta in records:
            number = _norm(meta.get("question_number"))
            page = meta.get("page")
            if not number.isdigit() or int(number) < 1 or not isinstance(page, int) or page < 1:
                continue
            book, topic = str(meta.get("book") or meta.get("document_name") or ""), str(meta.get("lesson_title") or "")
            if not book or "پاسخ" in _norm(topic):
                continue
            groups.setdefault((book, topic), set()).add((page, int(number)))
        result = {}
        for (book, topic), questions in groups.items():
            runs = result.setdefault(Path(book).stem.strip(), [])
            previous = None
            for page, number in sorted(questions):
                if previous and previous["q_to"] + 1 == number:
                    previous["q_to"] = number
                    previous["page_to"] = page
                    previous["question_pages"].append((number, page))
                else:
                    previous = {"q_from": number, "q_to": number, "page_from": page, "page_to": page,
                                "topic": topic, "question_pages": [(number, page)]}
                    runs.append(previous)
        return result
    except Exception:
        # The promoted local OCR remains usable when Chroma is unavailable.
        return {}


def available_books(db, student, user_id=None):
    books = _raw_books(student)
    by_name = {row["book"]: row for row in books}
    by_name.update({Path(row["book"]).stem.strip(): row for row in books})
    known_pdfs = {pdf.name for pdf in (Path(get_settings().RAW_DIR) / "test-books").rglob("*.pdf")}
    known_stems = {Path(name).stem.strip() for name in known_pdfs}
    for row in db.query(BookCatalog).order_by(BookCatalog.book_id).all():
        entry = by_name.get(row.book_id)
        if entry is None:
            if row.book_id in known_pdfs:
                continue  # Known but ineligible branch/grade; do not re-add it.
            entry = {"book": row.book_id, "subject": _subject(row.subject), "grade": 33, "ranges": []}
            books.append(entry)
            by_name[row.book_id] = entry
        start, end = row.question_range_start, row.question_range_end
        if start and end and 0 < start <= end:
            entry["ranges"].append({"q_from": start, "q_to": end,
                                    "topic": "، ".join(filter(None, (row.chapter, row.section))),
                                    "page_from": None, "page_to": None})
    for entry in books:
        if not entry["ranges"]:
            entry["ranges"] = _ocr_ranges(entry["book"])
    for entry in _processed_books(student):
        if entry["book"] not in by_name and entry["book"] not in known_stems:
            books.append(entry)
            by_name[entry["book"]] = entry
    indexed = _indexed_ranges(user_id)
    for entry in books:
        extra = indexed.get(Path(entry["book"]).stem.strip(), [])
        signatures = {(r["q_from"], r["q_to"], r["page_from"], r["page_to"], r["topic"]) for r in entry["ranges"]}
        entry["ranges"].extend(r for r in extra if (r["q_from"], r["q_to"], r["page_from"], r["page_to"], r["topic"]) not in signatures)
    for name, ranges in indexed.items():
        # A student's indexed upload need not be in the shared raw directory.
        # Never reintroduce a shared PDF excluded for its track/grade above.
        if name not in known_stems and name not in by_name:
            subject = _subject(name)
            if subject in _SUBJECTS:
                books.append({"book": name, "subject": subject, "grade": 33, "ranges": ranges})
    return books


def assign_test_resources(db, student, blocks, progress, *, books=None, reserved=None):
    books = books if books is not None else available_books(db, student)

    used = {}
    for row in progress:
        if row.status == "completed" and row.resource and row.question_start and row.question_end:
            used.setdefault(row.resource, []).append((row.question_start, row.question_end, row.page_start, row.page_end))
    for block in reserved or []:
        if block.get("resource") and block.get("question_start") and block.get("question_end"):
            used.setdefault(block["resource"], []).append((block["question_start"], block["question_end"],
                                                          block.get("page_start"), block.get("page_end")))
    sources, warnings = set(), set()
    for block in blocks:
        if block["task_type"] != "test" or block["subject"] == "آزمون":
            continue
        options = [entry for entry in books if entry["subject"] == _subject(block["subject"])]
        if not options:
            warnings.add(f"کتاب تست برای {block['subject']} در منابع ثبت نشده است.")
            continue
        choices = []
        wanted = max(1, int(block.get("count") or 20))
        for entry in options:
            for item in entry["ranges"]:
                relevance = _topic_score(block["topic"], item["topic"])
                if not relevance:
                    continue
                start = item["q_from"]
                occupied = sorted(used.get(entry["book"], []))
                # Completed questions and earlier blocks reserve their ranges.
                # A page span distinguishes books that restart numbers by chapter.
                for lo, hi, page_lo, page_hi in occupied:
                    if item["page_from"] and page_lo and page_hi and (item["page_to"] < page_lo or page_hi < item["page_from"]):
                        continue
                    if hi < start or lo > item["q_to"]:
                        continue
                    if lo > start:
                        break
                    start = max(start, hi + 1)
                end = min(item["q_to"], start + wanted - 1)
                for lo, hi, page_lo, page_hi in occupied:
                    if item["page_from"] and page_lo and page_hi and (item["page_to"] < page_lo or page_hi < item["page_from"]):
                        continue
                    if start < lo <= end:
                        end = lo - 1
                if end < start:
                    continue
                grade_score = 2 if entry["grade"] == _grade(student) else 1 if entry["grade"] == 33 else 0
                choices.append(((relevance, grade_score, end - start + 1), entry, item, start, end))
        if choices:
            _, entry, item, start, end = max(choices, key=lambda choice: choice[0])
            pages = [page for number, page in item.get("question_pages", []) if start <= number <= end]
            page_from = min(pages) if pages else item["page_from"]
            page_to = max(pages) if pages else item["page_to"]
            block.update(resource=entry["book"], question_start=start, question_end=end,
                         page_start=page_from, page_end=page_to, count=end - start + 1)
            title = f"تست‌های {start} تا {end} کتاب {Path(entry['book']).stem.strip()}"
            if item["topic"]:
                title += f" — {item['topic']}"
            if page_from:
                title += f"، صفحه {page_from} تا {page_to}"
            block["title"] = title.translate(_FA)
            used.setdefault(entry["book"], []).append((start, end, page_from, page_to))
        else:
            entry = max(options, key=lambda row: (bool(row["ranges"]), row["grade"] == _grade(student), row["grade"] == 33))
            block["resource"] = entry["book"]
            block["title"] = f"{wanted} تست {block['subject']} از کتاب {Path(entry['book']).stem.strip()}: {block['topic']}".translate(_FA)
            message = f"شماره تست‌های {block['subject']} برای این مبحث در منابع ثبت نشده یا قبلاً تخصیص داده شده است."
            warnings.add(message)
            block["description"] += "؛ " + message
        sources.add(block["resource"])
    return sorted(sources), sorted(warnings)
