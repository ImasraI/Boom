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
_ACCESS_BLOCKS: dict[str, str] = {}
_RATE_BLOCKS: dict[str, float] = {}
_LOADED_PATHS: set[str] = set()
DAILY_QUOTA_MESSAGE = (
    "سهمیه روزانه سرویس ساخت آزمون تمام شده است. آزمون‌های آماده همچنان قابل "
    "استفاده‌اند؛ برای ساخت آزمون جدید باید تا بازنشانی سهمیه صبر کنید یا مدیر "
    "سایت سرویس تولید آزمون را تغییر دهد."
)


def is_daily_quota_error(reason: str) -> bool:
    return bool(re.search(r"per.?day|daily", reason or "", re.IGNORECASE))


def is_terminal_provider_error(reason: str) -> bool:
    return is_daily_quota_error(reason) or bool(re.search(r"\bHTTP (?:401|403)\b", reason or ""))


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
        access = entries.get('__access', {})
        if isinstance(access, dict):
            for identity, code in access.items():
                if re.fullmatch(r'[0-9a-f]{64}', identity) and code in {'HTTP 401','HTTP 403'}:
                    _ACCESS_BLOCKS[identity] = code
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
        if _ACCESS_BLOCKS:
            saved['__access'] = dict(_ACCESS_BLOCKS)
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


def block_daily_quota(identity: str, reason: str, *, retry_seconds: float | None = None) -> None:
    now = datetime.now(timezone.utc)
    until = (now.timestamp() + retry_seconds if retry_seconds is not None
             else next_gemini_reset(now).timestamp())
    with _LOCK:
        _load_saved_locked()
        _BLOCKS[identity] = (until, reason)
        _save_locked()


def block_rate_limit(identity: str, seconds: float) -> None:
    with _LOCK:
        _RATE_BLOCKS[identity] = datetime.now(timezone.utc).timestamp() + max(1, seconds)


def rate_limited(identity: str) -> float:
    with _LOCK:
        remaining = _RATE_BLOCKS.get(identity, 0) - datetime.now(timezone.utc).timestamp()
        if remaining <= 0:
            _RATE_BLOCKS.pop(identity, None)
            return 0
        return remaining


def block_access(identity: str, status: int) -> None:
    """A rejected credential/model needs changed configuration, not daily retries."""
    assert status in (401, 403)
    with _LOCK:
        _load_saved_locked()
        _ACCESS_BLOCKS[identity] = f'HTTP {status}'
        _save_locked()


def blocked_access(identity: str) -> str | None:
    with _LOCK:
        _load_saved_locked()
        return _ACCESS_BLOCKS.get(identity)


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


def pool_gemini_keys(settings, *, verification: bool = False) -> list[str]:
    """Explicit pool credentials in priority order, without duplicates.

    The primary retains the existing dedicated/shared-key behavior. Backups
    are opt-in and are never implicitly taken from chat or embedding workers.
    """
    dedicated = (getattr(settings, "POOL_VERIFY_LLM_API_KEY", "") if verification
                 else settings.POOL_LLM_API_KEY)
    primary = ((dedicated or "").strip()
               or (settings.GEMINI_API_KEY or "").strip())
    name = "POOL_VERIFY_GEMINI_API_KEYS" if verification else "POOL_GEMINI_API_KEYS"
    extras = getattr(settings, name, "") or ""
    return list(dict.fromkeys(key.strip() for key in [primary, *extras.split(",")]
                             if key.strip()))


def groq_keys(settings, *, pool: bool = False) -> list[str]:
    primary = ((getattr(settings, "POOL_LLM_API_KEY", "") if pool else "")
               or settings.LLM_API_KEY or "")
    extras = getattr(settings, "POOL_GROQ_API_KEYS" if pool else "LLM_GROQ_API_KEYS", "")
    return list(dict.fromkeys(key.strip() for key in [primary, *(extras or "").split(",")]
                             if key.strip()))


def _has_pool_fallback(settings) -> bool:
    """Mirror supported factory fallbacks without opening HTTP clients."""
    names = {name.strip().lower() for name in
             (settings.POOL_LLM_FALLBACK_PROVIDERS or "").split(",")}
    for name in names - {"gemini"}:
        if name in {"groq", "openai", "omniroute"} and (settings.LLM_API_KEY or "").strip():
            return True
        if name == "cerebras" and (settings.CEREBRAS_API_KEY or "").strip():
            return True
        if name == "ollama" and any(host in settings.LLM_BASE_URL for host in
                                    ("localhost:11434", "127.0.0.1:11434")):
            return True
    return False


