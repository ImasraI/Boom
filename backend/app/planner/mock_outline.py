"""Read saved mock-plan outlines; keep dates, topics and book numbers distinct."""
import json
import re
from datetime import timedelta
from pathlib import Path
from app.config import get_settings
from app.planner.resources import _norm, _subject


def next_mock_outline(student, week_start):
    from app.routers.boom_ai import _jalali, _J_MONTHS
    path = Path(get_settings().RAW_DIR).parent / "cache" / "mock_extraction.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    candidates = []
    for key, text in cache.items():
        if not key.startswith("norm2|") or not isinstance(text, str):
            continue
        norm = _norm(text)
        major = _norm(student.get("major", "ریاضی"))
        if any(track in norm and track not in major for track in ("ریاضی", "تجربی", "انسانی") if track in norm[:150]):
            continue
        # Documents dated in another year are not recurring exam schedules.
        year = _jalali(week_start.year, week_start.month, week_start.day)[0]
        explicit_years = re.findall(r"(?<!\d)(14\d{2})(?!\d)", norm + " " + key)
        if not explicit_years or str(year) not in explicit_years:
            continue
        hits = set(re.findall(r"(?<!\d)(\d{1,2})\s+(" + "|".join(_J_MONTHS) + ")", norm))
        dates = []
        for offset in range(21):
            actual = week_start + timedelta(days=offset)
            jy, jm, jd = _jalali(actual.year, actual.month, actual.day)
            if jy == year and (str(jd), _J_MONTHS[jm - 1]) in hits:
                dates.append(actual)
        if not dates:
            continue
        topics, subject, optional = {}, None, False
        for line in text.splitlines():
            if line.lstrip().startswith("###"):
                optional = "اختیاری" in line
                subject = None
            if optional:
                continue
            heading = re.match(r"\s*-\s*\*\*([^*]+)\*\*", line)
            if heading:
                subject = _subject(heading.group(1))
            elif subject and "مباحث:" in line:
                value = line.split("مباحث:", 1)[1].strip().replace("\u202f", " ")
                if any(word in value for word in ("نامشخص", "همان مباحث", "مشابه دفترچه")):
                    continue
                rows = [v.strip() for v in re.split("[،,]", value) if v.strip()]
                topics.setdefault(subject, []).extend(rows)
        if topics:
            candidates.append({"date": min(dates), "document": key.split("|", 1)[1],
                               "topics": {s: list(dict.fromkeys(t)) for s, t in topics.items()}})
    return min(candidates, key=lambda c: c["date"]) if candidates else None
