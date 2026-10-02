"""Build auditable study candidates from the student's persisted evidence."""
import json
import hashlib
from uuid import uuid4
from datetime import date, datetime, timedelta
from collections import defaultdict

from sqlalchemy import select
from app.auth.database import (StudentProfile, StudySession, TaskProgress, MockAttempt,
                               GeneratedMock, WrongAnswer, Assessment, DailyTask)
from app.planner.engine import PlannerInput, generate_plan, validate_plan_items

DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سهشنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
SUBJECTS = {
    "ریاضی": ["ریاضی", "فیزیک", "شیمی"],
    "تجربی": ["زیست", "شیمی", "فیزیک", "ریاضی", "زمین‌شناسی"],
    "انسانی": ["ادبیات", "عربی", "تاریخ", "جغرافیا", "فلسفه", "منطق", "اقتصاد", "جامعه‌شناسی"],
}


def decoded(value, fallback):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, type(fallback)) else fallback
    except (ValueError, TypeError):
        return fallback


def student_state(db, user_id, supplied=None):
    student = dict(supplied or {})
    row = db.query(StudentProfile).filter_by(user_id=user_id).first()
    if row:
        for source, target in (("major", "major"), ("grade", "grade"), ("name", "name"),
                               ("target_rank", "targetRank"), ("study_hours", "studyHours")):
            if getattr(row, source):
                student[target] = getattr(row, source)
        availability = decoded(row.availability, {})
        student.update(availability.get("preferences") or {})
        for key, target in (("wake", "wakeTime"), ("sleep_hours", "sleepHours"), ("daily_hours", "dailyHours")):
            if key in availability:
                student[target] = availability[key]
    return student


def topic_evidence(db, user_id):
    """Count correct, wrong and blank outcomes; never infer accuracy from misses alone."""
    stats = defaultdict(lambda: {"attempted": 0, "correct": 0, "wrong": 0, "blank": 0})
    since = datetime.utcnow() - timedelta(days=90)
    attempts = db.execute(select(MockAttempt, GeneratedMock).join(
        GeneratedMock, MockAttempt.mock_id == GeneratedMock.id).where(
        MockAttempt.student_id == user_id, MockAttempt.created_at >= since)).all()
    for attempt, mock in attempts:
        answers = decoded(attempt.answers, {})
        for q in decoded(mock.questions, []):
            key = (q.get("subject") or "عمومی", q.get("topic") or "مرور مباحث")
            stat = stats[key]
            value = answers.get(str(q.get("_id", q.get("id"))))
            stat["attempted"] += 1
            if value in (None, "", "null"):
                stat["blank"] += 1
            elif str(value) == str(q.get("answer")):
                stat["correct"] += 1
            else:
                stat["wrong"] += 1
    return [{"subject": subject, "topic": topic, **values,
             "accuracy": round(values["correct"] / values["attempted"], 3)}
            for (subject, topic), values in sorted(stats.items())]


# Thin-fragment policy for the default 1.5h block standard: a package whose
# total slightly exceeds the block cap must not become a stub part (90+15 for a
# 105-minute package), and a leftover below MIN_FRAGMENT_MINUTES must not be
# emitted as a useless block. See PlannerInput.min_block_minutes.
MIN_FRAGMENT_MINUTES = 30
HARD_MAX_BLOCK_MINUTES = 120


