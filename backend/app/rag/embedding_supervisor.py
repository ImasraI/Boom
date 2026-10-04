"""Keep a resumable migration alive during an explicit provider quota wait."""
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.rag.embedding_progress import MigrationLock, worker_alive, write_status


def quota_retry_at(state):
    candidates = []
    if state.get("status") == "waiting_for_quota" and state.get("retry_not_before"):
        candidates.append(datetime.fromisoformat(state["retry_not_before"]))
    for event in state.get("workers", {}).values():
        if event.get("phase") != "daily_quota_exhausted":
            continue
        seconds = event.get("wait_seconds", 0)
        if type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds <= 0:
            continue
        observed = datetime.fromisoformat(event["updated_at"])
        candidates.append(observed + timedelta(seconds=seconds + 5))
    return max((date for date in candidates if date.tzinfo is not None), default=None)


def supervise_migration(run_once, status_path, now=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    status_path = Path(status_path)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor_lock = MigrationLock(status_path.with_name("gemini-supervisor.lock"))
    try:
        supervisor_lock.acquire()
    except BlockingIOError:
        print("A migration supervisor is already running; no duplicate worker started.", flush=True)
        return 2
    try:
        while True:
            state = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            if state.get("status") == "complete":
                return 0
            active = state.get("status") in {"starting", "probe_passed", "running", "waiting_for_quota"}
            if active and state.get("worker_pid") != os.getpid() and worker_alive(state.get("worker_pid")) is not False:
                print("Another migration owns the saved status; no duplicate worker started.", flush=True)
                return 2
            deadline = quota_retry_at(state)
            if deadline and deadline > now():
                # Also prevent a manual migration from racing the sleeping supervisor.
                migration_lock = MigrationLock(status_path.with_name("gemini.lock"))
                try:
                    migration_lock.acquire()
                except BlockingIOError:
                    return 2
                try:
                    state.update(status="waiting_for_quota", phase="waiting_for_daily_quota",
                                 worker_pid=os.getpid(), retry_not_before=deadline.isoformat(),
                                 reason="Daily project quota exhausted; worker will resume automatically at the provider retry time.")
                    status_path.with_name("gemini-process.pid").write_text(str(os.getpid()), encoding="utf-8")
                    print(json.dumps({"status": state["status"], "retry_not_before": state["retry_not_before"],
                                      "remaining": state.get("overall_total", 0) - state.get("overall_completed", 0)}), flush=True)
                    while deadline > now():
                        state.update(quota_remaining_seconds=max(0, math.ceil((deadline - now()).total_seconds())),
                                     updated_at=now().isoformat())
                        write_status(status_path, state)
                        sleep(max(0, min(30, (deadline - now()).total_seconds())))
                finally:
                    migration_lock.close()
            code = run_once()
            if code in {0, 2, 130}:
                return code
            failed = json.loads(status_path.read_text(encoding="utf-8"))
            if not quota_retry_at(failed):
                return code  # Auth/index/network failures need their own diagnosis.
    except KeyboardInterrupt:
        if status_path.exists():
            state = json.loads(status_path.read_text(encoding="utf-8"))
            state.update(status="stopped", phase="interrupted", reason="Supervisor interrupted; saved vectors are intact.")
            write_status(status_path, state)
        return 130
    finally:
        supervisor_lock.close()
