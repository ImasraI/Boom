"""SMS.ir verification-code sender.

Uses the SMS.ir "send verify" REST endpoint with a panel-side template:
    POST {SMS_BASE_URL}/v1/send/verify
    headers: x-api-key: <SMS_API_KEY>, Content-Type: application/json
    body:    {"mobile": "9xxxxxxxxx", "templateId": 123456,
              "parameters": [{"name": "Code", "value": "12345"}]}

Notes (matched to the SMS.ir docs / panel template):
- "templateId" must be a NUMBER, not a string.
- The parameter name must match the template's placeholder name exactly
  (SMS.ir's default template uses "Code", capital C).
- SMS.ir replies HTTP 200 even when the send fails; success is only
  "status": 1 in the JSON body, so that is what we validate.

The template must contain the {Code} parameter (create it in the SMS.ir
panel under the verification-templates section and put its numeric id in
SMS_VERIFY_TEMPLATE_ID).
"""

from __future__ import annotations

import logging
import random

import requests

from ..config import get_settings

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 120  # signup codes live for 2 minutes


def generate_code() -> str:
    """6-digit numeric code, cryptographically random."""
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_ir_mobile(phone: str) -> str:
    """Accept 09xxxxxxxxx / 9xxxxxxxxx / +989xxxxxxxxx -> 9xxxxxxxxx."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("98"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or not digits.startswith("9"):
        raise ValueError("invalid Iranian mobile number")
    return digits


def send_verification_code(mobile: str, code: str) -> None:
    """Send `code` to `mobile` (9xxxxxxxxx) via the SMS.ir verify template.

    Raises RuntimeError with a user-safe message on failure; the raw error
    goes to the log only.
    """
    settings = get_settings()
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
        "parameters": [{"name": "Code", "value": code}],
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "x-api-key": settings.SMS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.error("SMS.ir unreachable: %s", exc)
        raise RuntimeError("سرویس پیامک در دسترس نیست") from exc

    if resp.status_code != 200:
        logger.error("SMS.ir verify failed %s: %s", resp.status_code, resp.text[:300])
        raise RuntimeError("ارسال پیامک ناموفق بود")

    # SMS.ir returns HTTP 200 even when the send failed; success is only
    # visible as "status": 1 in the body (see docs: {"status": 1,
    # "message": "موفق", "data": {"messageId": ..., "cost": ...}}).
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if body.get("status") != 1:
        logger.error(
            "SMS.ir verify rejected: status=%s message=%s data=%s",
            body.get("status"), body.get("message"), str(body.get("data"))[:200],
        )
        raise RuntimeError("ارسال پیامک ناموفق بود")


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
        resp = requests.get(
            f"{settings.SMS_BASE_URL.rstrip('/')}/v1/credit",
            headers={"x-api-key": settings.SMS_API_KEY,
                     "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"credit": 0, "configured": True,
                    "detail": f"خطای {resp.status_code} از سرویس"}
        body = resp.json()
        if body.get("status") != 1:
            return {"credit": 0, "configured": True,
                    "detail": body.get("message") or "پاسخ نامعتبر"}
        return {"credit": int(body.get("data") or 0), "configured": True,
                "detail": ""}
    except (requests.RequestException, ValueError) as exc:
        logger.warning("SMS credit check failed: %s", exc)
        return {"credit": 0, "configured": True, "detail": "سرویس در دسترس نیست"}