def build_week(db, user_id, supplied, daily_hours, week_start, statics, *, now=None):
    from app.routers.boom_ai import _day_constraints, _occupied_slots
    student = student_state(db, user_id, supplied)
    now = now or datetime.now()
    evidence = topic_evidence(db, user_id)
    major = student.get("major", "ریاضی")
    subjects = next((v for k, v in SUBJECTS.items() if k in major), SUBJECTS["ریاضی"])
    confidence = student.get("confidence") or {}
    completion = student.get("completion") or {}
    topic_scores = {(e["subject"], e["topic"]): 1 - e["accuracy"] for e in evidence}
    # Manual mistakes identify topics but do not invent an accuracy denominator.
    for row in db.query(WrongAnswer).filter(WrongAnswer.student_id == user_id,
            WrongAnswer.created_at >= datetime.utcnow() - timedelta(days=90)).all():
        topic_scores.setdefault((row.subject, row.topic or "مرور مباحث"), 0.65)
    for subject in subjects:
        if not any(s == subject for s, _ in topic_scores):
            rating = confidence.get(subject, completion.get(subject, 50))
            try:
                weakness = 1 - max(0, min(100, float(rating))) / 100
            except (TypeError, ValueError):
                weakness = 0.5
            topic_scores[(subject, "مرور مباحث")] = weakness

    profile_hours, windows, fixed = {}, [], []
    for day in range(7):
        cap, wake, sleep = _day_constraints(day, daily_hours, student)
        actual = week_start + timedelta(days=day)
        profile_hours[str(actual.weekday())] = 0 if actual < date.today() else cap
        windows.append((wake, sleep))
    wake, sleep = windows[0]
    def clock(hour):
        return f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}"
    # Engine HH:MM uses 23:59; the one-minute boundary remains unavailable.
    profile = {"wake": clock(wake), "sleep": clock(min(sleep, 23 + 59 / 60)), "daily_hours": profile_hours}
    if week_start <= now.date() <= week_start + timedelta(days=6):
        # A regenerated plan starts after the current minute, never this morning.
        elapsed = min(23 * 60 + 59, now.hour * 60 + now.minute + 1)
        fixed.append({"date": now.date().isoformat(), "start": "00:00",
                      "end": f"{elapsed // 60:02d}:{elapsed % 60:02d}", "title": "زمان سپری‌شده"})
    for ev in _occupied_slots(statics):
        start, end = max(0, ev["startHour"]), min(23 + 59 / 60, ev["startHour"] + ev["duration"])
        if end > start:
            fixed.append({"date": (week_start + timedelta(days=ev["day"])).isoformat(),
                          "start": clock(start), "end": clock(end), "title": ev["title"]})

    studied, candidates = set(), []
    sessions = db.query(StudySession).filter_by(student_id=user_id).all()
    progress = db.query(TaskProgress).filter(TaskProgress.student_id == user_id,
        TaskProgress.date <= week_start + timedelta(days=6)).all()
    weekly_actual = defaultdict(int)
    for row in progress:
        if week_start <= row.date and row.actual_minutes > 0:
            key = (row.subject, row.topic or "مرور مباحث", row.task_type)
            weekly_actual[key] += row.actual_minutes
            day_key = str(row.date.weekday())
            profile_hours[day_key] = max(0, profile_hours[day_key] - row.actual_minutes / 60)
    last_seen = {}
    for row in sessions:
        key = (row.subject_name or "", row.topic_name or "مرور مباحث")
        if row.completion_status == "completed" and (row.actual_minutes or row.duration_minutes or 0) > 0:
            studied.add(key)
            last_seen[key] = row.started_at.date()
        if row.completion_status in ("missed", "partially_completed"):
            planned = decoded(row.completion_data, {}).get("planned_minutes", 60)
            remaining = max(0, int(planned) - (row.actual_minutes or 0) - sum(p.actual_minutes for p in progress if p.source_ref == f"session-{row.id}"))
            if remaining:
                candidates.append({"id": f"session-{row.id}", "subject": key[0], "topic": key[1],
                    "task_type": "study", "planned_minutes": remaining, "overdue": 1,
                    "reason": "تکمیل زمان باقی‌مانده از جلسه قبلی"})
    recovered = defaultdict(int)
    for row in progress:
        if row.source_ref and row.status in ("completed", "partially_completed"):
            recovered[row.source_ref] += row.actual_minutes
    for row in progress:
        key = (row.subject, row.topic or "مرور مباحث")
        if row.status == "completed":
            if row.task_type == "study":
                studied.add(key)
            last_seen[key] = row.date
        if row.source_ref and row.source_ref.startswith(("backlog-", "session-", "daily-")):
            continue  # The original work owns the remaining balance.
        if row.status in ("missed", "partially_completed") or (row.status == "planned" and row.date < date.today()):
            remaining = max(0, row.planned_minutes - row.actual_minutes - recovered["backlog-" + row.client_ref])
            if remaining:
                candidates.append({"id": f"backlog-{row.client_ref}", "subject": key[0], "topic": key[1],
                    "task_type": row.task_type, "planned_minutes": remaining, "overdue": 1,
                    "reason": "جبران کار انجام‌نشده؛ فقط زمان باقی‌مانده"})
    for row in db.query(DailyTask).filter(DailyTask.user_id == user_id, DailyTask.completed.is_(False),
            DailyTask.date < week_start).all():
        candidates.append({"id": f"daily-{row.id}", "subject": row.subject, "topic": "مرور مباحث",
            "task_type": row.task_type, "planned_minutes": max(0, row.duration_minutes - (row.actual_minutes or 0) - recovered[f"daily-{row.id}"]), "overdue": 1,
            "reason": row.description})

    exams = db.query(Assessment).filter(Assessment.student_id == user_id,
        Assessment.date >= week_start, Assessment.date < week_start + timedelta(days=21)).all()
    deadlines = {}
    for exam in exams:
        data = decoded(exam.results, {})
        for entry in data.get("subjects", []):
            subject = entry if isinstance(entry, str) else entry.get("name", "")
            deadlines[subject] = min(deadlines.get(subject, exam.date), exam.date)
    # Reserve one timed mock and a correction session in a normal study week.
    exam_in_week = next((e for e in exams if e.date <= week_start + timedelta(days=6)), None)
    available_dates = [week_start + timedelta(days=d) for d in range(7)
                       if profile_hours[str((week_start + timedelta(days=d)).weekday())] >= 1.5
                       and week_start + timedelta(days=d) >= date.today()]
    mock_day = exam_in_week.date if exam_in_week else (available_dates[-1] if available_dates else None)
    if mock_day:
        mock_remaining = max(0, 60 - weekly_actual[("آزمون", "مرور مباحث", "test")])
        candidates.extend([
            {"id":"weekly-mock", "subject":"آزمون", "topic":"", "task_type":"test", "planned_minutes":mock_remaining,
             "target_count":20, "not_before":mock_day.isoformat(), "deadline":mock_day.isoformat(), "overdue":1,
             "reason": "آزمون زمان‌دار برای ارزیابی آموخته‌های هفته"},
            {"id":"weekly-correction", "subject":"آزمون", "topic":"", "task_type":"review", "planned_minutes":max(0, 30 - weekly_actual[("آزمون", "مرور مباحث", "review")]),
             "requires_task":"weekly-mock" if mock_remaining else None, "not_before":mock_day.isoformat(), "overdue":1,
             "reason":"تحلیل پاسخ‌های غلط و ثبت علت اشتباه"},
        ])
    load_ratio = {"انعطافپذیر": 0.65, "متعادل": 0.8, "سختگیر": 0.9}.get(student.get("strictness"), 0.8)
    study_ratio = {"بیشتر تمرین": 0.3, "بیشتر مطالعه نظری": 0.65}.get(student.get("studyStyle"), 0.45)
    total = max(0, int(sum(profile_hours.values()) * 60 * load_ratio)
                - sum(t["planned_minutes"] for t in candidates))
    weights = {key: 0.5 + weakness for key, weakness in topic_scores.items()}
    denominator = sum(weights.values()) or 1

    # --- Work packages (readable schedule) ----------------------------------
    # One candidate per (subject, kind) instead of one per (subject, topic,
    # kind). Many thin 15-30 min blocks fragment the day and are unreadable
    # on the week grid; the package TITLE lists its topics, e.g.
    # «مطالعه فیزیک: الکتریسیته ساکن، حرکت‌شناسی». Allocations below 30
    # minutes are dropped rather than emitted as thin fragments.
    packages: dict = {}
    for key, weight in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])):
        subject, topic = key
        minutes = int(total * weight / denominator / 15) * 15
        if minutes < 15:
            continue
        weakness = topic_scores[key]
        days_since = (week_start - last_seen.get(key, week_start - timedelta(days=14))).days
        pkg = packages.setdefault(subject, {
            "subject": subject, "weakness": 0.0, "days_since": 0,
            "topics": [], "study": 0, "test": 0, "review": 0, "deadline": None,
        })
        pkg["weakness"] = max(pkg["weakness"], weakness)
        pkg["days_since"] = max(pkg["days_since"], days_since)
        pkg["topics"].append(topic)
        study_minutes = 0 if key in studied else max(15, int(minutes * study_ratio / 15) * 15)
        review_minutes = min(30, max(15, int(minutes * 0.2 / 15) * 15))
        pkg["study"] += study_minutes
        pkg["test"] += max(0, minutes - study_minutes - review_minutes)
        pkg["review"] += min(review_minutes, max(0, minutes - study_minutes))
        if subject in deadlines:
            exam_date = deadlines[subject]
            pkg["deadline"] = (min(pkg["deadline"], exam_date)
                               if pkg["deadline"] else exam_date)

    for subject, pkg in sorted(packages.items()):
        shown = pkg["topics"][:3]
        topics_line = "، ".join(shown) + (" و…" if len(pkg["topics"]) > 3 else "")
        # Weekly actuals credit the whole package (any topic of the subject).
        done = {k: sum(v for (s, _t, kind), v in weekly_actual.items()
                       if s == subject and kind == k)
                for k in ("study", "test", "review")}
        allocations = [("study", max(0, pkg["study"] - done["study"])),
                       ("test", max(0, pkg["test"] - done["test"])),
                       ("review", max(0, pkg["review"] - done["review"]))]
        has_test = allocations[1][1] > 0
        n = hashlib.sha256("\0".join(("pkg", subject)).encode()).hexdigest()[:12]
        for kind, duration in allocations:
            if duration < 30:
                continue  # no thin fragments below half an hour
            candidates.append({"id": f"topic-{n}-{kind}", "subject": subject,
                "topic": topics_line, "task_type": kind, "planned_minutes": duration,
                "weakness": pkg["weakness"],
                "target_count": duration // 3 if kind == "test" else 0,
                "deadline": pkg["deadline"].isoformat() if pkg["deadline"] else None,
                "requires_task": f"topic-{n}-test" if kind == "review" and has_test else None,
                "forgetting_risk": min(1, max(0, pkg["days_since"]) / 14),
                "reason": f"نیاز به تمرین {round(pkg['weakness'] * 100)}٪؛ مرور برای حفظ یادگیری"})
    try:
        # Standard focus block is 1.5h unless the student set their own limit.
        max_block = max(15, min(120, int(float(student.get("maxConsec") or 1.5) * 60)))
    except (ValueError, TypeError):
        max_block = 90
    preferred_blocks = {"پومودورو ۲۵ دقیقه": (25, 5), "تمرکز ۴۵ دقیقه": (45, 10), "بلوکهای ۶۰ دقیقه": (60, 15)}
    chosen = preferred_blocks.get(student.get("breakStyle"))
    preferred_block, break_minutes = chosen or (max_block, 15)
    max_block = min(max_block, preferred_block)
    # Thin-fragment policy only for the DEFAULT 1.5h standard. A student who
    # explicitly asked for 25-minute pomodoro blocks wants exactly that, so the
    # engine must not merge a leftover into a longer block or drop it.
    result = generate_plan(PlannerInput(profile=profile, tasks=candidates, fixed_events=fixed,
        studied_topics=studied, max_block_minutes=max_block, default_break_minutes=break_minutes,
        min_block_minutes=0 if chosen else MIN_FRAGMENT_MINUTES,
        hard_max_block_minutes=0 if chosen else HARD_MAX_BLOCK_MINUTES,
        start_date=week_start.isoformat()))
    validation = validate_plan_items(result.items, profile, fixed)
    if not validation["valid"]:
        raise ValueError("Planner produced an invalid schedule")
    labels = {"study": "مطالعه", "test": "تست", "review": "مرور", "practice": "تمرین"}
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    blocks = []
    generation_id = uuid4().hex[:12]
    for item in result.items:
        h, m = map(int, item["start"].split(":"))
        # The engine adds break minutes (15 by default) between blocks, which
        # produces off-grid starts like 12:53. The week grid is half-hour
        # based, so snap the start forward to the next 30-minute boundary
        # (never backward, to keep clear of the previous block / fixed events).
        m = 30 if m % 30 else 0
        if m == 30:
            h += 1
        title = f'{labels.get(item["task_type"], "مطالعه")} {item["subject"]}: {item["topic"]}'
        if item.get("parts", 1) > 1:
            title += f' (بخش {item["part"]}/{item["parts"]})'.translate(fa)
        blocks.append({"id": item["id"] + "@" + generation_id, "day": (date.fromisoformat(item["date"]) - week_start).days,
            "startHour": h + m / 60, "duration": item["planned_minutes"] / 60,
            "title": title,
            "source_ref": item["id"].rsplit("#p", 1)[0],
            "subject": item["subject"], "topic": item["topic"], "task_type": item["task_type"],
            "type": "test" if item["task_type"] == "test" else "study",
            "count": item["target_count"], "description": item["reason"],
            "color": "#9B7AAD" if item["task_type"] == "test" else "#e2c983"})
    # Persist planned work so silence on a past day can become an explicit backlog.
    from sqlalchemy.dialects.sqlite import insert
    for old in progress:
        if old.status == "planned" and week_start <= old.date <= week_start + timedelta(days=6) and old.date >= date.today():
            old.status = "rescheduled"
    db.flush()
    for block in blocks:
        planned_date = week_start + timedelta(days=block["day"])
        values = dict(student_id=user_id, client_ref=f'{planned_date.isoformat()}:{block["id"]}',
            source_ref=block["source_ref"], date=planned_date, subject=block["subject"], topic=block["topic"],
            task_type=block["task_type"], planned_minutes=round(block["duration"] * 60), actual_minutes=0, status="planned")
        statement = insert(TaskProgress).values(**values).on_conflict_do_update(
            index_elements=[TaskProgress.student_id, TaskProgress.client_ref],
            set_={k: v for k,v in values.items() if k not in ("student_id", "client_ref")},
            where=TaskProgress.status.in_(("planned", "rescheduled")))
        db.execute(statement)
    db.commit()
    return {"week_start": week_start.isoformat(), "blocks": blocks, "llm_used": False,
            "source_books": [], "planner": "adaptive-v1", "evidence": evidence,
            "warnings": result.warnings, "unscheduled": result.unscheduled,
            "note": "برنامه بر اساس زمان آزاد، نتایج آزمون و کارهای ثبت‌شده ساخته شد.",
            "exams": [{"title": e.title, "date": e.date.isoformat()} for e in exams]}
