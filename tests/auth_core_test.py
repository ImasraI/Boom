"""Offline tests for the auth core pieces that had no coverage until now.

Covers:
  - app/auth/security.py: bcrypt hashing (incl. the 72-byte truncation rule),
    legacy-hash detection, JWT roundtrip + invalid tokens
  - app/auth/sms.py: Iranian mobile normalization + OTP generation format
  - app/auth/limits.py: daily AI quotas, token budget, sliding-window rate
    limiter, client_ip extraction
  - app/auth/router.py: signup-bypass path (allowlisted phone) - the response
    must NOT echo the shared bypass code (regression: it used to leak it,
    letting anyone who knew an allowlisted phone reset that password), the
    bypass code must complete signup, and an empty bypass code fails closed
  - app/routers/tasks.py: the AI plan-update endpoint applies add/update/delete
    changes from the LLM's JSON (regression: its Persian prompt was mojibake)

No network access: settings are patched and the LLM client is stubbed.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import limits, router as auth_router, security
from app.auth.database import Base, PhoneCode, SignupAllowlist, User
from app.auth.sms import CODE_TTL_SECONDS, generate_code, normalize_ir_mobile

PHONE = "9121112233"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_db(monkeypatch, tmp_path, auth_router_module=None):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    if auth_router_module is not None:
        monkeypatch.setattr(auth_router_module, "SessionLocal", TestSession,
                            raising=False)
    session = TestSession()
    return session, engine


def _fake_request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))


def _settings(**overrides):
    base = dict(
        SMS_DEBUG_ECHO=False,
        SMS_API_KEY="",
        SMS_VERIFY_TEMPLATE_ID="",
        SIGNUP_BYPASS_CODE="",
        DISABLE_AUTH=False,
        APP_ENV="development",
    )
    base.update(overrides)
    return type("_S", (), base)


# ---------------------------------------------------------------------------
# security.py
# ---------------------------------------------------------------------------

def test_password_hash_and_verify_roundtrip():
    h = security.get_password_hash("s3cret!")
    assert h != "s3cret!"
    assert security.verify_password("s3cret!", h)
    assert not security.verify_password("wrong", h)


def test_password_hash_accepts_long_multibyte_password():
    """bcrypt caps input at 72 BYTES; Persian chars are 2 bytes each, so a
    long password must be truncated deterministically instead of erroring,
    and the truncation must be transparent to verify_password."""
    long_pw = "فارسی" * 30  # 150 chars, 300 bytes
    h = security.get_password_hash(long_pw)
    assert security.verify_password(long_pw, h)
    # First 72 bytes = first 36 Persian chars; anything after byte 72 is
    # ignored by bcrypt, so a matching prefix must also verify.
    assert security.verify_password("فارسی" * 36, h)


def test_needs_rehash_flags_legacy_and_current():
    current = security.get_password_hash("abc12345")
    assert not security.needs_rehash(current)
    # A sha256_crypt hash represents the legacy scheme (no $2b$ prefix).
    legacy = security.pwd_context.hash("abc12345", scheme="sha256_crypt")
    assert security.needs_rehash(legacy)


def test_token_roundtrip_and_garbage():
    token = security.create_access_token({"sub": "42"})
    payload = security.decode_token(token)
    assert payload is not None and payload["sub"] == "42"
    assert "exp" in payload
    assert security.decode_token("not-a-jwt") is None


# ---------------------------------------------------------------------------
# sms.py
# ---------------------------------------------------------------------------

def test_normalize_ir_mobile_accepts_all_shapes():
    assert normalize_ir_mobile("09121112233") == "9121112233"
    assert normalize_ir_mobile("9121112233") == "9121112233"
    assert normalize_ir_mobile("+98 912 111 2233") == "9121112233"
    assert normalize_ir_mobile("+989121112233") == "9121112233"


def test_normalize_ir_mobile_rejects_invalid():
    for bad in ("", "12345", "2121112233", "0912111223", "abcdefghij", None):
        with pytest.raises(ValueError):
            normalize_ir_mobile(bad)


def test_generate_code_is_six_digits():
    for _ in range(20):
        code = generate_code()
        assert len(code) == 6 and code.isdigit()


def test_code_ttl_is_short():
    assert 0 < CODE_TTL_SECONDS <= 300


# ---------------------------------------------------------------------------
# limits.py (fresh instances, not the module singletons)
# ---------------------------------------------------------------------------

def test_daily_counters_record_and_precheck():
    c = limits._DailyCounters()
    c.precheck(1, "chat", 2)  # under limit: no raise
    c.record(1, "chat")
    c.precheck(1, "chat", 2)
    c.record(1, "chat")
    with pytest.raises(HTTPException) as exc:
        c.precheck(1, "chat", 2)
    assert exc.value.status_code == 429
    # Another user / feature is unaffected.
    c.precheck(2, "chat", 1)
    c.precheck(1, "mock_generate", 1)
    assert c.snapshot(1) == {"chat": 2}


def test_daily_counters_clear_user():
    c = limits._DailyCounters()
    c.record(7, "chat")
    c.record(7, "_tokens")
    c.clear_user(7)
    assert c.snapshot(7) == {}


def test_check_ai_quota_zero_limit_is_unlimited(monkeypatch):
    monkeypatch.setattr(limits, "get_settings",
                        lambda: _settings(AI_DAILY_CHAT=0))
    limits.check_ai_quota(1, "chat")  # must not raise
    limits.record_ai_use(1, "chat")   # recording is a no-op, still fine


def test_check_ai_quota_enforces_limit(monkeypatch):
    s = _settings(AI_DAILY_CHAT=1)
    monkeypatch.setattr(limits, "get_settings", lambda: s)
    limits.check_ai_quota(1, "chat")
    limits.record_ai_use(1, "chat")
    with pytest.raises(HTTPException) as exc:
        limits.check_ai_quota(1, "chat")
    assert exc.value.status_code == 429


def test_token_budget(monkeypatch):
    s = _settings(AI_DAILY_TOKEN_BUDGET=100)
    monkeypatch.setattr(limits, "get_settings", lambda: s)
    limits.check_token_budget(1)
    limits.record_token_use(1, 40)
    limits.record_token_use(1, 50)
    assert limits.tokens_used_today(1) == 90
    limits.record_token_use(1, 0)  # zero/negative is ignored
    limits.check_token_budget(1)
    limits.record_token_use(1, 10)
    with pytest.raises(HTTPException) as exc:
        limits.check_token_budget(1)
    assert exc.value.status_code == 429


def test_rate_limiter_window():
    rl = limits._RateLimiter()
    for _ in range(3):
        rl.hit("ip", limit=3, window_s=60)
    with pytest.raises(HTTPException) as exc:
        rl.hit("ip", limit=3, window_s=60)
    assert exc.value.status_code == 429
    rl.hit("other-ip", limit=3, window_s=60)  # independent buckets


def test_client_ip_prefers_forwarded_for():
    req = SimpleNamespace(
        headers={"x-forwarded-for": "5.6.7.8, 9.9.9.9"},
        client=SimpleNamespace(host="1.2.3.4"),
    )
    assert limits.client_ip(req) == "5.6.7.8"
    assert limits.client_ip(_fake_request()) == "1.2.3.4"


# ---------------------------------------------------------------------------
# signup bypass (auth/router.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_rate_limiter():
    """request_code rate-limits per IP through a module-level singleton.
    Tests here call it repeatedly from one fake IP, which would 429 later
    test files (auth_disable_test) - reset the buckets around every test."""
    limits._limiter._hits.clear()
    yield
    limits._limiter._hits.clear()


@pytest.fixture()
def db(monkeypatch, tmp_path):
    session, engine = _make_db(monkeypatch, tmp_path, auth_router)
    yield session
    session.close()
    engine.dispose()


def _allowlist(db, phone=PHONE):
    db.add(SignupAllowlist(phone=phone, note="test"))
    db.commit()


def test_bypass_never_echoes_the_shared_code(monkeypatch, db):
    """Regression: request-code used to return debug_code=bypass_code, so
    anyone who knew an allowlisted phone could read the shared secret from
    the API and reset that account's password."""
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SIGNUP_BYPASS_CODE="313131"))
    _allowlist(db)
    resp = auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
    )
    assert resp.bypass_mode is True
    assert resp.debug_code is None  # <- the leak
    # A hashed PhoneCode row is stored so register/complete validates it.
    rec = db.query(PhoneCode).filter(PhoneCode.phone == PHONE).first()
    assert rec is not None and rec.purpose == "signup"


