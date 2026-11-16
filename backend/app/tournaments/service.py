"""Atomic, persisted tournament lifecycle. No live question generation or Elo."""
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select, update

from app.auth.database import BankQuestion, StudentProfile, User
from app.rag.konkur_format import major_key
from app.tournaments.engine import cutoff_ties, knockout_pairs, score_packet, standings, swiss_pairs
from app.tournaments.models import TournamentEvent


LABELS = {"league": "لیگ", "quarterfinal": "یک‌چهارم نهایی", "semifinal": "نیمه‌نهایی",
          "final": "فینال", "third_place": "رده‌بندی"}
DONE = {"completed", "forfeit", "bye"}


def now_utc():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise HTTPException(422, "زمان مسابقه باید منطقهٔ زمانی مشخص داشته باشد.")
    return parsed.astimezone(timezone.utc)


def fail(message, status=409):
    raise HTTPException(status, message)


def _safe_name(profile, user_id):
    name = (profile.name or "").strip() if profile else ""
    digits = name.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not name or re.search(r"\d{7,}", re.sub(r"[\s+()\-]", "", digits)):
        return f"بازیکن {user_id}"
    return name[:80]


def _grade(value):
    text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return {"دهم": 10, "یازدهم": 11, "دوازدهم": 12}.get(text, int(text) if text.isdigit() else None)


def _players(db, participant_ids, major, grade):
    if len(set(participant_ids)) != len(participant_ids):
        fail("هر بازیکن فقط یک بار می‌تواند در فهرست باشد.", 422)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(participant_ids)))}
    profiles = {p.user_id: p for p in db.scalars(select(StudentProfile).where(StudentProfile.user_id.in_(participant_ids)))}
    players = []
    for user_id in participant_ids:
        profile = profiles.get(user_id)
        if user_id not in users or not profile:
            fail("بازیکن و پروفایل معتبر برای همهٔ شناسه‌ها لازم است.", 422)
        if major_key(profile.major or "") != major_key(major) or _grade(profile.grade) != _grade(grade):
            fail("همهٔ بازیکنان باید رشته و پایهٔ همین تورنومنت را داشته باشند.", 422)
        players.append({"id": user_id, "name": _safe_name(profile, user_id)})
    return players


def _packet(db, bank_ids, major, grade):
    if not bank_ids or len(set(bank_ids)) != len(bank_ids):
        fail("دفترچه باید سؤال‌های یکتا و تأییدشده داشته باشد.", 422)
    bank = {row.id: row for row in db.scalars(select(BankQuestion).where(BankQuestion.id.in_(bank_ids)))}
    result = []
    for bank_id in bank_ids:
        row = bank.get(bank_id)
        if (row is None or row.owner_id != 0 or not row.verified or row.status != "active"
                or major_key(row.major) != major_key(major)
                or _grade(row.grade) != _grade(grade)):
            fail("دفترچه فقط می‌تواند از سؤال‌های عمومی، فعال و تأییدشدهٔ همین پایه و رشته باشد.", 422)
        try:
            q = json.loads(row.content)
        except (ValueError, TypeError):
            fail("متن ذخیره‌شدهٔ یکی از سؤال‌ها معتبر نیست.", 422)
        if (not isinstance(q, dict) or not isinstance(q.get("text"), str) or not q["text"].strip()
                or not isinstance(q.get("options"), list) or len(q["options"]) != 4
                or any(not isinstance(v, str) or not v.strip() for v in q["options"])
                or type(q.get("answer")) is not int or q["answer"] not in range(4)):
            fail("متن، چهار گزینه و پاسخ معتبر برای همهٔ سؤال‌ها لازم است.", 422)
        result.append({"id": str(bank_id), "text": q["text"], "options": q["options"],
                       "answer": q["answer"], "subject": row.subject, "topic": row.topic,
                       "figure": q.get("figure", {"type": "none", "data": {}})})
    return result


