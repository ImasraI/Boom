"""Pace mock drafting across clients without throttling interactive chat.

Deployment uses a single API process; a separate worker has its own budget.
Waits never hold matchmaking, provider-health or HTTP-client locks.
"""
import threading
import time

_LOCK = threading.Lock()
_NEXT_START: dict[str, float] = {}


def wait_for_draft_slot(identity: str, requests_per_minute: int) -> None:
    if requests_per_minute <= 0:
        return
    interval = 60.0 / requests_per_minute
    with _LOCK:
        now = time.monotonic()
        start = max(now, _NEXT_START.get(identity, now))
        _NEXT_START[identity] = start + interval
    if start > now:
        time.sleep(start - now)