def test_bypass_code_completes_signup(monkeypatch, db):
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SIGNUP_BYPASS_CODE="313131"))
    _allowlist(db)
    auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
    )
    token = auth_router.register_complete(
        auth_router.CompleteSignupRequest(
            phone=PHONE, code="313131", password="abcd1234")
        , db
    )
    assert token.access_token
    user = db.query(User).filter(User.phone == PHONE).first()
    assert user is not None
    assert security.verify_password("abcd1234", user.hashed_password)
    # The code row is consumed: the same code cannot sign up twice.
    rec = db.query(PhoneCode).filter(PhoneCode.phone == PHONE).first()
    assert rec.consumed is True


def test_wrong_bypass_code_rejected_and_counted(monkeypatch, db):
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SIGNUP_BYPASS_CODE="313131"))
    _allowlist(db)
    auth_router.request_code(
        auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
    )
    with pytest.raises(HTTPException) as exc:
        auth_router.register_complete(
            auth_router.CompleteSignupRequest(
                phone=PHONE, code="999999", password="abcd1234"),
            db,
        )
    assert exc.value.status_code == 400
    rec = db.query(PhoneCode).filter(PhoneCode.phone == PHONE).first()
    assert rec.attempts == 1 and rec.consumed is False


def test_empty_bypass_code_fails_closed(monkeypatch, db):
    """No bypass configured + no SMS configured = 503, and no code row and
    no account can materialize (fresh deployments ship no known passcode)."""
    monkeypatch.setattr(auth_router, "get_settings", lambda: _settings())
    _allowlist(db)
    with pytest.raises(HTTPException) as exc:
        auth_router.request_code(
            auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
        )
    assert exc.value.status_code == 503
    assert db.query(PhoneCode).count() == 0


