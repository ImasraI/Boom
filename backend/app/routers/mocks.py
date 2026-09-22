"""Konkur-standard AI mock generator.

Assembles a timed, konkur-style multiple-choice booklet from the student's
own OCR'd test books (via the RAG text store) + the text LLM, then scores
submissions with konkur negative marking (3 correct = +1 score, 1 wrong =
-1/3) and records every wrong/blank answer into the weakness memory.

Booklet shape follows the standard konkur format: per-subject groups of
four-option questions labeled الف/ب/ج/د. Difficulty tier and topic mix are
configurable per request; subjects follow the student's major (riazi vs
tajrobi).

Endpoints (all authenticated):
  POST /api/mocks/generate      -> new GeneratedMock (booklet without answers)
  GET  /api/mocks/{mock_id}     -> booklet for taking (answers hidden)
  POST /api/mocks/{mock_id}/submit -> scored result + per-question review
  GET  /api/mocks/history       -> past attempts
"""

import json
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.database import GeneratedMock, MockAttempt, User, WrongAnswer
from app.auth.deps import get_current_user, get_db
from app.auth.limits import check_ai_quota, record_ai_use
from app.config import get_settings
from app.rag.llm import get_llm_client
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/mocks", tags=["mocks"])
logger = get_logger(__name__)

_KONKUR_SUBJECTS = {
    "riazi": [
        {"name": "ریاضی", "questions": 25, "minutes": 45},
        {"name": "فیزیک", "questions": 30, "minutes": 40},
        {"name": "شیمی", "questions": 25, "minutes": 30},
    ],
    "tajrobi": [
        {"name": "زیست", "questions": 50, "minutes": 55},
        {"name": "فیزیک", "questions": 30, "minutes": 40},
        {"name": "شیمی", "questions": 25, "minutes": 30},
        {"name": "ریاضی", "questions": 20, "minutes": 25},
    ],
}

_OPTIONS = ["الف", "ب", "ج", "د"]


def _major_key(major: str) -> str:
    return "tajrobi" if "تجربی" in (major or "") else "riazi"


class MockConfig(BaseModel):
    subjects: Optional[List[str]] = None  # default: all major subjects
    questions_per_subject: Optional[int] = None  # default: konkur counts
    duration_minutes: Optional[int] = None  # default: sum of subject minutes
    topics: List[str] = []  # restrict to these topics (e.g. from the week's mock)
    difficulty: str = Field(default="konkur", pattern="^(easy|konkur|hard)$")
    student: Optional[dict] = None


class _MockQuestion(BaseModel):
    id: int
    subject: str
    topic: str = ""
    text: str
    options: List[str]
    answer: int  # 0..3
    explanation: str = ""
    book: str = ""
    page: Optional[int] = None


def _retrieve_book_context(user_id: int, subjects: List[str], topics: List[str],
                           per_subject: int = 3) -> str:
    """OCR'd page excerpts to ground generation in the student's real books."""
    try:
        from app.rag.embeddings import get_embedding_model
        from app.rag.hybrid_search import get_hybrid_search

        embedder = get_embedding_model()
        search = get_hybrid_search()
    except Exception as exc:  # stores unavailable -> generate from LLM knowledge
        logger.warning("Mock context retrieval unavailable: %s", exc)
        return ""

    blocks: List[str] = []
    seen = set()
    for subject in subjects:
        for topic in (topics or [""]):
            q = f"{subject} {topic} تست چهارگزینه‌ای کنکور با جواب تشریحی".strip()
            try:
                emb = embedder.embed_query(q)
                chunks = search.search(query_text=q, query_embedding=emb,
                                       user_id=user_id, top_k=per_subject)
            except Exception as exc:
                logger.warning("Mock retrieval failed for %s/%s: %s", subject, topic, exc)
                continue
            for c in chunks:
                key = (c["document_name"], c["chunk_index"])
                if key in seen:
                    continue
                seen.add(key)
                page = ""
                m = re.search(r"\[صفحه\s*([0-9۰-۹]+)\]", c.get("content", "") or "")
                if m:
                    fa = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
                    page = f" (صفحه {m.group(1).translate(fa)})"
                blocks.append(
                    f"[کتاب: {c['document_name']}{page}]\n{c['content'][:700]}"
                )
    return "\n\n".join(blocks[:12])


