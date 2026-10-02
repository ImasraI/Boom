from datetime import date, datetime, timedelta
from typing import Any, Optional, cast
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db
from app.auth.database import User, DailyTask, WrongAnswer, StudySession, ReviewLog
from app.planner.replan import (classify_status, completion_ratio,
                                resolve_backlog, replan_decision)
from app.rag.llm import get_llm_client
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = get_logger(__name__)


class TaskCreate(BaseModel):
    date: str  # YYYY-MM-DD
    subject: str
    task_type: str
    description: str
    duration_minutes: int


class TaskUpdate(BaseModel):
    completed: Optional[bool] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    date: str
    subject: str
    task_type: str
    description: str
    duration_minutes: int
    completed: bool


class UpdatePlanRequest(BaseModel):
    instruction: str
    context: Optional[dict] = None


@router.get("/daily/{date_str}")
def get_daily_tasks(
    date_str: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tasks for a specific date."""
    try:
        task_date = date.fromisoformat(date_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}
    
    tasks = db.query(DailyTask).filter(
        DailyTask.user_id == current_user.id,
        DailyTask.date == task_date
    ).all()
    
    return {
        "date": date_str,
        "tasks": [
            TaskResponse(
                id=cast(int, t.id),
                date=cast(Any, t.date).isoformat(),
                subject=cast(str, t.subject),
                task_type=cast(str, t.task_type),
                description=cast(str, t.description),
                duration_minutes=cast(int, t.duration_minutes),
                completed=cast(bool, t.completed)
            ) for t in tasks
        ]
    }


@router.post("/daily")
def create_task(
    task: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new task."""
    try:
        task_date = date.fromisoformat(task.date)
    except ValueError:
        return {"error": "Invalid date format"}
    
    new_task = DailyTask(
        user_id=cast(int, current_user.id),
        date=task_date,
        subject=task.subject,
        task_type=task.task_type,
        description=task.description,
        duration_minutes=task.duration_minutes
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    return {"id": new_task.id, "message": "Task created"}


@router.patch("/daily/{task_id}")
def update_task(
    task_id: int,
    update: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a task."""
    task = db.query(DailyTask).filter(
        DailyTask.id == task_id,
        DailyTask.user_id == current_user.id
    ).first()
    
    if not task:
        return {"error": "Task not found"}
    
    task_row: Any = task
    if update.completed is not None:
        task_row.completed = update.completed
    if update.description:
        task_row.description = update.description
    if update.duration_minutes:
        task_row.duration_minutes = update.duration_minutes
    
    db.commit()
    return {"message": "Task updated"}


@router.delete("/daily/{task_id}")
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a task."""
    task = db.query(DailyTask).filter(
        DailyTask.id == task_id,
        DailyTask.user_id == current_user.id
    ).first()
    
    if not task:
        return {"error": "Task not found"}
    
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}


@router.post("/update-plan")
def update_plan_with_ai(
    request: UpdatePlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Use AI to update the task plan based on user instruction."""
    
    # Get upcoming tasks for context
    from datetime import timedelta
    today = date.today()
    week_ahead = today + timedelta(days=7)
    
    tasks = db.query(DailyTask).filter(
        DailyTask.user_id == current_user.id,
        DailyTask.date >= today,
        DailyTask.date <= week_ahead
    ).all()
    
    task_context = "\n".join([
        f"- {t.date.isoformat()}: {t.subject} - {t.description} ({t.duration_minutes} دقیقه)"
        for t in tasks
    ])
    
    prompt = f"""تو «بوم» هستی؛ دستیار برنامه‌ریزی مطالعه.
کاربر می‌خواهد برنامه‌اش را تغییر دهد.

وظایف فعلی هفته آینده:
{task_context or 'برنامه‌ای وجود ندارد'}

درخواست کاربر: {request.instruction}

بر اساس این درخواست، تغییرات مورد نیاز را به صورت JSON برگردان:
{{
  "action": "delete" یا "update" یا "add",
  "changes": [
    {{"task_id": شناسه وظیفه (برای delete/update), "date": "YYYY-MM-DD", "subject": "نام درس", "description": "شرح", "duration_minutes": عدد}}
  ]
}}

فقط JSON برگردان، بدون توضیح اضافه."""

    try:
        llm_response = get_llm_client().generate(
            [{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        # Try to parse JSON from response
        import json
        import re
        json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
        if json_match:
            changes = json.loads(json_match.group())
            
            # Apply changes
            action = changes.get("action")
            modifications = changes.get("changes", [])
            
            applied = []
            for mod in modifications:
                if action == "delete" and "task_id" in mod:
                    task = db.query(DailyTask).filter(
                        DailyTask.id == mod["task_id"],
                        DailyTask.user_id == current_user.id
                    ).first()
                    if task:
                        db.delete(task)
                        applied.append(f"حذف: {task.description}")
                
                elif action == "update" and "task_id" in mod:
                    task = db.query(DailyTask).filter(
                        DailyTask.id == mod["task_id"],
                        DailyTask.user_id == current_user.id
                    ).first()
                    if task:
                        if "description" in mod:
                            task.description = mod["description"]
                        if "duration_minutes" in mod:
                            task.duration_minutes = mod["duration_minutes"]
                        applied.append(f"به‌روزرسانی: {task.description}")
                
                elif action == "add":
                    new_task = DailyTask(
                        user_id=current_user.id,
                        date=date.fromisoformat(mod["date"]),
                        subject=mod.get("subject", ""),
                        task_type=mod.get("task_type", "study"),
                        description=mod.get("description", ""),
                        duration_minutes=mod.get("duration_minutes", 60)
                    )
                    db.add(new_task)
                    applied.append(f"افزوده: {new_task.description}")
            
            db.commit()
            return {
                "success": True,
                "message": f"{len(applied)} تغییر اعمال شد",
                "applied": applied
            }
        
        return {"success": False, "message": "پاسخ نامعتبر از AI", "raw": llm_response}
    
    except Exception as e:
        logger.error(f"AI plan update failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Replanning & backlog (growth-readiness project 3)
# ---------------------------------------------------------------------------

VALID_REPORT_REASONS = {
    "no_time", "task_too_hard", "tired", "forgot", "lost_focus",
    "resources_missing", "other",
}


class TaskReport(BaseModel):
    actual_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    completed_count: Optional[int] = Field(default=None, ge=0)
    planned_count: Optional[int] = Field(default=None, ge=0)
    reason: Optional[str] = None   # one of VALID_REPORT_REASONS
    energy: Optional[int] = Field(default=None, ge=1, le=5)


class ReplanRequest(BaseModel):
    capacity_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    adherence: Optional[float] = Field(default=None, ge=0, le=1)


def _task_dict(t: DailyTask) -> dict:
    row: Any = t
    return {
        "id": t.id,
        "date": cast(Any, t.date).isoformat(),
        "subject": t.subject,
        "task_type": t.task_type,
        "description": t.description,
        "duration_minutes": t.duration_minutes,
        "completed": bool(t.completed),
        "status": row.status or "planned",
        "actual_minutes": row.actual_minutes,
        "completed_count": row.completed_count,
        "planned_count": row.planned_count,
        "reason": row.reason,
        "replan_note": row.replan_note,
        "miss_count": row.miss_count or 0,
    }


def _week_adherence(db: Session, user_id: int) -> float:
    """Completed/planned minutes over the last 7 days (floor 0.25).

    Tasks with no report (still 'planned', date passed) count as missed -
    an honest adherence number must include silence.
    """
    since = date.today() - timedelta(days=7)
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id,
        DailyTask.date >= since,
        DailyTask.date < date.today(),
    ).all()
    planned = 0
    done = 0
    for t in rows:
        row: Any = t
        st: str = row.status or "planned"
        duration = cast(int, row.duration_minutes)
        actual_minutes = cast(Optional[int], row.actual_minutes)
        if st not in ("cancelled_by_planner", "rescheduled"):
            planned += duration
        if st == "completed":
            done += actual_minutes if actual_minutes is not None else duration
        elif st == "partially_completed":
            done += actual_minutes or 0
    if planned <= 0:
        return 1.0
    return min(1.0, max(0.25, done / planned))


@router.patch("/daily/{task_id}/report")
def report_task(
    task_id: int,
    report: TaskReport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Honest completion report for one task.

    Records what ACTUALLY happened (not just a checkbox), classifies the
    status, and bumps miss_count so the replanner can shrink chronically
    missed work. Returns the decision that WILL happen on replan.
    """
    t = db.query(DailyTask).filter(
        DailyTask.id == task_id,
        DailyTask.user_id == current_user.id,
    ).first()
    if not t:
        return {"error": "Task not found"}
    row: Any = t
    if report.reason is not None and report.reason not in VALID_REPORT_REASONS:
        return {"error": f"reason must be one of {sorted(VALID_REPORT_REASONS)}"}

    row.actual_minutes = report.actual_minutes
    row.completed_count = report.completed_count
    row.planned_count = report.planned_count
    row.reason = report.reason
    duration = cast(int, row.duration_minutes)
    ratio = completion_ratio(duration, report.actual_minutes,
                             report.planned_count, report.completed_count)
    status = classify_status(duration, report.actual_minutes,
                             report.planned_count, report.completed_count)
    row.status = status
    if status == "completed":
        row.completed = True
        row.miss_count = 0
    elif status == "partially_completed":
        row.replan_note = (
            f"{int(ratio * 100)}٪ انجام شد؛ باقی‌مانده به فردا می‌رود")
    else:  # missed
        row.miss_count = (row.miss_count or 0) + 1
        row.replan_note = "انجام نشد؛ در بازبرنامه‌ریزی تصمیم گرفته می‌شود"
    if report.energy is not None:
        row.replan_note = ((row.replan_note or "") +
                           f" | انرژی: {report.energy}/5").strip(" |")
    db.commit()

    # Preview the decision (the actual move happens in /replan).
    d = replan_decision(
        {"planned_minutes": duration,
         "priority": 0.5 + 0.5 * ratio},
        capacity_left_minutes=max(0, duration - (report.actual_minutes or 0)),
        missed_count=row.miss_count or 0,
        days_to_deadline=None,
    )
    return {"task": _task_dict(t), "decision": d}


@router.post("/replan")
def replan_backlog(
    request: ReplanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve ALL unresolved backlog into tomorrow's real capacity.

    Carries/shrinks/drops missed + partially-completed remainders by
    priority. Dropped items get status cancelled_by_planner + a visible
    note - the plan never becomes silently impossible. Also marks past
    'planned' tasks with no report as missed first (silence = missed).
    """
    today = date.today()
    adherence = (request.adherence if request.adherence is not None
                 else _week_adherence(db, cast(int, current_user.id)))
    adherence = min(1.0, max(0.0, adherence))

    # 1) Silence on past days counts as missed (honest backlog).
    stale = db.query(DailyTask).filter(
        DailyTask.user_id == current_user.id,
        DailyTask.date < today,
        DailyTask.status == "planned",
        DailyTask.completed == False,  # noqa: E712
    ).all()
    for t in stale:
        row_a: Any = t
        row_a.status = "missed"
        row_a.miss_count = (row_a.miss_count or 0) + 1
        row_a.replan_note = "گزارشی ثبت نشد؛ غلط‌شده محسوب شد"
    db.flush()  # SessionLocal uses autoflush=False; the next query must see these

    # 2) Collect the backlog: missed tasks + partial remainders.
    candidates = db.query(DailyTask).filter(
        DailyTask.user_id == current_user.id,
        DailyTask.status.in_(["missed", "partially_completed"]),
    ).order_by(DailyTask.date.asc()).all()

    def _remaining_minutes(t: DailyTask) -> int:
        row: Any = t
        status: str = row.status or ""
        actual_minutes = cast(Optional[int], row.actual_minutes)
        duration = cast(int, row.duration_minutes)
        if status == "partially_completed" and actual_minutes is not None:
            return max(0, duration - actual_minutes)
        return duration

    def _miss_count(t: DailyTask) -> int:
        row: Any = t
        return cast(int, row.miss_count or 0)

    backlog = [{
        "id": t.id,
        "description": t.description,
        "subject": t.subject,
        "planned_minutes": max(1, _remaining_minutes(t)),
        "priority": 0.5 + (0.2 if _miss_count(t) >= 2 else 0.0),
        "missed_count": _miss_count(t),
        "days_to_deadline": None,
    } for t in candidates]

    capacity = request.capacity_minutes if request.capacity_minutes is not None else 180
    result = resolve_backlog(backlog, capacity_minutes=capacity,
                             adherence=adherence)

    tomorrow = today + timedelta(days=1)
    applied = {"carried": [], "shrunk": [], "dropped": []}
    by_id = {t.id: t for t in candidates}

    for kind in ("carried", "shrunk", "dropped"):
        for item in result[kind]:
            t = by_id.get(item["id"])
            if not t:
                continue
            row_b: Any = t
            decision = item["decision"]
            if kind == "dropped":
                row_b.status = "cancelled_by_planner"
            else:
                row_b.status = "rescheduled"
                row_b.date = tomorrow
                row_b.completed = False
                # Only the REMAINING work moves: a partially-completed task
                # carries what is left, not its original size.
                row_b.duration_minutes = int(
                    decision.get("new_minutes") or item["planned_minutes"])
                row_b.actual_minutes = 0
            row_b.replan_note = decision.get("note", "")
            applied[kind].append({"id": t.id, "description": t.description,
                                  "minutes": row_b.duration_minutes,
                                  "note": row_b.replan_note})
    db.commit()

    return {
        "tomorrow": tomorrow.isoformat(),
        "adherence": round(adherence, 2),
        "capacity_minutes": result["capacity_minutes"],
        **applied,
        "message": (
            f"{len(applied['carried']) + len(applied['shrunk'])} تکلیف به فردا منتقل شد، "
            f"{len(applied['dropped'])} تکلیف کم‌اولویت حذف شد تا برنامه واقعی بماند"
            if applied["dropped"] else
            f"{len(applied['carried']) + len(applied['shrunk'])} تکلیف برای فردا برنامه‌ریزی شد"
        ),
    }


@router.get("/backlog")
def get_backlog(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview the backlog without applying anything."""
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == current_user.id,
        DailyTask.date < today,
        DailyTask.status.in_(["planned", "missed", "partially_completed"]),
    ).order_by(DailyTask.date.asc()).all()
    return {
        "tasks": [_task_dict(t) for t in rows],
        "total_minutes": sum(t.duration_minutes for t in rows),
        "adherence": _week_adherence(db, cast(int, current_user.id)),
    }


@router.get("/review-queue")
def review_queue(
    limit: int = 12,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a deterministic spaced-review queue from recent mistakes.

    A topic advances through 1, 3, 7, 14 and 30-day intervals. A later
    completed study session resets the topic's next review from that session,
    while repeated mistakes increase urgency and keep the item visible.
    """
    limit = max(1, min(limit, 50))
    rows = db.query(WrongAnswer).filter(
        WrongAnswer.student_id == current_user.id,
    ).order_by(WrongAnswer.created_at.desc()).limit(200).all()
    latest = {}
    for row in rows:
        key = (row.subject, row.topic or "مرور مباحث")
        latest.setdefault(key, row)

    sessions = db.query(StudySession).filter(
        StudySession.student_id == current_user.id,
        StudySession.completion_status == "completed",
    ).all()
    completed_at = {}
    for session in sessions:
        key = (session.subject_name or "", session.topic_name or "مرور مباحث")
        completed_at[key] = max(completed_at.get(key, datetime.min), session.created_at or datetime.min)
    reviews = db.query(ReviewLog).filter(
        ReviewLog.student_id == current_user.id,
    ).all()
    for review in reviews:
        key = (review.subject, review.topic)
        completed_at[key] = max(completed_at.get(key, datetime.min), review.created_at or datetime.min)

    intervals = (1, 3, 7, 14, 30)
    today = date.today()
    result = []
    for (subject, topic), row in latest.items():
        created = row.created_at or datetime.utcnow()
        days_old = max(0, (today - created.date()).days)
        repetitions = sum(
            1 for candidate in rows
            if candidate.subject == subject and (candidate.topic or "مرور مباحث") == topic
        )
        interval = intervals[min(repetitions - 1, len(intervals) - 1)]
        last_review = completed_at.get((subject, topic))
        anchor = max(created, last_review) if last_review else created
        due_date = anchor.date() + timedelta(days=interval)
        result.append({
            "subject": subject,
            "topic": topic,
            "book": row.book,
            "page": row.page,
            "question_text": row.question_text,
            "due_date": due_date.isoformat(),
            "due": due_date <= today,
            "days_overdue": max(0, (today - due_date).days),
            "repetitions": repetitions,
            "was_blank": bool(row.was_blank),
        })
    result.sort(key=lambda item: (not item["due"], item["due_date"], -item["repetitions"], item["subject"], item["topic"]))
    return {"today": today.isoformat(), "items": result[:limit]}


class ReviewComplete(BaseModel):
    subject: str = Field(..., min_length=1, max_length=120)
    topic: str = Field(..., min_length=1, max_length=200)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


@router.post("/review-queue/complete")
def complete_review(
    payload: ReviewComplete,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a review so the next interval starts from this event."""
    row = ReviewLog(
        student_id=current_user.id,
        subject=payload.subject.strip(),
        topic=payload.topic.strip(),
        rating=payload.rating,
    )
    db.add(row)
    db.commit()
    created_at = cast(Optional[datetime], row.created_at)
    return {"ok": True, "reviewed_at": created_at.isoformat() if created_at else None}
