"""Regressions for the AI-rival fallback in the ranked arena.

The non-negotiable invariant under test: AI-rival matches are an EXHIBITION
track that can never blend into the real ranking. Every exclusion point is
proved directly:

  1. record_match_rating() refuses to move Elo on is_ai_opponent rows.
  2. AI matches never count toward the placement K-factor count.
  3. user_elo() ignores AI rows (even a newer AI row must not shadow a
     real match's rating).
  4. The /me record excludes AI matches.
  5. The leaderboard query source (users.rating) never changes after AI play.
  6. The simulated answers are scored by the SAME _score() path with
     negative marking (raw score < correct-count percent for imperfect runs).
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import (
    ArenaMatch, Base, GeneratedMock, MockAttempt, User, record_match_rating,
    user_elo,
)
from app.routers import arena


BOOKLET = (
    '[{"_id":1,"subject":"ریاضی","topic":"","text":"q1",'
    '"options":["a","b","c","d"],"answer":1,"explanation":""},'
    '{"_id":2,"subject":"ریاضی","topic":"","text":"q2",'
    '"options":["a","b","c","d"],"answer":2,"explanation":""},'
    '{"_id":3,"subject":"فیزیک","topic":"","text":"q3",'
    '"options":["a","b","c","d"],"answer":0,"explanation":""}]'
)


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


def _mk_mock(db, student_id):
    db.add(GeneratedMock(
        student_id=student_id, title="t", major="ریاضی فیزیک", grade="",
        duration_minutes=10, questions=BOOKLET, status="claimed",
    ))
    db.commit()
    return db.query(GeneratedMock).order_by(GeneratedMock.id.desc()).first()


class _Ctx:
    def __init__(self, user):
        self.id = user.id
        self.username = user.username


def test_sample_rival_answers_hits_accuracy_and_always_answers():
    questions = [
        {"_id": i, "answer": i % 4,
         "options": ["a", "b", "c", "d"], "text": "q", "subject": "s"}
        for i in range(1, 501)
    ]
    mock = GeneratedMock(questions=__import__("json").dumps(questions))
    answers = arena._sample_rival_answers(mock, accuracy=0.78)
    assert len(answers) == 500  # never blanks
    hits = sum(1 for i in range(1, 501) if answers[str(i)] == (i % 4))
    # Binomial(500, .78): mean 390, sd ~9.3 - 200 hits of margin is impossible
    # unless the sampler is broken.
    assert abs(hits - 390) < 60
    for i in range(1, 501):
        assert 0 <= answers[str(i)] <= 3


def test_ai_rival_submit_scores_identically_and_touches_no_elo(db):
    player = _mk_user(db, "09120000001")
    mock = _mk_mock(db, player.id)
    match = ArenaMatch(
        student_a_id=player.id,        student_b_id=0, mock_id=mock.id,
        status="pending", elo_a=1000, elo_b=1850,
        is_ai_opponent=True, ai_rival="top1000",
        ai_answers='{"1": 1, "2": 0, "3": 0}',  # 2 correct, 1 wrong
    )
    db.add(match)
    db.commit()

    res = arena.submit(
        match.id, arena.SubmitPayload(
            answers={"1": 1, "2": 2, "3": 0}, duration_seconds=60),
        current_user=_Ctx(player), db=db,
    )
    db.refresh(match)

    # Player went 3/3; rival 2/3 with one wrong. Negative marking:
    # player raw 3 -> 100%; rival raw 2 - 1/3 -> 55.6%.
    assert res["finished"] is True and res["ranked"] is False
    assert match.score_a == 100.0
    assert match.score_b == round(100 * (2 - 1 / 3) / 3, 1)
    assert match.delta_a == 0 and match.delta_b == 0
    assert match.status == "finished"
    assert match.winner_id == player.id

    # THE INVARIANT: user rating is untouched after AI play.
    assert user_elo(db, player.id) == 1000
    assert db.get(User, player.id).rating == 1000


def test_record_match_rating_guard_blocks_ai_rows_even_if_called(db):
    player = _mk_user(db, "09120000002")
    mock = _mk_mock(db, player.id)
    match = ArenaMatch(
        student_a_id=player.id,        student_b_id=0, mock_id=mock.id,
        status="finished", elo_a=1000, elo_b=1850, score_a=100.0, score_b=0.0,
        is_ai_opponent=True,
    )
    db.add(match)
    db.commit()

    # Direct call - the belt-and-suspenders guard inside the function.
    record_match_rating(match, db)
    assert match.delta_a == 0 and match.delta_b == 0
    assert db.get(User, player.id).rating == 1000


def test_ai_matches_never_count_toward_placement_k(db):
    player = _mk_user(db, "09120000003")
    other = _mk_user(db, "09120000004")
    # 10 finished AI exhibitions - more than the placement threshold.
    for _ in range(10):
        mock = _mk_mock(db, player.id)
        m = ArenaMatch(
            student_a_id=player.id,        student_b_id=0, mock_id=mock.id,
            status="finished", elo_a=1000, elo_b=1400,
            score_a=80.0, score_b=60.0, is_ai_opponent=True,
        )
        db.add(m)
    db.commit()

    # A REAL match's placement count must still be 0 -> K stays 48.
    real_mock = _mk_mock(db, player.id)
    real = ArenaMatch(
        student_a_id=player.id, student_b_id=other.id, mock_id=real_mock.id,
        status="pending", elo_a=1000, elo_b=1000,
        score_a=90.0, score_b=50.0,
    )
    db.add(real)
    db.commit()
    record_match_rating(real, db)
    # K=48: sa_n=0.643, ea=0.5 -> delta = round(48*0.143)=7 (not 32-based 5)
    assert real.delta_a == 7


def test_user_elo_ignores_newer_ai_row(db):
    player = _mk_user(db, "09120000005")
    other = _mk_user(db, "09120000006")
    mock = _mk_mock(db, player.id)
    real = ArenaMatch(
        student_a_id=player.id, student_b_id=other.id, mock_id=mock.id,
        status="finished", elo_a=1240, elo_b=1000,
        score_a=80.0, score_b=60.0,
    )
    db.add(real)
    db.commit()
    record_match_rating(real, db)
    db.refresh(real)
    assert user_elo(db, player.id) == real.elo_a

    # A NEWER AI-rival row (snapshot elo_a=1000 from a later join) must NOT
    # shadow the real rating.
    ai_mock = _mk_mock(db, player.id)
    db.add(ArenaMatch(
        student_a_id=player.id,        student_b_id=0, mock_id=ai_mock.id,
        status="pending", elo_a=1000, elo_b=1400, is_ai_opponent=True,
        created_at=real.created_at,
    ))
    db.commit()
    assert user_elo(db, player.id) == real.elo_a


def test_me_record_excludes_ai_matches(db):
    player = _mk_user(db, "09120000007")
    other = _mk_user(db, "09120000008")
    mock = _mk_mock(db, player.id)
    db.add(ArenaMatch(
        student_a_id=player.id, student_b_id=other.id, mock_id=mock.id,
        status="finished", elo_a=1000, elo_b=1000,
        score_a=90.0, score_b=40.0, winner_id=player.id,
    ))
    db.add(ArenaMatch(
        student_a_id=player.id,        student_b_id=0, mock_id=mock.id,
        status="finished", elo_a=1000, elo_b=1400,
        score_a=10.0, score_b=80.0, is_ai_opponent=True,
    ))
    db.commit()
    out = arena.me(current_user=_Ctx(player), db=db)
    assert out["matches"] == 1 and out["wins"] == 1 and out["losses"] == 0


def test_leaderboard_source_unchanged_after_ai_play(db):
    player = _mk_user(db, "09120000009")
    rival_beater = _mk_user(db, "09120000010")
    # rival_beater wins a REAL match -> enters the leaderboard via rating.
    m1 = _mk_mock(db, rival_beater.id)
    real = ArenaMatch(
        student_a_id=rival_beater.id, student_b_id=player.id,
        mock_id=m1.id, status="finished", elo_a=1000, elo_b=1000,
        score_a=95.0, score_b=10.0,
    )
    db.add(real)
    db.commit()
    record_match_rating(real, db)

    # player then crushes 10 AI rivals (would be huge Elo gains if blended).
    for _ in range(10):
        mock = _mk_mock(db, player.id)
        m = ArenaMatch(
            student_a_id=player.id,        student_b_id=0, mock_id=mock.id,
            status="finished", elo_a=1000, elo_b=1850,
            score_a=100.0, score_b=0.0, is_ai_opponent=True,
        )
        db.add(m)
    db.commit()
    record_match_rating(m, db)  # even called directly: guarded

    rows = db.execute(
        select(User.id, User.username, User.rating)
        .where(User.rating != 1000)
        .order_by(User.rating.desc())
    ).all()
    by_user = {uid: elo for uid, _u, elo in rows}
    # player LOST the one real match (dropped to real.elo_b) and must stay
    # exactly there despite crushing 10 AI rivals afterwards; rival_beater
    # keeps exactly the real win's rating.
    db.refresh(real)
    assert by_user[player.id] == real.elo_b
    assert by_user[rival_beater.id] == real.elo_a


def test_status_offers_ai_rival_only_after_threshold(db):
    player = _mk_user(db, "09120000011")
    from app.auth.database import ArenaQueueEntry
    from datetime import datetime, timedelta
    db.add(ArenaQueueEntry(student_id=player.id, elo=1000,
                           joined_at=datetime.utcnow() - timedelta(seconds=5)))
    db.commit()
    out = arena.status(current_user=_Ctx(player), db=db)
    assert out["state"] == "queued" and out["ai_offer"] is False

    db.query(ArenaQueueEntry).delete()
    db.add(ArenaQueueEntry(student_id=player.id, elo=1000,
                           joined_at=datetime.utcnow() - timedelta(seconds=25)))
    db.commit()
    out = arena.status(current_user=_Ctx(player), db=db)
    assert out["ai_offer"] is True
    assert len(out["ai_rivals"]) == 3


def test_ai_rival_match_creation_pools_booklet_and_leaves_queue(db):
    player = _mk_user(db, "09120000012")
    from app.auth.database import ArenaQueueEntry
    db.add(ArenaQueueEntry(student_id=player.id, elo=1000))
    db.commit()
    out = arena.create_ai_rival_match(
        arena.AiRivalPayload(rival="top5000", student={"major": "ریاضی فیزیک"}),
        current_user=_Ctx(player), db=db,
    )
    match = db.get(ArenaMatch, out["match_id"])
    assert match.is_ai_opponent is True
    assert match.ai_rival == "top5000"
    assert match.student_b_id == 0
    assert match.elo_b == 1400
    # Every booklet question gets a sampled answer (never blanks); the count
    # tracks the pooled booklet rather than a hardcoded size.
    booklet = __import__("json").loads(db.get(GeneratedMock, match.mock_id).questions)
    answers = __import__("json").loads(match.ai_answers)
    assert len(answers) == len(booklet) > 0
    assert set(answers) == {str(q["_id"]) for q in booklet}
    # Queue entry consumed.
    assert db.query(ArenaQueueEntry).count() == 0
    assert out["opponent_elo"] == 1400

    # Defense-in-depth: the endpoint's own guard rejects unknown levels even
    # if a payload slips past pydantic's pattern (model_construct skips it).
    with pytest.raises(arena.HTTPException) as e:
        arena.create_ai_rival_match(
            arena.AiRivalPayload.model_construct(rival="bogus"),
            current_user=_Ctx(player), db=db)
    assert e.value.status_code == 400