def _rounds(config):
    start = instant(config["starts_at"])
    duration = timedelta(minutes=config["duration_minutes"])
    result = []
    for number in range(1, config["league_rounds"] + 1):
        when = start + timedelta(hours=(number - 1) * config["round_interval_hours"])
        result.append({"id": f"league-{number}", "number": number, "stage": "league",
                       "label": f"دور {number} لیگ", "starts_at": iso(when), "ends_at": iso(when + duration),
                       "matches": [], "questions": []})
    when = start + timedelta(hours=config["league_rounds"] * config["round_interval_hours"])
    stages = ["quarterfinal", "semifinal", "final", "third_place"] if config["playoff_size"] == 8 else ["semifinal", "final", "third_place"]
    for number, stage in enumerate(stages):
        offset = min(number, len(stages) - 2)
        at = when + timedelta(hours=offset * config["playoff_interval_hours"])
        result.append({"id": stage, "number": number + 1, "stage": stage, "label": LABELS[stage],
                       "starts_at": iso(at), "ends_at": iso(at + duration), "matches": [], "questions": []})
    return result


def build_draft(db, config):
    if config["playoff_size"] not in (4, 8):
        fail("مرحلهٔ حذفی باید ۴ یا ۸ نفره باشد.", 422)
    if config["attendance_grace_minutes"] > config["duration_minutes"]:
        fail("مهلت حضور نمی‌تواند از زمان مسابقه بیشتر باشد.", 422)
    if min(config["round_interval_hours"], config["playoff_interval_hours"]) * 60 < config["duration_minutes"] + config["attendance_grace_minutes"]:
        fail("فاصلهٔ دورها باید برای زمان مسابقه و مهلت حضور کافی باشد.", 422)
    if any(player <= 0 for player in config["participant_ids"]):
        fail("شناسهٔ بازیکن معتبر لازم است.", 422)
    if len(config["packets"]) > 15 or any(len(ids) > 100 for ids in config["packets"].values()):
        fail("اندازهٔ دفترچه یا تعداد دورها بیشتر از حد مجاز است.", 422)
    config = deepcopy(config)
    config["starts_at"] = iso(instant(config["starts_at"]))
    players = _players(db, config.pop("participant_ids"), config["major"], config["grade"])
    packets = config.pop("packets")
    if len(players) > config["capacity"]:
        fail("تعداد بازیکنان از ظرفیت بیشتر است.", 422)
    rounds = _rounds(config)
    known_ids = {r["id"] for r in rounds}
    if set(packets) - known_ids:
        fail("شناسهٔ دفترچه با دورهای تورنومنت سازگار نیست.", 422)
    used = set()
    for rnd in rounds:
        ids = packets.get(rnd["id"], [])
        if used.intersection(ids):
            fail("سؤال یک دور نباید در دور دیگری تکرار شود.", 422)
        used.update(ids)
        if ids:
            rnd["questions"] = _packet(db, ids, config["major"], config["grade"])
    return {**config, "status": "draft", "players": players, "rounds": rounds,
            "qualification_results": [], "registration_status": "closed"}


def _new_match(rnd, slot, a, b, **extra):
    return {"id": f"{rnd['id']}-{slot}", "round_id": rnd["id"], "slot": slot,
            "stage": rnd["stage"], "a": a, "b": b, "status": "scheduled", "attempts": {},
            "winner_id": None, "score_a": None, "score_b": None, **extra}


def activate(state, db, now):
    if state["status"] != "draft":
        fail("این تورنومنت قبلاً آغاز شده است.")
    if (len(state["players"]) < state["playoff_size"] or len(state["players"]) % 2
            or state["league_rounds"] >= len(state["players"])):
        fail("فهرست بازیکنان باید زوج، برای مرحلهٔ حذفی کافی و بیشتر از تعداد دورهای لیگ باشد.")
    if state["league_rounds"] > len(state["players"]) // 2:
        fail("برای تضمین ادامهٔ لیگ بدون تکرار حریف، تعداد دورها نباید از نصف شرکت‌کنندگان بیشتر باشد.")
    if instant(state["starts_at"]) <= now:
        fail("شروع تورنومنت باید در آینده باشد.")
    used = set()
    for rnd in state["rounds"]:
        if not rnd["questions"]:
            fail("دفترچهٔ همهٔ دورهای لیگ و حذفی باید پیش از آغاز آماده باشد.")
        ids = [int(q["id"]) for q in rnd["questions"]]
        if used.intersection(ids):
            fail("سؤال تکراری بین دورها مجاز نیست.")
        # Revalidate current status at activation, then freeze the snapshot.
        rnd["questions"] = _packet(db, ids, state["major"], state["grade"])
        used.update(ids)
    state["status"] = "league"
    first = state["rounds"][0]
    first["matches"] = [_new_match(first, i, a, b) for i, (a, b) in enumerate(swiss_pairs(state), 1)]


