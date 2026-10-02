"""Fail-fast startup validation (growth-readiness project 8).

Production must never boot with a missing or guessable SECRET_KEY: tokens
are HS256-signed with it, so a weak key means anyone can forge a login for
any user. Development keeps working without one (security.py generates a
random per-process secret and warns).
"""
from __future__ import annotations

MIN_SECRET_LENGTH = 32
KNOWN_PLACEHOLDERS = {
    "your-secret-key-change-me",
    "change-me",
    "secret",
    "changeme",
}


def validate_startup_secrets(env: str, min_length: int = MIN_SECRET_LENGTH) -> None:
    """Raise RuntimeError in production when SECRET_KEY is missing, too
    short, or a known placeholder. No-op outside production."""
    if env != "production":
        return
    from app.auth.security import _resolve_secret

    secret = _resolve_secret()
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set: production refuses to start (JWTs would be "
            "forgeable). Set a strong SECRET_KEY in backend/.env.")
    if secret.lower() in KNOWN_PLACEHOLDERS:
        raise RuntimeError(
            "SECRET_KEY is a known placeholder value: production refuses to start.")
    if len(secret) < min_length:
        raise RuntimeError(
            f"SECRET_KEY is too short ({len(secret)} chars; need >= {min_length}) "
            "for production. Generate one with: python -c "
            "\"import secrets; print(secrets.token_hex(32))\"")
