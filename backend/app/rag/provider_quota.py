"""Remember terminal Gemini generation limits across newly-created clients.

This is provider health, not a quota workaround. A credential/model is
only retried after Google's next Pacific midnight or a configuration change.
No credential or provider response is exposed by the public health snapshot.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re
import threading
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOCK = threading.Lock()
_BLOCKS: dict[str, tuple[float, str]] = {}
_LOADED_PATHS: set[str] = set()
DAILY_QUOTA_MESSAGE = (
    "سهمیه روزانه سرویس ساخت آزمون تمام شده است. آزمون‌های آماده همچنان قابل "
    "استفاده‌اند؛ برای ساخت آزمون جدید باید تا بازنشانی سهمیه صبر کنید یا مدیر "
    "سایت سرویس تولید آزمون را تغییر دهد."
)


def is_daily_quota_error(reason: str) -> bool:
    return bool(re.search(r"per.?day|daily", reason or "", re.IGNORECASE))


def quota_identity(base_url: str, model: str, key: str) -> str:
    return hashlib.sha256(f"{base_url.rstrip('/')}\0{model}\0{key}".encode()).hexdigest()


def _state_file() -> Path | None:
    from app.config import get_settings
    value = getattr(get_settings(), "POOL_QUOTA_STATE_PATH", "")
    return Path(value) if value else None


def _load_saved_locked() -> None:
    path = _state_file()
    if not path or str(path) in _LOADED_PATHS:
        return
    _LOADED_PATHS.add(str(path))
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).timestamp()
        for identity, until in entries.items():
            if re.fullmatch(r"[0-9a-f]{64}", identity) and isinstance(until, (int, float)) and math.isfinite(until) and until > now:
                _BLOCKS[identity] = (until, DAILY_QUOTA_MESSAGE)
    except (OSError, ValueError, TypeError, AttributeError):
        pass


def _save_locked() -> None:
    path = _state_file()
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        # Provider response text can contain credentials; store only fingerprints and reset times.
        saved = {identity: until for identity, (until, _) in _BLOCKS.items()
                 if until > datetime.now(timezone.utc).timestamp()}
        temporary.write_text(json.dumps(saved), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    except OSError:
        pass  # In-memory protection still works if the configured file is unavailable.


def next_gemini_reset(now: datetime) -> datetime:
    try:
        pacific = ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        # Conservative fallback: never retry an hour early during daylight time.
        pacific = timezone(timedelta(hours=-8))
    local = now.astimezone(pacific)
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=pacific).astimezone(timezone.utc)


def block_daily_quota(identity: str, reason: str) -> None:
    until = next_gemini_reset(datetime.now(timezone.utc)).timestamp()
    with _LOCK:
        _load_saved_locked()
        _BLOCKS[identity] = (until, reason)
        _save_locked()


def blocked_quota(identity: str) -> tuple[float, str] | None:
    now = datetime.now(timezone.utc).timestamp()
    with _LOCK:
        _load_saved_locked()
        entry = _BLOCKS.get(identity)
        if entry and entry[0] <= now:
            _BLOCKS.pop(identity, None)
            _save_locked()
            return None
        return entry


def pool_quota_status() -> dict:
    """Read health without a network request or creating another HTTP client."""
    from app.config import get_settings

    settings = get_settings()
    provider = (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER or "").strip().lower()
    if provider != "gemini":
        return {"blocked": False}
    model = (settings.POOL_LLM_MODEL_NAME or settings.GEMINI_MODEL_NAME).strip()
    key = (settings.POOL_LLM_API_KEY or settings.GEMINI_API_KEY).strip()
    entry = blocked_quota(quota_identity(settings.GEMINI_BASE_URL, model, key))
    # Explicitly configured alternatives may still answer. Never enable the
    # chat provider implicitly: stocking shelves must not drain chat's quota.
    fallback = bool((settings.POOL_LLM_FALLBACK_PROVIDERS or "").strip())
    if not entry or fallback:
        return {"blocked": False}
    until, _reason = entry
    return {
        "blocked": True,
        "code": "provider_daily_quota",
        "message": DAILY_QUOTA_MESSAGE,
        "retry_at": datetime.fromtimestamp(until, timezone.utc).isoformat(),
        "retry_after": max(1, math.ceil(until - datetime.now(timezone.utc).timestamp())),
    }


def require_pool_available() -> None:
    from fastapi import HTTPException

    status = pool_quota_status()
    if status["blocked"]:
        raise HTTPException(503, detail=status,
                            headers={"Retry-After": str(status["retry_after"])})