def test_non_allowlisted_phone_ignores_bypass(monkeypatch, db):
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SIGNUP_BYPASS_CODE="313131"))
    _allowlist(db, phone="9350000000")
    with pytest.raises(HTTPException) as exc:
        auth_router.request_code(
            auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
        )
    assert exc.value.status_code == 503  # falls through to the SMS guard


def test_sms_provider_failure_is_503_not_500(monkeypatch, db):
    """Regression: when the SMS provider is unreachable (raises RuntimeError
    from sms.py), request-code must return a clean 503 carrying the
    user-safe message instead of an unhandled 500."""
    monkeypatch.setattr(auth_router, "get_settings",
                        lambda: _settings(SMS_API_KEY="k",
                                          SMS_VERIFY_TEMPLATE_ID="1"))

    def _boom(mobile, code):
        raise RuntimeError("سرویس پیامک در دسترس نیست")

    monkeypatch.setattr(auth_router, "send_verification_code", _boom)
    with pytest.raises(HTTPException) as exc:
        auth_router.request_code(
            auth_router.RequestCodeRequest(phone=PHONE), _fake_request(), db
        )
    assert exc.value.status_code == 503
    assert "پیامک" in exc.value.detail
    # Nothing may be persisted: no code row, or the retry would be blocked
    # by the resend cooldown while the user never received anything.
    assert db.query(PhoneCode).count() == 0


# ---------------------------------------------------------------------------
# tasks.py update-plan (LLM stubbed)
# ---------------------------------------------------------------------------

