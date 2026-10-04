"""From backend/: python scripts/embedding_status.py --watch"""
import argparse
import json
import sys
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.config import Settings
from app.rag.embedding_progress import checked_status, collection_counts
from app.rag.gemini_embeddings import gemini_collection_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    settings = Settings(_env_file=root / ".env")
    path = root / "data" / "embedding_migrations" / "gemini-status.json"
    while True:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            # Legacy status records used the Windows venv launcher PID.
            pid_path = path.with_name("gemini-process.pid")
            if not state.get("worker_pid") and pid_path.exists():
                state["worker_pid"] = int(pid_path.read_text().strip())
            state = checked_status(state)
            directory = Path(settings.CHROMA_DIR)
            if not directory.is_absolute():
                directory = root / directory
            counts = collection_counts(directory)
            sources = [settings.CHROMA_COLLECTION, settings.CHROMA_QA_COLLECTION]
            total = sum(counts.get(name, 0) for name in sources)
            done = sum(counts.get(gemini_collection_name(name, state["model"], state["dimensions"]), 0)
                       for name in sources)
            percent = 100 * done / total if total else 0
            print(f"{state['status']} | {done}/{total} ({percent:.1f}%) | {max(0, total-done)} remaining | "
                  f"{state.get('phase', state.get('reason', 'indexing'))}", flush=True)
            if state.get("reason"):
                print(state["reason"], flush=True)
            if state.get("status") == "waiting_for_quota" and state.get("retry_not_before"):
                deadline = datetime.fromisoformat(state["retry_not_before"])
                remaining = max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))
                tehran = deadline.astimezone(timezone(timedelta(hours=3, minutes=30)))
                print(f"Automatic resume: {tehran:%Y-%m-%d %H:%M:%S} Tehran | quota wait {remaining // 60}m {remaining % 60}s | worker alive: {state.get('worker_alive')}", flush=True)
            if not args.watch or state["status"] in {"complete", "stopped", "interrupted"}:
                return 0 if state["status"] == "complete" else 1 if state["status"] in {"stopped", "interrupted"} else 0
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            print(f"Cannot read progress: {type(error).__name__}", flush=True)
            if not args.watch:
                return 1
        time.sleep(5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass  # Ctrl+C stops this viewer, never the migration.