def _attempt_score(attempt, questions):
    return score_packet(questions, attempt.get("answers") or {})


def _match_times(rnd, match):
    return instant(match.get("starts_at") or rnd["starts_at"]), instant(match.get("ends_at") or rnd["ends_at"])


def _finish_match(rnd, match, now):
    if match["status"] in DONE or match["status"] == "awaiting_tiebreak":
        return
    start, end = _match_times(rnd, match)
    ids = [match["a"]] if match.get("qualifier") else [match["a"], match["b"]]
    if None in ids:
        return
    attempts = match["attempts"]
    # An existing started attempt expires at the common server deadline.
    for attempt in attempts.values():
        if not attempt.get("submitted_at") and now >= end:
            attempt["submitted_at"] = iso(end)
            attempt["answers"] = attempt.get("answers") or {}
            attempt["score"] = _attempt_score(attempt, match.get("questions") or rnd["questions"])
            attempt["timed_out"] = True
    submitted = all(str(p) in attempts and attempts[str(p)].get("submitted_at") for p in ids)
    if not submitted and now < end:
        if attempts:
            match["status"] = "live"
        return
    present = [p for p in ids if str(p) in attempts]
    for side, player in (("a", match["a"]), ("b", match["b"])):
        attempt = attempts.get(str(player))
        match["score_" + side] = attempt["score"]["percent"] if attempt and attempt.get("score") else None
    if match.get("qualifier"):
        match["status"] = "completed" if present else "forfeit"
        return
    if len(present) < 2:
        match["winner_id"] = present[0] if present else None
        match["double_forfeit"] = not present
        match["status"] = "forfeit"
        return
    a, b = (attempts[str(p)]["score"]["units"] for p in ids)
    match["winner_id"] = ids[0] if a > b else ids[1] if b > a else None
    if a == b and rnd["stage"] != "league":
        match["status"] = "awaiting_tiebreak"
    else:
        match["status"] = "completed"


def _complete_round(rnd):
    return bool(rnd["matches"]) and all(m["status"] in DONE for m in rnd["matches"])


def _future_window(state, rnd, now, interval):
    """Never create a newly paired match inside an already expired slot.

    Late tie-breaks/administrative downtime shift unpaired downstream rounds
    together, preserving a full published notice interval for the entrants.
    Existing started or already-paired matches are never silently moved.
    """
    old_start = instant(rnd["starts_at"])
    if old_start > now:
        return
    delta = now + timedelta(hours=interval) - old_start
    for other in state["rounds"]:
        if not other["matches"] and not other.get("kind") and instant(other["starts_at"]) >= old_start:
            other["starts_at"] = iso(instant(other["starts_at"]) + delta)
            other["ends_at"] = iso(instant(other["ends_at"]) + delta)
    state["schedule_note"] = "زمان دورهای بعدی برای داشتن مهلت حضور کامل به‌روزرسانی شده است."


def _start_knockout(state, now):
    if cutoff_ties(state):
        state["status"] = "awaiting_tiebreak"
        state["tie_reason"] = "در مرز صعود هم‌امتیازی کامل وجود دارد؛ آزمون تکمیلی لازم است."
        return
    rows = standings(state)
    players = [r["player_id"] for r in rows[:state["playoff_size"]]]
    stage = "quarterfinal" if len(players) == 8 else "semifinal"
    rnd = next(r for r in state["rounds"] if r["stage"] == stage)
    if not rnd["matches"]:
        _future_window(state, rnd, now, state["playoff_interval_hours"])
        rnd["matches"] = [_new_match(rnd, i, a, b) for i, (a, b) in enumerate(knockout_pairs(players), 1)]
    state["status"] = "knockout"
    state.pop("tie_reason", None)


