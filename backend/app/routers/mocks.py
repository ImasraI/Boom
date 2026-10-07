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
from threading import Thread
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.database import (
    ArenaMatch,
    ChallengeInvite,
    GeneratedMock,
    MockAttempt,
    SessionLocal,
    StudentProfile,
    User,
    WrongAnswer,
)
from app.auth.deps import get_current_user, get_db
from app.auth.limits import consume_ai_use, release_ai_use
from app.rag import mock_generation, question_bank, mock_jobs
from app.rag.provider_quota import (
    DAILY_QUOTA_MESSAGE, is_daily_quota_error, require_pool_available,
)
from app.rag.mock_generation import (
    KONKUR_SUBJECTS as _KONKUR_SUBJECTS,
    MAJOR_ALIASES as _MAJOR_ALIASES,
    OPTIONS as _OPTIONS,
    major_key as _major_key,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/mocks", tags=["mocks"])


@router.post("/assessment/{test_id}")
def start_assessment(test_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.rag.assessment_bank import create_assessment
    return create_assessment(db, current_user.id, test_id)

# Serializes pool claims within this server process (sync endpoints run in a
# threadpool). Deployment is a single uvicorn process; SQLite serializes the
# conditional claim update also prevents double assignment across processes.
_POOL_CLAIM_LOCK = threading.Lock()

# major-key -> every Persian label that maps to it (for pool matching).
_MAJOR_LABELS: dict = {}
for _label, _key in _MAJOR_ALIASES.items():
    _MAJOR_LABELS.setdefault(_key, []).append(_label)
# Canonical (first-registered) label per key - what pool rows are stored with.
_CANONICAL_MAJOR = {k: v[0] for k, v in _MAJOR_LABELS.items()}


class MockConfig(BaseModel):
    subjects: Optional[List[str]] = None  # default: all major subjects
    questions_per_subject: Optional[int] = Field(default=None, ge=1)  # default: konkur counts
    duration_minutes: Optional[int] = Field(default=None, ge=1)  # default: sum of subject minutes
    topics: List[str] = []  # restrict to these topics (e.g. from the week's mock)
    difficulty: str = Field(default="konkur", pattern="^(easy|konkur|hard)$")
    mode: str = Field(default="general", pattern="^(general|practice|practice_weak_areas)$")
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
        rows = db.execute(
            select(GeneratedMock)
            .where(GeneratedMock.status == "pending_use")
            .where(GeneratedMock.difficulty == difficulty)
            .where(GeneratedMock.major.in_(labels))
            .where(GeneratedMock.id.not_in(seen))
            .order_by(GeneratedMock.created_at.asc())
        ).scalars().all()
        from app.rag.pool_core import verified_booklet
        for row in rows:
            if grade and question_bank.grade_number(row.grade) > question_bank.grade_number(grade):
                continue
            if not verified_booklet(row.questions):
                db.execute(update(GeneratedMock).where(GeneratedMock.id == row.id,
                    GeneratedMock.status == "pending_use").values(status="quarantined"))
                continue
            questions = question_bank.active_questions(db, row)
            if len(questions) != len(json.loads(row.questions)):
                row.status = "quarantined"
                continue
            claimed = db.execute(update(GeneratedMock).where(GeneratedMock.id == row.id,
                GeneratedMock.status == "pending_use").values(
                    status="claimed", student_id=user_id, grade=grade or row.grade))
            if claimed.rowcount == 1:
                question_bank.mark_used(db, questions)
                db.commit()
                db.refresh(row)
                return row
        db.commit()
        return None


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
    db.flush()
    question_bank.index_mock(db, mock)
    db.commit()
    db.refresh(mock)
    return mock


@router.post("/generate")
def generate_mock(
    config: MockConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    consume_ai_use(current_user.id, "mock_generate")
    try:
        return _generate_reserved_mock(config, current_user, db)
    except Exception:
        # Provider, retrieval and persistence failures must all refund the reservation.
        release_ai_use(current_user.id, "mock_generate")
        raise


def _run_generation_job(job_id: str, config: MockConfig, user_id: int) -> None:
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None:
                raise HTTPException(401, "حساب کاربری پیدا نشد.")
            result = _generate_reserved_mock(config, user, db)
        mock_jobs.finish(job_id, result=result)
    except Exception as exc:
        release_ai_use(user_id, "mock_generate")
        if isinstance(exc, HTTPException):
            error = exc
        else:
            logger.exception("Background mock generation failed for user %s", user_id)
            error = HTTPException(502, "ساخت دفترچه ناموفق بود؛ دوباره تلاش کنید.")
        mock_jobs.finish(job_id, error=error)


@router.post("/generation", status_code=202)
def start_generation(config: MockConfig, current_user: User = Depends(get_current_user)):
    job, created = mock_jobs.reserve(current_user.id)
    if not created:
        return job  # Repeated clicks resume the same job without more quota.
    reserved = False
    try:
        consume_ai_use(current_user.id, "mock_generate")
        reserved = True
        Thread(target=_run_generation_job,
            args=(job['job_id'], config, current_user.id), daemon=True,
            name="mock-generation").start()
    except Exception:
        mock_jobs.discard(job['job_id'])
        if reserved:
            release_ai_use(current_user.id, "mock_generate")
        raise
    return job


@router.get("/generation/{job_id}")
def generation_status(job_id: str, current_user: User = Depends(get_current_user)):
    return mock_jobs.get(job_id, current_user.id)


def _generate_reserved_mock(config: MockConfig, current_user: User, db: Session):
    profile = db.execute(select(StudentProfile).where(StudentProfile.user_id == current_user.id)).scalar_one_or_none()
    student = dict(config.student or {})
    if profile:
        for field in ("major", "grade"):
            if getattr(profile, field, None):
                student[field] = getattr(profile, field)
    config = config.model_copy(update={"student": student})
    poolable, plan, major = _resolve_plan(config)
    grade = (config.student or {}).get("grade") or ""
    weak = []
    if config.mode == "practice_weak_areas":
        weak = mock_generation.weak_areas(current_user.id)
        plan = mock_generation.bias_plan(plan, weak)
    labels = _MAJOR_LABELS.get(_major_key(major)) or [major]
    topics = config.topics or [w.get("topic", "") for w in weak]
    practice = config.mode != "general"
    questions = question_bank.assemble(db, current_user.id, plan, labels, config.difficulty,
        grade, topics, prefer_used=True, used_only=practice, allow_partial=practice)
    if practice and not questions:
        questions = question_bank.assemble(db, current_user.id, plan, labels, config.difficulty,
            grade, topics, prefer_used=True, allow_partial=True)
    if questions:
        actual_plan = [{**s, "questions": sum(q["subject"] == s["name"] for q in questions)} for s in plan]
        actual_plan = [s for s in actual_plan if s["questions"]]
        duration = config.duration_minutes or max(1, round(sum(s["minutes"] for s in plan) * len(questions) / sum(s["questions"] for s in plan)))
        mock = question_bank.create_reused_mock(db, current_user.id, questions, major or "ریاضی فیزیک", grade,
            config.difficulty, duration)
        db.commit()
        return {"mock_id": mock.id, "title": mock.title, "duration_minutes": duration,
                "total_questions": len(questions), "subjects": actual_plan, "source": "question_bank"}
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    # 1) Fast path: claim a pre-generated booklet from the pool.
    if poolable:
        claimed = _claim_pool_mock(db, current_user.id,
                                   _major_key(major), config.difficulty, grade)
        if claimed is not None:
            # Quota already reserved atomically at entry - nothing more to record.
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
    require_pool_available()

    duration = config.duration_minutes or sum(s["minutes"] for s in plan)

    provider_error = ""

    def report(event, data):
        nonlocal provider_error
        if event == "provider_error":
            provider_error = data.get("message") or ""

    questions = mock_generation.generate_booklet(
        current_user.id, plan,
        topics=config.topics, difficulty=config.difficulty,
        grade=grade, report=report,
    )
    if questions:
        questions = mock_generation.verify_and_repair_booklet(
            questions, current_user.id, difficulty=config.difficulty, report=report)
    if questions and (is_daily_quota_error(provider_error) or any(
            sum(q.get("subject") == row["name"] for q in questions) != row["questions"] for row in plan)):
        _persist_mock(db, user_id=current_user.id, questions=questions, duration=duration,
            major=major or "ریاضی فیزیک", grade=grade, difficulty=config.difficulty,
            title="سوال‌های تاییدشده از تولید ناتمام", status="bank_only")
    if is_daily_quota_error(provider_error):
        require_pool_available()  # Includes the provider reset time when available.
        raise HTTPException(503, detail={"code": "provider_daily_quota",
                                         "message": DAILY_QUOTA_MESSAGE})
    if not questions or any(sum(q.get("subject") == row["name"] for q in questions) != row["questions"] for row in plan):
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
    # Quota already reserved at entry.
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
    percent = round(100.0 * raw / total, 1) if total else 0.0
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


@router.get("/{mock_id:int}")
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
            # Same for async friend challenges: the accepted recipient reads
            # the sender's booklet through the normal mock-taking flow.
            is_challenge_recipient = mock is not None and db.execute(
                select(ChallengeInvite)
                .where(ChallengeInvite.mock_id == mock_id)
                .where(ChallengeInvite.recipient_id == current_user.id)
                .where(ChallengeInvite.status.in_(("accepted", "completed")))
            ).scalar_one_or_none() is not None
            if not is_challenge_recipient:
                raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    questions = question_bank.active_questions(db, mock)
    db.commit()
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


class QuestionReportIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/{mock_id:int}/questions/{question_id:int}/report")
def report_question(mock_id: int, question_id: int, payload: QuestionReportIn,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Reuse exactly the booklet read authorization, including duel opponents
    # and accepted challenge recipients. An arbitrary bank id is never accepted.
    get_mock(mock_id, current_user, db)
    return question_bank.record_report(db, db.get(GeneratedMock, mock_id), current_user.id,
                                       question_id, payload.reason.strip())


class SubmitPayload(BaseModel):
    answers: dict = Field(default_factory=dict)  # {"1": 2, "2": "", ...}
    duration_seconds: int = Field(default=0, ge=0)

    @field_validator("answers", mode="before")
    @classmethod
    def validate_answers(cls, values):
        if not isinstance(values, dict):
            raise ValueError("answers must be a question-to-option map")
        out = {}
        for key, value in values.items():
            if value is None or (isinstance(value, str) and value in ("", "null")):
                out[str(key)] = None
                continue
            if isinstance(value, str) and value in ("0", "1", "2", "3"):
                value = int(value)
            if type(value) is not int or not 0 <= value <= 3:
                raise ValueError("answer must be an option index from 0 to 3, or blank")
            out[str(key)] = value
        return out


@router.post("/{mock_id}/submit")
def submit_mock(
    mock_id: int,
    payload: SubmitPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mock = db.get(GeneratedMock, mock_id)
    challenge_invite: Optional[ChallengeInvite] = None
    if not mock or mock.student_id != current_user.id:
        # Challenge recipients submit through this same endpoint (konkur
        # scoring + weakness memory must run exactly once, here).
        challenge_invite = None if not mock else db.execute(
            select(ChallengeInvite)
            .where(ChallengeInvite.mock_id == mock_id)
            .where(ChallengeInvite.recipient_id == current_user.id)
            .where(ChallengeInvite.status.in_(("accepted", "completed")))
        ).scalar_one_or_none()
        if challenge_invite is None:
            raise HTTPException(status_code=404, detail="آزمون پیدا نشد")
    questions = question_bank.active_questions(db, mock)
    if not questions:
        raise HTTPException(status_code=409, detail="سوال معتبری برای تصحیح این دفترچه باقی نمانده است")

    # A database write lock serializes submissions for this student across processes.
    # This preserves historical rows while making retries return the first result.
    db.execute(update(User).where(User.id == current_user.id).values(rating=User.rating))
    prior = db.execute(select(MockAttempt).where(MockAttempt.student_id == current_user.id,
        MockAttempt.mock_id == mock_id).order_by(MockAttempt.id).limit(1)).scalar_one_or_none()
    if prior is not None:
        saved = SubmitPayload(answers=json.loads(prior.answers or "{}"), duration_seconds=prior.duration_seconds or 0)
        response = _submission_response(prior, _score(questions, saved.answers), questions, saved)
        db.rollback()
        return response

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

    # Challenge completion: if this submit was an accepted friend challenge,
    # flip the invite to "completed" so /complete just returns the scores.
    if challenge_invite is not None:
        challenge_invite.status = "completed"
        db.commit()
        logger.info("Challenge invite %s auto-completed by submit",
                    challenge_invite.invite_code)

    return _submission_response(attempt, result, questions, payload)


def _submission_response(attempt, result, questions, payload):
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
