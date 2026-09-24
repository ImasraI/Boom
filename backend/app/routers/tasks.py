from datetime import date
from typing import Any, Optional, cast
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db
from app.auth.database import User, DailyTask
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
    from datetime import datetime, timedelta
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
