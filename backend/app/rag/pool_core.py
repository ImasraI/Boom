"""Pool core: shared sweep logic for the mock pool.

Both callers import THIS module:
  - scripts/mock_pool_worker.py (separate process; CLI + loop around it)
  - /api/admin/pool + /api/admin/pool/restock (admin panel: levels + a
    manual "generate now" button)

Pooling rules live here so the worker and the admin trigger can never
drift: what counts as a shelf, how deficits are computed, how rows are
inserted with status="pending_use".
"""

import json
import threading
import time
from datetime import datetime

from sqlalchemy import select, update

from app.auth.database import GeneratedMock, MockAttempt
from app.rag import mock_generation
from app.rag.konkur_format import MAJOR_ALIASES, SPECIALIZED_SUBJECTS
from app.utils.logger import get_logger

logger = get_logger("mock_pool")

# The canonical Persian label each major key is stored under - must match
# what /api/mocks/generate matches against (first-registered alias per key).
CANONICAL_MAJOR: dict[str, str] = {}
for _label, _key in MAJOR_ALIASES.items():
    CANONICAL_MAJOR.setdefault(_key, _label)

# Only majors with an official specialized plan can be pooled.
POOL_MAJORS = [k for k in SPECIALIZED_SUBJECTS if k in CANONICAL_MAJOR]
POOL_DIFFICULTIES = ["easy", "konkur", "hard"]

# student_id sentinel for unassigned pool rows (no real user has id 0).
POOL_OWNER_ID = 0

# Consecutive LLM refusals (quota exhausted, rate limit, provider down) after
# which a sweep gives up. Without this a single dead quota queue made the run
# retry every remaining shelf for minutes on end while the panel kept saying
# "0 booklets", with no hint at the cause.
POOL_MAX_PROVIDER_FAILURES = 3


# --- Cooperative cancellation --------------------------------------------
# A sweep runs many multi-minute LLM booklets; the only safe way to stop it
# is at a booklet boundary. request_cancel() sets a flag that sweep() checks
# between booklets, so the in-flight booklet finishes and every already-
# produced row is kept.
_cancel_event = threading.Event()


def request_cancel() -> None:
    """Ask the running sweep to stop after its current booklet."""
    _cancel_event.set()


def cancel_requested() -> bool:
    """True when a cancel has been requested but the sweep may still be
    finishing its current booklet."""
    return _cancel_event.is_set()


def clear_cancel() -> None:
    """Reset the flag before starting a new sweep (never call mid-sweep)."""
    _cancel_event.clear()


# --- Live progress --------------------------------------------------------
# Filling several empty shelves takes many minutes. The admin panel polls
# progress_snapshot() to draw a real progress bar: which shelf is in flight,
# how many booklets this run has finished, and how long it has been running.
#
# Ownership: a sweep opens a record for itself when nobody else owns one, so
# the worker script and the in-process budgeted worker report progress too.
# The admin restock opens one FIRST so its pool + duel sweeps share a single
# bar. Every mutator below is a no-op while no record is active, which keeps
# dry runs and bare generate_one() calls from leaving stale state behind.
_progress_lock = threading.Lock()
_PROGRESS_TEMPLATE: dict = {
    "active": False,
    "label": "",
    "phase": "",
    "planned": 0,
    "produced": 0,
    # Question bookkeeping. One booklet takes minutes and holds ~100
    # questions, so "how many questions exist so far" is the number the admin
    # panel actually needs: questions_planned counts the plan targets of the
    # booklets this run started, questions what was committed to stored rows,
    # and current_* describes the booklet being worked on right now.
    "questions_planned": 0,
    "questions": 0,
    "current": None,
    "current_target": 0,
    "current_questions": 0,
    "current_verified": 0,
    # Provider health: consecutive refusals abort the run (see
    # POOL_MAX_PROVIDER_FAILURES) and last_error is the reason to show.
    "failures": 0,
    "last_error": "",
    "started_at": None,
    "finished_at": None,
}
_progress: dict = dict(_PROGRESS_TEMPLATE)


