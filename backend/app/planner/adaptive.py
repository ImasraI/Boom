"""Build auditable study candidates from the student's persisted evidence."""
import json
import hashlib
from uuid import uuid4
from datetime import date, datetime, timedelta
from collections import defaultdict

from sqlalchemy import select
from app.auth.database import (StudentProfile, StudySession, TaskProgress, MockAttempt,
                               GeneratedMock, WrongAnswer, Assessment, DailyTask, BankQuestion, StudentCalendar)
from app.planner.engine import PlannerInput, generate_plan, validate_plan_items
from app.planner.clock import planner_now

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
        if row.test_exams is not None and (row.version or decoded(row.test_exams, [])):
            student["testExams"] = decoded(row.test_exams, [])
        if row.exam_year:
            student["examYear"] = row.exam_year
        student.update(availability.get("preferences") or {})
        for key, target in (("wake", "wakeTime"), ("sleep_hours", "sleepHours"), ("daily_hours", "dailyHours")):
            if key in availability:
                student[target] = availability[key]
    return student


def topic_evidence(db, user_id, *, trusted_only=False):
    """Count correct, wrong and blank outcomes; never infer accuracy from misses alone."""
    stats = defaultdict(lambda: {"attempted": 0, "correct": 0, "wrong": 0, "blank": 0})
    since = datetime.utcnow() - timedelta(days=90)
    attempts = db.execute(select(MockAttempt, GeneratedMock).join(
        GeneratedMock, MockAttempt.mock_id == GeneratedMock.id).where(
        MockAttempt.student_id == user_id, MockAttempt.created_at >= since)).all()
    bank_ids = {q.get("bank_id") for _, mock in attempts for q in decoded(mock.questions, [])
                if isinstance(q, dict) and q.get("bank_id")}
    invalid_bank_ids = set(db.scalars(select(BankQuestion.id).where(
        BankQuestion.id.in_(bank_ids), (BankQuestion.status != "active") | (BankQuestion.verified.is_(False))))) if bank_ids else set()
    for attempt, mock in attempts:
        answers = decoded(attempt.answers, {})
        for q in decoded(mock.questions, []):
            if not isinstance(q, dict) or (trusted_only and (
                    q.get("verification_status") != "verified" or q.get("bank_id") in invalid_bank_ids)):
                continue
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


def focus_parts(minutes, cap, minimum):
    """Rebalance 45+15 into 30+30 before tasks become separate calendar blocks."""
    parts = []
    while minutes > cap:
        parts.append(cap)
        minutes -= cap
    if minutes:
        if parts and minutes < minimum and parts[-1] - (minimum - minutes) >= minimum:
            parts[-1] -= minimum - minutes
            minutes = minimum
        parts.append(minutes)
    return parts


