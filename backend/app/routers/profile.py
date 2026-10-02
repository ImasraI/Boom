"""Server-side student state (growth-readiness projects 1 + 4).

Project 1 - single source of truth: the profile lives in the DB, versioned
for safe multi-device edits (PATCH carries the version it was based on; a
stale one gets 409 + the server state back, never a silent overwrite).
localStorage stays as an offline cache only.

Project 4 - real study sessions: quick-log (three taps) distinguishes what
was PLANNED from what HAPPENED, feeding the planner's future per-student
estimates.
"""
from datetime import datetime, timezone
from typing import Optional, Literal
from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db
from app.auth.database import StudentProfile, StudySession, User, WrongAnswer
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Profile (project 1)
# ---------------------------------------------------------------------------

class ProfileIn(BaseModel):
    # Client sends the version it read; None = blind write (first save).
    version: Optional[int] = None
    name: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    exam_year: Optional[str] = None
    target_rank: Optional[str] = None
    study_hours: Optional[str] = None
    test_exams: Optional[list] = None
    availability: Optional[dict] = None  # {wake, sleep, daily_hours}


def _profile_payload(p: StudentProfile) -> dict:
    import json
    return {
        "name": p.name,
        "major": p.major,
        "grade": p.grade,
        "exam_year": p.exam_year,
        "target_rank": p.target_rank,
        "study_hours": p.study_hours,
        "test_exams": json.loads(p.test_exams or "[]"),
        "availability": json.loads(p.availability or "{}"),
        "version": p.version,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("")
def get_profile(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Read the server-side profile; auto-provisions an empty row so the
    first PATCH has something to update."""
    p = db.query(StudentProfile).filter(
        StudentProfile.user_id == current_user.id).first()
    if not p:
        p = StudentProfile(user_id=current_user.id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return {"profile": _profile_payload(p)}


@router.patch("")
def patch_profile(payload: ProfileIn,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Optimistic-concurrency update. Send the version you read; a stale
    version returns 409 with the current server profile (no lost update)."""
    p = db.query(StudentProfile).filter(
        StudentProfile.user_id == current_user.id).first()
    if not p:
        p = StudentProfile(user_id=current_user.id)
        db.add(p)
        db.commit()
        db.refresh(p)

    if payload.version is not None and payload.version != p.version:
        raise HTTPException(status_code=409, detail={
            "message": "پروفایل روی دستگاه دیگری تغییر کرده است",
            "profile": _profile_payload(p),
        })

    import json
    changed = False
    for field in ("name", "major", "grade", "exam_year",
                  "target_rank", "study_hours"):
        v = getattr(payload, field, None)
        if v is not None:
            setattr(p, field, v)
            changed = True
    if payload.test_exams is not None:
        p.test_exams = json.dumps(payload.test_exams, ensure_ascii=False)
        changed = True
    if payload.availability is not None:
        p.availability = json.dumps(payload.availability, ensure_ascii=False)
        changed = True
    if changed:
        p.version += 1
        db.commit()
        db.refresh(p)
    return {"profile": _profile_payload(p), "conflict": False}


# ---------------------------------------------------------------------------
# Study sessions (project 4)
# ---------------------------------------------------------------------------

class SessionIn(BaseModel):
    subject: str = Field(..., min_length=1)
    topic: Optional[str] = None
    task_id: Optional[int] = None
    plan_item_id: Optional[int] = None
    started_at: Optional[str] = None        # ISO; default = now
    ended_at: Optional[str] = None
    actual_minutes: Optional[int] = Field(None, ge=0, le=1440)
    attempted_questions: Optional[int] = Field(None, ge=0)
    correct_count: Optional[int] = Field(None, ge=0)
    wrong_count: Optional[int] = Field(None, ge=0)
    blank_count: Optional[int] = Field(None, ge=0)
    perceived_difficulty: Optional[int] = Field(None, ge=1, le=5)
    focus_level: Optional[int] = Field(None, ge=1, le=5)
    energy_level: Optional[int] = None
    interruption_count: Optional[int] = Field(None, ge=0)
    completion_status: Literal["planned", "completed", "partially_completed", "missed", "rescheduled"] = "completed"
    logged_via: str = "quick"               # timer | quick | auto_test
    completion_data: Optional[dict] = None  # legacy JSON blob passthrough


@router.get("/sessions")
def list_sessions(days: int = 30,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """The student's real (not just planned) study history, newest first."""
    from datetime import timedelta
    import json as _json
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = db.execute(
        _sa_select(StudySession)
        .where(StudySession.student_id == current_user.id)
        .where(StudySession.created_at >= since)
        .order_by(StudySession.created_at.desc())
        .limit(200)
    ).scalars().all()
    out = []
    for s in rows:
        out.append({
            "id": s.id,
            "task_id": s.task_id,
            "plan_item_id": s.plan_item_id,
            "subject": s.subject_name or (s.subject_id and "درس") or "",
            "topic": s.topic_name or "",
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "actual_minutes": s.actual_minutes or s.duration_minutes,
            "attempted_questions": s.attempted_questions,
            "correct_count": s.correct_count,
            "wrong_count": s.wrong_count,
            "blank_count": s.blank_count,
            "perceived_difficulty": s.perceived_difficulty,
            "focus_level": s.focus_level,
            "energy_level": s.energy_level,
            "completion_status": s.completion_status,
            "logged_via": s.logged_via,
            "completion_data": _json.loads(s.completion_data) if s.completion_data else None,
        })
    return {"count": len(out), "sessions": out}


@router.get("/analytics")
def learning_analytics(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return per-subject evidence for the analytics and confidence views."""
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    stats = defaultdict(lambda: {
        "minutes": 0, "sessions": 0, "attempted": 0,
        "correct": 0, "wrong": 0, "blank": 0,
    })
    sessions = db.query(StudySession).filter(
        StudySession.student_id == current_user.id,
        StudySession.created_at >= since,
    ).all()
    for session in sessions:
        subject = session.subject_name or "عمومی"
        row = stats[subject]
        row["sessions"] += 1
        row["minutes"] += session.actual_minutes or session.duration_minutes or 0
        row["attempted"] += session.attempted_questions or 0
        row["correct"] += session.correct_count or 0
        row["wrong"] += session.wrong_count or 0
        row["blank"] += session.blank_count or 0

    mistakes = db.query(WrongAnswer).filter(
        WrongAnswer.student_id == current_user.id,
        WrongAnswer.created_at >= since,
    ).all()
    for mistake in mistakes:
        row = stats[mistake.subject or "عمومی"]
        if mistake.was_blank:
            row["blank"] += 1
        else:
            row["wrong"] += 1

    subjects = []
    for subject, row in sorted(stats.items()):
        attempted = row["attempted"] + row["wrong"] + row["blank"]
        accuracy = row["correct"] / attempted if attempted else None
        confidence = round(100 * accuracy) if accuracy is not None else None
        subjects.append({"subject": subject, **row, "accuracy": accuracy, "confidence": confidence})
    return {"days": days, "subjects": subjects}


def _sa_select(model):
    from sqlalchemy import select
    return select(model)


@router.post("/sessions")
def create_session(payload: SessionIn,
                   current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Quick-log one real study session. Optional fields stay optional:
    daily logging must be fast, deep data can come later."""
    import json

    def _parse_dt(v: Optional[str]):
        if not v:
            return None
        try:
            parsed = datetime.fromisoformat(v)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            raise HTTPException(status_code=422, detail="تاریخ جلسه نامعتبر است")

    started = _parse_dt(payload.started_at) or datetime.utcnow()
    ended = _parse_dt(payload.ended_at)
    if ended and ended < started:
        raise HTTPException(status_code=422, detail="پایان جلسه باید پس از شروع باشد")
    if not payload.subject.strip():
        raise HTTPException(status_code=422, detail="نام درس لازم است")
    counts = (payload.correct_count, payload.wrong_count, payload.blank_count)
    if payload.attempted_questions is not None and sum(c or 0 for c in counts) > payload.attempted_questions:
        raise HTTPException(status_code=422, detail="تعداد پاسخ‌ها بیشتر از تعداد سوال‌ها است")
    from app.auth.database import Subject, Task
    if payload.task_id is not None:
        task = db.get(Task, payload.task_id)
        if not task or task.student_id != current_user.id:
            raise HTTPException(status_code=404, detail="تکلیف یافت نشد")
    from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(Subject).values(name=payload.subject.strip()).on_conflict_do_nothing(index_elements=[Subject.name]))
    subject = db.query(Subject).filter_by(name=payload.subject.strip()).one()
    minutes = payload.actual_minutes
    if minutes is None and started and ended:
        minutes = max(0, int((ended - started).total_seconds() // 60))

    s = StudySession(
        student_id=current_user.id,
        task_id=payload.task_id,
        plan_item_id=payload.plan_item_id,
        subject_id=subject.id,
        topic_id=None,
        subject_name=payload.subject.strip(),
        topic_name=(payload.topic or "").strip() or None,
        started_at=started,
        ended_at=ended,
        duration_minutes=minutes,
        actual_minutes=minutes,
        attempted_questions=payload.attempted_questions,
        correct_count=payload.correct_count,
        wrong_count=payload.wrong_count,
        blank_count=payload.blank_count,
        perceived_difficulty=payload.perceived_difficulty,
        focus_level=payload.focus_level,
        energy_level=payload.energy_level,
        interruption_count=payload.interruption_count,
        completion_status=payload.completion_status,
        logged_via=payload.logged_via,
        completion_data=json.dumps(payload.completion_data, ensure_ascii=False)
        if payload.completion_data else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    logger.info("Study session %d logged (user %d, via %s, %s min).",
                s.id, current_user.id, payload.logged_via, minutes)
    return {"id": s.id, "logged": True, "actual_minutes": minutes}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int,
                   current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Privacy: a student can remove their own logged session."""
    s = db.get(StudySession, session_id)
    if not s or s.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="یافت نشد")
    db.delete(s)
    db.commit()
    return {"deleted": True}


class ProgressIn(BaseModel):
    client_ref: str = Field(min_length=1, max_length=200)
    source_ref: Optional[str] = Field(default=None, max_length=200)
    date: date
    subject: str = Field(min_length=1, max_length=100)
    topic: str = Field(default="", max_length=300)
    task_type: Literal["study", "test", "review", "practice"] = "study"
    planned_minutes: int = Field(ge=1, le=1440)
    actual_minutes: int = Field(default=0, ge=0, le=1440)
    status: Literal["planned", "completed", "partially_completed", "missed", "rescheduled"]


@router.put("/progress")
def save_progress(payload: ProgressIn, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    from app.auth.database import TaskProgress
    from sqlalchemy.dialects.sqlite import insert
    values = payload.model_dump()
    statement = insert(TaskProgress).values(student_id=current_user.id, **values)
    statement = statement.on_conflict_do_update(
        index_elements=[TaskProgress.student_id, TaskProgress.client_ref],
        set_={**values, "updated_at": datetime.utcnow()})
    db.execute(statement)
    db.commit()
    return {"saved": True}


class ExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date: date
    subjects: list[str] = Field(min_length=1)


@router.post("/exams")
def add_exam(payload: ExamIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.auth.database import Assessment
    import json
    if payload.date < date.today():
        raise HTTPException(status_code=422, detail="تاریخ آزمون باید امروز یا آینده باشد")
    row = Assessment(student_id=current_user.id, title=payload.title, date=payload.date,
                     source="scheduled_mock", results=json.dumps({"subjects": payload.subjects}, ensure_ascii=False))
    db.add(row)
    db.commit()
    return {"id": row.id}
