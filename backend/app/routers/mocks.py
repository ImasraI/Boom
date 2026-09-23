"""Konkur-standard AI mock generator.

Assembles a timed, konkur-style multiple-choice booklet from the student's
own OCR'd test books (via the RAG text store) + the text LLM, then scores
submissions with konkur negative marking (3 correct = +1 score, 1 wrong =
-1/3) and records every wrong/blank answer into the weakness memory.

Booklet shape follows the standard konkur format: per-subject groups of
four-option questions labeled الف/ب/ج/د. Difficulty tier and topic mix are
configurable per request; subjects follow the student's major (riazi vs
tajrobi).

The generation pipeline itself (retrieval -> prompt -> LLM -> parse -> pad)
lives in app.rag.mock_generation and is shared with the arena duels; this
router adds quota handling, persistence, scoring, and review.

Endpoints (all authenticated):
  POST /api/mocks/generate      -> new GeneratedMock (booklet without answers)
  GET  /api/mocks/{mock_id}     -> booklet for taking (answers hidden)
  POST /api/mocks/{mock_id}/submit -> scored result + per-question review
  GET  /api/mocks/history       -> past attempts

Instant serve: standard requests (official plan, general mode) are claimed
from a pre-generated pool of status="pending_use" rows maintained by
scripts/mock_pool_worker.py; only an empty pool falls back to the slow
live generation call.
"""

