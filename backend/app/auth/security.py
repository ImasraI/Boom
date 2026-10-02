from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import os
import secrets as _secrets
import threading as _threading

# ---------------------------------------------------------------------------
# JWT/code-hashing secret resolution - never directory-dependent.
#
# Regression: this used to be os.getenv("SECRET_KEY", "your-secret-key-
# change-me") after a bare load_dotenv(), so launching uvicorn from any
# directory other than backend/ silently signed every token with a PUBLIC
# fallback string - anyone could then forge a valid login for ANY user id.
# Resolution order now:
#   1. real environment variable (systemd/docker/venv exports work)
#   2. backend/.env next to this file (cwd-independent)
#   3. a RANDOM secret generated once per process (tokens survive only
#      within one run - strictly better than a well-known constant)
# A process that lands on (3) logs loudly so the operator fixes the env.
# ---------------------------------------------------------------------------
_SECRET_LOCK = _threading.Lock()
_SECRET_CACHE: str | None = None


def _resolve_secret() -> str:
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    try:
        from dotenv import load_dotenv  # cheap, already a dependency
        # app/auth/security.py -> ../../ = backend/ (cwd-independent)
        dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
        load_dotenv(dotenv_path, override=False)
    except Exception:
        pass
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    return ""


def get_secret_key() -> str:
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE
    with _SECRET_LOCK:
        if _SECRET_CACHE is None:
            resolved = _resolve_secret()
            if not resolved:
                resolved = _secrets.token_hex(32)
                print("WARNING: SECRET_KEY is not set - generating a RANDOM "
                      "per-process secret. All logins reset on restart. "
                      "Set SECRET_KEY in backend/.env!", flush=True)
            _SECRET_CACHE = resolved
    return _SECRET_CACHE


def reset_secret_cache() -> None:
    """Test hook: force re-resolution on next use."""
    global _SECRET_CACHE
    with _SECRET_LOCK:
        _SECRET_CACHE = None


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

# bcrypt (salted, slow) for all NEW hashes; sha256_crypt stays only so
# accounts created before the switch can still log in and get upgraded.
pwd_context = CryptContext(schemes=["bcrypt", "sha256_crypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if isinstance(password, str):
        # bcrypt operates on at most 72 bytes; truncate deterministically.
        password_bytes = password.encode('utf-8')[:72]
        password = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def needs_rehash(hashed_password: str) -> bool:
    """True when `hashed_password` uses a legacy scheme (login should upgrade)."""
    return pwd_context.needs_update(hashed_password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"JWT decode error: {e}")
        return None
