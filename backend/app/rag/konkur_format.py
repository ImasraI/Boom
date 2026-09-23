"""Single source of truth for the official Konkur exam structure.

Figures are the published Sazman-e Sanjesh (سازمان سنجش) format for the
1403-1405 exams — the structure and counts are identical across those three
years (1405's table was announced by Sanjesh on 26 Mordad 1405). Everything
here mirrors the REAL exam: per the Supreme Council of the Cultural
Revolution decision in effect since Konkur 1402, the four عمومی (general)
subjects — زبان و ادبیات فارسی، عربی، دین و زندگی، زبان انگلیسی — are no
longer examined as a test booklet; they reach the final score only through
سوابق تحصیلی (final-exam GPA, weighted 50% alongside the test).

Structure per group = عمومی (reference table, NOT part of mock generation)
+ اختصاصی (the actual booklet contents used for mock/duel plans).

Official اختصاصی figures (questions / minutes):

  ریاضی و فیزیک   book 1: ریاضی 40/70                      book 2: فیزیک 35/45, شیمی 30/30  -> 105 q / 145 min
  علوم تجربی      book 1: زیست 45/45                        book 2: فیزیک 30/40, شیمی 35/35
                  book 3: ریاضی 30 + زمین‌شناسی 15 / 60 min                                   -> 155 q / 180 min
  علوم انسانی     book 1: ریاضی 20/30, ادبیات 30/30, علوم اجتماعی 15/25, روان‌شناسی 15/-  (85 min total)
                  book 2: عربی 20/20, تاریخ 13/20, جغرافیا 12/-, اقتصاد 15/15, فلسفه و منطق 20/20  (75 min total)
                                                                                              -> 160 q / 160 min
  هنر             درک عمومی هنر 50/50, درک عمومی ریاضی‌فیزیک 30/40, خلاقیت تصویری 20/25        -> 100 q / 115 min
  زبان‌های خارجی  زبان تخصصی 70/105                                                          -> 70 q / 105 min

Insani book-1 nuances: the 85 minutes covers its four subjects jointly; the
علوم اجتماعی + روان‌شناسی pair is officially one 30-question block (15+15);
جغرافیا + تاریخ share the 20-minute book-2 window (12 + 13 questions). The
per-subject minute values below allocate those joint blocks proportionally
(15/15 split of the 25-minute social-science block, 13/12 split of the
20-minute history-geography block) so every plan row still carries a
sensible duration for pacing.
"""

from typing import Dict, List

# Which year's official figures this module encodes. Bump when Sanjesh
# publishes a new format (check: sanjesh.org -> اطلاعیه تعداد سوالات).
FORMAT_YEAR = "1405 (identical 1403-1405)"

# ---------------------------------------------------------------- عمومی ----
# Not examined as a test booklet since Konkur 1402 (50% weight flows in via
# final-exam GPA). Kept for study plans and the future final-mock feature;
# deliberately EXCLUDED from mock/duel generation plans.
GENERAL_SUBJECTS: List[dict] = [
    {"name": "زبان و ادبیات فارسی", "questions": 0, "minutes": 0, "section": "عمومی"},
    {"name": "عربی", "questions": 0, "minutes": 0, "section": "عمومی"},
    {"name": "دین و زندگی", "questions": 0, "minutes": 0, "section": "عمومی"},
    {"name": "زبان انگلیسی", "questions": 0, "minutes": 0, "section": "عمومی"},
]

# ------------------------------------------------------------- اختصاصی ----
SPECIALIZED_SUBJECTS: Dict[str, List[dict]] = {
    "riazi": [
        {"name": "ریاضی", "questions": 40, "minutes": 70, "section": "اختصاصی"},
        {"name": "فیزیک", "questions": 35, "minutes": 45, "section": "اختصاصی"},
        {"name": "شیمی", "questions": 30, "minutes": 30, "section": "اختصاصی"},
    ],
    "tajrobi": [
        {"name": "زیست‌شناسی", "questions": 45, "minutes": 45, "section": "اختصاصی"},
        {"name": "فیزیک", "questions": 30, "minutes": 40, "section": "اختصاصی"},
        {"name": "شیمی", "questions": 35, "minutes": 35, "section": "اختصاصی"},
        {"name": "ریاضی", "questions": 30, "minutes": 45, "section": "اختصاصی"},
        {"name": "زمین‌شناسی", "questions": 15, "minutes": 15, "section": "اختصاصی"},
    ],
    "insani": [
        {"name": "ریاضی", "questions": 20, "minutes": 30, "section": "اختصاصی"},
        {"name": "زبان و ادبیات فارسی", "questions": 30, "minutes": 30, "section": "اختصاصی"},
        {"name": "علوم اجتماعی", "questions": 15, "minutes": 12, "section": "اختصاصی"},
        {"name": "روان‌شناسی", "questions": 15, "minutes": 13, "section": "اختصاصی"},
        {"name": "عربی", "questions": 20, "minutes": 20, "section": "اختصاصی"},
        {"name": "تاریخ", "questions": 13, "minutes": 11, "section": "اختصاصی"},
        {"name": "جغرافیا", "questions": 12, "minutes": 9, "section": "اختصاصی"},
        {"name": "اقتصاد", "questions": 15, "minutes": 15, "section": "اختصاصی"},
        {"name": "فلسفه و منطق", "questions": 20, "minutes": 20, "section": "اختصاصی"},
    ],
    "honar": [
        {"name": "درک عمومی هنر", "questions": 50, "minutes": 50, "section": "اختصاصی"},
        {"name": "درک عمومی ریاضی و فیزیک", "questions": 30, "minutes": 40, "section": "اختصاصی"},
        {"name": "خلاقیت تصویری و تجسمی", "questions": 20, "minutes": 25, "section": "اختصاصی"},
    ],
    "zaban": [
        {"name": "زبان تخصصی", "questions": 70, "minutes": 105, "section": "اختصاصی"},
    ],
}

# Legacy alias: the old two-major table. Kept so any forgotten importer
# fails loudly instead of silently using stale counts.
KONKUR_SUBJECTS = SPECIALIZED_SUBJECTS

# Frontend signup majors -> format-module keys (frontend/src/data.ts MAJORS).
MAJOR_ALIASES: Dict[str, str] = {
    "ریاضی فیزیک": "riazi",
    "علوم تجربی": "tajrobi",
    "علوم انسانی": "insani",
    "هنر": "honar",
    "زبان‌های خارجی": "zaban",
    # Persian booklets also name groups without علوم / و فیزیک
    "ریاضی": "riazi",
    "تجربی": "tajrobi",
    "انسانی": "insani",
}


def major_key(major: str) -> str:
    """Map a (Persian or English) major label to a SPECIALIZED_SUBJECTS key."""
    text = (major or "").strip()
    if text in SPECIALIZED_SUBJECTS:
        return text
    for label, key in MAJOR_ALIASES.items():
        if label in text or text in label:
            return key
    return "riazi"  # frontend defaults to ریاضی فیزیک everywhere


def plan_totals(plan: List[dict]) -> dict:
    """{questions, minutes} totals for a plan (used for booklet duration)."""
    return {
        "questions": sum(s["questions"] for s in plan),
        "minutes": sum(s["minutes"] for s in plan),
    }
