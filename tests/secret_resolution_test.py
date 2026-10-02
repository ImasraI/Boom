"""Regressions for JWT secret resolution (app/auth/security.py).

The attack this pins: the secret used to be os.getenv with a hardcoded
"your-secret-key-change-me" fallback after a bare load_dotenv(), so any
process started OUTSIDE backend/ signed tokens with a PUBLIC string -
anyone could forge a login for ANY user id (sub is just the user id).
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.auth import security


def _fresh_key(monkeypatch, **env):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    security.reset_secret_cache()
    try:
        return security.get_secret_key()
    finally:
        security.reset_secret_cache()


def test_env_var_beats_everything(monkeypatch):
    assert _fresh_key(monkeypatch, SECRET_KEY="env-wins") == "env-wins"


def test_dotenv_file_used_when_env_missing(monkeypatch):
    """No env var: the backend/.env file's SECRET_KEY must be found via the
    __file__-relative path (NOT the cwd)."""
    dotenv = (BACKEND / ".env").read_text(encoding="utf-8")
    expected = None
    for line in dotenv.splitlines():
        if line.startswith("SECRET_KEY="):
            expected = line.split("=", 1)[1].strip()
            break
    assert expected, "backend/.env must define SECRET_KEY for this test"
    assert _fresh_key(monkeypatch) == expected


def test_foreign_cwd_gets_file_secret_not_public_fallback(monkeypatch):
    """THE regression, end to end: a python -c one-liner with a DIFFERENT
    cwd and no SECRET_KEY env must still resolve the file secret - never
    the old hardcoded 'your-secret-key-change-me'."""
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    script = (
        "import sys; sys.path.insert(0, r'%s');"
        "from app.auth import security;"
        "print(security.get_secret_key())" % str(BACKEND)
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),  # NOT backend/
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    resolved = proc.stdout.strip().splitlines()[-1]
    assert resolved != "your-secret-key-change-me"
    assert len(resolved) >= 6


def test_random_fallback_when_no_config_anywhere(monkeypatch, tmp_path):
    """Neither env nor a readable .env: a RANDOM secret is generated (and
    warned about) instead of a well-known constant."""
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setattr(security.os.path, "dirname",
                        lambda p: str(tmp_path), raising=False)
    import unittest.mock as mock
    # Point the dotenv lookup at an empty dir: no .env anywhere.
    with mock.patch.object(security.os.path, "join",
                           side_effect=lambda *a: str(tmp_path / "missing.env")):
        key = _fresh_key(monkeypatch)
    assert len(key) == 64  # token_hex(32), not the old public constant
    assert key != "your-secret-key-change-me"


def test_tokens_roundtrip_with_resolved_secret(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    security.reset_secret_cache()
    try:
        token = security.create_access_token({"sub": "42"})
        assert security.decode_token(token)["sub"] == "42"
        assert security.decode_token(token + "x") is None
    finally:
        security.reset_secret_cache()
