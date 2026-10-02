"""Regressions for the account-exists signup intercept.

The bug this pins down: re-signing up with an existing number used to
SILENTLY take the account over - overwrite the password and log the
visitor in - with no warning. Now:

  - request-code flags account_exists=True on every path (SMS, dev
    bypass, allowlist bypass)
  - register/complete without reset=true on an existing number fails
    409 BEFORE consuming the SMS code (so the reset screen can reuse it)
  - reset=true after the user explicitly opted in updates the SAME
    account row (no duplicates) and logs in
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import router as auth_router
from app.auth.database import Base, PhoneCode, SignupAllowlist, User
from app.auth.security import verify_password


PHONE = "9121112233"


class _FakeSettings:
    SMS_DEBUG_ECHO = False
    SMS_API_KEY = ""
    SMS_VERIFY_TEMPLATE_ID = ""
    SIGNUP_BYPASS_CODE = ""
    DISABLE_AUTH = True
    APP_ENV = "development"


@pytest.fixture()
def db(monkeypatch, tmp_path):
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


def _settings(**over):
    s = type("_S", (), dict(vars(_FakeSettings)))
    for k, v in over.items():
        setattr(s, k, v)
    return s


def _mk_user(db, phone=PHONE, password="orig-pass"):
    u = User(username=phone, phone=phone,
             hashed_password=auth_router.get_password_hash(password),
             phone_verified=True)
    db.add(u)
    db.commit()
    return u


def test_request_code_flags_existing_account(monkeypatch, db):
    """DISABLE_AUTH dev path: request-code reports account_exists=True."""
    monkeypatch.setattr(auth_router, "get_settings", lambda: _settings())
    _mk_user(db)

    resp = auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE),
        type("R", (), {"headers": {}, "client": type("C", (), {"host": "1.2.3.4"})()}),
        db,
    )
    assert resp.account_exists is True


def test_request_code_fresh_number_not_flagged(monkeypatch, db):
    monkeypatch.setattr(auth_router, "get_settings", lambda: _settings())
    resp = auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE),
        type("R", (), {"headers": {}, "client": type("C", (), {"host": "1.2.3.4"})()}),
        db,
    )
    assert resp.account_exists is False


def test_repeat_signup_rejected_409_not_taken_over(monkeypatch, db):
    """THE regression: register/complete on an existing number without
    reset=true must fail 409 and leave the original password working."""
    monkeypatch.setattr(auth_router, "get_settings", lambda: _settings())
    u = _mk_user(db)

    with pytest.raises(HTTPException) as exc:
        auth_router.register_complete(
            auth_router.CompleteSignupRequest(
                phone=PHONE, code="000000", password="hacked"),
            db,
        )
    assert exc.value.status_code == 409
    assert exc.value.headers.get("X-Account-Exists") == "1"
    # Original credentials untouched.
    db.refresh(u)
    assert verify_password("orig-pass", u.hashed_password)
    assert not verify_password("hacked", u.hashed_password)
    # No duplicate row appeared.
    assert db.query(User).filter(User.phone == PHONE).count() == 1


def test_repeat_signup_409_preserves_sms_code_for_reset(monkeypatch, db):
    """The 409 must fire BEFORE code validation: the code the user received
    stays unconsumed so the reset screen can resubmit with the same code."""
    # Real code-validation path (DISABLE_AUTH off) - in dev-disabled mode
    # codes are never consumed, which is exactly what this test pins.
    monkeypatch.setattr(
        auth_router, "get_settings",
        lambda: _settings(DISABLE_AUTH=False, SMS_DEBUG_ECHO=True))
    u = _mk_user(db)
    db.add(PhoneCode(phone=PHONE, code_hash=auth_router._hash_code("654321"),
                     purpose="signup",
                     expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        auth_router.register_complete(
            auth_router.CompleteSignupRequest(
                phone=PHONE, code="WRONG", password="hacked"),
            db,
        )
    assert exc.value.status_code == 409  # NOT the wrong-code 400
    rec = db.query(PhoneCode).filter(PhoneCode.phone == PHONE).first()
    assert rec.consumed is False

    # Same code now completes the EXPLICIT reset.
    token = auth_router.register_complete(
        auth_router.CompleteSignupRequest(
            phone=PHONE, code="654321", password="new-pass", reset=True),
        db,
    )
    assert token.access_token
    db.refresh(u)
    assert verify_password("new-pass", u.hashed_password)
    rec = db.query(PhoneCode).filter(PhoneCode.phone == PHONE).first()
    assert rec.consumed is True
    assert db.query(User).filter(User.phone == PHONE).count() == 1


def test_reset_updates_same_account_row(monkeypatch, db):
    """reset=true after opt-in: same row, new password, no duplicate."""
    monkeypatch.setattr(auth_router, "get_settings", lambda: _settings())
    u = _mk_user(db)

    token = auth_router.register_complete(
        auth_router.CompleteSignupRequest(
            phone=PHONE, code="000000", password="new-pass", reset=True),
        db,
    )
    assert token.access_token
    assert db.query(User).filter(User.phone == PHONE).count() == 1
    db.refresh(u)
    assert verify_password("new-pass", u.hashed_password)


def test_account_exists_flagged_on_bypass_path(monkeypatch, db):
    """Allowlist-bypass path must also surface account_exists."""
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SIGNUP_BYPASS_CODE="313131"))
    db.add(SignupAllowlist(phone=PHONE))
    db.commit()
    _mk_user(db)

    resp = auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE),
        type("R", (), {"headers": {}, "client": type("C", (), {"host": "1.2.3.4"})()}),
        db,
    )
    assert resp.bypass_mode is True
    assert resp.account_exists is True
