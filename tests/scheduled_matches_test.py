"""Regressions for the scheduled-duel arena option.

Invariants under test:
  1. Creating an invite stores the kickoff in UTC and rejects bad times.
  2. A second open offer from the same host is refused (anti-spam).
  3. Acceptance books ONE ArenaMatch at status="scheduled", marks the invite
     accepted, and refuses a second acceptor (race safety).
  4. The list endpoint shows open offers with can_accept, plus my booked
     duels with countdowns; my own offer is not bookable by me.
  5. A scheduled match does NOT play early: submit/get_match before kickoff
     refuse, and /status does not report it as matched.
  6. Activation is lazy: at/after starts_at, /status flips the row to
     "pending" and reports state=matched for both players.
  7. Elo bookkeeping ignores scheduled rows: user_elo keeps the rating of a
     real finished match played after booking one.
  8. Cancellation: the host can withdraw an open offer; the acceptor can
     back out before kickoff (offer re-opens); nobody can cancel after
     kickoff; a stranger cannot cancel at all.
  9. Refused accepts REFUND the acceptor's arena_join unit (only a real
     booking costs), and /scheduled reports the remaining daily quota.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import (
    ArenaMatch, ArenaScheduledInvite, Base, GeneratedMock, User, user_elo,
)
from app.routers import arena
from app.auth.limits import _counters as _quota_counters


BOOKLET = (
    '[{"_id":1,"subject":"ریاضی","topic":"","text":"q1",'
    '"options":["a","b","c","d"],"answer":1,"explanation":""}]'
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
    # The daily arena_join counter is process-global; accept paths consume
    # it, so a clean slate per test keeps the suite independent.
    _quota_counters._counts.clear()
    yield session
    session.close()


def _mk_user(db, username, rating=1000):
    u = User(username=username, hashed_password="x", rating=rating)
    db.add(u)
    db.commit()
    return u


def _ctx(user):
    return SimpleNamespace(id=user.id, username=user.username)


def _future(hours=2):
    return (datetime.utcnow() + timedelta(hours=hours)).isoformat()


def test_create_invite_stores_utc_kickoff_and_validates(db):
    host = _mk_user(db, "09120000001")
    view = arena.create_scheduled(
        arena.ScheduleInvitePayload(starts_at=_future(3)),
        current_user=_ctx(host), db=db,
    )
    assert view["is_mine"] is True
    row = db.query(ArenaScheduledInvite).one()
    assert row.starts_at > datetime.utcnow()
    assert row.accepted_by is None

    with pytest.raises(HTTPException) as err:
        arena.create_scheduled(
            arena.ScheduleInvitePayload(starts_at="not-a-date"),
            current_user=_ctx(host), db=db,
        )
    assert err.value.status_code == 422
    # A failed create must not leave a second row.
    assert db.query(ArenaScheduledInvite).count() == 1


def test_second_open_invite_from_same_host_refused(db):
    host = _mk_user(db, "09120000001")
    arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                           current_user=_ctx(host), db=db)
    with pytest.raises(HTTPException) as err:
        arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(5)),
                               current_user=_ctx(host), db=db)
    assert err.value.status_code == 409


def test_accept_books_one_scheduled_match_and_blocks_second_acceptor(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    other = _mk_user(db, "09120000003")
    view = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                  current_user=_ctx(host), db=db)

    res = arena.accept_scheduled(
        view["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
        current_user=_ctx(rival), db=db,
    )
    match = db.get(ArenaMatch, res["match_id"])
    assert match.status == "scheduled"
    assert match.student_a_id == host.id and match.student_b_id == rival.id
    assert match.starts_at is not None
    assert db.query(ArenaScheduledInvite).one().accepted_by == rival.id

    # A second acceptor must be refused (409) and must not create a match.
    with pytest.raises(HTTPException) as err:
        arena.accept_scheduled(
            view["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
            current_user=_ctx(other), db=db,
        )
    assert err.value.status_code == 409
    assert db.query(ArenaMatch).count() == 1

    # The host cannot book their own offer.
    view2 = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(4)),
                                   current_user=_ctx(other), db=db)
    with pytest.raises(HTTPException) as err:
        arena.accept_scheduled(view2["id"], None, current_user=_ctx(other), db=db)
    assert err.value.status_code == 400


def test_list_shows_open_offers_and_booked_duels(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    far = _mk_user(db, "09120000003")
    # user_elo() reads Elo snapshots off FINISHED matches (never User.rating),
    # so make `far` genuinely 700 points above the host via a finished row.
    book = GeneratedMock(student_id=far.id, title="t", major="ریاضی فیزیک",
                         grade="", duration_minutes=10, questions=BOOKLET,
                         status="claimed")
    db.add(book)
    db.commit()
    db.add(ArenaMatch(student_a_id=far.id, student_b_id=host.id,
                      mock_id=book.id, status="finished",
                      elo_a=1700, elo_b=1000, score_a=90.0, score_b=10.0,
                      delta_a=12, delta_b=-12))
    db.commit()
    invite = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                    current_user=_ctx(host), db=db)

    listing = arena.list_scheduled(current_user=_ctx(rival), db=db)
    assert len(listing["open"]) == 1
    entry = listing["open"][0]
    assert entry["host"] == host.username and entry["can_accept"] is True
    assert entry["seconds_until"] > 0

    listing_far = arena.list_scheduled(current_user=_ctx(far), db=db)
    assert listing_far["open"][0]["can_accept"] is False

    # Own invites are never bookable by the host.
    mine = arena.list_scheduled(current_user=_ctx(host), db=db)
    assert mine["open"][0]["is_mine"] is True
    assert mine["open"][0]["can_accept"] is False

    arena.accept_scheduled(invite["id"],
                           arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
                           current_user=_ctx(rival), db=db)
    booked = arena.list_scheduled(current_user=_ctx(rival), db=db)
    assert listing["open"] and len(booked["mine"]) == 1
    row = booked["mine"][0]
    assert row["status"] == "scheduled" and row["you_booked"] is True
    assert row["opponent"] == host.username
    # Booked duels leave the open list.
    after = arena.list_scheduled(current_user=_ctx(rival), db=db)
    assert all(o["id"] != invite["id"] for o in after["open"])


def test_scheduled_match_cannot_play_early(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    invite = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                    current_user=_ctx(host), db=db)
    res = arena.accept_scheduled(invite["id"],
                                 arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
                                 current_user=_ctx(rival), db=db)
    mock = GeneratedMock(
        student_id=host.id, title="t", major="ریاضی فیزیک", grade="",
        duration_minutes=10, questions=BOOKLET, status="claimed",
    )
    db.add(mock)
    db.commit()
    match = db.get(ArenaMatch, res["match_id"])
    match.mock_id = mock.id
    db.commit()

    # Submit before kickoff is refused.
    with pytest.raises(HTTPException) as err:
        arena.submit(res["match_id"], arena.SubmitPayload(answers={"1": 1}),
                     current_user=_ctx(rival), db=db)
    assert err.value.status_code == 400

    # /status does NOT report the future match as playable.
    state = arena.status(current_user=_ctx(rival), db=db)
    assert state["state"] == "idle"


def test_activation_is_lazy_at_kickoff_for_both_players(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    invite = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(1)),
                                    current_user=_ctx(host), db=db)
    res = arena.accept_scheduled(invite["id"],
                                 arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
                                 current_user=_ctx(rival), db=db)
    match = db.get(ArenaMatch, res["match_id"])
    # Simulate the clock reaching the kickoff.
    match.starts_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    for user in (host, rival):
        state = arena.status(current_user=_ctx(user), db=db)
        assert state["state"] == "matched", user.username
        assert state["match_id"] == res["match_id"]
    db.refresh(match)
    assert match.status == "pending"


def test_scheduled_rows_do_not_shadow_fresh_elo(db):
    host = _mk_user(db, "09120000001", rating=1000)
    invite = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                    current_user=_ctx(host), db=db)
    rival = _mk_user(db, "09120000002")
    arena.accept_scheduled(invite["id"],
                           arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
                           current_user=_ctx(rival), db=db)
    # The host plays (and finishes) a NORMAL ranked duel afterwards.
    mock = GeneratedMock(
        student_id=host.id, title="t", major="ریاضی فیزیک", grade="",
        duration_minutes=10, questions=BOOKLET, status="claimed",
    )
    db.add(mock)
    db.commit()
    live = ArenaMatch(student_a_id=host.id, student_b_id=rival.id,
                      mock_id=mock.id, status="pending",
                      elo_a=1000, elo_b=1000)
    db.add(live)
    db.commit()
    live.score_a, live.score_b = 80.0, 20.0
    from app.auth.database import record_match_rating
    record_match_rating(live, db)
    live.status = "finished"
    db.commit()
    assert user_elo(db, host.id) > 1000

    # The still-scheduled row (older) must not shadow the fresh rating.
    assert user_elo(db, host.id) == db.get(User, host.id).rating


def test_cancellation_rules(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    stranger = _mk_user(db, "09120000003")
    invite = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                    current_user=_ctx(host), db=db)
    row = lambda: db.get(ArenaScheduledInvite, invite["id"])

    # A stranger can neither cancel nor accept-then-... well, not cancel.
    with pytest.raises(HTTPException) as err:
        arena.cancel_scheduled(invite["id"], current_user=_ctx(stranger), db=db)
    assert err.value.status_code == 403

    # Acceptor books, then backs out: the offer re-opens.
    booked = arena.accept_scheduled(
        invite["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
        current_user=_ctx(rival), db=db)
    booked_match_id = booked["match_id"]
    arena.cancel_scheduled(invite["id"], current_user=_ctx(rival), db=db)
    assert row().accepted_by is None and row().cancelled_at is None
    # The booked match itself is dead, but the offer is bookable again.
    assert db.get(ArenaMatch, booked_match_id).status == "cancelled"

    # Host withdraws the open offer entirely.
    arena.cancel_scheduled(invite["id"], current_user=_ctx(host), db=db)
    assert row().cancelled_at is not None

    # A kickoff-passed booked duel cannot be cancelled anymore.
    invite2 = arena.create_scheduled(
        arena.ScheduleInvitePayload(starts_at=_future(1)),
        current_user=_ctx(host), db=db)
    booked2 = arena.accept_scheduled(
        invite2["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
        current_user=_ctx(rival), db=db)
    match = db.get(ArenaMatch, booked2["match_id"])
    match.starts_at = datetime.utcnow() - timedelta(seconds=5)
    db.commit()
    with pytest.raises(HTTPException) as err:
        arena.cancel_scheduled(invite2["id"], current_user=_ctx(host), db=db)
    assert err.value.status_code == 409


def test_failed_accept_does_not_burn_quota(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    other = _mk_user(db, "09120000003")
    view = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                  current_user=_ctx(host), db=db)

    def used(u):
        return _quota_counters._counts.get(u.id, {}).get("arena_join", 0)

    # Booking your own offer is refused and must stay free.
    with pytest.raises(HTTPException) as err:
        arena.accept_scheduled(view["id"], None, current_user=_ctx(host), db=db)
    assert err.value.status_code == 400
    assert used(host) == 0

    # A real booking consumes exactly one unit.
    arena.accept_scheduled(
        view["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
        current_user=_ctx(rival), db=db)
    assert used(rival) == 1

    # The lost race (someone already booked) is refunded too.
    with pytest.raises(HTTPException) as err:
        arena.accept_scheduled(view["id"], None, current_user=_ctx(other), db=db)
    assert err.value.status_code == 409
    assert used(other) == 0


def test_scheduled_list_reports_remaining_quota(db):
    host = _mk_user(db, "09120000001")
    rival = _mk_user(db, "09120000002")
    listing = arena.list_scheduled(current_user=_ctx(rival), db=db)
    assert listing["quota"]["remaining"] == listing["quota"]["limit"]

    view = arena.create_scheduled(arena.ScheduleInvitePayload(starts_at=_future(2)),
                                  current_user=_ctx(host), db=db)
    arena.accept_scheduled(
        view["id"], arena.JoinPayload(student={"major": "ریاضی فیزیک"}),
        current_user=_ctx(rival), db=db)
    listing = arena.list_scheduled(current_user=_ctx(rival), db=db)
    assert listing["quota"]["used"] == 1
    assert listing["quota"]["remaining"] == listing["quota"]["limit"] - 1
