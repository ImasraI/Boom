import json
import re
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, List, Optional, cast
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rag.pipeline import answer_question
from app.rag.embeddings import get_embedding_model
from app.rag.hybrid_search import get_hybrid_search
from app.rag.llm import get_llm_client, get_vision_llm_client
from app.auth.database import Assessment
from app.config import get_settings
from app.schemas import ChatMessage
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/boom", tags=["boom-ai"])

logger = get_logger(__name__)

_GRADE_LABELS = {
    "10": "پایه دهم",
    "11": "پایه یازدهم",
    "12": "پایه دوازدهم",
    "33": "جامع (پایه‌های دهم تا دوازدهم)",
}

_SOURCE_TYPES = {
    "plans": "برنامه آزمون",
    "test-books": "کتاب تست",
    "ministerial-books": "کتاب درسی وزارت",
    "custom-sources": "منبع اختصاصی",
}

_SUBJECT_LABELS = {
    "physics": "فیزیک",
    "hendese": "هندسه",
    "shimi": "شیمی",
    "riazi": "ریاضی",
    "zist": "زیست",
    "arabi": "عربی",
    "adabiat": "ادبیات",
    "dini": "دینی",
}


_GRADE_KEYS = {
    "10": "10", "پایه دهم": "10", "دهم": "10",
    "11": "11", "پایه یازدهم": "11", "یازدهم": "11",
    "12": "12", "پایه دوازدهم": "12", "دوازدهم": "12",
    "33": "33", "جامع": "33",
}


def _book_catalog_rows() -> List[dict]:
    """[(name, grade, subject_label, kind_label)] for every raw PDF."""
    try:
        from app.rag.ingest_raw import list_raw_pdfs
    except Exception:
        return []
    rows = []
    for pdf in list_raw_pdfs():
        parts = []
        parent = pdf.parent
        while parent.name != "raw" and parent != parent.parent:
            parts.append(parent.name)
            parent = parent.parent
        parts.reverse()
        kind = parts[0] if parts else ""
        grade = next((p for p in parts if p in _GRADE_LABELS), "")
        subject = next(
            (p for p in reversed(parts)
             if p not in ("test-books", "ministerial-books", "custom-sources", "plans")
             and p not in _GRADE_LABELS and p != kind),
            "",
        )
        rows.append({
            "name": pdf.name,
            "kind": kind,
            "grade": grade,
            "subject": _SUBJECT_LABELS.get(subject, subject),
        })
    return rows


def book_catalog() -> List[str]:
    """Human-readable list of the reference sources on disk (no ingestion
    required), e.g. ``فیزیک ۱ خیلی سبز.pdf (دهم، فیزیک، کتاب تست)``.

    The model needs these names to ground test blocks in real books instead
    of asking the student which book to use.
    """
    entries = []
    seen = set()
    for row in _book_catalog_rows():
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        grade = row["grade"] and _GRADE_LABELS.get(row["grade"], "")
        kind_label = _SOURCE_TYPES.get(row["kind"], "منبع")
        tags = "، ".join(x for x in [grade, row["subject"] or None, kind_label] if x)
        entries.append(f"{row['name']} ({tags})")
    return entries


def _pick_main_book(student: Optional[dict]) -> str:
    """Best test-book filename from the catalog for this student's branch,
    grade and weak subjects; "" if the catalog has no test books."""
    student = student or {}
    major = (student.get("major") or "").lower()
    grade_txt = " ".join([
        str(student.get("grade") or ""),
        str(student.get("gradeName") or ""),
    ])
    weak = " ".join(student.get("weakSubjects") or student.get("weak_subjects") or [])
    rows = [r for r in _book_catalog_rows() if r["kind"] == "test-books"]
    if not rows:
        return ""

    def _score(row: dict) -> int:
        s = 0
        if any(g in grade_txt for g in ("دهم", "10")) and row["grade"] == "10":
            s += 2
        if any(g in grade_txt for g in ("یازدهم", "11")) and row["grade"] == "11":
            s += 2
        if any(g in grade_txt for g in ("دوازدهم", "12")) and row["grade"] == "12":
            s += 2
        if "جامع" in grade_txt and row["grade"] == "33":
            s += 2
        subj = row["subject"]
        if subj and weak and any(w in subj or subj in w for w in weak.split()):
            s += 3
        if major in ("ریاضی", "ریاضی فیزیک") and row["name"].lower().find("ریاضی") >= 0:
            s += 1
        if "تجربی" in major and subj in ("زیست",):
            s += 1
        return s

    best = max(rows, key=_score)
    return best["name"] if _score(best) else rows[0]["name"]

_J_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


class BoomChatRequest(BaseModel):
    question: str
    history: Optional[List[dict]] = None
    top_k: int = 5
    student: Optional[dict] = None
    schedule: Optional[dict] = None


class StudyPlanRequest(BaseModel):
    months: int = Field(default=6, ge=1, le=24)
    daily_hours: float = Field(default=4, ge=0.5, le=16)
    major: str = "ریاضی فیزیک"
    grade: str = "دوازدهم (سال کنکور)"
    target_rank: str = "زیر ۵٬۰۰۰"
    weak_subjects: List[str] = []
    strong_subjects: List[str] = []
    exam_date: Optional[str] = None
    notes: str = ""
    student: Optional[dict] = None
    schedule: Optional[dict] = None


class WeeklyPlanRequest(BaseModel):
    student: Optional[dict] = None
    daily_hours: float = Field(default=4, ge=0.5, le=16)
    week_start: Optional[str] = None
    statics: List[dict] = []
    schedule: Optional[dict] = None
    history: Optional[List[dict]] = None


