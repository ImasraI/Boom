"""Replanning & backlog policy (growth-readiness project 3).

Pure, deterministic, no LLM. A missed task is NOT just copied to tomorrow:
the policy decides per the roadmap document:

    if completion_ratio >= 0.8:           -> completed
    elif deadline_is_close:               -> keep full size, still capacity-capped
    elif missed_count_for_task >= 2:      -> shrink + schedule diagnostic review
    elif daily_adherence < 0.6:           -> reduce next-day capacity

And the backlog is BOUNDED: resolve_backlog() fills tomorrow up to real
capacity by priority and explicitly drops the overflow with a visible note -
it never silently accumulates an impossible plan.
"""
from __future__ import annotations

from typing import Any, Optional

COMPLETION_RATIO_DONE = 0.8      # >= 80% done counts as completed
ADHERENCE_CAPACITY_CUT = 0.6     # week adherence below this shrinks capacity
CAPACITY_FLOOR_RATIO = 0.5       # but capacity never shrinks below half
MIN_TASK_MINUTES = 25            # shrunken tasks never go below this
MAX_MISSES_BEFORE_SHRINK = 2     # miss twice -> the task was probably too big

# All task statuses the system understands (roadmap section 3).
TASK_STATUSES = (
    "planned",
    "in_progress",
    "completed",
    "partially_completed",
    "missed",
    "skipped_by_student",
    "cancelled_by_planner",
    "rescheduled",
)


def completion_ratio(
    planned_minutes: int, actual_minutes: Optional[int],
    planned_count: Optional[int] = None, completed_count: Optional[int] = None,
) -> float:
    """Best available completion ratio in 0..1 (minutes- or count-based)."""
    if planned_count and completed_count is not None and planned_count > 0:
        return max(0.0, min(1.0, completed_count / planned_count))
    if planned_minutes and actual_minutes is not None and planned_minutes > 0:
        return max(0.0, min(1.0, actual_minutes / planned_minutes))
    return 0.0


def classify_status(
    planned_minutes: int, actual_minutes: Optional[int],
    planned_count: Optional[int] = None, completed_count: Optional[int] = None,
) -> str:
    """Honest status for a report - never guesses 'completed' from a blank."""
    ratio = completion_ratio(planned_minutes, actual_minutes,
                             planned_count, completed_count)
    if actual_minutes is None and completed_count is None:
        return "missed"          # no report at all
    if ratio <= 0.0:
        return "missed"          # reported, but nothing got done
    if ratio >= COMPLETION_RATIO_DONE:
        return "completed"
    return "partially_completed"


def replan_decision(
    task: dict,
    *,
    capacity_left_minutes: int,
    missed_count: int,
    days_to_deadline: Optional[int],
    adherence: float = 1.0,
) -> dict:
    """Decide what to do with ONE missed task.

    `task` needs: planned_minutes, priority (0..1, optional).
    Returns {action, new_minutes, note} - actions: keep | shrink | drop.
    Deterministic for identical inputs.
    """
    minutes = int(task.get("planned_minutes") or 0)
    priority = float(task.get("priority") or 0.0)

    capacity = max(0, capacity_left_minutes)
    if capacity == 0 or minutes <= 0:
        return {"action": "drop", "new_minutes": None,
                "note": "ظرفیت آزاد وجود ندارد؛ نیازمند بازبینی زمان یا اولویت است"}
    desired = minutes
    if not (days_to_deadline is not None and days_to_deadline <= 2):
        if missed_count >= MAX_MISSES_BEFORE_SHRINK or (adherence < ADHERENCE_CAPACITY_CUT and minutes > 60):
            desired = min(minutes, max(MIN_TASK_MINUTES, int(minutes * 0.6)))
    allocated = min(desired, capacity)
    if allocated < minutes:
        return {"action": "shrink", "new_minutes": allocated,
                "note": f"{allocated} دقیقه در ظرفیت آزاد جا شد؛ {minutes - allocated} دقیقه نیازمند بازبینی است"}
    return {"action": "keep", "new_minutes": None, "note": "در ظرفیت آزاد منتقل شد"}


def next_day_capacity(daily_capacity_minutes: int, adherence: float) -> int:
    """Capacity for tomorrow: a bad week shrinks the load, with a floor."""
    daily_capacity_minutes = max(0, daily_capacity_minutes)
    if adherence >= ADHERENCE_CAPACITY_CUT:
        return int(daily_capacity_minutes)
    floor = int(daily_capacity_minutes * CAPACITY_FLOOR_RATIO)
    return max(floor, int(daily_capacity_minutes * max(0.25, adherence)))


def resolve_backlog(
    missed_tasks: list,
    *,
    capacity_minutes: int,
    adherence: float = 1.0,
) -> dict:
    """Fit ALL missed tasks into tomorrow's real capacity, by priority.

    Overflow is explicitly dropped (with a note) - never silently carried,
    so the plan stays possible. Deterministic: ties broken by (priority desc,
    id asc, planned_minutes desc).

    missed_tasks item: {id, description, subject, planned_minutes, priority,
                        missed_count, days_to_deadline(optional), ...}
    Returns {carried: [...], shrunk: [...], dropped: [...], capacity_minutes}
    """
    cap = next_day_capacity(capacity_minutes, adherence)
    order = sorted(
        missed_tasks,
        key=lambda t: (
            0 if t.get("days_to_deadline") is not None and t["days_to_deadline"] <= 2 else 1,
            -float(t.get("priority") or 0.0),
            str(t.get("id") or ""),
            -int(t.get("planned_minutes") or 0),
        ),
    )
    carried: list = []
    shrunk: list = []
    dropped: list = []
    left = cap
    for t in order:
        d = replan_decision(
            t,
            capacity_left_minutes=left,
            missed_count=int(t.get("missed_count") or 0),
            days_to_deadline=t.get("days_to_deadline"),
            adherence=adherence,
        )
        row = dict(t)
        row["decision"] = d
        if d["action"] == "drop":
            dropped.append(row)
            continue
        if d["action"] == "shrink" and d["new_minutes"]:
            left -= int(d["new_minutes"])
            shrunk.append(row)
        else:  # keep
            left -= min(int(t.get("planned_minutes") or 0), max(left, 0))
            carried.append(row)
    return {"carried": carried, "shrunk": shrunk, "dropped": dropped,
            "capacity_minutes": cap}