def begin_progress(label: str = "") -> bool:
    """Open a fresh run record; True when this caller owns it."""
    with _progress_lock:
        if _progress["active"]:
            return False
        _progress.clear()
        _progress.update(_PROGRESS_TEMPLATE)
        _progress.update(active=True, label=label, started_at=time.time())
        return True


def finish_progress() -> None:
    """Close the run record (the last produced row is already committed)."""
    with _progress_lock:
        if not _progress["active"]:
            return
        _progress.update(active=False, current=None,
                         finished_at=time.time())


def progress_snapshot() -> dict:
    """Read-only view of the run state; safe to call from any thread."""
    with _progress_lock:
        snap = dict(_progress)
    started, finished = snap.pop("started_at"), snap.pop("finished_at")
    snap["elapsed_seconds"] = (round((finished or time.time()) - started, 1)
                               if started else 0)
    return snap


def add_planned(count: int) -> None:
    """Grow the run's expected booklet count as shelves are discovered."""
    if count <= 0:
        return
    with _progress_lock:
        if _progress["active"]:
            _progress["planned"] += count


def set_current(major_key: str, difficulty: str) -> None:
    """Mark the shelf a booklet is being generated for right now."""
    with _progress_lock:
        if _progress["active"]:
            _progress["current"] = {
                "major_key": major_key,
                "major": CANONICAL_MAJOR.get(major_key, major_key),
                "difficulty": difficulty,
            }


def bump_produced(count: int = 1) -> None:
    with _progress_lock:
        if _progress["active"]:
            _progress["produced"] += count


def set_phase(phase: str) -> None:
    """Which step the run is in: generating / verifying / saving."""
    with _progress_lock:
        if _progress["active"]:
            _progress["phase"] = str(phase or "")


def start_booklet(target: int) -> None:
    """A new booklet is being written: count its questions from zero."""
    target = int(target or 0)
    with _progress_lock:
        if not _progress["active"]:
            return
        _progress.update(phase="generating", current_target=target,
                         current_questions=0, current_verified=0)
        _progress["questions_planned"] += target


def note_generated(count: int) -> None:
    """Questions the model handed back for the booklet in flight."""
    if count <= 0:
        return
    with _progress_lock:
        if _progress["active"]:
            _progress["current_questions"] += count


def note_verified(count: int) -> None:
    """Questions that survived the independent verification pass."""
    if count <= 0:
        return
    with _progress_lock:
        if _progress["active"]:
            _progress["current_verified"] += count


def commit_questions(count: int) -> None:
    """A booklet row was stored: add its questions to the run total. Also
    clears the failure streak - the provider just answered fine."""
    with _progress_lock:
        if not _progress["active"]:
            return
        _progress["questions"] += max(0, int(count))
        _progress["failures"] = 0
        _progress["last_error"] = ""
        _progress["phase"] = "saving"


def note_provider_error(message: str) -> None:
    """The LLM refused a call (quota/rate limit/outage); `failures` counts
    consecutive refusals so sweep() can give up instead of burning hours."""
    with _progress_lock:
        if not _progress["active"]:
            return
        _progress["failures"] += 1
        _progress["last_error"] = str(message or "")[:400]


def provider_stall() -> str:
    """Reason the run must stop, or "" while the provider is healthy."""
    with _progress_lock:
        if (_progress["active"]
                and _progress["failures"] >= POOL_MAX_PROVIDER_FAILURES):
            return (_progress["last_error"]
                    or "provider refused repeatedly (no error text)")
        return ""