def pool_quota_status() -> dict:
    """Read health without a network request or creating another HTTP client."""
    from app.config import get_settings

    settings = get_settings()
    generation = _stage_quota_status(settings)
    if generation["blocked"]:
        return {**generation, "stage": "generation",
                "provider": (settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER).strip().lower()}
    if (getattr(settings, "POOL_VERIFY_LLM_PROVIDER", "") or "").strip():
        verification = _stage_quota_status(settings, verification=True)
        if verification["blocked"]:
            return {**verification, "provider": settings.POOL_VERIFY_LLM_PROVIDER.strip().lower()}
        return verification
    return generation


def _stage_quota_status(settings, *, verification: bool = False) -> dict:
    if verification:
        provider = settings.POOL_VERIFY_LLM_PROVIDER.strip().lower()
        override_model = getattr(settings, "POOL_VERIFY_LLM_MODEL_NAME", "")
    else:
        provider = ((settings.POOL_LLM_PROVIDER or "").strip()
                    or (settings.LLM_PROVIDER or "").strip()).lower()
        override_model = settings.POOL_LLM_MODEL_NAME
    if provider not in {"gemini", "groq"}:
        return {"blocked": False}
    model = ((override_model or "").strip() or
             (settings.GEMINI_MODEL_NAME if provider == "gemini" else settings.LLM_MODEL_NAME).strip())
    base = settings.GEMINI_BASE_URL if provider == "gemini" else "https://api.groq.com/openai/v1"
    keys = (pool_gemini_keys(settings, verification=verification) if provider == "gemini"
            else groq_keys(settings, pool=True))
    identities = [quota_identity(base, model, key) for key in keys]
    entries = [(blocked_quota(identity), blocked_access(identity)) for identity in identities]
    cooldowns = [rate_limited(identity) for identity in identities]
    # Explicitly configured alternatives may still answer. Never enable the
    # chat provider implicitly: stocking shelves must not drain chat's quota.
    fallback = not verification and _has_pool_fallback(settings)
    if entries and not fallback and all(daily or access or seconds > 0
            for (daily, access), seconds in zip(entries, cooldowns)):
        waits = [seconds for (daily, access), seconds in zip(entries, cooldowns)
                 if not daily and not access and seconds > 0]
        if waits:
            retry_after = max(1, math.ceil(min(waits)))
            return {"blocked": True, "code": "provider_rate_limit", "retry_after": retry_after,
                    "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(),
                    "message": "سرویس ساخت آزمون به سقف موقت درخواست‌ها رسیده است؛ پس از زمان اعلام‌شده دوباره تلاش کنید.",
                    **({"stage": "verification"} if verification else {})}
    if not entries and verification:
        return {"blocked":True, "code":"provider_not_configured", "stage":"verification",
                "message":"کلید سرویس بررسی پاسخ آزمون تنظیم نشده است؛ مدیر سایت تنظیمات را بررسی کند."}
    if not entries or any(not daily and not access for daily, access in entries) or fallback:
        return {"blocked": False}
    retryable = [daily[0] for daily, access in entries if daily and not access]
    if not retryable:
        return {"blocked":True, "code":"provider_access_denied",
                **({"stage":"verification"} if verification else {}),
                "message":"کلید سرویس آزمون رد شده یا دسترسی ندارد؛ مدیر سایت باید کلید معتبر تنظیم کند."}
    until = min(retryable)
    return {
        "blocked": True,
        "code": "provider_daily_quota",
        "message": DAILY_QUOTA_MESSAGE,
        "retry_at": datetime.fromtimestamp(until, timezone.utc).isoformat(),
        "retry_after": max(1, math.ceil(until - datetime.now(timezone.utc).timestamp())),
        **({"stage": "verification"} if verification else {}),
    }


def require_pool_available() -> None:
    from fastapi import HTTPException

    status = pool_quota_status()
    if status["blocked"]:
        raise HTTPException(503, detail=status,
                            headers=({"Retry-After": str(status["retry_after"])}
                                     if status.get("retry_after") else None))