def reconcile(state, now):
    """Resolve expired play and prepare only rounds whose predecessors ended."""
    if state["status"] in ("draft", "completed"):
        return
    for rnd in state["rounds"]:
        for match in rnd["matches"]:
            _finish_match(rnd, match, now)
    league = [r for r in state["rounds"] if r["stage"] == "league" and not r.get("kind")]
    for i, rnd in enumerate(league):
        if not rnd["matches"]:
            if i and _complete_round(league[i - 1]):
                _future_window(state, rnd, now, state["round_interval_hours"])
                rnd["matches"] = [_new_match(rnd, n, a, b) for n, (a, b) in enumerate(swiss_pairs(state), 1)]
                for match in rnd["matches"]:
                    _finish_match(rnd, match, now)
            else:
                return
        if not _complete_round(rnd):
            return
    qualifiers = [r for r in state["rounds"] if r.get("kind") == "qualification_tiebreak"]
    for rnd in qualifiers:
        if not _complete_round(rnd):
            return
        if not rnd.get("recorded"):
            scores = {}
            for match in rnd["matches"]:
                attempt = match["attempts"].get(str(match["a"]))
                scores[str(match["a"])] = ({"units": attempt["score"]["units"], "total": len(rnd["questions"])}
                                           if attempt and attempt.get("score") else None)
            state["qualification_results"].append(scores)
            rnd["recorded"] = True
    if not any(r["matches"] for r in state["rounds"] if r["stage"] != "league"):
        _start_knockout(state, now)
    if state["status"] == "awaiting_tiebreak":
        return
    quarters = next((r for r in state["rounds"] if r["stage"] == "quarterfinal"), None)
    semis = next(r for r in state["rounds"] if r["stage"] == "semifinal")
    if quarters and _complete_round(quarters) and not semis["matches"]:
        if any(m["winner_id"] is None for m in quarters["matches"]):
            state["status"] = "awaiting_tiebreak"
            state["tie_reason"] = "یکی از بازی‌های حذفی برنده ندارد؛ تعیین تکلیف مدیر لازم است."
            return
        winners = [m["winner_id"] for m in quarters["matches"]]
        _future_window(state, semis, now, state["playoff_interval_hours"])
        semis["matches"] = [_new_match(semis, i + 1, winners[i * 2], winners[i * 2 + 1]) for i in range(2)]
    if _complete_round(semis):
        final = next(r for r in state["rounds"] if r["stage"] == "final")
        third = next(r for r in state["rounds"] if r["stage"] == "third_place")
        if not final["matches"]:
            if any(m["winner_id"] is None for m in semis["matches"]):
                state["status"] = "awaiting_tiebreak"
                state["tie_reason"] = "نیمه‌نهایی بدون برنده است؛ تعیین تکلیف مدیر لازم است."
                return
            winners = [m["winner_id"] for m in semis["matches"]]
            losers = [m["b"] if m["winner_id"] == m["a"] else m["a"] for m in semis["matches"]]
            _future_window(state, final, now, state["playoff_interval_hours"])
            final["matches"] = [_new_match(final, 1, *winners)]
            third["matches"] = [_new_match(third, 1, *losers)]
        if _complete_round(final) and _complete_round(third):
            if final["matches"][0]["winner_id"] is None or third["matches"][0]["winner_id"] is None:
                state["status"] = "awaiting_tiebreak"
                state["tie_reason"] = "فینال یا رده‌بندی بدون برنده است؛ آزمون تازه با زمان اعلام‌شده لازم است."
            else:
                state["status"] = "completed"


def mutate(db, event_id, operation):
    """Optimistic transaction: concurrent starts/submits cannot overwrite each other."""
    for _ in range(5):
        db.expire_all()
        event = db.get(TournamentEvent, event_id)
        if not event:
            fail("تورنومنت پیدا نشد.", 404)
        state = json.loads(event.data)
        before = json.dumps(state, ensure_ascii=False, sort_keys=True)
        now = now_utc()
        reconcile(state, now)
        result = operation(state, now)
        reconcile(state, now)
        after = json.dumps(state, ensure_ascii=False, sort_keys=True)
        if before == after:
            return state, result
        changed = db.execute(update(TournamentEvent).where(
            TournamentEvent.id == event_id, TournamentEvent.version == event.version
        ).values(data=after, version=event.version + 1, updated_at=now.replace(tzinfo=None)))
        if changed.rowcount:
            db.commit()
            return state, result
        db.rollback()
    fail("اطلاعات مسابقه هم‌زمان تغییر کرد؛ دوباره تلاش کن.")


