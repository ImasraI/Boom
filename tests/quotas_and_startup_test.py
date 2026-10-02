"""Growth-readiness projects 8+9 regressions.

- Atomic AI quota: N concurrent consume_ai_use() calls can NEVER exceed the
  daily cap (the old check-then-record pattern let them all through).
- release_ai_use refunds a reservation exactly once.
- Production startup fails loudly without a real SECRET_KEY (project 8:
  "fail startup در صورت نبود secret معتبر").
"""
import os
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from fastapi import HTTPException

from app.auth import limits
from app.auth import security


@pytest.fixture()
def quotas(monkeypatch):
    """Deterministic per-feature limits + a fresh counter store per test."""
    monkeypatch.setattr(limits, "get_settings",
                        lambda: type("S", (), {
                            "AI_DAILY_MOCK_GENERATE": 5,
                            "AI_DAILY_ARENA_JOIN": 3,
                            "AI_DAILY_TOKEN_BUDGET": 0,
                        })())
    fresh = limits._DailyCounters()
    monkeypatch.setattr(limits, "_counters", fresh)
    return fresh


def test_concurrent_consumes_never_exceed_cap(quotas):
    """THE cost-control bug: 20 threads racing for 5 slots -> exactly 5 win,
    15 get 429. The old pattern admitted all 20 and recorded all 20."""
    allowed, rejected = [], []
    lock = threading.Lock()

    def worker(i):
        try:
            limits.consume_ai_use(1, "mock_generate")
            with lock:
                allowed.append(i)
        except HTTPException as e:
            assert e.status_code == 429
            with lock:
                rejected.append(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(allowed) == 5
    assert len(rejected) == 15
    assert quotas._counts[1]["mock_generate"] == 5  # never above the cap


def test_release_refunds_one_reservation(quotas):
    for _ in range(3):
        limits.consume_ai_use(1, "arena_join")
    with pytest.raises(HTTPException):
        limits.consume_ai_use(1, "arena_join")
    limits.release_ai_use(1, "arena_join")
    limits.consume_ai_use(1, "arena_join")  # refunded slot is usable again
    assert quotas._counts[1]["arena_join"] == 3
    with pytest.raises(HTTPException):
        limits.consume_ai_use(1, "arena_join")


def test_release_never_goes_negative(quotas):
    limits.release_ai_use(2, "mock_generate")  # nothing reserved
    assert quotas._counts.get(2, {}).get("mock_generate", 0) == 0


def test_production_startup_fails_without_secret(monkeypatch, tmp_path):
    """Project 8: production must refuse to boot with a missing/weak secret
    instead of silently signing tokens with a guessable key."""
    from app.utils.startup_checks import validate_startup_secrets
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setattr(security, "_resolve_secret", lambda: "")
    with pytest.raises(RuntimeError):
        validate_startup_secrets(env="production")


def test_production_startup_allows_strong_secret(monkeypatch):
    from app.utils.startup_checks import validate_startup_secrets
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setattr(security, "_resolve_secret", lambda: "x" * 32)
    validate_startup_secrets(env="production")  # no raise

    monkeypatch.setattr(security, "_resolve_secret", lambda: "short")
    with pytest.raises(RuntimeError):
        validate_startup_secrets(env="production", min_length=32)


def test_development_boots_without_secret(monkeypatch):
    from app.utils.startup_checks import validate_startup_secrets
    monkeypatch.setattr(security, "_resolve_secret", lambda: "")
    validate_startup_secrets(env="development")  # dev is allowed (random key)
