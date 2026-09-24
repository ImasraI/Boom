import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth.database import get_db, User, PhoneCode, SignupAllowlist
from ..auth.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    needs_rehash,
    SECRET_KEY,
)
from ..auth.deps import get_current_user
from ..auth.sms import (
    CODE_TTL_SECONDS,
    generate_code,
    normalize_ir_mobile,
    send_verification_code,
)
from ..auth.limits import rate_limit
from ..config import get_settings
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/api/auth", tags=["auth"])

REQUEST_COOLDOWN_SECONDS = 90  # per phone, between code sends
MAX_VERIFY_ATTEMPTS = 5        # per code


def _hash_code(code: str) -> str:
    """Codes are hashed at rest (DB leak must not leak live codes)."""
    return hashlib.sha256((code + SECRET_KEY).encode("utf-8")).hexdigest()


class RequestCodeRequest(BaseModel):
    phone: str


class RequestCodeResponse(BaseModel):
    ok: bool = True
    resend_after: int = REQUEST_COOLDOWN_SECONDS
    debug_code: str | None = None  # only when SMS_DEBUG_ECHO=true (dev)
    bypass_mode: bool = False  # allowlisted number: enter SIGNUP_BYPASS_CODE instead
    auth_disabled: bool = False  # DISABLE_AUTH=true (dev): skip code entry entirely


class CompleteSignupRequest(BaseModel):
    phone: str
    code: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/request-code", response_model=RequestCodeResponse)
def request_code(
    request: RequestCodeRequest,
    http: Request,
    db: Session = Depends(get_db),
):
    """Send a 6-digit verification code to an Iranian mobile via SMS.ir."""
    # 5 code requests / 10 min / IP: SMS costs real money - brute force on
    # this endpoint is a wallet attack, not just a spam one.
    rate_limit(http, limit=5, window_s=600)
    try:
        mobile = normalize_ir_mobile(request.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="شماره موبایل معتبر نیست")

    settings = get_settings()
    echo_mode = settings.SMS_DEBUG_ECHO and settings.APP_ENV != "production"
    # Dev convenience: DISABLE_AUTH=true (and not production) skips SMS
    # verification entirely - the client goes straight to setting a password.
    auth_disabled = settings.DISABLE_AUTH and settings.APP_ENV != "production"
    now = datetime.now(timezone.utc)

    # SMS-template-approval stopgap: allowlisted numbers can sign up without
    # SMS by using the shared bypass passcode. We store a PhoneCode row
    # hashed from the bypass code, so register/complete validates it with
    # the exact same path as a texted code (attempt cap, expiry, consume).
    # Checked BEFORE the SMS-config guard: this exists precisely for the
    # period when SMS is not configured/approved yet.
    bypass_code = (settings.SIGNUP_BYPASS_CODE or "").strip()
    if bypass_code and db.query(SignupAllowlist).filter(
            SignupAllowlist.phone == mobile).first() is not None:
        db.add(PhoneCode(
            phone=mobile,
            code_hash=_hash_code(bypass_code),
            purpose="signup",
            expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        ))
        db.commit()
        # Never echo the bypass code back: it is a shared secret. Anyone who
        # knows an allowlisted phone could otherwise read it here and reset
        # that account's password. The legit user got it from support.
        return RequestCodeResponse(resend_after=0, bypass_mode=True)

    if auth_disabled:
        return RequestCodeResponse(resend_after=0, auth_disabled=True)

    if not echo_mode and (not settings.SMS_API_KEY or not settings.SMS_VERIFY_TEMPLATE_ID):
        raise HTTPException(
            status_code=503, detail="سرویس پیامک پیکربندی نشده است"
        )

    recent = (
        db.query(PhoneCode)
        .filter(
            PhoneCode.phone == mobile,
            PhoneCode.created_at > now - timedelta(seconds=REQUEST_COOLDOWN_SECONDS),
        )
        .first()
    )
    if recent:
        raise HTTPException(
            status_code=429,
            detail="کد قبلاً ارسال شده؛ کمی صبر کنید و دوباره تلاش کنید",
        )

    code = generate_code()
    if settings.SMS_DEBUG_ECHO and settings.APP_ENV != "production":
        debug_code = code  # dev convenience: no SMS spent
    else:
        send_verification_code(mobile, code)
        debug_code = None

    db.add(
        PhoneCode(
            phone=mobile,
            code_hash=_hash_code(code),
            purpose="signup",
            expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        )
    )
    db.commit()
    return RequestCodeResponse(debug_code=debug_code)


@router.post("/register/complete", response_model=TokenResponse)
def register_complete(request: CompleteSignupRequest, db: Session = Depends(get_db)):
    """Verify the SMS code, then create the account with the chosen password."""
    try:
        mobile = normalize_ir_mobile(request.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="شماره موبایل معتبر نیست")

    if len(request.password or "") < 4:
        raise HTTPException(status_code=400, detail="رمز عبور باید حداقل ۴ کاراکتر باشد")

    now = datetime.now(timezone.utc)
    settings = get_settings()
    auth_disabled = settings.DISABLE_AUTH and settings.APP_ENV != "production"

    rec = None
    if not auth_disabled:
        rec = (
            db.query(PhoneCode)
            .filter(
                PhoneCode.phone == mobile,
                PhoneCode.purpose == "signup",
                PhoneCode.consumed.is_(False),
                PhoneCode.expires_at > now,
            )
            .order_by(PhoneCode.created_at.desc())
            .first()
        )
        if not rec:
            raise HTTPException(
                status_code=400, detail="کد منقضی شده است؛ کد جدید بگیرید"
            )
        if rec.attempts >= MAX_VERIFY_ATTEMPTS:
            rec.consumed = True
            db.commit()
            raise HTTPException(
                status_code=429, detail="تلاش‌های ناموفق زیاد؛ کد جدید بگیرید"
            )
        if not secrets.compare_digest(rec.code_hash, _hash_code(request.code or "")):
            rec.attempts += 1
            db.commit()
            raise HTTPException(status_code=400, detail="کد وارد شده درست نیست")
        rec.consumed = True

    existing = (
        db.query(User)
        .filter((User.username == mobile) | (User.phone == mobile))
        .first()
    )
    if existing:
        # Re-verification of a known number: refresh the password.
        existing.hashed_password = get_password_hash(request.password)
        existing.phone_verified = True
        if existing.phone != mobile:
            existing.phone = mobile
        db.commit()
        db.refresh(existing)
        user = existing
    else:
        user = User(
            username=mobile,
            phone=mobile,
            hashed_password=get_password_hash(request.password),
            phone_verified=True,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="این شماره قبلاً ثبت شده است")
        db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(
    http: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # 10 login attempts / 5 min / IP: blunts password brute force.
    rate_limit(http, limit=10, window_s=300)
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    # Transparent upgrade: legacy sha256 hashes become bcrypt on first login.
    if needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(form_data.password)
        db.commit()
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "phone": current_user.phone,
        "phone_verified": bool(current_user.phone_verified),
        "is_admin": bool(current_user.is_admin),
    }