def _public_match(state, rnd, match):
    players = {p["id"]: p for p in state["players"]}
    closed = match["status"] in DONE
    return {"id": match["id"], "round_id": rnd["id"], "slot": match["slot"], "stage": rnd["stage"],
            "player_a": players.get(match["a"]), "player_b": players.get(match["b"]),
            "score_a": match.get("score_a") if closed else None,
            "score_b": match.get("score_b") if closed else None,
            "winner_id": match.get("winner_id") if closed else None, "status": match["status"],
            "starts_at": match.get("starts_at") or rnd["starts_at"],
            "ends_at": match.get("ends_at") or rnd["ends_at"]}


def public_event(event_id, state, detail=True):
    now = now_utc()
    fields = ("title", "description", "status", "major", "grade", "capacity", "league_rounds",
              "playoff_size", "duration_minutes", "attendance_grace_minutes", "starts_at", "registration_status")
    result = {"id": event_id, **{k: state[k] for k in fields}, "participant_count": len(state["players"]),
              "server_now": iso(now), "tie_reason": state.get("tie_reason"),
              "schedule_note": state.get("schedule_note"),
              "ends_at": max([r["ends_at"] for r in state["rounds"]] +
                             [m["ends_at"] for r in state["rounds"] for m in r["matches"] if m.get("ends_at")])}
    if not detail:
        return result
    result["standings"] = [{k: v for k, v in row.items() if not k.startswith("_")} for row in standings(state)]
    result["rounds"] = []
    for rnd in state["rounds"]:
        if any(m["status"] == "awaiting_tiebreak" for m in rnd["matches"]):
            status = "awaiting_tiebreak"
        elif _complete_round(rnd):
            status = "completed"
        elif rnd["matches"] and instant(rnd["starts_at"]) <= now:
            status = "active"
        else:
            status = "scheduled"
        result["rounds"].append({k: rnd[k] for k in ("id", "number", "stage", "label", "starts_at", "ends_at")} | {
            "ends_at": max([rnd["ends_at"]] + [m["ends_at"] for m in rnd["matches"] if m.get("ends_at")]),
            "status": status, "question_count": len(rnd["questions"]),
            "matches": [_public_match(state, rnd, m) for m in rnd["matches"]]})
    return result


def _find_match(state, match_id, user_id):
    for rnd in state["rounds"]:
        for match in rnd["matches"]:
            if match["id"] == match_id:
                if user_id not in (match["a"], match["b"]):
                    fail("این بازی به حساب تو تعلق ندارد.", 403)
                return rnd, match
    fail("بازی پیدا نشد.", 404)


def eligibility(state, rnd, match, user_id, now):
    start, end = _match_times(rnd, match)
    attempt = match["attempts"].get(str(user_id))
    if state["status"] == "draft":
        return False, False, "تورنومنت هنوز آغاز نشده است."
    if attempt and attempt.get("submitted_at"):
        return False, False, "پاسخ‌های این بازی ثبت شده است."
    if match["status"] in DONE or match["status"] == "awaiting_tiebreak":
        return False, False, "بازی پایان یافته یا در انتظار آزمون تکمیلی است."
    if now < start:
        return False, False, "بازی در زمان اعلام‌شده باز می‌شود."
    if now >= end:
        return False, False, "مهلت بازی پایان یافته است."
    if not attempt and now > start + timedelta(minutes=state["attendance_grace_minutes"]):
        return False, False, "مهلت حضور در بازی پایان یافته است."
    return not bool(attempt), bool(attempt), ""


def my_matches(event_id, state, user_id):
    participant = next((p for p in state["players"] if p["id"] == user_id), None)
    result = {"player_id": participant["id"] if participant else None, "matches": []}
    if not participant:
        return result
    for rnd in state["rounds"]:
        for match in rnd["matches"]:
            if user_id not in (match["a"], match["b"]):
                continue
            can_start, can_resume, reason = eligibility(state, rnd, match, user_id, now_utc())
            attempt = match["attempts"].get(str(user_id))
            result["matches"].append(_public_match(state, rnd, match) | {
                "can_start": can_start, "can_resume": can_resume, "reason": reason,
                "has_submitted": bool(attempt and attempt.get("submitted_at")),
                "deadline_at": iso(_match_times(rnd, match)[1])})
    return result