import json
import threading
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.database import ArenaMatch, GeneratedMock, MockAttempt, User, WrongAnswer
from app.auth.deps import get_current_user, get_db
from app.auth.limits import check_ai_quota, record_ai_use
from app.rag import mock_generation
from app.rag.mock_generation import (
    KONKUR_SUBJECTS as _KONKUR_SUBJECTS,
    MAJOR_ALIASES as _MAJOR_ALIASES,
    OPTIONS as _OPTIONS,
    major_key as _major_key,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mocks", tags=["mocks"])

# Serializes pool claims within this server process (sync endpoints run in a
# threadpool). Deployment is a single uvicorn process; SQLite serializes the
# commit itself, so worst case across processes is a benign double-check.
_POOL_CLAIM_LOCK = threading.Lock()

# major-key -> every Persian label that maps to it (for pool matching).
_MAJOR_LABELS: dict = {}
for _label, _key in _MAJOR_ALIASES.items():
    _MAJOR_LABELS.setdefault(_key, []).append(_label)
# Canonical (first-registered) label per key - what pool rows are stored with.
_CANONICAL_MAJOR = {k: v[0] for k, v in _MAJOR_LABELS.items()}


class MockConfig(BaseModel):
    subjects: Optional[List[str]] = None  # default: all major subjects
    questions_per_subject: Optional[int] = None  # default: konkur counts
    duration_minutes: Optional[int] = None  # default: sum of subject minutes
    topics: List[str] = []  # restrict to these topics (e.g. from the week's mock)
    difficulty: str = Field(default="konkur", pattern="^(easy|konkur|hard)$")
    mode: str = Field(default="general", pattern="^(general|practice_weak_areas)$")
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


def _resolve_plan(config: "MockConfig") -> Tuple[bool, List[dict], str]:
    """-> (poolable, plan, major).

    A request can be served from the pre-generated pool only when it asks
    for exactly a standard booklet: official subject plan, no custom
    subjects/counts/duration/topics, general mode. Anything customized is
    always generated live for that student.
    """
    student = config.student or {}
    major = student.get("major") or ""
    poolable = (
        not config.subjects
        and not config.questions_per_subject
        and not config.duration_minutes
        and not config.topics
        and config.mode == "general"
    )
    plan = [dict(s) for s in _KONKUR_SUBJECTS[_major_key(major)]]
    if config.subjects:
        plan = [s for s in plan if s["name"] in config.subjects] or plan
    if config.questions_per_subject:
        plan = [{**s, "questions": min(config.questions_per_subject, s["questions"])}
                for s in plan]
    return poolable, plan, major


def _claim_pool_mock(db: Session, user_id: int, major_key_str: str,
                     difficulty: str, grade: str) -> Optional[GeneratedMock]:
    """Atomically claim the oldest pending_use pool row matching
    (major, difficulty): mark it claimed and assign it to the student.

    Pool rows this student has already attempted (MockAttempt history -
    covers both /api/mocks submits and arena duels) are skipped, so a
    returning student always gets fresh questions; when every matching row
    is already seen, returns None and the caller falls back to live
    generation for a genuinely new booklet.
    """
    labels = _MAJOR_LABELS.get(major_key_str) or []
    if not labels:
        return None
    with _POOL_CLAIM_LOCK:
        seen = select(MockAttempt.mock_id).where(
            MockAttempt.student_id == user_id)
        row = db.execute(
            select(GeneratedMock)
            .where(GeneratedMock.status == "pending_use")
            .where(GeneratedMock.difficulty == difficulty)
            .where(GeneratedMock.major.in_(labels))
            .where(GeneratedMock.id.not_in(seen))
            .order_by(GeneratedMock.created_at.asc())
            .limit(1)
        ).scalars().first()
        if row is None:
            return None
        row.status = "claimed"
        row.student_id = user_id
        row.grade = grade or row.grade
        db.commit()
        return row


def _persist_mock(db: Session, *, user_id: int, questions: List[dict],
                  duration: int, major: str, grade: str, difficulty: str,
                  title: str, status: str = "claimed") -> GeneratedMock:
    mock = GeneratedMock(
        student_id=user_id,
        title=title,
        major=major,
        grade=grade,
        duration_minutes=duration,
        questions=json.dumps(questions, ensure_ascii=False),
        status=status,
        difficulty=difficulty,
    )
    db.add(mock)
    db.commit()
    db.refresh(mock)
    return mock


@router.post("/generate")
def generate_mock(
    config: MockConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_ai_quota(current_user.id, "mock_generate")
    poolable, plan, major = _resolve_plan(config)
    grade = (config.student or {}).get("grade") or ""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    # 1) Fast path: claim a pre-generated booklet from the pool.
    if poolable:
        claimed = _claim_pool_mock(db, current_user.id,
                                   _major_key(major), config.difficulty, grade)
        if claimed is not None:
            record_ai_use(current_user.id, "mock_generate")
            logger.info("Served mock %d from the pre-generated pool for user %d.",
                        claimed.id, current_user.id)
            return {
                "mock_id": claimed.id,
                "title": claimed.title,
                "duration_minutes": claimed.duration_minutes,
                "total_questions": len(_load_questions(claimed)),
                "subjects": plan,
            }

    # 2) Slow path: live generation (pool empty for this combination, or a
       # customized request the pool can never satisfy).
    weak = []
    if config.mode == "practice_weak_areas":
        weak = mock_generation.weak_areas(current_user.id)
        if weak:
            plan = mock_generation.bias_plan(plan, weak)
        else:
            logger.info("practice_weak_areas requested but user %d has no "
                        "WrongAnswer rows; falling back to general mode.",
                        current_user.id)

    duration = config.duration_minutes or sum(s["minutes"] for s in plan)

    questions = mock_generation.generate_booklet(
        current_user.id, plan,
        topics=config.topics, difficulty=config.difficulty,
    )
    if not questions:
        raise HTTPException(status_code=502,
                            detail="مدل زبانی دفترچه معتبری تولید نکرد؛ دوباره تلاش کنید.")

    mock = _persist_mock(
        db, user_id=current_user.id, questions=questions,
        duration=duration, major=major or "ریاضی فیزیک", grade=grade,
        difficulty=config.difficulty,
        title=(f"آزمون نقطه‌ضعف‌ها — {now}"
               if config.mode == "practice_weak_areas" and weak else
               f"آزمون آزمایشی بوم — {now}"),
        status="claimed",  # live rows are assigned immediately, never pooled
    )
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
        # Ranked-duel booklets are owned by one player but served to both:
        # any authenticated participant of the match may read them too.
        is_duel_participant = mock is not None and db.execute(
            select(ArenaMatch)
            .where(ArenaMatch.mock_id == mock_id)
            .where((ArenaMatch.student_a_id == current_user.id)
                   | (ArenaMatch.student_b_id == current_user.id))
        ).scalar_one_or_none() is not None
        if not is_duel_participant:
            raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    questions = _load_questions(mock)
    # Duel booklets are filled asynchronously after match reservation: hide
    # placeholder rows (empty text) so the duel client keeps polling until
    # the real AI-generated questions land.
    visible = [q for q in questions if (q.get("text") or "").strip()]
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
            for q in visible
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