def test_update_plan_applies_llm_changes(monkeypatch, tmp_path):
    from app.routers import tasks as tasks_router

    session, engine = _make_db(monkeypatch, tmp_path)
    try:
        user = User(username=PHONE, phone=PHONE, hashed_password="x")
        session.add(user)
        session.commit()

        existing = tasks_router.DailyTask(
            user_id=user.id,
            date=datetime.now(timezone.utc).date() + timedelta(days=1),
            subject="فیزیک", task_type="study",
            description="تست قدیمی", duration_minutes=60,
        )
        session.add(existing)
        session.commit()

        llm_json = (
            '{"action": "add", "changes": [{"date": "'
            + (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
            + '", "subject": "ریاضی", "task_type": "test", '
            '"description": "حل تمرین فصل ۲", "duration_minutes": 90}]}'
        )
        monkeypatch.setattr(tasks_router, "get_llm_client",
                            lambda: SimpleNamespace(
                                generate=lambda *a, **k: llm_json))

        result = tasks_router.update_plan_with_ai(
            tasks_router.UpdatePlanRequest(instruction="یه آزمون ریاضی بذار"),
            user, session,
        )
        assert result["success"] is True
        assert "افزوده" in result["message"] or result["applied"]
        added = session.query(tasks_router.DailyTask).filter(
            tasks_router.DailyTask.subject == "ریاضی").first()
        assert added is not None
        assert added.description == "حل تمرین فصل ۲"
        assert added.duration_minutes == 90
    finally:
        session.close()
        engine.dispose()


def test_update_plan_delete_and_update(monkeypatch, tmp_path):
    from app.routers import tasks as tasks_router

    session, engine = _make_db(monkeypatch, tmp_path)
    try:
        user = User(username="9351112223", phone="9351112223",
                    hashed_password="x")
        session.add(user)
        session.commit()

        keep = tasks_router.DailyTask(
            user_id=user.id,
            date=datetime.now(timezone.utc).date() + timedelta(days=1),
            subject="شیمی", task_type="study",
            description="مرور حل التمرین", duration_minutes=45,
        )
        drop = tasks_router.DailyTask(
            user_id=user.id,
            date=datetime.now(timezone.utc).date() + timedelta(days=1),
            subject="زیست", task_type="study",
            description="حذف شو", duration_minutes=30,
        )
        session.add_all([keep, drop])
        session.commit()

        llm_json = (
            '{"action": "delete", "changes": [{"task_id": %d}]}' % drop.id
        )
        monkeypatch.setattr(tasks_router, "get_llm_client",
                            lambda: SimpleNamespace(
                                generate=lambda *a, **k: llm_json))
        result = tasks_router.update_plan_with_ai(
            tasks_router.UpdatePlanRequest(instruction="زیست رو حذف کن"),
            user, session,
        )
        assert result["success"] is True
        assert session.query(tasks_router.DailyTask).get(drop.id) is None
        assert session.query(tasks_router.DailyTask).get(keep.id) is not None

        # Now an update against the surviving row.
        llm_json2 = (
            '{"action": "update", "changes": [{"task_id": %d, '
            '"duration_minutes": 120}]}' % keep.id
        )
        monkeypatch.setattr(tasks_router, "get_llm_client",
                            lambda: SimpleNamespace(
                                generate=lambda *a, **k: llm_json2))
        result2 = tasks_router.update_plan_with_ai(
            tasks_router.UpdatePlanRequest(instruction="دو ساعتش کن"),
            user, session,
        )
        assert result2["success"] is True
        assert session.query(tasks_router.DailyTask).get(keep.id) \
            .duration_minutes == 120
    finally:
        session.close()
        engine.dispose()


def test_update_plan_survives_garbage_llm_output(monkeypatch, tmp_path):
    from app.routers import tasks as tasks_router

    session, engine = _make_db(monkeypatch, tmp_path)
    try:
        user = User(username="9351112224", phone="9351112224",
                    hashed_password="x")
        session.add(user)
        session.commit()
        monkeypatch.setattr(tasks_router, "get_llm_client",
                            lambda: SimpleNamespace(
                                generate=lambda *a, **k: "سلام! متوجه نشدم."))
        result = tasks_router.update_plan_with_ai(
            tasks_router.UpdatePlanRequest(instruction="هرچی"),
            user, session,
        )
        assert result["success"] is False
        assert "raw" in result
    finally:
        session.close()
        engine.dispose()
