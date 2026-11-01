"""Local scanner controls; contains no credentials and never makes API calls."""
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from app.rag.exam_corpus import atomic_json, read_json


@contextmanager
def keep_awake():
    """Prevent idle system sleep during scanning; restore this thread on exit.

    Display sleep is allowed. Explicit sleep/lid-close/shutdown still wins.
    No persistent power settings are modified.
    """
    if os.name != 'nt':
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    previous = kernel.SetThreadExecutionState(0x80000001)
    if not previous:
        raise OSError('Could not prevent idle sleep; check Windows power settings')
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(previous)


class ScanStopped(Exception):
    def __init__(self, root):
        self.root = Path(root)


def stopped(root):
    return (Path(root) / 'stop-requested').exists()


def check_stop(root):
    if stopped(root):
        raise ScanStopped(root)


def settings_signature(root):
    paths = [Path(root) / name for name in ('scanner-settings.json', 'quota-recheck.json')]
    result = []
    for path in paths:
        try:
            stat = path.stat(); result.append((stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            result.append(None)
    return tuple(result)


def set_proxy(root, value):
    # Explicit direct mode is allowed, but disappearance of a proxy never
    # implicitly authorizes direct routing. No credentials in proxy URLs.
    if value not in ('direct', 'auto'):
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or not parsed.port or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Use http(s)://host:port, auto, or direct; no credentials')
    atomic_json(Path(root) / 'scanner-settings.json', {'proxy': value})


def apply_settings(root):
    path = Path(root) / 'scanner-settings.json'
    if not path.exists():
        if os.environ.get('EXAM_OCR_PROXY','').strip().lower()=='auto':
            os.environ['EXAM_OCR_PROXY']='http://127.0.0.1:10809'
        return
    row = read_json(path, None)
    if not isinstance(row, dict) or not isinstance(row.get('proxy'), str):
        raise ValueError('Invalid scanner-settings.json; repair local proxy setting')
    value = row['proxy']
    if value == 'auto':
        # This launcher's documented VPN endpoint, even while offline.
        value = 'http://127.0.0.1:10809'
    elif value == 'direct':
        value = 'direct'
    else:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or not parsed.port or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Invalid local scanner proxy setting')
    os.environ['EXAM_OCR_PROXY'] = value


def request_quota_recheck(root):
    """Queue one explicit operator override; never erase refusal evidence."""
    import time, uuid
    row = {'request_id': uuid.uuid4().hex, 'requested_at': time.time()}
    atomic_json(Path(root)/'quota-recheck.json', row)
    return row


def apply_quota_recheck(fleet):
    """Worker-only, idempotent retry grant for saved cooldowns, not access errors."""
    import time
    root = fleet.root
    request = read_json(root/'quota-recheck.json', {})
    done = read_json(root/'quota-recheck-applied.json', {})
    if not request.get('request_id') or done.get('request_id') == request['request_id']:
        return 0
    # Archive before changing either store. Checkpoints are never touched.
    shared = read_json(fleet.shared_path, {})
    archive = root/'quota-rechecks'/request['request_id']
    atomic_json(archive/'vision-quota.json', fleet.state)
    atomic_json(archive/'shared-quota.json', shared)
    count = 0
    for spec in fleet.specs:
        saved = fleet.state.get(spec.identity, {})
        if saved.get('access_denied') or saved.get('http_status') == 401:
            continue
        if saved.get('retry_at'):
            fleet.state[spec.identity] = {**saved, 'retry_at': 0,
                'operator_recheck_at': time.time(), 'previous_retry_at': saved['retry_at']}
            count += 1
        shared.pop(spec.identity, None)
    atomic_json(fleet.state_path, fleet.state)
    atomic_json(fleet.shared_path, shared)
    atomic_json(root/'quota-recheck-applied.json', {**request, 'applied_at': time.time(),
        'cooldowns_released': count})
    return count


def scanner_running(root):
    """Probe the actual worker lock; Windows can reuse stale saved PIDs."""
    import errno
    path=Path(root)/'worker.lock'
    if not path.exists():return False
    with path.open('r+b') as handle:
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):return True
            raise
        if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(handle,fcntl.LOCK_UN)
    return False