def _progress_reporter():
    """Adapt generator events (mock_generation.Reporter) to the record."""
    def report(event: str, data: dict) -> None:
        if event == "booklet":
            start_booklet(int(data.get("target") or 0))
        elif event == "phase":
            set_phase(str(data.get("name") or ""))
        elif event == "generated":
            note_generated(int(data.get("count") or 0))
        elif event == "verified":
            note_verified(int(data.get("count") or 0))
        elif event == "provider_error":
            note_provider_error(str(data.get("message") or ""))

    return report


def pool_levels(db) -> list:
    """pending_use count for every (major, difficulty) shelf."""
    counts = {}
    rows = db.execute(
        select(GeneratedMock.major, GeneratedMock.difficulty)
        .where(GeneratedMock.status == "pending_use")
    ).all()
    for major_label, difficulty in rows:
        counts[(major_label, difficulty)] = counts.get((major_label, difficulty), 0) + 1
    return [
        {
            "major_key": key,
            "major": CANONICAL_MAJOR[key],
            "difficulty": difficulty,
            "available": counts.get((CANONICAL_MAJOR[key], difficulty), 0),
        }
        for key in POOL_MAJORS
        for difficulty in POOL_DIFFICULTIES
    ]


def pool_deficit(db, major_key: str, difficulty: str, target: int) -> int:
    """How many more pending_use rows this combination needs."""
    available = db.execute(
        select(GeneratedMock.id)
        .where(GeneratedMock.status == "pending_use")
        .where(GeneratedMock.difficulty == difficulty)
        .where(GeneratedMock.major == CANONICAL_MAJOR[major_key])
    ).scalars().all()
    return max(0, target - len(available))


def generate_one(db, major_key: str, difficulty: str) -> bool:
    """Generate one standard booklet and insert it as a pending_use pool row.

    Returns True when a row was added. Generation failures are logged and
    swallowed: one broken booklet must never kill a sweep.
    """
    try:
        questions, _plan, duration = mock_generation.build_pool_booklet(
            major_key, difficulty, user_id=POOL_OWNER_ID,
            report=_progress_reporter())
    except Exception:
        logger.exception("Pool generation failed for %s/%s.",
                         major_key, difficulty)
        return False
    if not questions:
        logger.warning("Pool generation produced nothing for %s/%s.",
                       major_key, difficulty)
        return False

    db.add(GeneratedMock(
        student_id=POOL_OWNER_ID,
        title=(f"آزمون آزمایشی بوم — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"),
        major=CANONICAL_MAJOR[major_key],
        grade="",
        duration_minutes=duration,
        questions=json.dumps(questions, ensure_ascii=False),
        status="pending_use",
        difficulty=difficulty,
    ))
    db.commit()
    logger.info("Pool +%d questions  [%s / %s]",
                len(questions), major_key, difficulty)
    commit_questions(len(questions))
    return True


def sweep(db, target: int, majors=None, difficulties=None,
          dry_run: bool = False, max_booklets: int = 0) -> int:
    """One pass over all (major, difficulty) shelves; returns rows produced.

    Uses the caller's session (the worker opens its own; the admin endpoint
    passes the request's). Unrecognized major keys are skipped with a log.
    `max_booklets` > 0 caps production per sweep (the in-process top-up
    uses this to stay inside free-tier LLM quotas); 0 = unlimited.

    Opens a progress record unless someone else already owns one (the admin
    restock does, so its pool + duel sweeps share one bar).
    """
    if dry_run:
        return _sweep_shelves(db, target, majors, difficulties, True,
                              max_booklets)
    owner = begin_progress("pool")
    try:
        return _sweep_shelves(db, target, majors, difficulties, False,
                              max_booklets)
    finally:
        if owner:
            finish_progress()


