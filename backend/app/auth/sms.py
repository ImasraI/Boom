"""SMS.ir verification-code sender.

Uses the SMS.ir "send verify" REST endpoint with a panel-side template:
    POST {SMS_BASE_URL}/v1/send/verify
    headers: x-api-key: <SMS_API_KEY>, Content-Type: application/json
    body:    {"mobile": "9xxxxxxxxx", "templateId": 123456,
              "parameters": [{"name": "OTP", "value": "12345"}]}

Notes (matched to the SMS.ir docs / panel template):
    - "templateId" must be a NUMBER, not a string.
    - The parameter name must match the template's placeholder name exactly
      (e.g., if template has #OTP#, use "OTP"; if {CODE}, use "CODE").
    - SMS.ir replies HTTP 200 even when the send fails; success is only
      "status": 1 in the JSON body, so that is what we validate.

    The template must contain the #OTP# parameter (create it in the SMS.ir
    panel under the verification-templates section and put its numeric id in
    SMS_VERIFY_TEMPLATE_ID).
    """

from __future__ import annotations

import time
import unicodedata
from datetime import datetime, timezone

import requests

from ..config import get_settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

CODE_TTL_SECONDS = 120  # signup codes live for 2 minutes


def _sms_session() -> requests.Session:
    """Session that IGNORES ambient proxy config by default (trust_env=False).

    requests picks up proxies from environment variables and - on Windows -
    from the system (registry) proxy, e.g. a v2rayN client at 127.0.0.1:10809.
    SMS.ir is an Iranian endpoint: routed through a VPN exit it usually hangs
    until the timeout, surfacing to users as «سرویس پیامک در دسترس نیست" even
    though the panel and key are perfectly fine (direct calls answer in <1s).

    Set SMS_TRUST_ENV=true in .env only if your network genuinely needs a
    proxy to reach api.sms.ir.
    """
    session = requests.Session()
    session.trust_env = get_settings().SMS_TRUST_ENV
    return session


def _proxy_dict(settings) -> dict[str, str] | None:
    """Explicit SMS-only proxy. Empty means direct, independent of AI routing."""
    url = (settings.SMS_PROXY or "").strip()
    if not url:
        return None
    return {"http": url, "https": url}


def generate_code() -> str:
    """6-digit numeric code, cryptographically random."""
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_ir_mobile(phone: str) -> str:
    """Accept 09xxxxxxxxx / 9xxxxxxxxx / +989xxxxxxxxx -> 9xxxxxxxxx."""
    digits = "".join(str(unicodedata.decimal(ch)) for ch in (phone or "") if ch.isdecimal())
    if digits.startswith("98"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or not digits.startswith("9"):
        raise ValueError("invalid Iranian mobile number")
    return digits


def send_verification_code(mobile: str, code: str) -> str | None:
    """Send `code` to `mobile` (9xxxxxxxxx) via the SMS.ir verify template.

    Raises RuntimeError with a user-safe message on failure; the raw error
    goes to the log only.
    """
    settings = get_settings()
    mobile = normalize_ir_mobile(mobile)
    if not settings.SMS_API_KEY.strip() or not settings.SMS_VERIFY_PARAMETER_NAME.strip():
        raise RuntimeError("سرویس پیامک پیکربندی نشده است")
    url = f"{settings.SMS_BASE_URL.rstrip('/')}/v1/send/verify"
    template_id = settings.SMS_VERIFY_TEMPLATE_ID.strip()
    if not template_id.isdigit():
        # Config error, not a user error - log the raw value, keep the
        # user-facing message generic.
        logger.error(
            "SMS_VERIFY_TEMPLATE_ID must be the numeric template id from "
            "the SMS.ir panel (got %r)", template_id,
        )
        raise RuntimeError("ارسال پیامک ناموفق بود")
    payload = {
        "mobile": mobile,
        "templateId": int(template_id),  # API expects a number
        "parameters": [{"name": settings.SMS_VERIFY_PARAMETER_NAME.strip(), "value": code}],
    }
    # Use only explicit SMS routing. Retry connect timeouts before transmission.
    proxies = _proxy_dict(settings)
    attempts: list[dict[str, str] | None] = [proxies, proxies]
    last_exc: requests.RequestException | None = None
    resp: requests.Response | None = None
    for attempt, use_proxies in enumerate(attempts, 1):
        try:
            with _sms_session() as session:
                resp = session.post(
                    url,
                    json=payload,
                    headers={
                        "x-api-key": settings.SMS_API_KEY,
                        "Content-Type": "application/json",
                    },
                    timeout=(5, 10),
                    proxies=use_proxies,
                )
            break
        except requests.ReadTimeout as exc:
            # The provider may already have accepted the SMS. Retrying here
            # can send duplicates; report uncertainty instead.
            logger.warning("SMS.ir response timeout; acceptance unknown (no retry)")
            raise RuntimeError("پاسخ سرویس پیامک نرسید؛ کمی صبر کنید و دوباره تلاش کنید") from exc
        except requests.RequestException as exc:
            last_exc = exc
            via = "proxy" if use_proxies else "direct"
            logger.warning("SMS.ir attempt %d/2 (%s) failed: %s", attempt, via, type(exc).__name__)
            # Only a connect timeout is known to occur before the request
            # was transmitted. Other connection errors can be ambiguous.
            if not isinstance(exc, requests.ConnectTimeout):
                break
            if attempt == 1:
                time.sleep(1.5)
    if resp is None:
        logger.error("SMS.ir unreachable: %s", type(last_exc).__name__)
        raise RuntimeError("سرویس پیامک در دسترس نیست") from last_exc

    if resp.status_code != 200:
        logger.error("SMS.ir verify HTTP status=%s", resp.status_code)
        raise RuntimeError("ارسال پیامک ناموفق بود")

    # SMS.ir returns HTTP 200 even when the send failed; success is only
    # visible as "status": 1 in the body (see docs: {"status": 1,
    # "message": "موفق", "data": {"messageId": ..., "cost": ...}}).
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict) or body.get("status") != 1:
        logger.error(
            "SMS.ir verify rejected: status=%s",
            body.get("status") if isinstance(body, dict) else "invalid-body",
        )
        raise RuntimeError("ارسال پیامک ناموفق بود")
    data = body.get("data")
    message_id = data.get("messageId") if isinstance(data, dict) else None
    # IDs and timestamps let operators obtain delivery reports without
    # recording the OTP, mobile number, provider body or API credentials.
    safe_id = str(message_id) if isinstance(message_id, int) or (isinstance(message_id, str) and message_id.isascii() and message_id.isdigit()) else None
    logger.info("SMS.ir accepted message_id=%s accepted_at=%s template_id=%s",
                safe_id, datetime.now(timezone.utc).isoformat(), template_id)
    return safe_id