def start_match(state, now, event_id, match_id, user_id):
    rnd, match = _find_match(state, match_id, user_id)
    can_start, can_resume, reason = eligibility(state, rnd, match, user_id, now)
    existing = match["attempts"].get(str(user_id))
    if not can_start and not can_resume and not (existing and existing.get("submitted_at")):
        fail(reason)
    if existing is None:
        existing = match["attempts"][str(user_id)] = {"started_at": iso(now), "answers": {}, "submitted_at": None,
                                                   "answers_revision": 0}
        match["status"] = "live"
    questions = match.get("questions") or rnd["questions"]
    # Returning only a fixed allowlist prevents future metadata from leaking keys.
    visible = [{k: q[k] for k in ("id", "text", "options", "subject", "topic", "figure") if k in q} for q in questions]
    return {"match_id": match_id, "tournament_id": event_id, "title": state["title"] + " · " + rnd["label"],
            "questions": [] if existing.get("submitted_at") else visible,
            "started_at": existing["started_at"], "deadline_at": iso(_match_times(rnd, match)[1]),
            "server_now": iso(now), "submitted": bool(existing.get("submitted_at")),
            "score": existing.get("score", {}).get("percent"),
            "saved_answers": existing.get("answers") or {}, "answers_revision": existing.get("answers_revision", 0)}


def _validate_answers(questions, answers):
    known = {q["id"] for q in questions}
    if set(answers) - known or any(v is not None and (type(v) is not int or v not in range(4)) for v in answers.values()):
        fail("پاسخ‌ها باید فقط شناسه‌های همین دفترچه و گزینهٔ صفر تا سه یا خالی باشند.", 422)


def save_answers(state, now, match_id, user_id, answers, revision):
    rnd, match = _find_match(state, match_id, user_id)
    attempt = match["attempts"].get(str(user_id))
    if not attempt:
        fail("ابتدا باید همین بازی را شروع کنی.")
    if attempt.get("submitted_at") or now >= _match_times(rnd, match)[1]:
        fail("پس از پایان بازی امکان تغییر پاسخ نیست.")
    _validate_answers(match.get("questions") or rnd["questions"], answers)
    previous = attempt.get("answers_revision", 0)
    if revision < previous or revision == previous and answers != attempt.get("answers"):
        fail("پاسخ‌های جدیدتری ثبت شده است؛ بازی را دوباره باز کن.")
    if revision > previous:
        attempt.update(answers=answers, answers_revision=revision, saved_at=iso(now))
    return {"revision": attempt["answers_revision"], "saved_at": attempt.get("saved_at", attempt["started_at"])}


def submit_match(state, now, match_id, user_id, answers):
    rnd, match = _find_match(state, match_id, user_id)
    attempt = match["attempts"].get(str(user_id))
    if not attempt:
        fail("ابتدا باید همین بازی را شروع کنی.")
    if attempt.get("submitted_at"):
        return {"match_id": match_id, "status": match["status"], "score": attempt["score"]["percent"], "submitted": True}
    if now >= _match_times(rnd, match)[1]:
        fail("مهلت بازی پایان یافته است؛ پاسخ دیرهنگام پذیرفته نمی‌شود.")
    questions = match.get("questions") or rnd["questions"]
    _validate_answers(questions, answers)
    attempt["answers"] = answers
    attempt["submitted_at"] = iso(now)
    attempt["score"] = score_packet(questions, answers)
    _finish_match(rnd, match, now)
    return {"match_id": match_id, "status": match["status"], "score": attempt["score"]["percent"], "submitted": True}


