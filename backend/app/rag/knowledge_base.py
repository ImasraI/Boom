"""Knowledge bases: what each major has actually studied.

A ranked duel is only fair if BOTH players have studied every topic in it, so
the arena pairs two students on the INTERSECTION of their knowledge bases and
generates the booklet only from subjects that survive it:

  * a 10th-grade ریاضی فیزیک student against a 12th-grade علوم تجربی student
    gets ریاضی + فیزیک + شیمی — the three subjects both majors study — and
    never زیست‌شناسی (only تجربی) or a topic like هندسه that تجربی's subject
    list does not contain;
  * when the two grades differ, the earlier grade wins: the older student has
    already covered the younger one's syllabus, so questions never ask the
    younger student about material they have not reached yet.

Players may also tick the subjects they WANT to be tested on. A tick is a
MATCHMAKING constraint: the opponent's knowledge base must contain every
ticked subject, so a ریاضی فیزیک student who ticks هندسه is never matched
with a علوم تجربی student (whose subjects are ریاضی/فیزیک/شیمی/زیست/زمین,
without هندسه). Ticked subjects that this app's exam booklets do not examine
(دین و زندگی، عربی عمومی، ...) still constrain matching — they just add no
questions, because a Konkur booklet does not contain them.

The study-subject lists below mirror frontend/src/data.ts SUBJECTS_BY_MAJOR;
GET /api/arena/filters serves them to the client so the arena UI never keeps
its own copy that could drift. The question counts come from
konkur_format.SPECIALIZED_SUBJECTS, the single source of truth for plans.
"""

from typing import Dict, Iterable, List, Optional, Sequence

from app.rag.konkur_format import SPECIALIZED_SUBJECTS, major_key

# --------------------------------------------------------------- subjects ---
# The subjects a student of each major studies in school (the planner's
# subject tabs). Mirrors frontend/src/data.ts SUBJECTS_BY_MAJOR.
MAJOR_STUDY_SUBJECTS: Dict[str, List[str]] = {
    "ریاضی فیزیک": [
        "حسابان", "جبر و گسسته", "هندسه", "فیزیک", "شیمی",
        "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی",
    ],
    "علوم تجربی": [
        "ریاضی", "فیزیک", "شیمی", "زیست‌شناسی",
        "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی",
    ],
    "علوم انسانی": [
        "ادبیات فارسی", "عربی", "تاریخ", "جغرافیا", "اقتصاد",
        "منطق و فلسفه", "دین و زندگی", "علوم اجتماعی", "ریاضی و آمار",
    ],
    "هنر": [
        "نقاشی و هنرهای تجسمی", "ترکیب‌بندی", "تاریخ هنر",
        "ادبیات فارسی", "زبان انگلیسی", "ریاضی",
    ],
    "زبان‌های خارجی": [
        "زبان انگلیسی", "زبان دوم", "ادبیات فارسی", "ریاضی", "تاریخ",
    ],
}

# Study subject -> the booklet subject questions on it are generated under.
# Several school subjects share one exam booklet subject (حسابان، جبر و گسسته
# and هندسه are all examined as ریاضی). A subject missing here is never part
# of a booklet; it can still be ticked as a matchmaking requirement.
STUDY_TO_BOOKLET: Dict[str, str] = {
    "حسابان": "ریاضی",
    "جبر و گسسته": "ریاضی",
    "هندسه": "ریاضی",
    "ریاضی": "ریاضی",
    "ریاضی و آمار": "ریاضی",
    "فیزیک": "فیزیک",
    "شیمی": "شیمی",
    "زیست‌شناسی": "زیست‌شناسی",
    "زمین‌شناسی": "زمین‌شناسی",
    "ادبیات فارسی": "زبان و ادبیات فارسی",
    "عربی": "عربی",
    "تاریخ": "تاریخ",
    "جغرافیا": "جغرافیا",
    "اقتصاد": "اقتصاد",
    "منطق و فلسفه": "فلسفه و منطق",
    "علوم اجتماعی": "علوم اجتماعی",
    "روان‌شناسی": "روان‌شناسی",
    "تاریخ هنر": "درک عمومی هنر",
    "نقاشی و هنرهای تجسمی": "خلاقیت تصویری و تجسمی",
    "ترکیب‌بندی": "خلاقیت تصویری و تجسمی",
    "زبان تخصصی": "زبان تخصصی",
}

