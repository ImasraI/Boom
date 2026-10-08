"""Insights API: the student's *memory*.

Every wrong/blank answer from any test (generated mock, arena duel, manual
practice) is recorded here. The weekly planner reads these rows to decide
which subjects/topics need more test blocks and which books to schedule.

Also implements ``GET /api/boom/last-mock-results`` which the frontend's
Exams page already calls but which never existed on the backend.
"""

from datetime import datetime, timedelta
import json
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.database import Assessment, User, WrongAnswer, MockAttempt, GeneratedMock, StudySession, StudentProfile
from app.auth.deps import get_current_user, get_db
from app.rag.knowledge_graph import build_graph
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/insights", tags=["insights"])
logger = get_logger(__name__)


class WrongAnswerIn(BaseModel):
    subject: str = Field(..., min_length=1)
    topic: Optional[str] = None
    book: Optional[str] = None
    page: Optional[int] = None
    question_text: Optional[str] = None
    correct_answer: Optional[str] = None
    student_answer: Optional[str] = None
    was_blank: bool = False
    source: Optional[str] = None  # mock / arena / practice


@router.post("/wrong-answers")
def record_wrong_answers(
    payload: List[WrongAnswerIn],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store a batch of wrong/blank answers from a finished test."""
    if not payload:
        return {"recorded": 0}
    rows = [
        WrongAnswer(
            student_id=current_user.id,
            subject=w.subject.strip(),
            topic=(w.topic or "").strip() or None,
            book=(w.book or "").strip() or None,
            page=w.page,
            question_text=(w.question_text or "").strip() or None,
            correct_answer=(w.correct_answer or "").strip() or None,
            student_answer=(w.student_answer or "").strip() or None,
            was_blank=bool(w.was_blank or not (w.student_answer or "").strip()),
            source=(w.source or "").strip() or None,
        )
        for w in payload
    ]
    db.add_all(rows)
    db.commit()
    logger.info("Recorded %d wrong answer(s) for user %d.", len(rows), current_user.id)
    return {"recorded": len(rows)}


@router.get("/wrong-answers")
def list_wrong_answers(
    subject: Optional[str] = None,
    days: int = 60,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent wrong answers, newest first — the planner's weakness memory."""
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    stmt = (
        select(WrongAnswer)
        .where(WrongAnswer.student_id == current_user.id)
        .where(WrongAnswer.created_at >= since)
        .order_by(WrongAnswer.created_at.desc())
    )
    if subject:
        stmt = stmt.where(WrongAnswer.subject == subject)
    rows = db.execute(stmt).scalars().all()
    return {
        "count": len(rows),
        "wrong_answers": [
            {
                "id": r.id,
                "subject": r.subject,
                "topic": r.topic,
                "book": r.book,
                "page": r.page,
                "question_text": r.question_text,
                "correct_answer": r.correct_answer,
                "student_answer": r.student_answer,
                "was_blank": bool(r.was_blank),
                "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


class WeakTopicOut(BaseModel):
    topic: str
    wrong_count: int
    blanks: int
    # Normalized wrong counts within a subject; blanks are separate.
    wrongness: float


class WeakSubjectOut(BaseModel):
    subject: str
    wrong_count: int
    topics: List[WeakTopicOut]


@router.get("/weakness-map")
def weakness_map(
    days: int = 90,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actual mistakes from verified answers, matched to this major's books."""
    from app.rag.learning_evidence import curriculum_events
    rows = curriculum_events(db, current_user.id, days=max(1, min(days, 365)))
    grouped = {}
    for row in rows:
        stats = grouped.setdefault(row["subject"], {}).setdefault(row["topic"], {"wrong": 0, "blanks": 0})
        if row["outcome"] == "wrong":
            stats["wrong"] += 1
        elif row["outcome"] == "blank":
            stats["blanks"] += 1

    subjects: List[WeakSubjectOut] = []
    for subject, topics in grouped.items():
        peak = max((s["wrong"] for s in topics.values()), default=0) or 1
        topic_list = sorted(
            (
                WeakTopicOut(
                    topic=t,
                    wrong_count=s["wrong"],
                    blanks=s["blanks"],
                    wrongness=round(s["wrong"] / peak, 2),
                )
                for t, s in topics.items() if s["wrong"]
            ),
            key=lambda t: (-t.wrong_count, t.topic),
        )
        if not topic_list:
            continue
        subjects.append(WeakSubjectOut(
            subject=subject,
            wrong_count=sum(t.wrong_count for t in topic_list),
            topics=topic_list,
        ))
    subjects.sort(key=lambda s: (-s.wrong_count, s.subject))

    return {
        "days": days,
        "total_answered": sum(r["outcome"] != "blank" for r in rows),
        "total_blank": sum(r["outcome"] == "blank" for r in rows),
        "total_wrong": sum(s.wrong_count for s in subjects),
        "subjects": [s.model_dump() for s in subjects],
    }


@router.get("/knowledge-graph")
def knowledge_graph(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated student's cached, book-sourced graph.

    Curriculum titles are extracted offline from shared book OCR; opened state and
    mastery evidence are always calculated from this user's records only.
    """
    major = "ریاضی فیزیک"
    profile_row = db.query(StudentProfile).filter_by(user_id=current_user.id).first()
    if profile_row and profile_row.major:
        major = profile_row.major

    from app.rag.learning_evidence import curriculum_events
    evidence = defaultdict(lambda: {"attempted": 0, "correct": 0, "wrong": 0})
    for event in curriculum_events(db, current_user.id, days=None):
        if event["outcome"] == "blank":
            continue
        row = evidence[(event["subject"], event["topic"])]
        row["attempted"] += 1
        row[event["outcome"]] += 1

    read_keys = set()
    for session in db.query(StudySession).filter(
        StudySession.student_id == current_user.id,
        StudySession.completion_status == "completed",
    ).all():
        if session.subject_name:
            read_keys.add((session.subject_name, session.topic_name or ""))

    return build_graph(major, dict(evidence), read_keys)


class MockSubjectResult(BaseModel):
    name: str
    score: float
    correct: int
    wrong: int
    blank: int


class MockResultIn(BaseModel):
    provider: str = "بوم"
    total_score: float = 0
    subjects: List[MockSubjectResult] = []


@router.post("/mock-results")
def record_mock_result(
    payload: MockResultIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist a finished mock exam result (also used by the arena)."""
    row = Assessment(
        student_id=current_user.id,
        title=payload.provider,
        date=datetime.utcnow().date(),
        source="mock_exam",
        results=payload.model_dump_json(),
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "message": "نتیجه آزمون ثبت شد"}


@router.get("/last-mock-results")
def last_mock_results(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All recorded mock results for the Exams page (newest first)."""
    rows = (
        db.execute(
            select(Assessment)
            .where(Assessment.student_id == current_user.id)
            .where(Assessment.source == "mock_exam")
            .order_by(Assessment.date.desc(), Assessment.id.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for i, r in enumerate(rows):
        try:
            data = r.results if isinstance(r.results, dict) else {}
            if isinstance(r.results, str):
                import json

                data = json.loads(r.results)
        except Exception:
            data = {}
        subjects = data.get("subjects") or []
        if isinstance(subjects, str):
            try:
                import json

                subjects = json.loads(subjects)
            except Exception:
                subjects = []
        out.append(
            {
                "id": r.id,
                "provider": data.get("provider") or r.title or "آزمون",
                "date": r.date.isoformat() if r.date else "",
                "totalScore": float(data.get("total_score") or 0),
                # The first row is "most recent"; the page renders a rank line.
                "rank": i + 1,
                "subjects": subjects,
            }
        )
    return out
