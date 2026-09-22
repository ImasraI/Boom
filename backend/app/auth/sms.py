"""SMS.ir (Melipayamak) verification-code sender.

Uses the SMS.ir "send verify" REST endpoint with a panel-side template:
    POST {SMS_BASE_URL}/v1/send/verify
    headers: x-api-key: <SMS_API_KEY>, Content-Type: application/json
    body:    {"mobile": "9xxxxxxxxx", "templateId": "<id>", "parameters": [{"name": "CODE", "value": "123456"}]}

The template must contain the {CODE} parameter (create it in the SMS.ir
panel under the verification-templates section).
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
    payload = {
        "mobile": mobile,
        "templateId": settings.SMS_VERIFY_TEMPLATE_ID,
        "parameters": [{"name": "CODE", "value": code}],
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
