"""Deterministic planner engine (growth-readiness project 2).

A plain, fully testable heuristic scheduler - no LLM in the loop:

    candidate tasks -> priority -> constraint-fit into free slots ->
    hard-constraint validation -> explanations

Hard constraints (NEVER violated, asserted by tests):
  - no overlap with fixed events (school/classes) or other scheduled items
  - nothing outside the wake..sleep window; never over daily free minutes
  - max contiguous study minutes per block (long tasks are SPLIT)
  - a test for a topic is never scheduled before that topic was studied
    (in this plan or in the student's session history)
  - never schedules a resource the student does not own

Soft constraints (scored, may bend):
  - heavy subjects not back-to-back; review near its study; weak subjects
    get a larger share (priority weights do this)

Same input -> same output, always. LLMs may only PROPOSE edits which are
re-validated here (later project).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Data shapes (plain dicts/dataclasses - no ORM coupling, easy to test)
# ---------------------------------------------------------------------------

@dataclass
class FixedEvent:
    """School/class/anything immovable, for one date."""
    date: str            # YYYY-MM-DD
    start: str           # HH:MM
    end: str             # HH:MM
    title: str = ""
    kind: str = "class"  # class | school | exam | other


@dataclass
class CandidateTask:
    """One thing the planner may schedule."""
    id: str
    subject: str
    topic: str = ""
    task_type: str = "study"          # study | test | review | practice
    planned_minutes: int = 60
    target_count: int = 0             # questions for test/practice tasks
    resource: str = ""                # empty = no resource needed
    deadline: Optional[str] = None    # YYYY-MM-DD, exam urgency
    preferred_deadline: Optional[str] = None  # preparation priority; later consolidation is allowed
    weakness: float = 0.0             # 0..1 (from mastery/wrong-answer data)
    forgetting_risk: float = 0.0      # 0..1 (days since last practice)
    overdue: float = 0.0              # 0..1 backlog pressure
    user_preference: float = 0.0      # 0..1
    reason: str = ""                  # human-facing, shown in the UI


@dataclass
class PlannerInput:
    profile: dict                     # wake, sleep, daily_hours per weekday
    fixed_events: list = field(default_factory=list)   # [FixedEvent-like dicts]
    tasks: list = field(default_factory=list)          # [CandidateTask-like dicts]
    studied_topics: set = field(default_factory=set)   # topics with real sessions
    max_block_minutes: int = 90
    default_break_minutes: int = 15
    # Thin-fragment policy, set by the caller (NOT the engine's opinion): a
    # task whose total slightly exceeds the block cap used to be emitted as a
    # stub part - 105 minutes became 90+15, 120 became 90+30 - and those stubs
    # are unreadable on the week grid, often spilling into the next day as a
    # lone 15-minute block (the "weekly plan is full of 30-minute blocks"
    # report). With a policy set, a block absorbs its own leftover up to
    # hard_max_block_minutes, and a leftover below min_block_minutes that is
    # only a FRAGMENT of a longer task is not emitted at all: those minutes
    # stay unscheduled (and are reported) instead of becoming a block the
    # student cannot use. 0 disables both, which is what an explicit
    # user-chosen block length (25-minute pomodoro, say) requires.
    min_block_minutes: int = 0
    hard_max_block_minutes: int = 0
    # ISO date the plan starts from. Default = today. Set explicitly in
    # tests/simulations so plans are reproducible regardless of clock.
    start_date: Optional[str] = None
    balance_subjects: bool = False


@dataclass
class PlannedItem:
    id: str
    subject: str
    topic: str
    task_type: str
    date: str
    start: str
    end: str
    planned_minutes: int
    target_count: int
    resource: str
    priority: float
    reason: str
    part: int = 1                     # 1 when not split, else 1..n
    parts: int = 1


@dataclass
class PlannerResult:
    items: list = field(default_factory=list)          # [PlannedItem dicts]
    warnings: list = field(default_factory=list)
    unscheduled: list = field(default_factory=list)    # [{id, reason}]
    explanations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "items": [dict(i) for i in self.items],
            "warnings": self.warnings,
            "unscheduled": self.unscheduled,
            "explanations": self.explanations,
        }


# ---------------------------------------------------------------------------
# Priority (the documented heuristic)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "exam_urgency": 0.30,
    "weakness": 0.25,
    "prerequisite_importance": 0.15,
    "overdue": 0.15,
    "forgetting_risk": 0.10,
    "user_preference": 0.05,
}


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _exam_urgency(task: dict, horizon_days: int = 14, reference_date=None) -> float:
    deadline = task.get("deadline") or task.get("preferred_deadline")
    if not deadline:
        return 0.0
    try:
        dl = datetime.fromisoformat(deadline).date()
    except ValueError:
        return 0.0
    days = (dl - (reference_date or datetime.now().date())).days
    if days < 0:
        return 1.0
    if days > horizon_days:
        return 0.0
    return 1.0 - (days / horizon_days)


def priority_of(task: dict, reference_date=None) -> float:
    """Deterministic 0..1 priority from the documented weights."""
    p = (
        WEIGHTS["exam_urgency"] * _exam_urgency(task, reference_date=reference_date)
        + WEIGHTS["weakness"] * float(task.get("weakness") or 0)
        + WEIGHTS["prerequisite_importance"]
        * (1.0 if task.get("task_type") == "study" else 0.0)
        + WEIGHTS["overdue"] * float(task.get("overdue") or 0)
        + WEIGHTS["forgetting_risk"] * float(task.get("forgetting_risk") or 0)
        + WEIGHTS["user_preference"] * float(task.get("user_preference") or 0)
    )
    return round(max(0.0, min(1.0, p)), 4)


# ---------------------------------------------------------------------------
# Slot machinery
# ---------------------------------------------------------------------------

def _overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


def _free_slots_for_day(day: datetime, profile: dict, fixed: list,
                        min_block: int = 30) -> list:
    """Wake..sleep minus fixed events -> [(start_dt, end_dt)] descending
    priority order (chronological)."""
    wake = _parse_hhmm(profile.get("wake") or "06:30")
    sleep = _parse_hhmm(profile.get("sleep") or "23:00")
    day_start = datetime.combine(day.date(), wake)
    day_end = datetime.combine(day.date(), sleep)
    if day_end <= day_start:  # past-midnight sleep window
        day_end += timedelta(days=1)

    events = []
    for ev in fixed:
        ev_day = datetime.fromisoformat(ev["date"]).date()
        ev_start = datetime.combine(ev_day, _parse_hhmm(ev["start"]))
        ev_end = datetime.combine(ev_day, _parse_hhmm(ev["end"]))
        if ev_end <= ev_start:
            ev_end += timedelta(days=1)
        if ev_start < day_end and ev_end > day_start:
            events.append((max(ev_start, day_start), min(ev_end, day_end)))
    events.sort()

    slots, cursor = [], day_start
    for ev_start, ev_end in events:
        if ev_start > cursor:
            slots.append((cursor, min(ev_start, day_end)))
        cursor = max(cursor, ev_end)
        if cursor >= day_end:
            break
    if cursor < day_end:
        slots.append((cursor, day_end))
    return [(s, e) for s, e in slots if (e - s).total_seconds() / 60 >= min_block]


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def generate_plan(inp: PlannerInput) -> PlannerResult:
    """Greedy highest-priority-first fit into free slots. Deterministic:
    ties break by (subject, topic, id) so the same input replays exactly."""
    result = PlannerResult()
    today = (datetime.fromisoformat(inp.start_date) if inp.start_date else
             datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    tasks = sorted([dict(t) for t in inp.tasks], key=lambda t: (
        -priority_of(t, today.date()), t.get("subject", ""),
        t.get("topic", ""), t.get("id", "")))
    daily_hours = inp.profile.get("daily_hours") or {}
    max_block = max(1, int(inp.max_block_minutes))
    min_fragment = max(0, int(inp.min_block_minutes))
    hard_max = max(max_block, int(inp.hard_max_block_minutes) or max_block)
    break_minutes = max(0, int(inp.default_break_minutes))
    studied = set(inp.studied_topics or set())
    finished_tasks = set()
    for t in tasks:
        t["_remaining"] = max(0, int(t.get("planned_minutes", 60)))
        t["_total"] = t["_remaining"]
        t["_items"] = []
        if t.get("resource") and not t.get("resource_owned", True):
            t["_blocked"] = "resource_not_owned"

    def ready(t):
        if t.get("requires_task") and t["requires_task"] not in finished_tasks:
            return False
        key = (t.get("subject", ""), t.get("topic", ""))
        return (t.get("task_type", "study") != "test" or not t.get("topic")
                or key in studied or t["topic"] in studied)

    def fitting_block(task, room):
        block = min(task["_remaining"], max_block, room)
        if min_fragment and 0 < task["_remaining"] - block < min_fragment:
            if task["_remaining"] <= hard_max and task["_remaining"] <= room:
                block = task["_remaining"]
            elif min_fragment <= task["_remaining"] - min_fragment <= room:
                block = task["_remaining"] - min_fragment
            else:
                return 0  # 45 in a 30-minute gap would strand a 15-minute tail.
        if min_fragment and block < min_fragment and task["_total"] >= min_fragment:
            return 0
        return max(0, block)

    for offset in range(7):
        day = today + timedelta(days=offset)
        date_key = day.strftime("%Y-%m-%d")
        raw = daily_hours.get(str(day.weekday()), daily_hours.get(day.weekday(), daily_hours.get("*")))
        # Missing availability means the waking window; explicit zero is rest.
        capacity = max(0, int(float(raw) * 60)) if raw is not None else 24 * 60
        used = 0
        subject_minutes = {}
        for start, end in _free_slots_for_day(day, inp.profile, inp.fixed_events, min_block=1):
            cursor = start
            while cursor < end and used < capacity:
                eligible = [t for t in tasks if t["_remaining"] > 0
                             and not t.get("_blocked") and ready(t)
                             and (not t.get("not_before") or date_key >= t["not_before"])
                             and (not t.get("deadline") or date_key <= t["deadline"])]
                if inp.balance_subjects:
                    eligible.sort(key=lambda t: (
                        0 if t.get("overdue") else 1,
                        subject_minutes.get(t.get("subject", ""), 0) / (0.5 + float(t.get("weakness") or 0)),
                        tasks.index(t)))
                room = min(capacity - used,
                           int((end - cursor).total_seconds() // 60))
                choice = next(((t, fitting_block(t, room)) for t in eligible if fitting_block(t, room) > 0), None)
                if choice is None:
                    break
                task, block = choice
                part = len(task["_items"]) + 1
                total_count = max(0, int(task.get("target_count") or 0))
                completed = task["_total"] - task["_remaining"]
                # Allocate questions proportionally without duplicating totals.
                count = (total_count * (completed + block) // task["_total"]
                         - total_count * completed // task["_total"])
                finish = cursor + timedelta(minutes=block)
                item = {
                    "id": f'{task["id"]}#p{part}',
                    "subject": task.get("subject", ""), "topic": task.get("topic", ""),
                    "task_type": task.get("task_type", "study"),
                    "date": cursor.date().isoformat(), "start": _fmt(cursor),
                    "end": _fmt(finish), "end_date": finish.date().isoformat(),
                    "planned_minutes": block, "target_count": count,
                    "resource": task.get("resource", ""),
                    "priority": priority_of(task, today.date()),
                    "reason": task.get("reason", ""), "part": part, "parts": part,
                }
                if task.get("preferred_deadline"):
                    item["preferred_deadline"] = task["preferred_deadline"]
                result.items.append(item)
                task["_items"].append(item)
                task["_remaining"] -= block
                used += block
                subject_minutes[task.get("subject", "")] = subject_minutes.get(task.get("subject", ""), 0) + block
                cursor = finish + timedelta(minutes=break_minutes)
                if task["_remaining"] == 0:
                    finished_tasks.add(task["id"])
                    if task.get("task_type", "study") == "study" and task.get("topic"):
                        studied.add((task.get("subject", ""), task["topic"]))
                    result.explanations.append(
                        f'{task.get("subject", "")} {task.get("topic", "")}: '
                        f'{priority_of(task, today.date()):.2f} - {task.get("reason", "")}')
        if used >= 360:
            result.warnings.append(f"{date_key}: heavy study load ({used} minutes).")

    for task in tasks:
        for item in task["_items"]:
            item["parts"] = len(task["_items"])
        if task.get("_blocked"):
            result.unscheduled.append({"id": task["id"], "reason": task["_blocked"]})
        elif task["_remaining"]:
            reason = "no_capacity_this_week" if ready(task) else ("dependency_not_scheduled" if task.get("requires_task") else "test_before_study")
            entry = {"id": task["id"], "reason": reason}
            if reason == "no_capacity_this_week":
                entry["remaining_minutes"] = task["_remaining"]
            result.unscheduled.append(entry)
    return result


# ---------------------------------------------------------------------------
# Validators (agent proposals MUST pass these before being applied)
# ---------------------------------------------------------------------------

def validate_plan_items(items: list, profile: dict, fixed_events: list,
                        daily_cap: Optional[int] = None) -> dict:
    """Hard-constraint check over a proposed item list. Returns
    {"valid": bool, "violations": [..]}. Used by tests and (later) by the
    agent-action endpoint: an LLM proposal that violates a hard constraint
    is rejected, never silently applied."""
    violations: list[str] = []
    parsed = []
    wake = _parse_hhmm(profile.get("wake") or "06:30")
    sleep = _parse_hhmm(profile.get("sleep") or "23:00")
    overnight = sleep <= wake
    per_day = {}
    for it in items:
        try:
            day = datetime.fromisoformat(it["date"]).date()
            start = datetime.combine(day, _parse_hhmm(it["start"]))
            end = datetime.combine(datetime.fromisoformat(it.get("end_date", it["date"])).date(),
                                   _parse_hhmm(it["end"]))
            if end <= start:
                violations.append(f'{it.get("id")}: start>=end')
                continue
            anchor = day - timedelta(days=1) if overnight and start.time() < sleep else day
            window_start = datetime.combine(anchor, wake)
            window_end = datetime.combine(anchor, sleep) + timedelta(days=int(overnight))
            if start < window_start or end > window_end:
                violations.append(f'{it.get("id")}: outside wake/sleep window')
            actual = int((end - start).total_seconds() // 60)
            if "planned_minutes" in it and int(it["planned_minutes"]) != actual:
                violations.append(f'{it.get("id")}: duration mismatch')
            per_day[anchor] = per_day.get(anchor, 0) + actual
            parsed.append((it, start, end))
        except (ValueError, TypeError, KeyError):
            violations.append(f'{it.get("id")}: invalid date/time or duration')
    for idx, (item, start, end) in enumerate(parsed):
        for other, other_start, other_end in parsed[idx + 1:]:
            if start < other_end and other_start < end:
                violations.append(f'overlap: {item.get("id")} vs {other.get("id")}')
        for ev in fixed_events:
            try:
                day = datetime.fromisoformat(ev["date"]).date()
                ev_start = datetime.combine(day, _parse_hhmm(ev["start"]))
                ev_end = datetime.combine(day, _parse_hhmm(ev["end"]))
                if ev_end <= ev_start:
                    ev_end += timedelta(days=1)
                if start < ev_end and ev_start < end:
                    violations.append(f'{item.get("id")}: overlaps fixed event {ev.get("title", ev.get("kind"))}')
            except (ValueError, TypeError, KeyError):
                violations.append("invalid fixed event")
    daily_hours = profile.get("daily_hours") or {}
    for day, minutes in per_day.items():
        hours = daily_hours.get(str(day.weekday()), daily_hours.get(day.weekday(), daily_hours.get("*")))
        caps = [daily_cap] if daily_cap is not None else []
        if hours is not None:
            caps.append(max(0, int(float(hours) * 60)))
        if caps and minutes > min(caps):
            violations.append(f"{day}: load {minutes} > capacity {min(caps)}")
    return {"valid": not violations, "violations": violations}
