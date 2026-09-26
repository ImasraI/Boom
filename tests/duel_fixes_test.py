"""Regressions for the question-generation & duel-system fix brief.

Covers: duel pool claim isolation, balanced pad_booklet distribution,
Elo placement acceleration + User.rating snapshots. The pool worker/sweep
behavior itself is covered by pool_cancel_test.
"""
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

from app.auth.database import (ArenaMatch, Base, GeneratedMock, MockAttempt, User,
                               record_match_rating)
from app.rag import mock_generation, pool_core


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


def _mk_duel_row(db, title="duel booklet"):
    db.add(GeneratedMock(
        student_id=0, title=title, major="ریاضی فیزیک", grade="",
        duration_minutes=30,
        questions='[{"_id":1,"subject":"ریاضی","topic":"","text":"سوال؟",'
                  '"options":["a","b","c","d"],"answer":1,"explanation":""}]',
        status="pending_use", difficulty=pool_core.DUEL_DIFFICULTY,
    ))
    db.commit()


def test_duel_claim_marks_row_and_never_reserves_twice(db):
    _mk_duel_row(db)
    a, b = _mk_user(db, "09120000001"), _mk_user(db, "09120000002")
    row = pool_core.claim_duel_booklet(db, a.id, b.id, "riazi")
    assert row is not None and row.status == "claimed"
    assert row.student_id == a.id
    # Same pair again: nothing left pending for them.
    assert pool_core.claim_duel_booklet(db, a.id, b.id, "riazi") is None


def test_duel_claim_skips_booklets_either_player_attempted(db):
    _mk_duel_row(db)
    a, b = _mk_user(db, "09120000003"), _mk_user(db, "09120000004")
    row = db.query(GeneratedMock).first()
    db.add(MockAttempt(student_id=a.id, mock_id=row.id, score=10.0))
    db.commit()
    assert pool_core.claim_duel_booklet(db, a.id, b.id, "riazi") is None


def test_duel_shelf_is_invisible_to_standard_mock_shelves(db):
    """difficulty='duel' rows must never count as standard pool stock."""
    _mk_duel_row(db)
    assert pool_core.pool_deficit(db, "riazi", "konkur", target=1) == 1
    assert pool_core.duel_pool_deficit(db, "riazi", target=1) == 0


def test_pad_booklet_balances_without_breaking_keys():
    qs = [
        {"text": f"q{i}", "options": ["صحیح", "ب", "ج", "د"], "answer": 0,
         "explanation": "", "subject": "ریاضی", "topic": ""}
        for i in range(10)
    ]
    out = mock_generation.pad_booklet([dict(q, options=list(q["options"])) for q in qs])
    keys = [q["answer"] for q in out]
    share0 = keys.count(0) / len(keys)
    assert share0 <= 0.35, f"option 0 still overloaded: {keys}"
    for q in out:
        assert q["options"][q["answer"]] == "صحیح"


def test_placement_elo_accelerates_then_settles(db):
    a, b = _mk_user(db, "09120000005"), _mk_user(db, "09120000006")
    from app.auth.database import ArenaMatch

    m = ArenaMatch(student_a_id=a.id, student_b_id=b.id, status="pending",
                   elo_a=1000, elo_b=1000, score_a=80, score_b=40)
    # First match for both -> placement K applies (48), not 32.
    record_match_rating(m, db)
    assert abs(m.delta_a) > 0 and m.delta_a == -m.delta_b
    d1 = m.delta_a
    m.status = "finished"
    db.commit()

    # A rating snapshot landed on the users.
    assert db.get(User, a.id).rating == m.elo_a
    assert db.get(User, b.id).rating == m.elo_b

    # Nine more finished matches for A: still within placement (< 10).
    for _ in range(9):
        db.add(ArenaMatch(student_a_id=a.id, student_b_id=b.id,
                          status="finished", elo_a=1100, elo_b=900,
                          score_a=80, score_b=40, delta_a=1, delta_b=-1))
    db.commit()
    m2 = ArenaMatch(student_a_id=a.id, student_b_id=b.id, status="pending",
                    elo_a=db.get(User, a.id).rating,
                    elo_b=db.get(User, b.id).rating, score_a=80, score_b=40)
    record_match_rating(m2, db)
    # A has now played 10 finished matches -> K drops to 32, so the swing
    # over the same score gap must not exceed the placement swing.
    assert abs(m2.delta_a) <= abs(d1)


def test_record_match_rating_without_session_still_works(db, monkeypatch):
    """Direct callers (no db arg) take the SessionLocal fallback path."""
    a, b = _mk_user(db, "09120000007"), _mk_user(db, "09120000008")
    m = ArenaMatch(student_a_id=a.id, student_b_id=b.id, status="pending",
                   elo_a=1000, elo_b=1000, score_a=80, score_b=40)
    # Point SessionLocal at the test engine for the fallback branch.
    import app.auth.database as adb
    monkeypatch.setattr(adb, "SessionLocal", sessionmaker(bind=db.get_bind()))
    record_match_rating(m)  # no db passed
    assert m.elo_a != 1000 and m.delta_a == -m.delta_b
