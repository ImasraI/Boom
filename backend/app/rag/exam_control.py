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
    path = Path(root) / 'scanner-settings.json'
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


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