def _sweep_shelves(db, target: int, majors=None, difficulties=None,
                   dry_run: bool = False, max_booklets: int = 0) -> int:
    """The real sweep body; see sweep() for the contract."""
    majors = list(majors or POOL_MAJORS)
    difficulties = list(difficulties or POOL_DIFFICULTIES)
    produced = 0
    for major_key in majors:
        if _cancel_event.is_set():
            logger.info("Pool sweep canceled after %d row(s).", produced)
            return produced
        if max_booklets and produced >= max_booklets:
            return produced
        if major_key not in CANONICAL_MAJOR:
            logger.warning("Unknown major key %r - skipping.", major_key)
            continue
        for difficulty in difficulties:
            if _cancel_event.is_set():
                logger.info("Pool sweep canceled after %d row(s).", produced)
                return produced
            if max_booklets and produced >= max_booklets:
                return produced
            deficit = pool_deficit(db, major_key, difficulty, target)
            if deficit == 0:
                continue
            if dry_run:
                print(f"[dry-run] {major_key}/{difficulty}: need {deficit} more")
                continue
            logger.info("Pool low: %s/%s needs %d more.",
                        major_key, difficulty, deficit)
            add_planned(deficit)
            for _ in range(deficit):
                # Cancellation lands here, between booklets: the in-flight
                # booklet finishes normally and its row is kept.
                if _cancel_event.is_set():
                    logger.info("Pool sweep canceled after %d row(s).", produced)
                    return produced
                if max_booklets and produced >= max_booklets:
                    return produced
                stall = provider_stall()
                if stall:
                    logger.error(
                        "Pool sweep aborted after %d row(s): the provider "
                        "refused %d call(s) in a row (%s).",
                        produced, POOL_MAX_PROVIDER_FAILURES, stall)
                    return produced
                set_current(major_key, difficulty)
                if generate_one(db, major_key, difficulty):
                    produced += 1
                    bump_produced()
    return produced


# ------------------------------- Duel stock -------------------------------
# Ranked duels used to generate their booklet LIVE at match time (a multi-
# minute wait for both players). These shelves pre-generate + verify scaled
# (divisor=3) duel booklets per major so _try_pair can claim one instantly.
# They are stored with difficulty="duel" (never one of POOL_DIFFICULTIES),
# which makes them invisible to the standard mock claim query - a scaled
# duel booklet can never be served as a full-length mock.
DUEL_DIFFICULTY = "duel"


def duel_pool_deficit(db, major_key: str, target: int) -> int:
    """How many more pending_use duel rows this major's shelf needs."""
    available = db.execute(
        select(GeneratedMock.id)
        .where(GeneratedMock.status == "pending_use")
        .where(GeneratedMock.difficulty == DUEL_DIFFICULTY)
        .where(GeneratedMock.major == CANONICAL_MAJOR[major_key])
    ).scalars().all()
    return max(0, target - len(available))