# Youngest first: the index is the syllabus scope, so min() = the grade whose
# material both players have certainly reached.
GRADE_ORDER: List[str] = ["دهم", "یازدهم", "دوازدهم", "فارغ‌التحصیل"]

# A duel is a SHORT booklet: question counts // divisor with a floor, exactly
# like the pre-generated duel shelves (mock_generation.scale_plan).
DUEL_DIVISOR = 3
DUEL_MIN_QUESTIONS = 3


def study_subjects(major: str) -> List[str]:
    """The study subjects a major's students take (empty for unknown input)."""
    text = (major or "").strip()
    if text in MAJOR_STUDY_SUBJECTS:
        return list(MAJOR_STUDY_SUBJECTS[text])
    # Labels with a suffix ("علوم تجربی (کنکور ۱۴۰۶)") or a konkur key.
    key = major_key(text)
    for label, subjects in MAJOR_STUDY_SUBJECTS.items():
        if major_key(label) == key:
            return list(subjects)
    return []


def booklet_rows(major: str) -> Dict[str, dict]:
    """{booklet subject: plan row} officially examined for this major."""
    return {row["name"]: dict(row)
            for row in SPECIALIZED_SUBJECTS.get(major_key(major), [])}


def booklet_subject_of(subject: str) -> Optional[str]:
    """Booklet subject a study subject is examined as (None = not examined)."""
    return STUDY_TO_BOOKLET.get((subject or "").strip())


def is_addressable(major: str, subject: str) -> bool:
    """Can this student actually get booklet questions on `subject`?

    True when the subject is examined under a name this major's booklet
    contains (هندسه -> ریاضی for ریاضی فیزیک, but not for علوم تجربی, whose
    list has no هندسه at all).
    """
    mapped = booklet_subject_of(subject)
    return bool(mapped) and mapped in booklet_rows(major)


def majors_covering(subject: str) -> List[str]:
    """Every major whose students study `subject` (the checkbox's audience)."""
    return [label for label, subjects in MAJOR_STUDY_SUBJECTS.items()
            if subject in subjects]


def all_study_subjects() -> List[str]:
    """Union of every major's subjects, in a stable first-seen order."""
    seen: List[str] = []
    for subjects in MAJOR_STUDY_SUBJECTS.values():
        for subject in subjects:
            if subject not in seen:
                seen.append(subject)
    return seen


def grade_scope(grade_a: str, grade_b: str) -> str:
    """The grade whose syllabus a duel may cover.

    Duel questions come from the EARLIER grade: a 12th-grade (or
    فارغ‌التحصیل) student has already covered a 10th-grade syllabus, so the
    younger player is never asked about material they have not reached.
    An unknown grade is ignored rather than assumed to be the youngest; both
    unknown yields "" (the generator then applies no grade restriction).
    """
    a = (grade_a or "").strip()
    b = (grade_b or "").strip()
    known = [g for g in (a, b) if g in GRADE_ORDER]
    if not known:
        return ""
    if len(known) == 1:
        return known[0]
    return min(known, key=GRADE_ORDER.index)


def clean_wanted(major: str, wanted: Optional[Iterable[str]]) -> List[str]:
    """Validate/normalise a tick list: only subjects the player studies.

    Unknown labels are dropped silently (a stale client tick must not break
    matchmaking); the caller decides whether an empty result is an error.
    """
    mine = set(study_subjects(major))
    out: List[str] = []
    for subject in wanted or []:
        label = (subject or "").strip()
        if label in mine and label not in out:
            out.append(label)
    return out