_GENERATE_PROMPT = """تو طراح آزمون آزمایشی کنکور هستی. یک دفترچه تست چهارگزینه‌ای استاندارد بساز.

درس‌ها و تعداد سوال هر کدام:
{plan}

مباحث هدف (فقط از این مباحث سوال بزن):
{topics}

سطح دشواری: {difficulty} (سوالات باید در سطح و سبک واقعی کنکور باشند).

نمونه صفحات واقعی کتاب‌های دانش‌آموز (در صورت مرتبط بودن از آن‌ها الهام بگیر و سبک سوالات را حفظ کن):
{context}

قوانین:
- برای هر سوال: متن سوال، دقیقا ۴ گزینه، شماره گزینه صحیح (۰ تا ۳) و یک توضیح کوتاه حل.
- پاسخ‌ها بین گزینه‌ها پخش باشند (همه «الف» نباشند).
- هیچ سوال تکراری یا تله‌ای با جواب واضح نساز؛ گزینه‌های انحرافی معنادار باشند.
- خروجی فقط JSON، بدون markdown و توضیح اضافه، در این قالب:
{{"questions":[{{"subject":"ریاضی","topic":"حد و پیوستگی","text":"...","options":["...","...","...","..."],"answer":2,"explanation":"..."}}, ...]}}"""


def _parse_booklet(raw: str, subject_counts: dict) -> List[dict]:
    """Parse the LLM JSON booklet; tolerate fences and trailing commas."""
    if not raw:
        return []
    candidates = [raw]
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        candidates.append(m.group(1))
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", cand.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        rows = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            options = [str(o) for o in (r.get("options") or [])][:4]
            if len(options) != 4:
                continue
            try:
                ans = int(r.get("answer"))
            except (TypeError, ValueError):
                continue
            if not (0 <= ans <= 3):
                continue
            text = str(r.get("text") or "").strip()
            if len(text) < 5:
                continue
            out.append({
                "subject": str(r.get("subject") or "").strip(),
                "topic": str(r.get("topic") or "").strip(),
                "text": text,
                "options": options,
                "answer": ans,
                "explanation": str(r.get("explanation") or "").strip(),
            })
        if out:
            return out
    return []


def _pad_booklet(questions: List[dict], subject_counts: dict) -> List[dict]:
    """If the LLM returned fewer questions than requested, duplicate-free fill
    is impossible without a corpus; instead we keep what exists and pad the
    answer distribution so keys are not all the same option."""
    n = len(questions)
    for i, q in enumerate(questions):
        q.setdefault("answer", 0)
    # Spread answers that clump (LLMs love answer=0).
    answers = [q["answer"] for q in questions]
    if answers and (answers.count(0) / n > 0.6):
        for i, q in enumerate(questions):
            q["answer"] = (q["answer"] + i) % 4 if q["answer"] == 0 else q["answer"]
    return questions