_BLOCK_COLORS = {
    "class": "#5C8BA8",
    "study": "#e2c983",
    "test": "#9B7AAD",
    "break": "#97b094",
}

_BLOCK_TYPES = set(_BLOCK_COLORS)

_TYPE_MAP = {
    "class": "class",
    "کلاس": "class",
    "تدریس": "class",
    "study": "study",
    "مطالعه": "study",
    "یادگیری": "study",
    "خواندن": "study",
    "مرور": "study",
    "test": "test",
    "تست": "test",
    "آزمون": "test",
    "تمرین": "test",
    "break": "break",
    "استراحت": "break",
    "وقفه": "break",
}


def _student_context(student: Optional[dict]) -> str:
    if not student:
        return "اطلاعات پروفایل دانشآموز در دسترس نیست."
    return "\n".join(f"- {k}: {v}" for k, v in student.items())


def _history_context(history: Optional[List[dict]]) -> str:
    if not history:
        return "سابقه گفتگوی قبلی وجود ندارد."
    lines = ["سابقه گفتگوهای قبلی با دانش‌آموز (برای درک بهتر شرایط و پیشرفت):"]
    for msg in history[-16:]:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))[:500]
        if role == "user":
            lines.append(f"[کاربر]: {content}")
        elif role == "assistant":
            lines.append(f"[بوم]: {content}")
    return "\n".join(lines) if len(lines) > 1 else "سابقه گفتگوی قبلی وجود ندارد."


def get_user_profile() -> dict:
    """Retrieve the current user's profile data including completion/confidence
    per subject from the database."""
    from app.auth.database import SessionLocal, User
    from sqlalchemy import select
    db = SessionLocal()
    try:
        user = db.execute(select(User)).scalar_one_or_none()
        if not user:
            return {}
        return {"weak_subjects": [], "strong_subjects": []}
    finally:
        db.close()


def get_book_catalog(subject: str) -> List[dict]:
    """Return catalog entries for a given subject from the book_catalog table."""
    from app.auth.database import SessionLocal, BookCatalog
    from sqlalchemy import select
    db = SessionLocal()
    try:
        statement = select(BookCatalog).where(BookCatalog.subject == subject)
        rows = db.execute(statement).scalars().all()
        return [{"book_id": r.book_id, "chapter": r.chapter, "section": r.section,
                 "question_range_start": r.question_range_start, "question_range_end": r.question_range_end,
                 "difficulty_tier": r.difficulty_tier, "avg_seconds_per_question": r.avg_seconds_per_question}
                for r in rows]
    finally:
        db.close()


def get_recent_wrong_answers() -> List[dict]:
    """Return recent wrong-answer logs for feedback-based planning."""
    from app.auth.database import SessionLocal
    from sqlalchemy import select
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=30)
        statement = select(Assessment).where(Assessment.student_id == 1).where(
            Assessment.date >= since
        )
        rows = db.execute(statement).scalars().all()
        results = []
        for r in rows:
            try:
                res = r.results if isinstance(r.results, dict) else {}
                results.append({
                    "question_id": res.get("last_wrong_id"),
                    "subject": res.get("subject"),
                    "topic": res.get("topic"),
                    "date": str(r.date),
                })
            except Exception:
                continue
        return results
    finally:
        db.close()


def get_last_mock_results() -> Optional[dict]:
    """Return the most recent mock-exam results, replacing the static EXAM_RESULTS array."""
    from app.auth.database import SessionLocal
    from sqlalchemy import select
    from datetime import datetime
    db = SessionLocal()
    try:
        statement = select(Assessment).order_by(Assessment.date.desc())
        row = db.execute(statement).scalar_one_or_none()
        if not row:
            return None
        try:
            results = row.results if isinstance(row.results, dict) else {}
            return {
                "exam_date": str(row.date),
                "subject": results.get("subject"),
                "score": results.get("score"),
                "total": results.get("total"),
                "topics": results.get("topics", []),
            }
        except Exception:
            return {"exam_date": str(row.date), "subject": "نامشخص", "score": "0", "total": "0", "topics": []}
    finally:
        db.close()


