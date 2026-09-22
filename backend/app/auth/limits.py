"""Per-user AI usage quotas + in-memory rate limiting.

AI_DAILY_LIMITS caps how many AI requests each feature can serve a user per
day (all adjustable in .env). Sliding-window per-IP rate limiting protects
the auth endpoints from brute force. Counters are process-local; a restart
resets them (acceptable for a single-process deployment; swap for Redis if
you ever go multi-process).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..config import get_settings


def _today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class _DailyCounters:
    """user_id -> {feature: count}, reset automatically at UTC midnight."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = _today_key()
        self._counts: dict[int, dict[str, int]] = defaultdict(dict)

    def _rollover(self) -> None:
        day = _today_key()
        if day != self._day:
            self._day = day
            self._counts.clear()

    def snapshot(self, user_id: int) -> dict[str, int]:
        with self._lock:
            self._rollover()
            return dict(self._counts.get(user_id, {}))

    def precheck(self, user_id: int, feature: str, limit: int) -> None:
        """Raise 429 when the user is over their daily budget for `feature`."""
        with self._lock:
            self._rollover()
            used = self._counts[user_id].get(feature, 0)
            if used >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="سهمیه روزانه‌ات برای این بخش تمام شده؛ فردا دوباره تلاش کن",
                )

    def record(self, user_id: int, feature: str) -> None:
        """Count one AI use AFTER the request succeeded (failures are free)."""
        with self._lock:
            self._rollover()
            self._counts[user_id][feature] = self._counts[user_id].get(feature, 0) + 1


_counters = _DailyCounters()


class QuotaExceeded(Exception):
    pass


def check_ai_quota(user_id: int, feature: str) -> None:
    """Raise 429 if over budget. Feature keys: chat, study_plan, weekly_plan,
    today_tests, mock_generate."""
    limit = getattr(get_settings(), f"AI_DAILY_{feature.upper()}", 0)
    if limit <= 0:
        return  # 0/negative = unlimited
    _counters.precheck(user_id, feature, limit)


def record_ai_use(user_id: int, feature: str) -> None:
    limit = getattr(get_settings(), f"AI_DAILY_{feature.upper()}", 0)
    if limit <= 0:
        return
    _counters.record(user_id, feature)


def usage_snapshot(user_id: int) -> dict:
    return {
        "day": _today_key(),
        "features": _counters.snapshot(user_id),
        "limits": {
            "chat": get_settings().AI_DAILY_CHAT,
            "study_plan": get_settings().AI_DAILY_STUDY_PLAN,
            "weekly_plan": get_settings().AI_DAILY_WEEKLY_PLAN,
            "today_tests": get_settings().AI_DAILY_TODAY_TESTS,
            "mock_generate": get_settings().AI_DAILY_MOCK_GENERATE,
        },
    }


# ---------------------------------------------------------------------------
# Sliding-window per-IP rate limiter (auth brute-force protection)
# ---------------------------------------------------------------------------


class _RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def hit(self, key: str, limit: int, window_s: int) -> None:
        now = time.monotonic()
        with self._lock:
            # occasional garbage collection so the map cannot grow unbounded
            if now - self._last_sweep > 600:
                self._last_sweep = now
                for k in [k for k, dq in self._hits.items() if not dq or now - dq[-1] > 3600]:
                    del self._hits[k]
            dq = self._hits[key]
            while dq and now - dq[0] > window_s:
                dq.popleft()
            if len(dq) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="درخواست‌های زیاد؛ کمی صبر کنید",
                )
            dq.append(now)


_limiter = _RateLimiter()


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, limit: int, window_s: int = 60) -> None:
    _limiter.hit(client_ip(request), limit, window_s)
