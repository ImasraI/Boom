"""Background pool worker for pre-generated Konkur mocks.

Runs as a separate process (same pattern as ocr-workers/worker.py) and keeps
a ready stock of standard booklets so /api/mocks/generate can serve users
instantly instead of waiting on a live multi-minute LLM generation.

For every (major, difficulty) shelf it counts GeneratedMock rows with
status="pending_use"; whenever the stock is below --target it generates a
new standard booklet through the SAME shared generation path the live
endpoint uses (build_pool_booklet, incl. answer verification) and inserts
it with status="pending_use".

    cd backend
    .venv/Scripts/python.exe scripts/mock_pool_worker.py                 # run forever
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --once          # one sweep, exit
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --target 5 --majors riazi
    .venv/Scripts/python.exe scripts/mock_pool_worker.py --dry-run       # show deficits only

All pooling rules (shelves, deficits, insertion) live in
app.rag.pool_core, which the admin panel's restock button also imports -
the two can never drift.

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
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.auth.database import SessionLocal
from app.rag import pool_core
from app.utils.logger import get_logger

logger = get_logger("mock_pool_worker")


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
    parser.add_argument("--admin-triggered", action="store_true",
                        help="(internal) sweep was triggered from the admin panel")
    parser.add_argument("--target-shelf", default="",
                        help="(internal) restrict to one major/difficulty shelf")
    parser.add_argument("--target-count", type=int, default=0,
                        help="(internal) override the target for this sweep")
    args = parser.parse_args()

    majors = ([m.strip() for m in args.majors.split(",") if m.strip()]
              if args.majors else None)
    difficulties = ([d.strip() for d in args.difficulties.split(",") if d.strip()]
                    if args.difficulties else None)

    logger.info("Mock pool worker: target=%d per shelf, majors=%s, difficulties=%s",
                args.target, majors or "all", difficulties or "all")

    if args.dry_run:
        db = SessionLocal()
        try:
            pool_core.sweep(db, args.target, majors, difficulties, dry_run=True)
        finally:
            db.close()
        return

    if args.once:
        db = SessionLocal()
        try:
            produced = pool_core.sweep(db, args.target, majors, difficulties)
            produced += pool_core.sweep_duels(db, max(2, args.target // 2), majors)
        finally:
            db.close()
        print(f"one sweep complete: {produced} pool row(s) generated")
        return

    # Continuous mode: keep the pool topped up forever. A crash inside one
    # sweep never ends the worker.
    while True:
        try:
            db = SessionLocal()
            try:
                produced = pool_core.sweep(db, args.target, majors, difficulties)
                produced += pool_core.sweep_duels(db, max(2, args.target // 2), majors)
            finally:
                db.close()
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