def prepare_tiebreak(db, state, payload, now):
    if state["status"] == "draft" or state["status"] == "completed":
        fail("آزمون تکمیلی برای این وضعیت تورنومنت مجاز نیست.")
    start = instant(payload["starts_at"])
    if start <= now:
        fail("زمان آزمون تکمیلی باید در آینده باشد.")
    questions = _packet(db, payload["bank_question_ids"], state["major"], state["grade"])
    used = {q["id"] for r in state["rounds"] for q in r["questions"]}
    used.update(q["id"] for r in state["rounds"] for m in r["matches"] for q in m.get("questions", []))
    used.update(q for r in state["rounds"] for m in r["matches"] for q in m.get("used_tiebreak_question_ids", []))
    if used.intersection(q["id"] for q in questions):
        fail("سؤال آزمون تکمیلی باید کاملاً تازه باشد.", 422)
    end = start + timedelta(minutes=payload["duration_minutes"])
    if payload.get("match_id"):
        target = next(((r, m) for r in state["rounds"] for m in r["matches"] if m["id"] == payload["match_id"]), None)
        if (target is None or target[0]["stage"] == "league" or
                not (target[1]["status"] == "awaiting_tiebreak" or
                     target[1]["status"] == "forfeit" and target[1].get("double_forfeit"))):
            fail("فقط بازی حذفی بدون برنده می‌تواند آزمون تازه بگیرد.")
        rnd, match = target
        match.setdefault("history", []).append({"attempts": match["attempts"], "questions": match.get("questions") or rnd["questions"],
                                                 "score_a": match["score_a"], "score_b": match["score_b"]})
        match.setdefault("used_tiebreak_question_ids", []).extend(q["id"] for q in match.get("questions", []))
        match.update(questions=questions, starts_at=iso(start), ends_at=iso(end), attempts={},
                     score_a=None, score_b=None, winner_id=None, status="scheduled", double_forfeit=False)
        # Finals may move beyond their original schedule; avoid pairing a
        # downstream game before its true predecessor has finished.
        state["status"] = "knockout"
        return
    ties = cutoff_ties(state)
    if not ties or any(r.get("kind") and not _complete_round(r) for r in state["rounds"]):
        fail("در مرز صعود هم‌امتیازی حل‌نشده‌ای برای آزمون تازه وجود ندارد.")
    number = 1 + sum(bool(r.get("kind")) for r in state["rounds"])
    rnd = {"id": f"qualification-tb-{number}", "number": state["league_rounds"] + number,
           "stage": "league", "kind": "qualification_tiebreak", "label": "آزمون تکمیلی صعود",
           "starts_at": iso(start), "ends_at": iso(end), "questions": questions, "matches": []}
    rnd["matches"] = [_new_match(rnd, i, player, None, qualifier=True) for i, player in enumerate(ties, 1)]
    state["rounds"].append(rnd)
    state["status"] = "awaiting_tiebreak"


def anonymize_participant(db, user_id):
    """Join the existing full account wipe transaction without committing it.

    Keep anonymous sporting results/bracket slots, erase the profile name and
    private answers, and replace the account ID with an event-local tombstone.
    A newly-created account reusing an old SQLite ID cannot inherit its games.
    Legacy standalone wipe tests may create only the old application's tables;
    the normal app registers this additive model before ensure_schema.
    """
    if not inspect(db.connection()).has_table(TournamentEvent.__tablename__):
        return 0
    changed_count = 0
    for event in list(db.scalars(select(TournamentEvent))):
        state = json.loads(event.data)
        player = next((p for p in state["players"] if p["id"] == user_id), None)
        if player is None:
            continue
        tombstone = min([p["id"] for p in state["players"]] + [0]) - 1
        player.update(id=tombstone, name="بازیکن حذف‌شده")

        def scrub_attempts(attempts, rnd):
            attempt = attempts.pop(str(user_id), None)
            # A completed exam can keep only its anonymous aggregate score.
            # An unsubmitted draft is removed and becomes a genuine absence.
            if attempt and attempt.get("score") and attempt.get("submitted_at"):
                attempts[str(tombstone)] = {"score": attempt["score"], "submitted_at": rnd["ends_at"],
                                            "anonymized": True}

        for rnd in state["rounds"]:
            for match in rnd["matches"]:
                for field in ("a", "b", "winner_id"):
                    if match.get(field) == user_id:
                        match[field] = tombstone
                scrub_attempts(match["attempts"], rnd)
                for history in match.get("history", []):
                    scrub_attempts(history.get("attempts", {}), rnd)
        for result in state.get("qualification_results", []):
            if str(user_id) in result:
                result[str(tombstone)] = result.pop(str(user_id))
        changed = db.execute(update(TournamentEvent).where(
            TournamentEvent.id == event.id, TournamentEvent.version == event.version
        ).values(data=json.dumps(state, ensure_ascii=False), version=event.version + 1,
                 updated_at=now_utc().replace(tzinfo=None)))
        if not changed.rowcount:
            fail("تورنومنت هم‌زمان تغییر کرده است؛ حذف حساب را دوباره انجام دهید.")
        changed_count += 1
    return changed_count
