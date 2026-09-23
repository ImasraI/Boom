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
from datetime import datetime

from sqlalchemy import select

from app.auth.database import GeneratedMock
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


def shelf_key(major_key: str, difficulty: str) -> str:
    return f"{major_key}/{difficulty}"


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
        if major_key not in CANONICAL_MAJOR:
            logger.warning("Unknown major key %r - skipping.", major_key)
            continue
        for difficulty in difficulties:
            deficit = pool_deficit(db, major_key, difficulty, target)
            if deficit == 0:
                continue
            if dry_run:
                print(f"[dry-run] {major_key}/{difficulty}: need {deficit} more")
                continue
            logger.info("Pool low: %s/%s needs %d more.",
                        major_key, difficulty, deficit)
            for _ in range(deficit):
                if generate_one(db, major_key, difficulty):
                    produced += 1
    return produced
