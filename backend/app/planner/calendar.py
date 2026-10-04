"""Calendar persistence and date-only recurrence (Saturday-based weekdays)."""
import json
import math
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from app.auth.database import StudentCalendar


def calendar_row(db, user_id):
    existing = db.get(StudentCalendar, user_id)
    if existing is not None:
        return existing
    db.execute(insert(StudentCalendar).values(student_id=user_id, weeks="{}", statics="[]", version=0)
               .on_conflict_do_nothing(index_elements=[StudentCalendar.student_id]))
    db.flush()
    return db.get(StudentCalendar, user_id)


def payload(row):
    return {"weeks": json.loads(row.weeks), "statics": json.loads(row.statics), "version": row.version}


def protected_blocks(blocks):
    return [b for b in blocks if b.get("origin") == "manual" or
            (b.get("origin") != "generated" and not b.get("source_ref"))]


def occurrences(templates, week_start):
    out = []
    end = week_start + timedelta(days=6)
    for template in templates:
        rule = template.get("recurrence")
        if not rule:  # Preserve old weekly/yearly templates.
            if template.get("day") is not None:
                out.append({**template, "day": template["day"]})
                continue
            anchor = date.fromisoformat(template["date"])
            rule = {"frequency": "yearly", "interval": 1}
        else:
            anchor = date.fromisoformat(template["date"])
        interval = int(rule.get("interval", 1))
        until = date.fromisoformat(rule["until"]) if rule.get("until") else end
        frequency = rule["frequency"]
        days = rule.get("weekdays") or [(anchor.weekday() + 2) % 7]
        cursor, count = anchor, 0
        # Date-only stepping avoids timezone and DST drift. Max 150 years is
        # plenty for the supported calendar; validation bounds the anchor.
        while cursor <= min(end, until):
            delta = (cursor - anchor).days
            week_delta = (delta + (anchor.weekday() + 2) % 7) // 7
            month_delta = (cursor.year - anchor.year) * 12 + cursor.month - anchor.month
            match = ((frequency == "daily" and delta % interval == 0)
                     or (frequency == "weekly" and week_delta % interval == 0 and (cursor.weekday() + 2) % 7 in days)
                     or (frequency == "monthly" and month_delta % interval == 0 and cursor.day == anchor.day)
                     or (frequency == "yearly" and (cursor.year - anchor.year) % interval == 0
                         and (cursor.month, cursor.day) == (anchor.month, anchor.day)))
            if match:
                count += 1
                if rule.get("count") and count > int(rule["count"]):
                    break
                if cursor >= week_start:
                    out.append({**template, "day": (cursor - week_start).days,
                                "id": f'{template.get("id", "repeat")}:{cursor.isoformat()}'})
            cursor += timedelta(days=1)
    return out


def validate_blocks(blocks, *, templates=False):
    ids = set()
    for b in blocks:
        try:
            if not b.get("id") or b["id"] in ids or not str(b["title"]).strip():
                raise ValueError()
            ids.add(b["id"])
            start, duration = float(b["startHour"]), float(b["duration"])
            if not all(map(math.isfinite, (start, duration))) or not (0 <= start < 24 and 0 < duration <= 24 - start):
                raise ValueError()
            if b["type"] not in ("class", "study", "test", "break"):
                raise ValueError()
            if templates and b.get("recurrence"):
                anchor = date.fromisoformat(b["date"])
                if not 2000 <= anchor.year <= 2100:
                    raise ValueError()
                r = b["recurrence"]
                if r["frequency"] not in ("daily", "weekly", "monthly", "yearly") or not 1 <= int(r.get("interval", 1)) <= 365:
                    raise ValueError()
                if r.get("count") is not None and not 1 <= int(r["count"]) <= 10000:
                    raise ValueError()
                if r.get("until") and date.fromisoformat(r["until"]) < anchor:
                    raise ValueError()
                if any(not isinstance(d, int) or not 0 <= d <= 6 for d in r.get("weekdays", [])):
                    raise ValueError()
            elif templates and b.get("date"):
                date.fromisoformat(b["date"])
            elif not isinstance(b.get("day"), int) or not 0 <= b["day"] <= 6:
                raise ValueError()
        except (ValueError, TypeError, KeyError, OverflowError):
            raise HTTPException(422, "زمان یا قانون تکرار فعالیت نامعتبر است")


def overlaps(blocks):
    return any(a["day"] == b["day"] and round(a["startHour"] * 60) < round((b["startHour"] + b["duration"]) * 60)
               and round(b["startHour"] * 60) < round((a["startHour"] + a["duration"]) * 60)
               for i, a in enumerate(blocks) for b in blocks[i + 1:])


def write_calendar(db, row, weeks, statics, version):
    result = db.execute(update(StudentCalendar).where(StudentCalendar.student_id == row.student_id,
        StudentCalendar.version == version).values(weeks=json.dumps(weeks, ensure_ascii=False),
        statics=json.dumps(statics, ensure_ascii=False), version=version + 1))
    if not result.rowcount:
        db.rollback()
        db.expire_all()
        raise HTTPException(409, {"message": "برنامه روی دستگاه دیگری تغییر کرده است؛ دوباره بارگذاری کنید.",
                                  "calendar": payload(db.get(StudentCalendar, row.student_id))})
    db.commit()
    db.refresh(row)
    return payload(row)