def generate_one_duel(db, major_key: str) -> bool:
    """Generate one scaled + verified duel booklet into the duel shelf.

    Same shared generation path as standard pool rows (build_pool_booklet),
    on the scaled plan; verification included, because a wrong key in a
    ranked duel moves Elo. Failures are logged and swallowed like the others.
    """
    plan = mock_generation.scale_plan(
        mock_generation.default_plan(major_key), divisor=3, minimum=3)
    duration = max(10, sum(s["minutes"] for s in plan) // 3)
    try:
        questions, _plan, _ = mock_generation.build_pool_booklet(
            major_key, "konkur", user_id=POOL_OWNER_ID, plan=plan,
            report=_progress_reporter())
    except Exception:
        logger.exception("Duel pool generation failed for %s.", major_key)
        return False
    if not questions:
        logger.warning("Duel pool generation produced nothing for %s.", major_key)
        return False

    db.add(GeneratedMock(
        student_id=POOL_OWNER_ID,
        title=(f"دوئل رنکینگ بوم — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"),
        major=CANONICAL_MAJOR[major_key],
        grade="",
        duration_minutes=duration,
        questions=json.dumps(questions, ensure_ascii=False),
        status="pending_use",
        difficulty=DUEL_DIFFICULTY,
    ))
    db.commit()
    logger.info("Duel pool +%d questions  [%s]", len(questions), major_key)
    commit_questions(len(questions))
    return True


def sweep_duels(db, target: int, majors=None, dry_run: bool = False,
                max_booklets: int = 0) -> int:
    """One pass over the per-major duel shelves (same cancel semantics;
    `max_booklets` caps production exactly like sweep(), and it opens its own
    progress record only when nobody else owns one)."""
    if dry_run:
        return _sweep_duel_shelves(db, target, majors, True, max_booklets)
    owner = begin_progress("duels")
    try:
        return _sweep_duel_shelves(db, target, majors, False, max_booklets)
    finally:
        if owner:
            finish_progress()


def _sweep_duel_shelves(db, target: int, majors=None, dry_run: bool = False,
                        max_booklets: int = 0) -> int:
    """The real duel sweep body; see sweep_duels() for the contract."""
    produced = 0
    for major_key in list(majors or POOL_MAJORS):
        if _cancel_event.is_set():
            break
        if max_booklets and produced >= max_booklets:
            break
        if major_key not in CANONICAL_MAJOR:
            continue
        deficit = duel_pool_deficit(db, major_key, target)
        if deficit == 0:
            continue
        if dry_run:
            print(f"[dry-run] duels/{major_key}: need {deficit} more")
            continue
        add_planned(deficit)
        for _ in range(deficit):
            if _cancel_event.is_set():
                return produced
            if max_booklets and produced >= max_booklets:
                return produced
            stall = provider_stall()
            if stall:
                logger.error(
                    "Duel sweep aborted after %d row(s): the provider "
                    "refused %d call(s) in a row (%s).",
                    produced, POOL_MAX_PROVIDER_FAILURES, stall)
                return produced
            set_current(major_key, DUEL_DIFFICULTY)
            if generate_one_duel(db, major_key):
                produced += 1
                bump_produced()
    return produced


def claim_duel_booklet(db, user_a: int, user_b: int, major_key: str):
    """Atomically claim the oldest pending_use duel row for this major that
    NEITHER player has attempted before. Marks it claimed + assigns it to
    player A (the match row's owner convention). Returns the row or None.
    Callers hold the matchmaking lock, so the claim is serialized exactly
    like mocks._claim_pool_mock's own lock.
    """
    label = CANONICAL_MAJOR.get(major_key)
    if not label:
        return None
    seen_a = select(MockAttempt.mock_id).where(MockAttempt.student_id == user_a)
    seen_b = select(MockAttempt.mock_id).where(MockAttempt.student_id == user_b)
    rows = db.execute(
        select(GeneratedMock)
        .where(GeneratedMock.status == "pending_use")
        .where(GeneratedMock.difficulty == DUEL_DIFFICULTY)
        .where(GeneratedMock.major == label)
        .where(GeneratedMock.id.not_in(seen_a))
        .where(GeneratedMock.id.not_in(seen_b))
        .order_by(GeneratedMock.created_at.asc())
    ).scalars().all()
    for row in rows:
        if not verified_booklet(row.questions):
            db.execute(update(GeneratedMock).where(GeneratedMock.id == row.id,
                GeneratedMock.status == "pending_use").values(status="quarantined"))
            continue
        claimed = db.execute(update(GeneratedMock).where(GeneratedMock.id == row.id,
            GeneratedMock.status == "pending_use").values(status="claimed", student_id=user_a))
        if claimed.rowcount == 1:
            db.flush()
            db.refresh(row)
            return row
    return None


def verified_booklet(raw):
    """Old or malformed pool stock must be reverified before serving."""
    try:
        questions = json.loads(raw)
        return bool(questions) and isinstance(questions, list) and all(
            isinstance(q, dict) and q.get("verification_status") == "verified"
            and isinstance(q.get("options"), list) and len(q["options"]) == 4
            and type(q.get("answer")) is int and 0 <= q["answer"] < 4
            for q in questions)
    except (ValueError, TypeError):
        return False
