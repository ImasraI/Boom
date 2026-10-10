"""Admin-managed pool credentials; secrets remain in the private backend .env."""
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values
from fastapi import HTTPException

from app.config import get_settings
from app.rag import provider_quota

_LOCK = threading.RLock()
_FIELDS = {
    ("groq", "generation"): "POOL_GROQ_API_KEYS",
    ("gemini", "generation"): "POOL_GEMINI_API_KEYS",
    ("gemini", "verification"): "POOL_VERIFY_GEMINI_API_KEYS",
}


def _env_path():
    return Path(__file__).resolve().parents[2] / ".env"


@contextmanager
def _file_lock(path):
    # Serialize read/append/replace across API processes, including Windows.
    with _LOCK, open(path.with_name(".env.pool-keys.lock"), "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            os.fchmod(handle.fileno(), 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _keys(settings, provider, stage):
    active_provider = ((settings.POOL_VERIFY_LLM_PROVIDER if stage == "verification"
                        else settings.POOL_LLM_PROVIDER or settings.LLM_PROVIDER) or "").lower().strip()
    if active_provider == provider:
        keys = (provider_quota.groq_keys(settings, pool=True) if provider == "groq"
                else provider_quota.pool_gemini_keys(settings, verification=stage == "verification"))
    else:
        keys = getattr(settings, _FIELDS[(provider, stage)], "").split(",")
    return list(dict.fromkeys(key.strip() for key in keys if key.strip())), active_provider == provider


def snapshot():
    settings = get_settings()
    groups = []
    for provider, stage in _FIELDS:
        keys, active = _keys(settings, provider, stage)
        model = ((settings.POOL_VERIFY_LLM_MODEL_NAME if stage == "verification"
                  else settings.POOL_LLM_MODEL_NAME) or
                 (settings.GEMINI_MODEL_NAME if provider == "gemini" else settings.LLM_MODEL_NAME))
        base = settings.GEMINI_BASE_URL if provider == "gemini" else "https://api.groq.com/openai/v1"
        counts = dict(available=0, daily_limited=0, access_denied=0, cooling_down=0)
        for key in keys:
            identity = provider_quota.quota_identity(base, model, key)
            if provider_quota.blocked_access(identity):
                counts["access_denied"] += 1
            elif provider_quota.blocked_quota(identity):
                counts["daily_limited"] += 1
            elif provider_quota.rate_limited(identity) > 0:
                counts["cooling_down"] += 1
            else:
                counts["available"] += 1
        groups.append(dict(provider=provider, stage=stage, active=active, total=len(keys), **counts))
    return {"groups": groups, "health": provider_quota.pool_quota_status(settings=settings)}


def add(provider, stage, key):
    # Manual validation avoids Pydantic's validation errors echoing secret input.
    if not isinstance(provider, str) or not isinstance(stage, str) or (provider, stage) not in _FIELDS:
        raise HTTPException(400, "سرویس یا کاربرد کلید معتبر نیست.")
    if not isinstance(key, str):
        raise HTTPException(400, "کلید معتبر نیست.")
    key = key.strip()
    prefix = r"gsk_" if provider == "groq" else r"(?:AIza|AQ\.)"
    if not 32 <= len(key) <= 512 or not re.fullmatch(prefix + r"[A-Za-z0-9_-]+", key):
        raise HTTPException(400, "قالب کلید معتبر نیست؛ کلید کامل همین سرویس را وارد کنید.")
    field = _FIELDS[(provider, stage)]
    path = _env_path()
    try:
        with _file_lock(path):
            # New Settings instances read this file. Preserve env-var overrides
            # explicitly for this field only, without changing other settings.
            settings = get_settings()
            stored = dotenv_values(path, interpolate=False)
            existing, _ = _keys(settings, provider, stage)
            extras = list(dict.fromkeys(k.strip() for k in
                          [*str(stored.get(field) or "").split(","),
                           *str(getattr(settings, field, "") or "").split(",")]
                          if k.strip()))
            if key in existing or key in extras:
                return {"added": False, **snapshot()}
            value = ",".join([*extras, key])
            original = path.read_text(encoding="utf-8") if path.exists() else ""
            pattern = re.compile(r"^[ \t]*(?:export[ \t]+)?" + field + r"[ \t]*=.*$", re.MULTILINE)
            # Remove duplicate definitions so old entries cannot win on reload.
            updated = pattern.sub("", original).rstrip("\r\n") + f"\n{field}='{value}'\n"
            descriptor, temp = tempfile.mkstemp(prefix=".env.pool-keys-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                    handle.write(updated)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp, 0o600)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            # Settings are freshly read on each factory call. A service manager
            # may also supply an EnvironmentFile, whose old value takes priority.
            if field in os.environ:
                os.environ[field] = value
    except (OSError, UnicodeError):
        raise HTTPException(503, "ذخیرهٔ امن کلید انجام نشد؛ دسترسی فایل تنظیمات سرور را بررسی کنید.") from None
    from app.rag import pool_service
    pool_service.notify_credentials_changed()
    return {"added": True, **snapshot()}
