"""Tests for the DISABLE_AUTH dev signup flow (app/auth/router.py).

Covers the three behaviors gated on settings.DISABLE_AUTH (and only active
outside production):
  - request-code returns auth_disabled=True without sending SMS, storing a
    code, or requiring SMS configuration
  - register/complete skips SMS code verification entirely (dummy code OK)
  - both are inert when APP_ENV=production
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import router as auth_router
from app.auth.database import Base, PhoneCode, User
from app.auth.security import verify_password


PHONE = "9121112233"


class _FakeSettings:
    """Minimal stand-in so router code sees deterministic flag values
    (get_settings() re-reads .env each call, so we patch it wholesale)."""

    SMS_DEBUG_ECHO = False
    SMS_API_KEY = ""
    SMS_VERIFY_TEMPLATE_ID = ""
    SIGNUP_BYPASS_CODE = ""
    DISABLE_AUTH = True
    APP_ENV = "development"


@pytest.fixture()
def db(monkeypatch, tmp_path):
    """Point the auth module at a throwaway SQLite DB for the duration."""
    test_engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(auth_router, "SessionLocal", TestSession, raising=False)
    session = TestSession()
    yield session
    session.close()
    test_engine.dispose()


@pytest.fixture()
def fake_request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))


def _patch_settings(monkeypatch, disable=True, app_env="development"):
    s = type("_S", (), dict(vars(_FakeSettings)))
    s.DISABLE_AUTH = disable
    s.APP_ENV = app_env
    monkeypatch.setattr(auth_router, "get_settings", lambda: s)


def test_request_code_flags_auth_disabled(monkeypatch, db, fake_request):
    """DISABLE_AUTH=true: request-code returns auth_disabled, no SMS config
    needed, and no PhoneCode row is stored."""
    _patch_settings(monkeypatch, disable=True)
    resp = auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE), fake_request, db
    )
    assert resp.auth_disabled is True
    assert resp.bypass_mode is False
    assert db.query(PhoneCode).count() == 0


def test_register_complete_skips_code_verification(monkeypatch, db):
    """DISABLE_AUTH=true: any dummy code is accepted and the account is
    created with the chosen password (regression: previously this raised
    'کد منقضی شده است' on an empty PhoneCode table)."""
    _patch_settings(monkeypatch, disable=True)
    token = auth_router.register_complete(
        auth_router.CompleteSignupRequest(
            phone=PHONE, code="000000", password="1234"
        ),
        db,
    )
    assert token.access_token
    user = db.query(User).filter(User.phone == PHONE).first()
    assert user is not None
    assert user.phone_verified is True
    assert verify_password("1234", user.hashed_password)


def test_request_code_still_gated_in_production(monkeypatch, db, fake_request):
    """DISABLE_AUTH must be inert in production: request-code behaves as if
    the flag were off (503 while SMS is unconfigured)."""
    _patch_settings(monkeypatch, disable=True, app_env="production")
    with pytest.raises(HTTPException) as exc:
        auth_router.request_code(
            auth_router.RequestCodeRequest(phone=PHONE), fake_request, db
        )
    assert exc.value.status_code == 503


def test_register_complete_still_verifies_in_production(monkeypatch, db):
    """DISABLE_AUTH must be inert in production: register/complete still
    requires a real, unexpired code."""
    _patch_settings(monkeypatch, disable=True, app_env="production")
    with pytest.raises(HTTPException) as exc:
        auth_router.register_complete(
            auth_router.CompleteSignupRequest(
                phone=PHONE, code="000000", password="1234"
            ),
            db,
        )
    assert exc.value.status_code == 400  # expired/missing code, as always
    assert db.query(User).filter(User.phone == PHONE).first() is None
