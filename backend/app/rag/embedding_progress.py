"""Read-only worker health checks and a portable single-writer migration lock."""
import os
import json
import sqlite3
import time
from pathlib import Path


def write_status(path, state):
    """Replace a complete snapshot, tolerating brief Windows reader locks."""
    path = Path(path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(.025 * (attempt + 1))


def worker_alive(pid):
    if not isinstance(pid, int) or pid < 1:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None if ctypes.get_last_error() == 5 else False
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # Unix probe only; NEVER use this on Windows.
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def collection_counts(directory):
    path = Path(directory) / "chroma.sqlite3"
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT c.name, count(e.id) FROM collections c "
            "LEFT JOIN segments s ON s.collection=c.id AND s.scope='METADATA' "
            "LEFT JOIN embeddings e ON e.segment_id=s.id GROUP BY c.name"
        ).fetchall()
    return dict(rows)


def checked_status(state):
    result = dict(state)
    if state.get("status") in {"starting", "probe_passed", "running", "waiting_for_quota"} and state.get("worker_pid"):
        alive = worker_alive(state["worker_pid"])
        result["worker_alive"] = alive
        if alive is False:
            result.update(status="interrupted", reason="Worker exited; stored progress is safe and resumable.")
    return result


class MigrationLock:
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def acquire(self):
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise BlockingIOError("Another embedding migration is already running.") from None

    def close(self):
        if self.file:
            self.file.close()  # OS releases the lock even after an abrupt process exit.
            self.file = None
