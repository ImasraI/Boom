"""Small process-local request/error counters for operational visibility.

The counters intentionally contain no user content or credentials. They are
useful on a single-process deployment and can later be replaced by Prometheus
or OpenTelemetry without changing callers.
"""
from collections import Counter
from threading import Lock
from typing import Dict

_lock = Lock()
_requests = Counter()
_errors = Counter()


def record_request(method: str, path: str, status_code: int) -> None:
    with _lock:
        _requests[f"{method} {path} {status_code // 100}xx"] += 1
        if status_code >= 500:
            _errors[f"{method} {path}"] += 1


def record_error(kind: str) -> None:
    with _lock:
        _errors[kind] += 1


def snapshot() -> Dict[str, Dict[str, int]]:
    with _lock:
        return {
            "requests": dict(_requests),
            "errors": dict(_errors),
        }