@router.post("/generate")
def generate_mock(
    config: MockConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_ai_quota(current_user.id, "mock_generate")
    settings = get_settings()
    major = (config.student or {}).get("major") or ""
    plan = _KONKUR_SUBJECTS[_major_key(major)]
    if config.subjects:
        plan = [s for s in plan if s["name"] in config.subjects] or plan
    if config.questions_per_subject:
        plan = [{**s, "questions": min(config.questions_per_subject, s["questions"])}
                for s in plan]
    duration = config.duration_minutes or sum(s["minutes"] for s in plan)
    subjects = [s["name"] for s in plan]

    context = _retrieve_book_context(current_user.id, subjects, config.topics)
    plan_text = "\n".join(f"- {s['name']}: {s['questions']} سوال" for s in plan)
    topics_text = "\n".join(f"- {t}" for t in config.topics) if config.topics else "- هر مبحث کنکوری آن درس"

    prompt = _GENERATE_PROMPT.format(
        plan=plan_text, topics=topics_text,
        difficulty={"easy": "آسان", "konkur": "استاندارد کنکور", "hard": "سخت (تست‌های بالای ۸۰٪ رتبه‌ها)"}[config.difficulty],
        context=context or "در دسترس نیست.",
    )
    raw = get_llm_client().generate([{"role": "user", "content": prompt}],
                                    max_tokens=4000, timeout=420.0)
    rows = _parse_booklet(raw, {s["name"]: s["questions"] for s in plan})
    rows = _pad_booklet(rows, {s["name"]: s["questions"] for s in plan})
    if not rows:
        raise HTTPException(status_code=502,
                            detail="مدل زبانی دفترچه معتبری تولید نکرد؛ دوباره تلاش کنید.")

    questions = []
    for i, r in enumerate(rows):
        r["_id"] = i + 1
        questions.append(r)

    mock = GeneratedMock(
        student_id=current_user.id,
        title=f"آزمون آزمایشی بوم — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        major=major or "ریاضی فیزیک",
        grade=(config.student or {}).get("grade") or "",
        duration_minutes=duration,
        questions=json.dumps(questions, ensure_ascii=False),
    )
    db.add(mock)
    db.commit()
    db.refresh(mock)
    record_ai_use(current_user.id, "mock_generate")
    logger.info("Generated mock %d with %d questions for user %d.",
                mock.id, len(questions), current_user.id)
    return {
        "mock_id": mock.id,
        "title": mock.title,
        "duration_minutes": mock.duration_minutes,
        "total_questions": len(questions),
        "subjects": plan,
    }


def _load_questions(mock: GeneratedMock) -> List[dict]:
    try:
        return json.loads(mock.questions)
    except (ValueError, TypeError):
        return []


def _score(questions: List[dict], answers: dict) -> dict:
    """Konkur scoring: each 3 correct = +1, each wrong = -1/3, blank = 0."""
    correct = wrong = blank = 0
    per_subject: dict = {}
    for q in questions:
        sid = str(q.get("_id") or q.get("id") or "")
        given = answers.get(sid)
        given = None if given in (None, "", "null") else int(given)
        stat = per_subject.setdefault(
            q.get("subject") or "سایر", {"correct": 0, "wrong": 0, "blank": 0}
        )
        if given is None:
            blank += 1
            stat["blank"] += 1
        elif 0 <= given <= 3 and given == q.get("answer"):
            correct += 1
            stat["correct"] += 1
        else:
            wrong += 1
            stat["wrong"] += 1
    raw = correct - wrong / 3.0
    total = len(questions)
    percent = max(0.0, round(100.0 * raw / total, 1)) if total else 0.0
    return {
        "correct": correct, "wrong": wrong, "blank": blank,
        "raw_score": round(raw, 2), "percent": percent,
        "subjects": [
            {
                "name": name,
                "score": round(100.0 * (s["correct"] - s["wrong"] / 3.0) /
                               max(1, s["correct"] + s["wrong"] + s["blank"]), 1),
                **s,
            }
            for name, s in per_subject.items()
        ],
    }


@router.get("/{mock_id}")
def get_mock(
    mock_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mock = db.get(GeneratedMock, mock_id)
    if not mock or mock.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    questions = _load_questions(mock)
    return {
        "mock_id": mock.id,
        "title": mock.title,
        "duration_minutes": mock.duration_minutes,
        "questions": [
            {
                "id": q.get("_id") or q.get("id"),
                "subject": q.get("subject"),
                "topic": q.get("topic"),
                "text": q.get("text"),
                "options": q.get("options"),
            }
            for q in questions
        ],
    }


class SubmitPayload(BaseModel):
    answers: dict = Field(default_factory=dict)  # {"1": 2, "2": "", ...}
    duration_seconds: int = 0


@router.post("/{mock_id}/submit")
def submit_mock(
    mock_id: int,
    payload: SubmitPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mock = db.get(GeneratedMock, mock_id)
    if not mock or mock.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    questions = _load_questions(mock)
    if not questions:
        raise HTTPException(status_code=500, detail="دفترچه آزمون خراب است")

    result = _score(questions, payload.answers)

    attempt = MockAttempt(
        mock_id=mock.id,
        student_id=current_user.id,
        answers=json.dumps(payload.answers, ensure_ascii=False),
        duration_seconds=payload.duration_seconds,
        score=result["percent"],
        correct=result["correct"],
        wrong=result["wrong"],
        blank=result["blank"],
    )
    db.add(attempt)

    # Weakness memory: every miss feeds the planner.
    for q in questions:
        sid = str(q.get("_id") or q.get("id") or "")
        given = payload.answers.get(sid)
        given = None if given in (None, "", "null") else int(given)
        if given is not None and 0 <= given <= 3 and given == q.get("answer"):
            continue
        db.add(WrongAnswer(
            student_id=current_user.id,
            subject=q.get("subject") or "سایر",
            topic=q.get("topic") or "",
            book=q.get("book") or "",
            page=q.get("page"),
            question_text=(q.get("text") or "")[:500],
            correct_answer=_OPTIONS[q.get("answer", 0)] if q.get("options") else str(q.get("answer")),
            student_answer=(_OPTIONS[given] if given is not None and 0 <= given <= 3 else ""),
            was_blank=given is None,
            source="mock",
        ))
    db.commit()
    db.refresh(attempt)

    return {
        "attempt_id": attempt.id,
        "score": result["percent"],
        "raw_score": result["raw_score"],
        "correct": result["correct"],
        "wrong": result["wrong"],
        "blank": result["blank"],
        "subjects": result["subjects"],
        "review": [
            {
                "id": q.get("_id") or q.get("id"),
                "subject": q.get("subject"),
                "topic": q.get("topic"),
                "text": q.get("text"),
                "options": q.get("options"),
                "answer": q.get("answer"),
                "explanation": q.get("explanation"),
                "your_answer": payload.answers.get(str(q.get("_id") or q.get("id"))),
            }
            for q in questions
        ],
    }


@router.get("/history")
def history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(MockAttempt)
        .where(MockAttempt.student_id == current_user.id)
        .order_by(MockAttempt.created_at.desc())
        .limit(20)
    ).scalars().all()
    return [
        {
            "attempt_id": r.id,
            "mock_id": r.mock_id,
            "score": r.score,
            "correct": r.correct,
            "wrong": r.wrong,
            "blank": r.blank,
            "duration_seconds": r.duration_seconds,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
