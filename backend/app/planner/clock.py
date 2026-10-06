"""Student-facing calendar time; persistence/auth timestamps remain UTC."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    _TIMEZONE = ZoneInfo("Asia/Tehran")
except ZoneInfoNotFoundError:
    # Windows installations without tzdata still use the project's local clock.
    _TIMEZONE = timezone(timedelta(hours=3, minutes=30))


def planner_now():
    return datetime.now(_TIMEZONE).replace(tzinfo=None)
