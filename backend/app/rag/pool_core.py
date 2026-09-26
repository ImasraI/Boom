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
from datetime import datetime

from sqlalchemy import select

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
            major_key, difficulty, user_id=POOL_OWNER_ID)
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
    return True


def sweep(db, target: int, majors=None, difficulties=None,
          dry_run: bool = False) -> int:
    """One pass over all (major, difficulty) shelves; returns rows produced.

    Uses the caller's session (the worker opens its own; the admin endpoint
    passes the request's). Unrecognized major keys are skipped with a log.
    """
    majors = list(majors or POOL_MAJORS)
    difficulties = list(difficulties or POOL_DIFFICULTIES)
    produced = 0
    for major_key in majors:
        if _cancel_event.is_set():
            logger.info("Pool sweep canceled after %d row(s).", produced)
            return produced
        if major_key not in CANONICAL_MAJOR:
            logger.warning("Unknown major key %r - skipping.", major_key)
            continue
        for difficulty in difficulties:
            if _cancel_event.is_set():
                logger.info("Pool sweep canceled after %d row(s).", produced)
                return produced
            deficit = pool_deficit(db, major_key, difficulty, target)
            if deficit == 0:
                continue
            if dry_run:
                print(f"[dry-run] {major_key}/{difficulty}: need {deficit} more")
                continue
            logger.info("Pool low: %s/%s needs %d more.",
                        major_key, difficulty, deficit)
            for _ in range(deficit):
                # Cancellation lands here, between booklets: the in-flight
                # booklet finishes normally and its row is kept.
                if _cancel_event.is_set():
                    logger.info("Pool sweep canceled after %d row(s).", produced)
                    return produced
                if generate_one(db, major_key, difficulty):
                    produced += 1
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
            major_key, "konkur", user_id=POOL_OWNER_ID, plan=plan)
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
    return True


def sweep_duels(db, target: int, majors=None, dry_run: bool = False) -> int:
    """One pass over the per-major duel shelves (same cancel semantics)."""
    produced = 0
    for major_key in list(majors or POOL_MAJORS):
        if _cancel_event.is_set():
            break
        if major_key not in CANONICAL_MAJOR:
            continue
        deficit = duel_pool_deficit(db, major_key, target)
        if deficit == 0:
            continue
        if dry_run:
            print(f"[dry-run] duels/{major_key}: need {deficit} more")
            continue
        for _ in range(deficit):
            if _cancel_event.is_set():
                return produced
            if generate_one_duel(db, major_key):
                produced += 1
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
    row = db.execute(
        select(GeneratedMock)
        .where(GeneratedMock.status == "pending_use")
        .where(GeneratedMock.difficulty == DUEL_DIFFICULTY)
        .where(GeneratedMock.major == label)
        .where(GeneratedMock.id.not_in(seen_a))
        .where(GeneratedMock.id.not_in(seen_b))
        .order_by(GeneratedMock.created_at.asc())
        .limit(1)
    ).scalars().first()
    if row is None:
        return None
    row.status = "claimed"
    row.student_id = user_a
    db.flush()
    return row