def sms_credit() -> dict:
    """Remaining SMS.ir panel credit: {"credit": int, "configured": bool}.

    Never raises: the admin panel wants a number to display, not an error
    page - unreachable/broken setups report credit=0 + a reason instead.
    Uses GET /v1/credit with the same x-api-key header as sending.
    """
    settings = get_settings()
    if not settings.SMS_API_KEY.strip():
        return {"credit": 0, "configured": False, "detail": "کلید API تنظیم نشده"}
    try:
        resp = _sms_session().get(
            f"{settings.SMS_BASE_URL.rstrip('/')}/v1/credit",
            headers={"x-api-key": settings.SMS_API_KEY,
                     "Accept": "application/json"},
            timeout=(5, 8),
            proxies=_proxy_dict(settings),
        )
        if resp.status_code != 200:
            return {"credit": 0, "configured": True,
                    "detail": f"خطای {resp.status_code} از سرویس"}
        body = resp.json()
        if not isinstance(body, dict) or body.get("status") != 1:
            return {"credit": 0, "configured": True,
                    "detail": "پاسخ نامعتبر از سرویس پیامک"}
        return {"credit": int(body.get("data") or 0), "configured": True,
                "detail": ""}
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("SMS credit check failed: %s", type(exc).__name__)
        return {"credit": 0, "configured": True, "detail": "سرویس در دسترس نیست"}


def sms_delivery_report(message_id: int) -> dict:
    """Read provider delivery timing; never return mobile, message text or OTP."""
    if message_id <= 0:
        raise ValueError('message_id must be positive')
    settings = get_settings()
    if not settings.SMS_API_KEY.strip():
        raise RuntimeError("سرویس پیامک پیکربندی نشده است")
    try:
        with _sms_session() as session:
            response = session.get(
                f"{settings.SMS_BASE_URL.rstrip('/')}/v1/send/{message_id}",
                headers={"x-api-key": settings.SMS_API_KEY},
                timeout=(5, 8), proxies=_proxy_dict(settings),
            )
        if response.status_code != 200:
            raise RuntimeError(f"دریافت گزارش پیامک ناموفق بود (HTTP {response.status_code})")
        body = response.json()
        data = body.get('data') if isinstance(body, dict) else None
        if not isinstance(data, dict) or body.get('status') != 1:
            raise RuntimeError("گزارش معتبر برای این پیامک دریافت نشد")
        def number(key):
            value = data.get(key)
            return value if type(value) is int else None
        return {'message_id': message_id, 'send_at': number('sendDateTime'),
                'delivery_at': number('deliveryDateTime'), 'delivery_state': number('deliveryState')}
    except (requests.RequestException, ValueError) as exc:
        logger.warning('SMS delivery lookup failed: %s', type(exc).__name__)
        raise RuntimeError("گزارش پیامک در دسترس نیست") from exc