def _parse_json_from_text(text: str):
    """Lenient JSON extraction: exact parse, then wrapped ```json``` or
    first {...} object, tolerating trailing commas."""
    if not text:
        return None
    candidates = [text]
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        candidates.append(m.group(1))
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            return json.loads(_fix_json_trailing(cand.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _fix_json_trailing(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _clamp_float(value, lo, hi, step=0.5):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo
    v = max(lo, min(hi, v))
    return round(v / step) * step


def _clamp_int(value, lo, hi, default=None):
    if isinstance(value, bool):
        return default if default is not None else lo
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return default if default is not None else lo
    return max(lo, min(hi, v))


def _normalize_block(raw: dict, idx: int) -> dict:
    day = _clamp_int(raw.get("day"), 0, 6, default=0)
    start = _clamp_float(raw.get("startHour"), 6.0, 23.5)
    duration = _clamp_float(raw.get("duration"), 0.5, min(6.0, 24.0 - start))
    title = str(raw.get("title") or "").strip() or "بلوک برنامه"
    btype_raw = str(raw.get("type") or "study").strip()
    btype = _TYPE_MAP.get(btype_raw, btype_raw if btype_raw in _BLOCK_TYPES else "study")
    count = raw.get("count")
    try:
        count = int(count) if count is not None else None
    except (TypeError, ValueError):
        count = None
    return {
        "id": f"gen-{idx}",
        "day": day,
        "startHour": start,
        "duration": duration,
        "title": title,
        "type": btype,
        "color": _BLOCK_COLORS[btype],
        "count": count,
    }


def _plan_blocks(data) -> List[dict]:
    if not isinstance(data, dict):
        return []
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        return []
    return [_normalize_block(b, i) for i, b in enumerate(blocks) if isinstance(b, dict)]


_DAY_LABELS = [
    "شنبه", "یکشنبه", "دوشنبه", "سهشنبه", "چهارشنبه", "پنجشنبه", "جمعه",
]


def _hours_overlap(a0, ad, b0, bd) -> bool:
    try:
        return float(a0) < float(b0) + float(bd) and float(b0) < float(a0) + float(ad)
    except (TypeError, ValueError):
        return False


def _static_weekday(s: dict) -> Optional[int]:
    day = s.get("day")
    if isinstance(day, int) and 0 <= day <= 6:
        return day
    try:
        if isinstance(day, (str, int)):
            day_i = int(day)
            if 0 <= day_i <= 6:
                return day_i
    except (TypeError, ValueError):
        pass
    date_s = s.get("date")
    if date_s:
        try:
            d = date.fromisoformat(str(date_s)[:10])
            return (d.weekday() + 2) % 7
        except ValueError:
            return None
    return None


def _occupied_slots(statics: Optional[List[dict]]) -> List[dict]:
    out: List[dict] = []
    for s in statics or []:
        if not isinstance(s, dict):
            continue
        day = _static_weekday(s)
        if day is None:
            continue
        try:
            start = float(s.get("startHour", 0))
            dur = float(s.get("duration", 1))
        except (TypeError, ValueError):
            continue
        out.append({
            "day": day,
            "startHour": start,
            "duration": max(0.5, dur),
            "title": str(s.get("title") or "بلاک ثابت"),
            "type": s.get("type") or "class",
        })
    return out


def _overlaps_occupied(day, start, dur, occupied: List[dict]) -> bool:
    for o in occupied:
        if int(o["day"]) != int(day):
            continue
        if _hours_overlap(start, dur, o["startHour"], o["duration"]):
            return True
    return False


def _find_free_start(day, duration, occupied: List[dict], preferred: float = 6.0):
    lo, hi = 6.0, 24.0
    hour = float(preferred)
    while hour + duration <= hi:
        if not _overlaps_occupied(day, hour, duration, occupied):
            return hour
        hour += 0.5
    hour = lo
    while hour < preferred and hour + duration <= hi:
        if not _overlaps_occupied(day, hour, duration, occupied):
            return hour
        hour += 0.5
    return None


def _occupied_prompt(occupied: List[dict]) -> str:
    if not occupied:
        return "هیچ بلوک ثابتی ثبت نشده است."
    lines = ["این ساعتها هر هفته اشغالاند (کلاس/بلاک ثابت). روی آنها هیچ بلوکی نگذار:"]
    for o in occupied:
        label = _DAY_LABELS[int(o["day"])]
        start = float(o["startHour"])
        end = start + float(o["duration"])
        lines.append(f"- {label}: {start:g} تا {end:g} «{o['title']}»")
    return "\n".join(lines)


PLAN_UPDATE_MARKER = "###UPDATE_PLAN###"


def _extract_plan_update(answer: str):
    """Pull the machine-readable plan-update section out of an LLM chat answer.

    Returns (clean_text_without_marker, update_or_None). The update is a dict
    {"blocks": [...], "removed": [...], "note": str} the frontend can apply to the current week.
    """
    if not answer or PLAN_UPDATE_MARKER not in answer:
        return answer, None
    idx = answer.find(PLAN_UPDATE_MARKER)
    clean = answer[:idx].rstrip()
    section = answer[idx + len(PLAN_UPDATE_MARKER):].strip()
    data = _parse_json_from_text(section)
    if not data:
        return clean, None
    blocks = _plan_blocks(data)
    # Also extract removed blocks (blocks to delete)
    removed_raw = data.get("removed") or data.get("deleted") or data.get("removed_blocks") or []
    removed_blocks = _plan_blocks({"blocks": removed_raw}) if isinstance(removed_raw, list) else []
    if not blocks and not removed_blocks:
        return clean, None
    return clean, {
        "blocks": blocks,
        "removed": removed_blocks,
        "note": str((data or {}).get("note") or ""),
    }


def _book_list(chunks: List[dict]) -> List[str]:
    seen = []
    for c in chunks:
        name = c.get("document_name")
        if name and name not in seen:
            seen.append(name)
    return seen


@router.post("/chat")
def boom_chat(request: BoomChatRequest):
    """Prototype chat endpoint for Boom's current frontend.

    It intentionally uses demo user 1 because Boom's current UI has a local
    demo login rather than a connected authentication flow. Production should
    replace this with get_current_user and the authenticated user's id.
    """
    settings = get_settings()
    history = [ChatMessage(**h) for h in (request.history or [])]
    result = answer_question(
        question=request.question,
        user_id=settings.DEMO_USER_ID,
        history=history,
        top_k=request.top_k,
        student=request.student,
        schedule=request.schedule,
    )
    if not result.get("answer"):
        result["answer"] = ("پاسخی از مدل زبانی دریافت نشد؛ احتمالاً مدل در این لحظه پاسخ مناسبی نداشت. "
                            "لطفاً چند لحظه بعد دوباره تلاش کنید.")
        return result

    # If the LLM decided to change the weekly plan, it embeds an
    # ###UPDATE_PLAN### JSON section.  Split it off the visible answer and
    # expose it as a first-class field so the frontend can apply it to the
    # user's schedule.
    clean, plan_update = _extract_plan_update(result["answer"])
    result["answer"] = clean
    if plan_update:
        result["plan_update"] = plan_update
    return result


@router.post("/study-plan")
def generate_study_plan(request: StudyPlanRequest):
    """Generate a multi-month Konkoor plan using RAG + the LLM.

    RAG grounds the plan in the indexed curriculum/resources, while the LLM
    turns the retrieved material and student constraints into a usable plan.
    """
    settings = get_settings()
    student = request.student or {}
    weak = request.weak_subjects or student.get("weakSubjects", []) or student.get("weak_subjects", [])
    strong = request.strong_subjects or student.get("strongSubjects", []) or student.get("strong_subjects", [])
    exam_year = student.get("examYear", "")
    tests = student.get("testExams", [])
    search_text = (
        f"برنامه مطالعاتی کنکور {request.major} {request.grade} سال {exam_year} برای {request.months} ماه، "
        f"هدف {request.target_rank}، روزانه {request.daily_hours} ساعت، "
        f"درس‌های ضعیف: {', '.join(weak) or 'نامشخص'}، درس‌های قوی: {', '.join(strong) or 'نامشخص'}، "
        f"آزمون‌های آزمایشی: {', '.join(tests) if isinstance(tests, list) else tests}"
    )
    embedder = get_embedding_model()
    search = get_hybrid_search()
    q = embedder.embed_query(search_text)
    chunks = search.search(
        query_text=search_text,
        query_embedding=q,
        user_id=settings.DEMO_USER_ID,
        top_k=8,
    )
    context = "\n\n".join(
        f"[منبع {i+1}] {c['document_name']}\n{c['content']}"
        for i, c in enumerate(chunks)
    )
    prompt = f"""تو «بوم» هستی؛ مربی هوشمند کنکور.
یک برنامه مطالعاتی واقع‌بینانه برای دانش‌آموز تولید کن.
برنامه باید از سطح ماهانه شروع شود و برای هر ماه هدف، مباحث، مرور و آزمون مشخص کند.
روزانه بیشتر از زمان اعلام‌شده برنامه‌ریزی نکن.
درس‌های ضعیف را با تکرار و تست بیشتر در اولویت قرار بده.
اگر منابع مرجع کافی نیستند، بر اساس دانش عمومی برنامه‌ریزی نکن و محدودیت را شفاف بگو.
پاسخ فارسی و ساختاریافته باشد.

اطلاعات دانش‌آموز:
{_student_context({**request.model_dump(exclude={"student"}), **student})}

متن‌های مرجع:
{context or 'منبع مرتبطی پیدا نشد.'}

خروجی را با این ساختار بده:
1. خلاصه استراتژی
2. ماه ۱ تا ماه {request.months}: برای هر ماه هدف، مباحث اصلی، تعداد روزهای تست/مرور و خروجی قابل اندازه‌گیری
3. الگوی هفتگی پیشنهادی
4. قوانین جبران عقب‌افتادگی
"""
    answer = get_llm_client().generate([{"role": "user", "content": prompt}], max_tokens=1800)
    if not answer:
        return {"plan": "مدل زبانی پاسخ نداد. تنظیماتprovider را بررسی کن.", "sources": chunks, "error": "llm_unavailable"}
    return {"plan": answer, "sources": chunks}


def _jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Gregorian -> Jalali (used to label weeks and to query the plan docs,
    whose mock dates are written in the Persian calendar)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    jy = 979 if gy > 1600 else 0
    gy -= 1600 if gy > 1600 else 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + (days // 31) if days < 186 else 7 + ((days - 186) // 30)
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


def _jalali_date_str(d: date) -> str:
    jy, jm, jd = _jalali(d.year, d.month, d.day)
    return f"{jd} {_J_MONTHS[jm - 1]} {jy}"


def _fa_digits(value) -> str:
    fa = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(fa[int(c)] if c.isdigit() else c for c in str(value))


def _week_mock_note(raw_summary: str, week_start: date, week_end: date) -> str:
    """Deterministically report which mock exam dates fall inside this week.

    Mock dates in the plan are written as `NUM month` with clean Arabic
    digits; scan the (NFKC-cleaned) plan text for them and compare against
    the week's Jalali range.  This gives the planner exact dates regardless
    of how well the schedule normalization preserves them.
    """
    months = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
    months_re = "|".join(months)
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    ws_j, we_j = _jalali(week_start.year, week_start.month, week_start.day), \
        _jalali(week_end.year, week_end.month, week_end.day)
    ws_d0 = (ws_j[1], ws_j[2])
    we_d0 = (we_j[1], we_j[2])

    found = []
    for day_s, month_s in re.findall(r"([۰-۹0-9]{1,2})\s*(%s)" % months_re, raw_summary):
        d = int(day_s.translate(digits))
        # skip page/chapter ranges like "۸۲ تا۶۹" never match a month, but
        # dates like "۱۶ مرداد" or "۲۷ شهریور" do; cross-check against week.
        if not 1 <= d <= 31:
            continue
        found.append((d, month_s))
    found = list(dict.fromkeys(found))

    in_week = []
    for d, mon in found:
        m_idx = months.index(mon) + 1
        if ws_d0 <= (m_idx, d) <= we_d0:
            in_week.append(f"{d} {mon}")
    if in_week:
        return (
            f"آزمون ماز در این هفته (شنبه {_jalali_date_str(week_start)} تا "
            f"جمعه {_jalali_date_str(week_end)}): {_fa_digits('، '.join(in_week))}. "
            f"کل هفته را طوری برنامه‌ریزی کن که دانش‌آموز برای مباحث همان آزمون آماده شود "
            f"و دقیقا در روز آزمون یک بلوک test با عنوان «آزمون آزمایشی ماز» قرار بده."
        )
    return (
        f"آزمون ماز در این هفته (شنبه {_jalali_date_str(week_start)} تا "
        f"جمعه {_jalali_date_str(week_end)}): برنامه‌ریزی نشده است."
    )


_MOCK_EXTRACT_PROMPT = """تو یک استخراج‌کننده دقیق از برنامه آزمون آزمایشی کنکور هستی.
این تصویر بخشی از برنامه آزمون‌های آزمایشی (مثلا برنامه ماز در تابستان) است. آن را با دقت بخوان و استخراج کن:
- تاریخ هر آزمون (روز و ماه شمسی)
- برای هر دفترچه و هر درس: نام درس، تعداد سوال، مباحث/فصل‌ها و بازه صفحه‌های کتاب اگر ذکر شده
- نوع آزمون (مثلا جمع‌بندی پایه یازدهم، تعیین سطح، پیش‌خوانی دوازدهم، جامع پایان تابستان)
خروجی را فقط به صورت متن فارسی سازمان‌یافته بنویس؛ برای هر درس یک خط با «-» شروع شود.
اگر صفحه‌ها درباره برنامه آزمون هفتگی نبودند، فقط عبارت «نامرتبط» را بنویس."""


def _clean_mock_page(text: str) -> str:
    """Collapse the messy whitespace that text-layer plan PDFs extract to.

    The PDF encodes Arabic letters with presentation-form glyphs; NFKC turns
    those back into standard Persian letters so the text reads normally.
    Rotated vertical English footer text (``M a z e E d u c...``) is dropped.
    """
    import unicodedata
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        alpha = sum(ch.isascii() and ch.isalpha() for ch in line)
        if alpha and alpha / max(len(line), 1) > 0.4:
            continue  # rotated vertical English footer
        lines.append(line)
    out = " ".join(lines)
    return re.sub(r"\s+", " ", out).strip()


def _extract_week_mock(user_id: int, week_start: date) -> Optional[dict]:
    """Find the plan/mock document and pull this week's mock context.

    Plan documents are normally text PDFs (e.g. the summer Maz schedule);
    their text is read directly through PyMuPDF — fast and faithful.  Only
    documents with no usable text layer fall back to a vision read of the
    most relevant indexed pages (cached by document + pages).
    """
    try:
        from app.config import get_settings
        from app.rag.ingest_raw import list_raw_pdfs, category_for_pdf

        settings = get_settings()
        plan_pdfs = [
            p for p in list_raw_pdfs()
            if category_for_pdf(p) == "plan"
        ]
        if not plan_pdfs:
            logger.info("Weekly mock: no `plan` documents for user %s.", user_id)
            return None

        doc_meta = {"document": "", "summary": "", "pages": []}
        for pdf in plan_pdfs:
            doc_meta["document"] = Path(pdf).name
            try:
                import fitz  # PyMuPDF
                with fitz.open(str(pdf)) as handle:
                    pages = []
                    for pno in range(handle.page_count):
                        page = cast(Any, handle[pno])
                        text = _clean_mock_page(page.get_text("text"))
                        if len(text) >= 150:
                            # Schedule tables carry dense digits; marketing
                            # pages are mostly prose.  Prefer digit-dense ones.
                            digits = len(re.findall(r"[۰-۹0-9]", text))
                            pages.append((pno + 1, digits, text))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Weekly mock: text read failed for %s: %s",
                               pdf.name, exc)
                continue

            # Highest-density schedule pages first, then fill to the cap.
            pages.sort(key=lambda it: (-it[1], it[0]))
            picked, total = [], 0
            for pno, _digits, text in pages:
                if len(picked) >= 3 or total >= 5200:
                    break
                picked.append((pno, text))
                total += len(text)
            picked.sort(key=lambda it: it[0])  # restore document order
            if picked:
                doc_meta["pages"] = [p for p, _ in picked]
                raw = "\n".join(t for _, t in picked)[:5200]
                week_end = week_start + timedelta(days=6)
                note = _week_mock_note(raw, week_start, week_end)
                norm = _normalize_mock_schedule(doc_meta["document"], raw)
                doc_meta["summary"] = f"{note}\n\n{norm}".strip()
                break  # first readable plan document is enough

        if not doc_meta["pages"]:
            # No text layer anywhere: fall back to the vision read of the
            # most relevant plan pages (cached, slow on the first call).
            return _extract_week_mock_vision(user_id, week_start)

        logger.info("Weekly mock: text plan '%s' pages %s (%.0f chars).",
                    doc_meta["document"], doc_meta["pages"], len(doc_meta["summary"]))
        return doc_meta
    except Exception as exc:  # noqa: BLE001 - never break plan generation
        logger.warning("Weekly mock extraction failed: %s", exc)
        return None


def _extract_week_mock_vision(user_id: int, week_start: date) -> Optional[dict]:
    """Vision fallback for image-based plan documents."""
    try:
        from app.rag.pipeline import _retrieve_image_hits

        week_end = week_start + timedelta(days=6)
        search = (
            f"برنامه آزمون آزمایشی هفتگی از {_jalali_date_str(week_start)} "
            f"تا {_jalali_date_str(week_end)} مباحث و سوالات هر درس و تاریخ آزمون"
        )
        hits = _retrieve_image_hits(search, user_id, 2, category="plan")
        if not hits:
            logger.info("Weekly mock: no indexed plan pages for %s.",
                        week_start.isoformat())
            return None

        keep = hits[:2]
        paths = [h["content"] for h in keep]
        cache_key = f"{keep[0]['document_name']}|{'-'.join(str(h['chunk_index'] + 1) for h in keep)}"
        summary = _mock_cache_read(cache_key)
        if summary:
            logger.info("Weekly mock: using cached vision extraction %s.", cache_key)
        else:
            labels = "\n".join(
                f"--- [تصویر {i + 1}] (سند: {h['document_name']}، صفحه {h['chunk_index'] + 1}) ---"
                for i, h in enumerate(keep)
            )
            messages = [
                {"role": "system", "content": _MOCK_EXTRACT_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"برنامه آزمون این هفته (از {week_start.isoformat()} تا {week_end.isoformat()}):\n"
                        f"تصاویر پیوست‌شده:\n{labels}"
                    ),
                },
            ]
            logger.info("Weekly mock: vision-extracting from '%s' pages %s ...",
                        keep[0]["document_name"], [h['chunk_index'] + 1 for h in keep])
            summary = get_vision_llm_client().generate(
                messages, images=paths, timeout=420.0
            )
            summary = (summary or "").strip()
            _mock_cache_write(cache_key, summary or "نامرتبط")
        return {
            "document": keep[0]["document_name"],
            "summary": summary,
            "pages": [h["chunk_index"] + 1 for h in keep],
        }
    except Exception as exc:  # noqa: BLE001 - never break plan generation
        logger.warning("Weekly mock vision extraction failed: %s", exc)
        return None


_MOCK_NORM_PROMPT = """تو یک استخراج‌کننده/خلاصه‌کننده دقیق برنامه آزمون‌های آزمایشی هستی.
متن زیر، متن خام و نامرتب (خروجی مستقیم لایه متن یک PDF) از «برنامه آزمون ماز در تابستان» ویژه دوازدهم ریاضی است؛ حروف ممکن است جابه‌جا یا درهم باشد.
از آن، برنامه آزمون‌ها را به صورت تمیز و ساختاریافته بازنویسی کن:
- برای هر تاریخ آزمون: تاریخ شمسی، نوع آزمون (تعیین سطح/جمع‌بندی پایه یازدهم/پیش‌خوانی دوازدهم/جامع پایان تابستان)، و اینکه از مباحث پایه دهم/یازدهم/دوازدهم است.
- برای هر آزمون و هر دفترچه (دفترچه اول/دوم/سوم): برای هر درس، نام درس، تعداد سوال، و مباحث/فصل‌ها و بازه صفحه‌های اعلام‌شده.
- فقط مواردی را بیاور که در متن هستند؛ برای موارد نامشخص «نامشخص» بنویس؛ هیچ چیز را از خودت اضافه نکن.
- خروجی فقط متن فارسی ساختاریافته؛ هر درس را با «-» شروع کن."""


def _normalize_mock_schedule(document: str, raw_summary: str) -> str:
    """Turn the noisy text-layer schedule into a clean structured summary.

    Normalizing is document-wide and expensive (~60-90s with the text LLM),
    so the result is cached per document; later weekly-plan calls reuse it.
    """
    norm = _mock_cache_read(f"norm2|{document}")
    if norm:
        logger.info("Weekly mock: using cached normalized schedule for %s.", document)
        return norm
    try:
        messages = [
            {"role": "system", "content": _MOCK_NORM_PROMPT},
            {"role": "user", "content": raw_summary},
        ]
        logger.info("Weekly mock: normalizing schedule text for %s ...", document)
        norm = get_llm_client().generate(messages, timeout=360.0)
        norm = (norm or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Weekly mock: schedule normalization failed, using raw: %s", exc)
        norm = ""
    if not norm:
        norm = raw_summary
    else:
        _mock_cache_write(f"norm2|{document}", norm)
    return norm[:5200]


_MOCK_CACHE_DIR = Path("data/cache")
_MOCK_CACHE_FILE = _MOCK_CACHE_DIR / "mock_extraction.json"
_mock_cache_lock = threading.Lock()


def _mock_cache_read(key: str) -> Optional[str]:
    """Return the cached mock summary for a (document, pages) key, or None."""
    try:
        with _mock_cache_lock:
            if not _MOCK_CACHE_FILE.exists():
                return None
            data = json.loads(_MOCK_CACHE_FILE.read_text("utf-8"))
        value = data.get(key)
        return str(value) if value else None
    except Exception:
        return None


def _mock_cache_write(key: str, summary: str) -> None:
    try:
        with _mock_cache_lock:
            _MOCK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            data = {}
            if _MOCK_CACHE_FILE.exists():
                try:
                    data = json.loads(_MOCK_CACHE_FILE.read_text("utf-8"))
                except ValueError:
                    data = {}
            data[key] = summary
            _MOCK_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mock extraction cache write failed: %s", exc)


def _default_week_plan(
    books: List[str],
    daily_hours: float,
    student: Optional[dict] = None,
    occupied: Optional[List[dict]] = None,
) -> List[dict]:
    """Deterministic standard week used when the LLM output is not parseable.

    Each day gets a reading/learning block, a book-grounded test block and a
    short review block, sized so totals never exceed the daily study hours.
    Occupied (static/class) slots are skipped.
    """
    occupied = occupied or []
    main_book = books[0] if books else "کتاب منبع کنکور"
    weak = (student or {}).get("weakSubjects") or (student or {}).get("weak_subjects") or []
    weak_line = f" (اولویت: {'، '.join(weak)})" if weak else ""
    study_h = max(0.5, float(daily_hours) if daily_hours else 4.0)

    read_dur = round(min(study_h * 0.5, 3.0) * 2) / 2
    test_dur = round(min(study_h * 0.25, 1.5) * 2) / 2
    review_dur = max(0.5, round((study_h - read_dur - test_dur) * 2) / 2)
    test_count = max(10, int(study_h * 4))

    blocks = []
    idx = 0
    for day in range(7):
        start = _find_free_start(day, read_dur, occupied, 6.0)
        if start is not None:
            blocks.append(_normalize_block({
                "day": day, "startHour": start, "duration": read_dur, "count": None,
                "title": f"مطالعه و یادگیری{weak_line}",
            }, idx))
            idx += 1
        start = _find_free_start(day, test_dur, occupied, 9.0)
        if start is not None:
            blocks.append(_normalize_block({
                "day": day, "startHour": start, "duration": test_dur, "count": test_count,
                "type": "test",
                "title": f"{test_count} تست از {main_book}",
            }, idx))
            idx += 1
        if review_dur >= 0.5:
            start = _find_free_start(day, review_dur, occupied, 16.0)
            if start is not None:
                blocks.append(_normalize_block({
                    "day": day, "startHour": start, "duration": review_dur, "count": None,
                    "title": "مرور و جمعبندی",
                }, idx))
                idx += 1
    return blocks


def _complete_week_plan(
    blocks: List[dict],
    books: List[str],
    daily_hours: float,
    student: Optional[dict],
    statics: Optional[List[dict]] = None,
    protected_statics: Optional[List[dict]] = None,
) -> List[dict]:
    """Ensure the weekly plan covers all 7 days with study + test blocks each.

    LLM JSON output is sometimes partial (a few days or one block type).
    Missing days and missing study/test blocks are backfilled from the
    deterministic default plan, then every block gets a stable generated id.
    Blocks that overlap protected static (user-created) slots are dropped.
    System static blocks can be modified by the LLM.
    """
    # Separate protected (user-created) statics from system statics
    protected_statics = protected_statics or []
    occupied = _occupied_slots(protected_statics)
    kept = [
        dict(b) for b in blocks
        if not _overlaps_occupied(b.get("day", 0), b.get("startHour", 0), b.get("duration", 1), occupied)
    ]
    default = _default_week_plan(books, daily_hours, student, _occupied_slots([]))
    by_day: dict[int, List[dict]] = {}
    for b in kept:
        by_day.setdefault(int(b.get("day", 0)), []).append(dict(b))

    out: List[dict] = []
    idx = 0
    for day in range(7):
        day_blocks = by_day.get(day, [])
        has_study = any(b["type"] == "study" for b in day_blocks)
        has_test = any(b["type"] == "test" for b in day_blocks)
        for db in default:
            if db["day"] != day:
                continue
            if db["type"] == "study" and has_study:
                continue
            if db["type"] == "test" and has_test:
                continue
            if _overlaps_occupied(db["day"], db["startHour"], db["duration"], _occupied_slots([])):
                continue
            if any(_hours_overlap(db["startHour"], db["duration"], b["startHour"], b["duration"]) for b in day_blocks):
                continue
            day_blocks.append(dict(db))
        day_blocks.sort(key=lambda b: b["startHour"])
        for b in day_blocks:
            b["id"] = f"gen-{idx}"
            idx += 1
            out.append(b)
    return out


WEEKLY_PLAN_PROMPT = """تو «بوم» هستی؛ مربی هوشمند کنکور.
برنامه هفتگی میسازی که دانشآموز را برای آزمونهای آزمایشی (ماک) آماده میکند.

روند اصلی برنامهریزی:
۱. تاریخ و محتوای آزمون بعدی را از بخش «آزمون بعدی» ببین.
۲. دروس و مباحثی که در آزمون میآید را مشخص کن.
۳. از «متنهای مرجع» ببین که هر مبحث در کدام کتاب و فصل است و چه تستهایی مناسباند.
۴. برنامه را به دو هفته تقسیم کن:
   - هفته اول: مطالعه + درک مطلب + تست پایه
   - هفته دوم: تست متمرکز و شبیهساز آزمون
۵. در توضیح برنامه بنویس که آزمون چه مباحثی دارد و چگونه آنها را بین دو هفته تقسیم کردی.
۶. روی ساعتهای اشغالشده (کلاس، کار، خانواده و...) هیچ بلوکی نگذار.

قوانین:
- مجموع ساعت هر روز حداکثر {daily_hours} ساعت.
- درسهای ضعیف: {weak} را اولویت بده.
- روزها: ۰=شنبه تا ۶=جمعه.
- startHour: ۶ تا ۲۳.۵ با گام ۰.۵؛ duration: ۰.۵ تا ۶ ساعت.
- type فقط: study, test, class, break.
- فقط یک JSON خروجی بده (بدون markdown، بدون کامنت).
- عنوان بلوک‌های تست باید نام کتاب واقعی از «منابع موجود در سامانه» را داشته باشد (مثلاً «۲۰ تست فیزیک از فیزیک ۱ خیلی سبز») و اگر آزمون بازه صفحه مشخص کرده، همان بازه را در عنوان بیاور (مثلاً «تست فیزیک از فیزیک ۱ خیلی سبز صفحات ۱۵۴ تا ۲۳۴»).
- نام کتاب را فقط از «منابع موجود در سامانه» انتخاب کن؛ برای کتابی که در لیست نیست عنوان ننویس و نپرس کدام کتاب — از همان لیست مناسب‌ترین را بر اساس رشته و پایه دانش‌آموز انتخاب کن.

قالب خروجی:
{{"blocks":[{{"day":0,"startHour":6,"duration":2,"title":"مطالعه فیزیک حرکتشناسی","type":"study","count":null}},{{"day":0,"startHour":9,"duration":1,"title":"۲۰ تست فیزیک از [نام کتاب]","type":"test","count":20}}],"note":"توضیح کوتاه درباره منطق برنامه و توزیع مباحث"}}

اطلاعات دانشآموز:
{student}

سابقه گفتگوها:
{history}

هفته جاری:
{week_range}

آزمون بعدی:
{mock}

ساعتهای اشغالشده (بلاک ثابت هر هفته):
{occupied}

متنهای مرجع (برای انتخاب کتاب تست):
{context}
"""


@router.post("/weekly-plan")
def generate_weekly_plan(request: WeeklyPlanRequest):
    """Generate a standard default weekly plan (study + test blocks) grounded
    in the retrieved Konkoor books, so empty weeks can be auto-filled by the
    schedule page."""
    settings = get_settings()
    student = request.student or {}
    daily = request.daily_hours
    major = student.get("major", "ریاضی فیزیک")
    grade = student.get("grade", "سال کنکور")
    weak = student.get("weakSubjects") or student.get("weak_subjects") or []

    search_text = (
        f"برنامه هفتگی مطالعاتی کنکور {major} {grade} با مطالعه، تست و آزمون، "
        f"راهنمای تست‌زنی و مرور مطالب از کتاب‌های جامع کنکور"
    )
    embedder = get_embedding_model()
    search = get_hybrid_search()
    q = embedder.embed_query(search_text)
    chunks = search.search(
        query_text=search_text,
        query_embedding=q,
        user_id=settings.DEMO_USER_ID,
        top_k=6,
    )
    books = _book_list(chunks)

    # The text store is often empty (books are scanned page images), so also
    # name the retrieved books from the image store to ground test blocks.
    try:
        from app.rag.pipeline import _retrieve_image_hits
        img_hits = _retrieve_image_hits(search_text, settings.DEMO_USER_ID, 4)
        books = list(dict.fromkeys(books + _book_list(img_hits)))
    except Exception:
        img_hits = []

    book_line = "کتاب‌های مرجع تست: " + ("، ".join(books) if books else "نامشخص")
    context = "\n\n".join(
        f"[منبع {i + 1}] {c['document_name']}:\n{c['content']}"
        for i, c in enumerate(chunks)
    )

    # If retrieval found no book (vector stores hold only plan docs so far),
    # still ground the plan in a sensible book from the on-disk catalog so
    # test blocks name a real source instead of a generic placeholder.
    if not books:
        picked = _pick_main_book(student)
        if picked:
            books = [picked]

    catalog = "، ".join(book_catalog())
    reference_block = (
        "منابع موجود در سامانه (کتاب‌های فایل‌شده):\n"
        + (catalog if catalog else "هنوز کتابی بارگذاری نشده است.")
        + "\n\n"
        + ("کتاب‌های به‌دست‌آمده از جستجو: " + "، ".join(books) if books else "کتابی از جستجو به‌دست نیامد.")
        + ("\n\n" + context if context else "")
    )

    # Anchor the planning to a concrete week (default: current week) and find
    # the mock exam scheduled inside it, so the plan prepares the student for
    # exactly the subjects/chapters tested by that week's mock.
    try:
        week_start = date.fromisoformat(request.week_start) if request.week_start else None
    except ValueError:
        week_start = None
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=(today.weekday() + 1) % 7)
    week_end = week_start + timedelta(days=6)
    week_range = (
        f"شنبه {_jalali_date_str(week_start)} تا جمعه {_jalali_date_str(week_end)}"
        f" (تاریخ میلادی: {week_start.isoformat()} تا {week_end.isoformat()})"
    )
    mock = _extract_week_mock(settings.DEMO_USER_ID, week_start)
    occupied = _occupied_slots(request.statics)

    prompt = WEEKLY_PLAN_PROMPT.format(
        daily_hours=daily,
        weak="، ".join(weak) if weak else "نامشخص",
        student=_student_context({**student, "ساعات مطالعه روزانه": daily}),
        history=_history_context(request.history),
        week_range=week_range,
        mock=(mock["summary"] if mock else "آزمون هفتگیای این هفته برنامهریزی نشده است."),
        occupied=_occupied_prompt(occupied),
        context=book_line + ("\n\n" + reference_block if reference_block else ""),
    )
    answer = get_llm_client().generate([{"role": "user", "content": prompt}], max_tokens=1600)

    data = _parse_json_from_text(answer)
    blocks = _plan_blocks(data)
    if blocks:
        note = str((data or {}).get("note") or "")
        llm_used = True
    else:
        blocks = _default_week_plan(books, daily, student)
        note = "برنامه استاندارد پیش‌فرض (خروجی مدل قابل تفسیر نبود). llm_used=false"
        llm_used = False

    # Separate user statics (protected) from system statics
    # User statics are the ones created by the user via static/repeating option
    # System statics are the pre-defined weekly schedule blocks
    # For now, we treat request.statics as user statics (protected)
    # and system statics as empty (to be added later if needed)
    blocks = _complete_week_plan(blocks, books, daily, student, statics=[], protected_statics=request.statics)
    if books:
        main = books[0]
        for b in blocks:
            if b["type"] == "test" and any(
                g in b["title"] for g in ("کتاب مرجع", "کتاب منبع", "منبع مرجع", "[نام کتاب]")
            ):
                b["title"] = b["title"].replace("کتاب مرجع", main).replace(
                    "کتاب منبع", main).replace("منبع مرجع", main).replace(
                    "[نام کتاب]", main)

    response = {
        "week_start": week_start.isoformat(),
        "blocks": blocks,
        "note": note,
        "source_books": books,
        "llm_used": llm_used,
    }
    if mock:
        response["mock"] = {
            "document": mock["document"],
            "pages": mock["pages"],
            "summary": mock["summary"],
        }
    return response
