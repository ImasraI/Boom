"""Background pool worker for pre-generated Konkur mocks.

Runs as a separate process (same pattern as ocr-workers/worker.py) and keeps
a ready stock of standard booklets so /api/mocks/generate can serve users
instantly instead of waiting on a live multi-minute LLM generation.

For every (major, difficulty) combination it counts GeneratedMock rows with
status="pending_use"; whenever the stock is below --target it generates a new
standard booklet through the SAME shared generation path the live endpoint
uses (app.rag.mock_generation.build_pool_booklet) and inserts it with
status="pending_use". Claimed/live/duel rows are never touched.

    cd backend
    .venv/Scripts/python.exe scripts/mock_pool_worker.py                 # run forever
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --once          # one sweep, exit
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --target 5 --majors riazi
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --dry-run       # show deficits only

Pool rows are stored with student_id=0 (a sentinel: no real user has id 0)
and the canonical Persian major label for their major key, so the endpoint's
claim query (major IN <labels>, difficulty = X, status = "pending_use")
matches them. The claim flips status to "claimed" and assigns the real
student_id atomically (see mocks._claim_pool_mock).
"""

import argparse
import io
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import json

from sqlalchemy import select

from app.auth.database import GeneratedMock, SessionLocal
from app.rag import mock_generation
from app.rag.konkur_format import MAJOR_ALIASES, SPECIALIZED_SUBJECTS
from app.utils.logger import get_logger

logger = get_logger("mock_pool_worker")

# The canonical Persian label each major key is stored under - must match
# what /api/mocks/generate matches against (first-registered alias per key).
CANONICAL_MAJOR = {}
for label, key in MAJOR_ALIASES.items():
    CANONICAL_MAJOR.setdefault(key, label)

# Only majors with an official specialized plan can be pooled.
POOL_MAJORS = [k for k in SPECIALIZED_SUBJECTS if k in CANONICAL_MAJOR]
POOL_DIFFICULTIES = ["easy", "konkur", "hard"]

# student_id sentinel for unassigned pool rows (no real user has id 0).
POOL_OWNER_ID = 0


def pool_deficit(db, major_key: str, difficulty: str, target: int) -> int:
    """How many more pending_use rows this combination needs."""
    available = len(
        db.execute(
            select(GeneratedMock.id)
            .where(GeneratedMock.status == "pending_use")
            .where(GeneratedMock.difficulty == difficulty)
            .where(GeneratedMock.major == CANONICAL_MAJOR[major_key])
        ).scalars().all()
    )
    return max(0, target - available)


def generate_one(db, major_key: str, difficulty: str) -> bool:
    """Generate one standard booklet and insert it as a pending_use pool row.

    Returns True when a row was added. Generation failures are logged and
    swallowed: a broken sweep must never kill the worker loop.
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


def sweep(target: int, majors: list, difficulties: list, dry_run: bool) -> int:
    """One pass over all combinations; returns rows generated this sweep."""
    db = SessionLocal()
    produced = 0
    try:
        for major_key in majors:
            if major_key not in CANONICAL_MAJOR:
                logger.warning("Unknown major key %r - skipping.", major_key)
                continue
            for difficulty in difficulties:
                deficit = pool_deficit(db, major_key, difficulty, target)
                if deficit == 0:
                    continue
                if dry_run:
                    print(f"[dry-run] {major_key}/{difficulty}: "
                          f"need {deficit} more")
                    continue
                logger.info("Pool low: %s/%s needs %d more.",
                            major_key, difficulty, deficit)
                for _ in range(deficit):
                    if generate_one(db, major_key, difficulty):
                        produced += 1
    finally:
        db.close()
    return produced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=5,
                        help="pending_use rows to keep per (major, difficulty)")
    parser.add_argument("--majors", default="",
                        help="comma list of major keys (default: all pooled)")
    parser.add_argument("--difficulties", default="",
                        help="comma list: easy,konkur,hard (default: all)")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="seconds between sweeps in continuous mode")
    parser.add_argument("--once", action="store_true",
                        help="one sweep then exit (for cron / testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report deficits without generating")
    args = parser.parse_args()

    majors = ([m.strip() for m in args.majors.split(",") if m.strip()]
              if args.majors else POOL_MAJORS)
    difficulties = ([d.strip() for d in args.difficulties.split(",") if d.strip()]
                    if args.difficulties else POOL_DIFFICULTIES)

    logger.info("Mock pool worker: target=%d per combination, majors=%s, "
                "difficulties=%s", args.target, majors, difficulties)

    if args.dry_run:
        sweep(args.target, majors, difficulties, dry_run=True)
        return

    if args.once:
        produced = sweep(args.target, majors, difficulties, dry_run=False)
        print(f"one sweep complete: {produced} pool row(s) generated")
        return

    # Continuous mode: keep the pool topped up forever. Each sweep exits the
    # loop condition naturally when everything is at target (produced == 0),
    # then sleeps. A crash inside one sweep never ends the worker.
    while True:
        try:
            produced = sweep(args.target, majors, difficulties, dry_run=False)
            if produced:
                logger.info("Sweep done: %d pool row(s) generated.", produced)
            else:
                logger.info("Pool full; next sweep in %.0fs.", args.interval)
        except KeyboardInterrupt:
            logger.info("Pool worker stopped by user.")
            return
        except Exception:
            logger.exception("Sweep crashed; retrying next interval.")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