def pair_plan(major_a: str, major_b: str,
              wanted_a: Optional[Sequence[str]] = None,
              wanted_b: Optional[Sequence[str]] = None
              ) -> Dict[str, object]:
    """Can these two players duel, and on what?

    Pure function - the whole matchmaking rule lives here, so the queue, the
    tests and any future mode share one definition.

    Returns {"ok", "reason", "booklet_subjects", "topics", "plan"}:
      * ok          - the pair may duel (non-empty common exam material);
      * reason      - Persian explanation when ok is False;
      * booklet_subjects - the shared BOOKLET subjects the duel covers;
      * topics      - study subjects to steer generation's "هدف مباحث";
      * plan        - duel-sized plan rows (questions // divisor, minutes
                      left for the caller to scale), ready for
                      mock_generation.generate_booklet.
    """
    a = clean_wanted(major_a, wanted_a)
    b = clean_wanted(major_b, wanted_b)
    kb_a, kb_b = set(study_subjects(major_a)), set(study_subjects(major_b))

    missing_b = [s for s in a if s not in kb_b]
    if missing_b:
        return {"ok": False, "plan": [], "booklet_subjects": [],
                "topics": [],
                "reason": "حریف این درسها را نخوانده: " + "، ".join(missing_b)}
    missing_a = [s for s in b if s not in kb_a]
    if missing_a:
        return {"ok": False, "plan": [], "booklet_subjects": [],
                "topics": [],
                "reason": "این درسها در رشته تو نیست: " + "، ".join(missing_a)}

    rows_a, rows_b = booklet_rows(major_a), booklet_rows(major_b)
    # Shared EXAM material is matched at the booklet-subject level, never at
    # the label level: ریاضی فیزیک studies حسابان/جبر/هندسه where علوم تجربی
    # studies ریاضی - the two majors share the ریاضی booklet although no
    # subject label matches. Ordering follows the alphabetically first major
    # so the same pair always produces the same plan whichever side queued
    # first (counts, duration and question order stay identical).
    first, second = ((rows_a, rows_b) if major_key(major_a) <= major_key(major_b)
                     else (rows_b, rows_a))
    shared = [name for name in first if name in second]

    ticked: List[str] = []
    for s in list(a) + list(b):
        if s not in ticked:
            ticked.append(s)
    # Ticks narrow the booklet to the booklet subjects they name, but a tick
    # on a subject this app never examines (دین و زندگی, عربی for a ریاضی
    # student, ...) only constrained matching above - it adds no questions.
    named = {booklet_subject_of(s) for s in ticked if booklet_subject_of(s)}
    narrowed = [name for name in shared if name in named]
    chosen = narrowed or shared

    plan: List[dict] = []
    for booklet in chosen:
        ra, rb = rows_a[booklet], rows_b[booklet]
        questions = min(int(ra.get("questions") or 0), int(rb.get("questions") or 0))
        if questions <= 0:
            continue
        row = {
            "name": booklet,
            "questions": max(DUEL_MIN_QUESTIONS, questions // DUEL_DIVISOR),
            # Minutes stay official here; the caller scales the match duration
            # exactly like the duel shelves do (sum // divisor).
            "minutes": min(int(ra.get("minutes") or 0),
                           int(rb.get("minutes") or 0)),
            "section": ra.get("section", "اختصاصی"),
        }
        # Ticked school subjects targeting this booklet subject become the
        # prompt's "مباحث هدف" (هندسه ticked -> geometry questions).
        topics = [s for s in ticked if booklet_subject_of(s) == booklet]
        if topics:
            row["topics"] = topics
        plan.append(row)

    if not plan:
        return {"ok": False, "plan": [], "booklet_subjects": [], "topics": [],
                "reason": "بین رشته شما و این حریف درس آزمونی مشترکی نیست"}
    return {"ok": True, "reason": "", "booklet_subjects": chosen,
            "topics": [s for s in ticked if booklet_subject_of(s)], "plan": plan}


def duel_duration_minutes(plan: Sequence[dict]) -> int:
    """Match duration for a duel plan (mirrors the duel shelves' // divisor)."""
    total = sum(int(row.get("minutes") or 0) for row in plan)
    return max(10, total // DUEL_DIVISOR)


def filter_options(major: str) -> Dict[str, object]:
    """Everything the arena's filter checkboxes need, for one player.

    `mine` are the tickable subjects (the player's own); `addressable` marks
    the ones that can also produce questions, and `majors_with` tells the UI
    exactly which majors a tick restricts the queue to - the user-visible
    consequence of checking هندسه is "only ریاضی فیزیک students".
    """
    mine = study_subjects(major)
    rows = booklet_rows(major)
    return {
        "all": all_study_subjects(),
        "mine": mine,
        "addressable": [s for s in mine if is_addressable(major, s)],
        "booklet_of": {s: booklet_subject_of(s) for s in mine
                       if booklet_subject_of(s)},
        "majors_with": {s: majors_covering(s) for s in all_study_subjects()},
        "major": (major or "").strip(),
        "major_key": major_key(major or ""),
        "booklet": [
            {"name": row["name"], "questions": row["questions"],
             "duel_questions": max(DUEL_MIN_QUESTIONS,
                                   int(row["questions"]) // DUEL_DIVISOR)}
            for row in rows.values()
        ],
        "grades": list(GRADE_ORDER),
    }