def build_week(db, user_id, supplied, daily_hours, week_start, statics, *, now=None, protected=None, commit=True):
    from app.routers.boom_ai import _day_constraints, _occupied_slots
    student = student_state(db, user_id, supplied)
    now = now or planner_now()
    protected = protected or []
    # The persisted onboarding goal wins over a stale browser default.
    try:
        import re
        value = str(student.get("studyHours") or daily_hours).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        daily_hours = max(0.5, min(16, float(re.search(r"\d+(?:\.\d+)?", value).group())))
    except (ValueError, AttributeError):
        pass
    evidence = topic_evidence(db, user_id, trusted_only=True)
    ignored_legacy_evidence = bool(topic_evidence(db, user_id)) and not evidence
    major = student.get("major", "ریاضی")
    subjects = next((v for k, v in SUBJECTS.items() if k in major), SUBJECTS["ریاضی"])
    confidence = student.get("confidence") or {}
    completion = student.get("completion") or {}
    from app.planner.resources import available_books, _topic_score, _subject, _grade, specific_topic, topic_heading_rank
    subjects = [_subject(s) for s in subjects]
    books = available_books(db, student, user_id)
    topic_scores = {(_subject(e["subject"]), e["topic"]): 1 - e["accuracy"] for e in evidence if _subject(e["subject"]) in subjects}
    topic_reasons = {(_subject(e["subject"]), e["topic"]): f"بر اساس {e['attempted']} پاسخ آزمون شما؛ دقت {round(e['accuracy'] * 100)}٪" for e in evidence if _subject(e["subject"]) in subjects}
    # Manual mistakes identify topics but do not invent an accuracy denominator.
    for row in db.query(WrongAnswer).filter(WrongAnswer.student_id == user_id,
            WrongAnswer.created_at >= datetime.utcnow() - timedelta(days=90)).all():
        if row.source == "mock":
            continue  # Verified mock answers already own their accuracy denominator.
        subject = _subject(row.subject)
        if subject in subjects:
            key = (subject, row.topic or "مرور مباحث")
            topic_scores.setdefault(key, 0.65)
            topic_reasons.setdefault(key, "مبحث پاسخ غلط ثبت‌شدهٔ شما")
    for subject in subjects:
        if not any(s == subject for s, _ in topic_scores):
            rating = confidence.get(subject, completion.get(subject, 50))
            try:
                weakness = 1 - max(0, min(100, float(rating))) / 100
            except (TypeError, ValueError):
                weakness = 0.5
            matching_books = [b for b in books if b["subject"] == subject]
            matching_books.sort(key=lambda b: (b["grade"] == _grade(student), b["grade"] == 33), reverse=True)
            topics = []
            for book in matching_books:
                coverage = defaultdict(int)
                for r in book["ranges"]:
                    if specific_topic(r["topic"], subject):
                        coverage[r["topic"]] += r["q_to"] - r["q_from"] + 1
                topics.extend(topic for topic in sorted(coverage, key=lambda t: (-topic_heading_rank(t, subject), -coverage[t], t)) if topic not in topics)
            topics = topics[:3]
            for topic in topics or ["مرور مباحث"]:
                topic_scores[(subject, topic)] = weakness
                source = next((b["book"] for b in matching_books if any(r["topic"] == topic for r in b["ranges"])), None)
                topic_reasons[(subject, topic)] = (f"مبحث ثبت‌شده در کتاب {source}" if source else "مرور کلی درس؛ مبحث دقیق یا نتیجهٔ آزمون هنوز ثبت نشده")
                if subject in confidence or subject in completion:
                    topic_reasons[(subject, topic)] += "؛ اولویت بر اساس خودارزیابی شما"

    profile_hours, windows, fixed, requested_minutes = {}, [], [], []
    for day in range(7):
        cap, wake, sleep = _day_constraints(day, daily_hours, student)
        actual = week_start + timedelta(days=day)
        profile_hours[str(actual.weekday())] = 0 if actual < now.date() else cap
        requested_minutes.append(round(cap * 60) if actual >= now.date() else 0)
        windows.append((wake, sleep))
    wake, sleep = windows[0]
    def clock(hour):
        minutes = round(hour * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    # Engine HH:MM uses 23:59; the one-minute boundary remains unavailable.
    profile = {"wake": clock(wake), "sleep": clock(min(sleep, 23 + 59 / 60)), "daily_hours": profile_hours}
    if week_start <= now.date() <= week_start + timedelta(days=6):
        # A regenerated plan starts after the current minute, never this morning.
        elapsed = min(23 * 60 + 59, now.hour * 60 + now.minute + 1)
        fixed.append({"date": now.date().isoformat(), "start": "00:00",
                      "end": f"{elapsed // 60:02d}:{elapsed % 60:02d}", "title": "زمان سپری‌شده"})
    for ev in _occupied_slots(statics + protected):
        start, end = max(0, ev["startHour"]), min(23 + 59 / 60, ev["startHour"] + ev["duration"])
        if end > start:
            fixed.append({"date": (week_start + timedelta(days=ev["day"])).isoformat(),
                          "start": clock(start), "end": clock(end), "title": ev["title"]})
    for block in statics + protected:
        if block.get("type") in ("study", "test"):
            key = str((week_start + timedelta(days=block["day"])).weekday())
            profile_hours[key] = max(0, profile_hours[key] - float(block["duration"]))

    studied, candidates = set(), []
    sessions = db.query(StudySession).filter_by(student_id=user_id).all()
    progress = db.query(TaskProgress).filter(TaskProgress.student_id == user_id,
        TaskProgress.date <= week_start + timedelta(days=6)).all()
    weekly_actual = defaultdict(int)
    completed_minutes = defaultdict(int)
    for row in progress:
        if week_start <= row.date and row.actual_minutes > 0:
            key = (_subject(row.subject), row.topic or "مرور مباحث", row.task_type)
            weekly_actual[key] += row.actual_minutes
            day_key = str(row.date.weekday())
            if not any(row.client_ref.endswith(":" + b["id"]) for b in protected):
                completed_minutes[(row.date - week_start).days] += row.actual_minutes
                profile_hours[day_key] = max(0, profile_hours[day_key] - row.actual_minutes / 60)
    last_seen = {}
    for row in sessions:
        key = (_subject(row.subject_name), row.topic_name or "مرور مباحث")
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
    calendar = db.get(StudentCalendar, user_id)
    manual_refs = set()
    other_week_reservations = []
    if calendar:
        from app.planner.calendar import protected_blocks
        for iso, saved in decoded(calendar.weeks, {}).items():
            start = date.fromisoformat(iso)
            manual_refs.update(f"{start + timedelta(days=b['day'])}:{b['id']}" for b in protected_blocks(saved))
            if start != week_start:
                other_week_reservations.extend(b for b in saved
                    if start + timedelta(days=b['day']) >= now.date())
    for row in progress:
        key = (_subject(row.subject), row.topic or "مرور مباحث")
        if row.status == "completed":
            if row.task_type == "study":
                studied.add(key)
            last_seen[key] = row.date
        if row.source_ref and row.source_ref.startswith(("backlog-", "session-", "daily-")):
            continue  # The original work owns the remaining balance.
        if row.status == "planned" and not row.actual_minutes and row.client_ref not in manual_refs and (
                (row.source_ref or "").startswith(("topic-", "weekly-")) or
                row.client_ref.split(":", 1)[-1].startswith(("topic-", "weekly-"))):
            continue  # Untouched generated proposals are not confirmed missed work.
        if row.status in ("missed", "partially_completed") or (row.status == "planned" and row.date < now.date()):
            remaining = max(0, row.planned_minutes - row.actual_minutes - recovered["backlog-" + row.client_ref])
            if remaining:
                candidates.append({"id": f"backlog-{row.client_ref}", "subject": key[0], "topic": key[1],
                    "task_type": row.task_type, "planned_minutes": remaining, "overdue": 1,
                    "reason": "جبران کار انجام‌نشده؛ فقط زمان باقی‌مانده"})
    for row in db.query(DailyTask).filter(DailyTask.user_id == user_id, DailyTask.completed.is_(False),
            DailyTask.date < week_start).all():
        if row.status not in ("missed", "partially_completed") and not row.actual_minutes:
            continue
        candidates.append({"id": f"daily-{row.id}", "subject": row.subject, "topic": "مرور مباحث",
            "task_type": row.task_type, "planned_minutes": max(0, row.duration_minutes - (row.actual_minutes or 0) - recovered[f"daily-{row.id}"]), "overdue": 1,
            "reason": row.description})

    exams = db.query(Assessment).filter(Assessment.student_id == user_id,
        Assessment.date >= max(week_start, now.date()),
        Assessment.date < week_start + timedelta(days=21)).order_by(Assessment.date, Assessment.id).all()
    deadlines = {}
    mock_topics = defaultdict(list)
    mock_sources = {}

    def add_exam_topics(subject, topics, exam_date, source):
        if not isinstance(topics, list):
            return
        topics = [topic.strip() for topic in topics if isinstance(topic, str) and topic.strip()]
        # A later exam must not add its chapters to the nearest exam's deadline.
        previous_date = deadlines.get(subject)
        if previous_date and previous_date < exam_date:
            return
        if previous_date is None or exam_date < previous_date:
            mock_topics[subject] = []
            mock_sources[subject] = {}
        deadlines[subject] = exam_date
        mock_topics[subject].extend(topics)
        mock_sources.setdefault(subject, {}).update({topic: source for topic in topics})

    for exam in exams:
        data = decoded(exam.results, {})
        for entry in data.get("subjects", []):
            if isinstance(entry, (dict, str)):
                subject = _subject(entry if isinstance(entry, str) else entry.get("name", ""))
                topics = (entry.get("topics") or []) if isinstance(entry, dict) else []
                add_exam_topics(subject, topics,
                                exam.date, "آزمون ثبت‌شدهٔ شما")
    # Already-read mock documents can carry a structured topic outline. Use
    # their cached extraction without asking a model to invent assignments.
    from app.planner.mock_outline import next_mock_outline
    outline = next_mock_outline(student, max(week_start, now.date()))
    if outline:
        for subject, topics in outline["topics"].items():
            add_exam_topics(subject, topics, outline["date"], f"منبع: {outline['document']}")
    for subject, topics in mock_topics.items():
        if subject not in subjects or not topics:
            continue
        existing = {t: score for (s, t), score in topic_scores.items() if s == subject}
        topic_scores = {key: value for key, value in topic_scores.items() if key[0] != subject}
        for topic in dict.fromkeys(topics):
            topic_scores[(subject, topic)] = max((score for t, score in existing.items() if _topic_score(topic, t)), default=0.5)
            topic_reasons[(subject, topic)] = "مبحث آزمون پیش‌رو؛ " + mock_sources[subject][topic]
    mock_topics = {subject: topics for subject, topics in mock_topics.items() if subject in subjects and topics}
    # Reserve one timed mock and a correction session in a normal study week.
    exam_in_week = next((e for e in exams if e.date <= week_start + timedelta(days=6)), None)
    available_dates = [week_start + timedelta(days=d) for d in range(7)
                       if profile_hours[str((week_start + timedelta(days=d)).weekday())] >= 1.5
                       and week_start + timedelta(days=d) >= now.date()]
    mock_day = exam_in_week.date if exam_in_week else (outline["date"] if outline and outline["date"] <= week_start + timedelta(days=6)
                                                     else (available_dates[-1] if available_dates else None))
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
    try:
        max_block = max(15, min(120, int(float(student.get("maxConsec") or 1.5) * 60)))
    except (ValueError, TypeError):
        max_block = 90
    preferred_blocks = {"پومودورو ۲۵ دقیقه": (25, 5), "تمرکز ۴۵ دقیقه": (45, 10), "بلوکهای ۶۰ دقیقه": (60, 15)}
    chosen = preferred_blocks.get(student.get("breakStyle"))
    preferred_block, break_minutes = chosen or (max_block, 15)
    max_block = min(max_block, preferred_block)
    # Short focus preferences retain their cap and break length, but a review
    # must not become 25+5 minutes. Rebalance useful 15–25 minute parts instead.
    minimum = MIN_FRAGMENT_MINUTES if max_block >= 30 else 15
    quantum = 30 if max_block >= 30 else 15
    study_ratio = {"بیشتر تمرین": 0.3, "بیشتر مطالعه نظری": 0.65}.get(student.get("studyStyle"), 0.45)
    total = max(0, int(sum(profile_hours.values()) * 60)
                - sum(t["planned_minutes"] for t in candidates))
    weights = {key: 0.5 + weakness for key, weakness in topic_scores.items()}
    denominator = sum(weights.values()) or 1

    # Divide the complete remaining goal across topics, retaining the
    # rounding remainder instead of silently losing time each week.
    ordered_weights = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    topic_minutes = {key: int(total * weight / denominator / quantum) * quantum for key, weight in ordered_weights}
    for i in range((total - sum(topic_minutes.values())) // quantum):
        topic_minutes[ordered_weights[i % len(ordered_weights)][0]] += quantum
    packages: dict = {}
    for key, weight in ordered_weights:
        subject, topic = key
        minutes = topic_minutes[key]
        if minutes < quantum:
            continue
        weakness = topic_scores[key]
        days_since = (week_start - last_seen.get(key, week_start - timedelta(days=14))).days
        pkg = packages.setdefault(key, {
            "subject": subject, "weakness": 0.0, "days_since": 0,
            "topics": [], "study": 0, "test": 0, "review": 0, "deadline": None,
        })
        pkg["weakness"] = max(pkg["weakness"], weakness)
        pkg["days_since"] = max(pkg["days_since"], days_since)
        pkg["topics"].append(topic)
        study_minutes = 0 if key in studied else max(quantum, int(minutes * study_ratio / quantum) * quantum)
        review_minutes = min(30, max(quantum, int(minutes * 0.2 / quantum) * quantum))
        pkg["study"] += study_minutes
        pkg["test"] += max(0, minutes - study_minutes - review_minutes)
        pkg["review"] += min(review_minutes, max(0, minutes - study_minutes))
        if subject in deadlines:
            exam_date = deadlines[subject]
            pkg["deadline"] = (min(pkg["deadline"], exam_date)
                               if pkg["deadline"] else exam_date)

    for (subject, _topic), pkg in sorted(packages.items()):
        shown = pkg["topics"][:3]
        topics_line = "، ".join(shown) + (" و…" if len(pkg["topics"]) > 3 else "")
        # Actual minutes already reduced calendar capacity above. Do not
        # subtract them from the remaining workload a second time.
        allocations = [("study", pkg["study"]), ("test", pkg["test"]), ("review", pkg["review"])]
        n = hashlib.sha256("\0".join(("pkg", subject, topics_line)).encode()).hexdigest()[:12]
        # Short study/practice cycles unlock practice throughout the week,
        # rather than requiring the entire subject's study package first.
        remaining = {kind: focus_parts(duration, min(max_block, 30) if kind == "review" else max_block, minimum)
                     for kind, duration in allocations}
        previous = None
        cycle = 0
        if not remaining["study"]:
            studied.add((subject, topics_line))
        while any(remaining.values()):
            cycle += 1
            for kind in ("study", "test", "review"):
                if not remaining[kind]:
                    continue
                duration = remaining[kind].pop(0)
                task_id = f"topic-{n}-{cycle}-{kind}"
                candidates.append({"id": task_id, "subject": subject,
                "topic": topics_line, "task_type": kind, "planned_minutes": duration,
                "weakness": pkg["weakness"],
                "target_count": duration // 3 if kind == "test" else 0,
                "preferred_deadline": pkg["deadline"].isoformat() if pkg["deadline"] else None,
                "requires_task": previous,
                "forgetting_risk": min(1, max(0, pkg["days_since"]) / 14),
                "reason": topic_reasons.get((subject, _topic), "تکمیل کار ثبت‌شدهٔ شما")})
                previous = task_id
    # The hard cap still honours explicitly chosen short focus blocks.
    result = generate_plan(PlannerInput(profile=profile, tasks=candidates, fixed_events=fixed,
        studied_topics=studied, max_block_minutes=max_block, default_break_minutes=break_minutes,
        min_block_minutes=minimum,
        hard_max_block_minutes=max_block if chosen or student.get("maxConsec") else HARD_MAX_BLOCK_MINUTES,
        start_date=week_start.isoformat(), balance_subjects=True))
    validation = validate_plan_items(result.items, profile, fixed)
    if not validation["valid"]:
        raise ValueError("Planner produced an invalid schedule")
    labels = {"study": "مطالعه", "test": "تست", "review": "مرور", "practice": "تمرین"}
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    blocks = []
    post_exam_consolidation = False
    generation_id = uuid4().hex[:12]
    for item in result.items:
        h, m = map(int, item["start"].split(":"))
        # Keep the validated minute exactly. Moving starts after validation
        # can collide with the next activity or a fixed class.
        title = f'{labels.get(item["task_type"], "مطالعه")} {item["subject"]}: {item["topic"]}'
        reason = item["reason"]
        if item.get("preferred_deadline") and item["date"] > item["preferred_deadline"]:
            post_exam_consolidation = True
            reason = reason.replace("مبحث آزمون پیش‌رو", "تثبیت مبحث پس از آزمون")
            reason += "؛ این فعالیت پس از تاریخ آزمون برای تثبیت یادگیری است."
        if item.get("parts", 1) > 1:
            title += f' (بخش {item["part"]}/{item["parts"]})'.translate(fa)
        blocks.append({"id": item["id"] + "@" + generation_id, "day": (date.fromisoformat(item["date"]) - week_start).days,
            "origin": "generated",
            "startHour": h + m / 60, "duration": item["planned_minutes"] / 60,
            "title": title,
            "source_ref": item["id"].rsplit("#p", 1)[0],
            "subject": item["subject"], "topic": item["topic"], "task_type": item["task_type"],
            "type": "test" if item["task_type"] == "test" else "study",
            "count": item["target_count"], "description": reason,
            "color": "#9B7AAD" if item["task_type"] == "test" else "#e2c983"})
        if blocks[-1]["source_ref"] == "weekly-mock":
            blocks[-1]["title"] = exam_in_week.title if exam_in_week else "آزمون زمان‌دار مباحث هفته"
            blocks[-1]["description"] += "؛ مباحث: " + "، ".join(f"{s}: {t}" for s, t in topic_scores)
            if outline and mock_day == outline["date"]:
                blocks[-1]["title"] = f"آزمون آزمایشی — {outline['document']}"
                blocks[-1]["description"] += "؛ برنامه آزمون: " + outline["document"]
        elif blocks[-1]["source_ref"] == "weekly-correction":
            blocks[-1]["title"] = "تحلیل آزمون و مرور پاسخ‌های غلط"
    from app.planner.resources import assign_test_resources
    source_books, resource_warnings = assign_test_resources(db, student, blocks, progress, books=books,
        reserved=protected + statics + other_week_reservations)
    for block in blocks:
        if block["task_type"] != "test" or block["subject"] == "آزمون":
            continue
        if not block.get("question_start"):
            # A timed question assignment must name a verified range. Where
            # indexing is incomplete, fill the study goal with lesson work
            # instead of presenting an invented or unspecified test count.
            from pathlib import Path
            resource = Path(block.get("resource") or "").stem
            block.update(task_type="practice", type="study", count=None, color="#e2c983")
            block["title"] = f"مرور درس‌نامه و تمرین تشریحی {block['subject']}: {block['topic']}"
            if resource:
                block["title"] += f" — کتاب {resource}"
            block["description"] += "؛ بازهٔ تست معتبر برای این مبحث موجود نیست؛ این زمان به مرور و تمرین درس اختصاص دارد."
        elif block["count"] * 3 + 20 < round(block["duration"] * 60):
            block["title"] += " + تحلیل پاسخ‌ها و مرور درس"
            block["description"] += "؛ پس از حل تست‌های مشخص‌شده، زمان باقی‌مانده برای تحلیل پاسخ‌ها و مرور درس‌نامه است."
    # Persist planned work so silence on a past day can become an explicit backlog.
    from sqlalchemy.dialects.sqlite import insert
    for old in progress:
        if any(old.client_ref.endswith(":" + b["id"]) for b in protected):
            continue
        if old.status == "planned" and week_start <= old.date <= week_start + timedelta(days=6) and old.date >= now.date():
            old.status = "rescheduled"
    db.flush()
    for block in blocks:
        planned_date = week_start + timedelta(days=block["day"])
        values = dict(student_id=user_id, client_ref=f'{planned_date.isoformat()}:{block["id"]}',
            source_ref=block["source_ref"], date=planned_date, subject=block["subject"], topic=block["topic"],
            task_type=block["task_type"], planned_minutes=round(block["duration"] * 60), actual_minutes=0, status="planned",
            resource=block.get("resource"), question_start=block.get("question_start"),
            question_end=block.get("question_end"), page_start=block.get("page_start"), page_end=block.get("page_end"))
        statement = insert(TaskProgress).values(**values).on_conflict_do_update(
            index_elements=[TaskProgress.student_id, TaskProgress.client_ref],
            set_={k: v for k,v in values.items() if k not in ("student_id", "client_ref")},
            where=TaskProgress.status.in_(("planned", "rescheduled")))
        db.execute(statement)
    if commit:
        db.commit()
    workload = [round(sum(b["duration"] * 60 for b in blocks + protected + statics
                         if b["day"] == d and b.get("type") in ("study", "test"))) for d in range(7)]
    capacity_warnings = [f"{DAYS[d]}: از هدف {requested_minutes[d]} دقیقه، {workload[d] + completed_minutes[d]} دقیقه قابل برنامه‌ریزی یا انجام‌شده است؛ زمان آزاد با استراحت‌ها و فعالیت‌های ثابت کافی نیست."
                         for d in range(7) if requested_minutes[d] - workload[d] - completed_minutes[d] > 30]
    grounding_warnings = []
    if post_exam_consolidation:
        grounding_warnings.append("بخشی از کارها برای تثبیت مباحث، پس از تاریخ آزمون قرار گرفت؛ فعالیت‌های پیش از آزمون را در اولویت انجام دهید.")
    if ignored_legacy_evidence:
        grounding_warnings.append("آزمون‌های قدیمیِ تأییدنشده مبنای انتخاب مبحث قرار نگرفتند؛ تاریخچهٔ پاسخ‌ها حفظ شده است.")
    if student.get("testExams") and not outline and not mock_topics:
        grounding_warnings.append("برنامهٔ معتبرِ آزمون انتخابی شما برای سه هفتهٔ آینده در منابع نیست؛ این هفته بر اساس نتایج شما و مباحث موجود در کتاب‌ها ساخته شد. برنامهٔ جدید آزمون را بارگذاری یا مباحث آن را ثبت کنید.")
    return {"week_start": week_start.isoformat(), "blocks": protected + blocks, "llm_used": False,
            "daily_minutes": workload, "target_daily_minutes": round(daily_hours * 60),
            "completed_minutes": [completed_minutes[d] for d in range(7)], "daily_targets": requested_minutes,
            "mock_source": outline["document"] if outline else None,
            "source_books": source_books, "planner": "adaptive-v3", "evidence": evidence,
            "warnings": result.warnings + resource_warnings + capacity_warnings + grounding_warnings, "unscheduled": result.unscheduled,
            "note": f"هدف روزانه: {round(daily_hours * 60)} دقیقه. برنامه بر اساس زمان آزاد، نتایج معتبر و کارهای ثبت‌شده ساخته شد. " + ("مباحث آزمون پیش‌رو اعمال شد." if mock_topics else "برنامهٔ آزمون پیش‌رو در منابع پیدا نشد؛ انتخاب مبحث از نتایج معتبر و فهرست کتاب‌های موجود است."),
            "exams": [{"title": e.title, "date": e.date.isoformat()} for e in exams]}
