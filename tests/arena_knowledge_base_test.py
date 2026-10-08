"""Knowledge-base duels: the booklet is the OVERLAP of both players' subjects.

The rule under test, end to end:

  1. Two students of different majors duel only on exam material BOTH are
     officially tested on (ریاضی فیزیک x علوم تجربی -> ریاضی/فیزیک/شیمی).
  2. A ticked subject is a MATCHMAKING requirement - the opponent's knowledge
     base must contain every tick, so a ریاضی فیزیک student who ticks هندسه
     is never paired with a علوم تجربی student.
  3. Zero shared exam material means no match (never a lopsided booklet).
  4. The younger grade scopes the questions.
  5. A plain same-major, unfiltered duel still comes off the pre-generated
     duel shelf (the pool contract must not regress).
"""
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import (ArenaQueueEntry, Base, GeneratedMock,
                               StudentProfile, User)
from app.rag import knowledge_base as kb, mock_generation, pool_core
from app.routers import arena


# A shelf booklet must carry verified questions: claim_duel_booklet quarantines
# any pending row whose answer keys were never verified.
VERIFIED_SHELF_BOOKLET = json.dumps([
    {'verification_status':'verified','_id':i+1,'subject':subject,'topic':'',
     'text':f'q {subject} {i}','options':['a','b','c','d'],'answer':1,'explanation':''}
    for subject, count in [('ریاضی',13),('فیزیک',11),('شیمی',10)]
    for i in range(count)], ensure_ascii=False)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _mk_user(db, username):
    u = User(username=username, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _queue(db, user, major, grade="", wanted=None, elo=1000):
    entry = ArenaQueueEntry(
        student_id=user.id, elo=elo, major=major, grade=grade,
        wanted=json.dumps(wanted or [], ensure_ascii=False),
    )
    db.add(entry)
    db.commit()
    return entry


def _subjects(mock):
    return [q["subject"] for q in json.loads(mock.questions)]


def _distinct(mock):
    out = []
    for subject in _subjects(mock):
        if subject not in out:
            out.append(subject)
    return out


# ------------------------------------------------------- overlap planning ---

def test_cross_major_plan_is_the_shared_exam_material():
    """ریاضی فیزیک x علوم تجربی: ریاضی + فیزیک + شیمی, and nothing else."""
    out = kb.pair_plan("ریاضی فیزیک", "علوم تجربی")
    assert out["ok"] is True
    assert [row["name"] for row in out["plan"]] == ["ریاضی", "فیزیک", "شیمی"]
    # Counts are the smaller of the two majors' official figures, // divisor.
    assert [row["questions"] for row in out["plan"]] == [10, 10, 10]
    # Never a subject only one side studies.
    assert "زیست‌شناسی" not in out["booklet_subjects"]


def test_pair_order_never_changes_the_plan():
    """Whichever player queued first, both must get the same booklet."""
    a = kb.pair_plan("ریاضی فیزیک", "علوم تجربی")
    b = kb.pair_plan("علوم تجربی", "ریاضی فیزیک")
    assert a["plan"] == b["plan"]


def test_shared_math_survives_different_subject_names():
    """ریاضی فیزیک studies حسابان/هندسه where علوم تجربی studies ریاضی - the
    رياضی booklet is shared although no subject LABEL matches."""
    out = kb.pair_plan("ریاضی فیزیک", "علوم تجربی")
    assert "ریاضی" in out["booklet_subjects"]
    # ...even though a label-level intersection would have missed it: the two
    # majors name their math subjects differently and share no label for it.
    labels = (set(kb.study_subjects("ریاضی فیزیک"))
              & set(kb.study_subjects("علوم تجربی")))
    assert "ریاضی" not in labels and "هندسه" not in labels
    assert kb.booklet_rows("ریاضی فیزیک").keys() & \
        kb.booklet_rows("علوم تجربی").keys() == {"ریاضی", "فیزیک", "شیمی"}


def test_same_major_plan_equals_the_pre_generated_duel_shape():
    """The per-major duel shelves stay valid: a plain same-major duel's plan
    must be exactly what build_pool_booklet stored (scale_plan, divisor 3)."""
    for major in ("ریاضی فیزیک", "علوم تجربی", "علوم انسانی", "هنر",
                  "زبان‌های خارجی"):
        shelf = mock_generation.scale_plan(
            mock_generation.default_plan(major), divisor=3, minimum=3)
        out = kb.pair_plan(major, major)
        assert out["ok"] is True
        assert [(r["name"], r["questions"], r["minutes"]) for r in out["plan"]] == \
               [(r["name"], r["questions"], r["minutes"]) for r in shelf]
        assert kb.duel_duration_minutes(out["plan"]) == \
               sum(r["minutes"] for r in shelf) // 3


def test_majors_without_shared_exam_material_never_pair():
    """هنر and زبان‌های خارجی share school subjects but no BOOKLET subject."""
    out = kb.pair_plan("هنر", "زبان‌های خارجی")
    assert out["ok"] is False and out["plan"] == []
    assert "مشترک" in out["reason"]
    # Same major always works, so those students can still duel.
    assert kb.pair_plan("هنر", "هنر")["ok"] is True
    assert kb.pair_plan("زبان‌های خارجی", "زبان‌های خارجی")["ok"] is True


# ------------------------------------------------------------- tick filter ---

def test_ticked_geometry_excludes_the_science_major():
    """The reported case: a ریاضی student ticking هندسه must not be paired
    with a علوم تجربی student (who never studied هندسه)."""
    out = kb.pair_plan("ریاضی فیزیک", "علوم تجربی", ["هندسه"], None)
    assert out["ok"] is False
    assert "هندسه" in out["reason"]
    # The same tick is fine against another ریاضی فیزیک student...
    assert kb.pair_plan("ریاضی فیزیک", "ریاضی فیزیک", ["هندسه"], None)["ok"] is True


def test_tick_narrows_the_booklet_and_steers_the_topics():
    out = kb.pair_plan("ریاضی فیزیک", "علوم تجربی", ["فیزیک"], None)
    assert out["ok"] is True
    assert out["booklet_subjects"] == ["فیزیک"]
    assert out["plan"][0]["topics"] == ["فیزیک"]


def test_ticks_are_mutual():
    """A tick by EITHER player constrains the pair: if one of them cannot
    cover the other's tick, the match is refused."""
    out = kb.pair_plan("ریاضی فیزیک", "علوم تجربی", None, ["زیست‌شناسی"])
    assert out["ok"] is False
    assert "زیست‌شناسی" in out["reason"]


def test_non_exam_tick_only_constrains_matching():
    """دین و زندگی is a عمومی subject: no booklet contains it, so a tick on
    it filters opponents without changing the questions."""
    ticked = kb.pair_plan("ریاضی فیزیک", "علوم تجربی", ["دین و زندگی"], None)
    plain = kb.pair_plan("ریاضی فیزیک", "علوم تجربی")
    assert ticked["ok"] is True and ticked["plan"] == plain["plan"]
    # A حریف who does not study it is still excluded.
    assert kb.pair_plan("ریاضی فیزیک", "هنر", ["دین و زندگی"], None)["ok"] is False


def test_ticks_outside_your_own_major_are_dropped():
    assert kb.clean_wanted("ریاضی فیزیک", ["هندسه", "زیست‌شناسی", "هندسه"]) == ["هندسه"]
    assert kb.clean_wanted("علوم تجربی", ["زیست‌شناسی", "هندسه"]) == ["زیست‌شناسی"]
    assert kb.clean_wanted("علوم تجربی", [None, "", "   "]) == []


# ------------------------------------------------------------- grade scope ---

def test_grade_scope_uses_the_younger_grade():
    assert kb.grade_scope("دوازدهم", "دهم") == "دهم"
    assert kb.grade_scope("دهم", "دوازدهم") == "دهم"
    assert kb.grade_scope("فارغ‌التحصیل", "یازدهم") == "یازدهم"
    assert kb.grade_scope("فارغ‌التحصیل", "دوازدهم") == "دوازدهم"


def test_grade_scope_ignores_unknown_and_empty_grades():
    assert kb.grade_scope("", "") == ""
    assert kb.grade_scope("دوازدهم", "") == "دوازدهم"
    assert kb.grade_scope("", "دهم") == "دهم"
    assert kb.grade_scope("پایه نامعلوم", "دوازدهم") == "دوازدهم"


def test_grade_reaches_the_generation_prompt():
    plan = [{"name": "ریاضی", "questions": 5}]
    tenth = mock_generation.build_booklet_prompt(plan, [], "konkur", "", grade="دهم")
    none = mock_generation.build_booklet_prompt(plan, [], "konkur", "")
    assert "پایه تحصیلی دانش‌آموز: دهم" in tenth
    assert "پایه تحصیلی" not in none
    assert mock_generation.grade_block("  ") == ""


# ----------------------------------------------------------- filter options ---

def test_backend_subject_table_matches_the_frontend():
    """Drift guard: rag/knowledge_base.py mirrors frontend/src/data.ts.

    The arena serves its checkbox list from the backend, so the two tables
    must stay identical - adding a subject to one without the other would
    silently make that subject unduelable (or tickable but never matched).
    """
    import re

    src = (REPO_ROOT / "frontend" / "src" / "data.ts").read_text(encoding="utf-8")
    block = src.split("SUBJECTS_BY_MAJOR", 1)[1]
    parsed = {
        m.group(1): re.findall(r'"([^"]+)"', m.group(2))
        for m in re.finditer(r'"([^"]+)"\s*:\s*\[([^\]]*)\]', block)
    }
    assert parsed, "could not parse SUBJECTS_BY_MAJOR from data.ts"
    assert parsed == kb.MAJOR_STUDY_SUBJECTS


def test_filter_options_mark_addressable_subjects():
    opts = kb.filter_options("ریاضی فیزیک")
    assert "هندسه" in opts["mine"] and "هندسه" in opts["addressable"]
    # عمومی subjects can be ticked (they restrict opponents) but are never
    # part of a booklet.
    assert "دین و زندگی" in opts["mine"]
    assert "دین و زندگی" not in opts["addressable"]
    # The user-visible consequence of a tick.
    assert opts["majors_with"]["هندسه"] == ["ریاضی فیزیک"]
    assert set(opts["majors_with"]["زیست‌شناسی"]) == {"علوم تجربی"}


def test_filters_endpoint_prefers_the_profile_row(db):
    user = _mk_user(db, "09120001001")
    db.add(StudentProfile(user_id=user.id, major="علوم تجربی", grade="یازدهم"))
    db.commit()
    payload = arena.duel_filters(current_user=user, db=db)
    assert payload["major"] == "علوم تجربی"
    assert payload["grade"] == "یازدهم"
    assert "زیست‌شناسی" in payload["mine"]
    assert "هندسه" not in payload["mine"]


def test_wanted_of_survives_junk():
    entry = ArenaQueueEntry(student_id=1, elo=1000, wanted="not json")
    assert arena._wanted_of(entry) == []
    entry.wanted = '{"a": 1}'
    assert arena._wanted_of(entry) == []
    entry.wanted = '["هندسه"]'
    assert arena._wanted_of(entry) == ["هندسه"]


# --------------------------------------------------------------- matching ---

def test_matchmaking_skips_incompatible_opponents(db):
    """A queue full of incompatible players must not stop a compatible pair:
    the skipped candidates stay queued, the compatible ones get matched."""
    b = _mk_user(db, "09120002001")   # زبان‌های خارجی: no shared booklet subject
    c = _mk_user(db, "09120002002")   # علوم تجربی
    d = _mk_user(db, "09120002003")   # ریاضی فیزیک

    _queue(db, b, "زبان‌های خارجی")
    entry_c = _queue(db, c, "علوم تجربی")

    # C queued with only B waiting, and B cannot duel C: no match, no booklet.
    assert arena._try_pair(db, entry_c) is None
    assert db.query(ArenaQueueEntry).filter(
        ArenaQueueEntry.student_id == c.id).count() == 1
    assert db.query(GeneratedMock).count() == 0

    # D arrives: B is skipped, C matches on the shared subjects.
    entry_d = _queue(db, d, "ریاضی فیزیک")
    match = arena._try_pair(db, entry_d)
    assert match is not None
    mock = db.get(GeneratedMock, match.mock_id)
    # The reserved booklet is the INTERSECTION skeleton: the three shared
    # subjects, 10 questions each, on the overlap plan's own duration.
    assert _distinct(mock) == ["ریاضی", "فیزیک", "شیمی"]
    assert len(_subjects(mock)) == 30
    assert mock.duration_minutes == 38
    assert mock.grade == ""
    # Both matched entries left the queue; the incompatible one is still in it.
    queued = [e.student_id for e in db.query(ArenaQueueEntry).all()]
    assert queued == [b.id]


def test_a_tick_that_no_queued_opponent_can_cover_keeps_waiting(db):
    a = _mk_user(db, "09120003001")   # ریاضی فیزیک, ticks هندسه
    b = _mk_user(db, "09120003002")   # علوم تجربی
    entry_a = _queue(db, a, "ریاضی فیزیک", wanted=["هندسه"])
    _queue(db, b, "علوم تجربی")
    assert arena._try_pair(db, entry_a) is None
    assert db.query(ArenaQueueEntry).filter(
        ArenaQueueEntry.student_id == a.id).count() == 1


def test_zero_overlap_pair_is_never_matched(db):
    a = _mk_user(db, "09120004001")   # هنر
    b = _mk_user(db, "09120004002")   # زبان‌های خارجی
    entry_a = _queue(db, a, "هنر")
    _queue(db, b, "زبان‌های خارجی")
    assert arena._try_pair(db, entry_a) is None
    assert db.query(GeneratedMock).count() == 0


def test_plain_same_major_duel_still_uses_the_pre_generated_shelf(db):
    """The fast path: same major, no ticks -> the pooled booklet is claimed
    instead of a slow live generation."""
    a = _mk_user(db, "09120005001")
    b = _mk_user(db, "09120005002")
    pooled = GeneratedMock(
        student_id=0, title="duel shelf", major="ریاضی فیزیک", grade="",
        duration_minutes=48, questions=VERIFIED_SHELF_BOOKLET,
        status="pending_use", difficulty=pool_core.DUEL_DIFFICULTY,
    )
    db.add(pooled)
    db.commit()
    entry_a = _queue(db, a, "ریاضی فیزیک")
    _queue(db, b, "ریاضی فیزیک")
    match = arena._try_pair(db, entry_a)
    assert match is not None and match.mock_ready is True
    assert match.mock_id == pooled.id
    assert db.get(GeneratedMock, match.mock_id).status == "claimed"


def test_cross_major_duel_never_takes_a_single_major_shelf_booklet(db):
    """A pooled booklet belongs to ONE major, so a cross-major duel must
    generate its own intersection booklet instead of claiming it."""
    a = _mk_user(db, "09120006001")
    b = _mk_user(db, "09120006002")
    db.add(GeneratedMock(
        student_id=0, title="riazi shelf", major="ریاضی فیزیک", grade="",
        duration_minutes=48, questions=VERIFIED_SHELF_BOOKLET,
        status="pending_use", difficulty=pool_core.DUEL_DIFFICULTY,
    ))
    db.commit()
    entry_a = _queue(db, a, "ریاضی فیزیک")
    _queue(db, b, "علوم تجربی")
    match = arena._try_pair(db, entry_a)
    assert match is not None and match.mock_ready is True
    # Its verified questions may assemble a new shared-intersection booklet,
    # while the single-major shelf row itself remains unclaimed.
    assert match.mock_id != db.query(GeneratedMock).filter(
        GeneratedMock.difficulty == pool_core.DUEL_DIFFICULTY,
        GeneratedMock.student_id == 0).first().id
    # The shelf row is untouched (still pending, still unclaimed).
    assert db.query(GeneratedMock).filter(
        GeneratedMock.difficulty == pool_core.DUEL_DIFFICULTY,
        GeneratedMock.student_id == 0
    ).one().status == "pending_use"


def test_duel_grade_is_the_younger_players(db):
    a = _mk_user(db, "09120007001")
    b = _mk_user(db, "09120007002")
    entry_a = _queue(db, a, "ریاضی فیزیک", grade="دوازدهم")
    _queue(db, b, "علوم تجربی", grade="دهم")
    match = arena._try_pair(db, entry_a)
    assert match is not None
    # The placeholder booklet records the scope the questions must respect,
    # and its title names the shared subjects.
    mock = db.get(GeneratedMock, match.mock_id)
    assert mock.grade == "دهم"
    assert "ریاضی" in mock.title


def test_duel_generation_gets_the_intersection_plan_ticks_and_grade(db, monkeypatch):
    """The live fallback must generate from the PAIR's intersection plan (not
    one player's full booklet), steer the ticks and respect the grade."""
    a = _mk_user(db, "09120009001")
    b = _mk_user(db, "09120009002")
    entry_a = _queue(db, a, "ریاضی فیزیک", grade="دوازدهم")
    entry_b = _queue(db, b, "علوم تجربی", grade="دهم")
    pair = kb.pair_plan("ریاضی فیزیک", "علوم تجربی", ["فیزیک"])
    grade = kb.grade_scope("دوازدهم", "دهم")
    match = arena._reserve_match(db, entry_a, entry_b, pair, grade)
    assert match.mock_ready is False  # placeholder: real questions come later

    seen = {}

    def fake_generate(user_id, plan, topics=None, difficulty="konkur", **kwargs):
        seen["plan"] = [dict(row) for row in plan]
        seen["topics"] = list(topics or [])
        seen["grade"] = kwargs.get("grade")
        seen["difficulty"] = difficulty
        return [{"_id": 1, "subject": plan[0]["name"], "topic": "فیزیک",
                 "text": "سوال تولید شده", "options": ["a", "b", "c", "d"],
                 "answer": 1, "explanation": "",
                 "verification_status": "verified"}]

    monkeypatch.setattr(mock_generation, "generate_booklet", fake_generate)
    monkeypatch.setattr(mock_generation, "verify_and_repair_booklet",
                        lambda questions, *args, **kwargs: questions)
    monkeypatch.setattr(arena, "SessionLocal",
                        sessionmaker(bind=db.get_bind()))

    arena._generate_duel_booklet(match, pair["plan"], topics=pair["topics"],
                                 grade=grade)
    assert seen["plan"] == pair["plan"]
    assert seen["topics"] == ["فیزیک"]
    assert seen["grade"] == "دهم"
    assert seen["difficulty"] == "konkur"

    db.expire_all()
    stored = db.get(GeneratedMock, match.mock_id)
    assert json.loads(stored.questions)[0]["text"] == "سوال تولید شده"


# ----------------------------------------------------------- wire contract ---

def _client(db, user):
    """The arena router alone, with auth/db pinned to the test session.

    Field NAMES are the contract the Arena page reads, so they are asserted
    here rather than trusted to survive a refactor.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(arena.router)
    app.dependency_overrides[arena.get_current_user] = lambda: user
    app.dependency_overrides[arena.get_db] = lambda: db
    return TestClient(app)


def test_filters_endpoint_contract(db):
    user = _mk_user(db, "09120008001")
    db.add(StudentProfile(user_id=user.id, major="ریاضی فیزیک", grade="دهم"))
    db.commit()
    body = _client(db, user).get("/api/arena/filters").json()
    assert body["major"] == "ریاضی فیزیک" and body["grade"] == "دهم"
    assert "هندسه" in body["mine"] and "هندسه" in body["addressable"]
    assert body["majors_with"]["هندسه"] == ["ریاضی فیزیک"]
    assert body["booklet_of"]["هندسه"] == "ریاضی"


def test_join_accepts_the_tick_list_and_reports_dropped_ones(db):
    user = _mk_user(db, "09120008002")
    db.add(StudentProfile(user_id=user.id, major="ریاضی فیزیک", grade="دهم"))
    db.commit()
    res = _client(db, user).post("/api/arena/join", json={
        "student": {"major": "ریاضی فیزیک", "grade": "دهم"},
        # زیست‌شناسی is not in a ریاضی فیزیک student's subjects: dropped.
        "wanted": ["هندسه", "زیست‌شناسی"],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["queued"] is True and body["match_id"] is None
    assert body["wanted"] == ["هندسه"]
    assert body["ignored_wanted"] == ["زیست‌شناسی"]
    assert body["major"] == "ریاضی فیزیک"

    status = _client(db, user).get("/api/arena/status").json()
    assert status["state"] == "queued"
    assert status["wanted"] == ["هندسه"]


def test_match_payload_names_the_shared_subjects(db):
    a = _mk_user(db, "09120008003")
    b = _mk_user(db, "09120008004")
    entry_a = _queue(db, a, "ریاضی فیزیک")
    _queue(db, b, "علوم تجربی")
    match = arena._try_pair(db, entry_a)
    body = _client(db, b).get(f"/api/arena/{match.id}").json()
    assert body["subjects"] == ["ریاضی", "فیزیک", "شیمی"]
    # The duel is short: 30 questions on the overlap plan's own duration.
    assert body["mock"]["duration_minutes"] == 38
