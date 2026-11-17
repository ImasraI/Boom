"""Tournament fairness, deadline, ownership and lifecycle regressions; no models/SMS."""
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.database import Base, BankQuestion, StudentProfile, User
from app.auth.deps import get_current_user, get_db
from app.routers import tournaments
from app.tournaments import engine, service
from app.tournaments.models import TournamentEvent


BASE = datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def db():
    db_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as db:
        for i in list(range(1, 33)) + [99]:
            db.add(User(id=i, username=f"0912000{i:04}", hashed_password="synthetic", is_admin=i == 99))
            db.add(StudentProfile(user_id=i, name="09129999999" if i == 1 else f"Student {i}",
                                  major="ریاضی فیزیک", grade="دوازدهم"))
        for i in range(1, 201):
            db.add(BankQuestion(id=i, fingerprint=f"tournament-fixture-{i}", owner_id=0,
                               major="ریاضی فیزیک", grade="دوازدهم", subject="ریاضی", topic="تابع",
                               verified=True, status="active", content=json.dumps({
                                   "text": f"Synthetic question {i}", "options": ["A", "B", "C", "D"],
                                   "answer": 0, "explanation": "PRIVATE answer explanation"})))
        db.commit()
        yield db
    db_engine.dispose()


@pytest.fixture
def clock(monkeypatch):
    clock = [BASE]
    monkeypatch.setattr(service, "now_utc", lambda: clock[0])
    return clock


@pytest.fixture
def client(db, clock):
    app = FastAPI()
    app.include_router(tournaments.router)
    app.dependency_overrides[get_db] = lambda: db

    def user(x_test_user: int | None = Header(default=None)):
        actor = db.get(User, x_test_user) if x_test_user else None
        if actor is None:
            raise HTTPException(401, "test login required")
        return actor

    app.dependency_overrides[get_current_user] = user
    with TestClient(app) as client:
        yield client


def config(players=8, rounds=2, playoff=4):
    slots = [f"league-{i + 1}" for i in range(rounds)] + (
        ["quarterfinal"] if playoff == 8 else []) + ["semifinal", "final", "third_place"]
    return tournaments.EventConfig(title="Synthetic tournament", major="ریاضی فیزیک", grade="دوازدهم",
          capacity=32, league_rounds=rounds, playoff_size=playoff, starts_at=BASE + timedelta(days=1),
          participant_ids=list(range(1, players + 1)), packets={key: [2 * i + 1, 2 * i + 2] for i, key in enumerate(slots)}).model_dump(mode="json")


def draft(db, **kw):
    return service.build_draft(db, config(**kw))


def active(db, **kw):
    state = draft(db, **kw)
    service.activate(state, db, BASE)
    return state


def store(db, state):
    row = TournamentEvent(data=json.dumps(state), created_by=99)
    db.add(row)
    db.commit()
    return row.id


def answer(rnd, correct=True):
    return {q["id"]: 0 if correct else 1 for q in rnd["questions"]}


def play(state, rnd, match, *, a=True, b=False):
    now = service.instant(match.get("starts_at") or rnd["starts_at"]) + timedelta(seconds=1)
    for user_id, correct in ((match["a"], a), (match["b"], b)):
        if user_id is not None:
            service.start_match(state, now, 1, match["id"], user_id)
            service.submit_match(state, now + timedelta(seconds=1), match["id"], user_id, answer(rnd, correct))
    return now + timedelta(seconds=2)


def finish_league(state):
    # Fixed differing per-player correctness creates wins/draws without ID
    # being used as a qualifying tie-break; tests can explicitly handle ties.
    for rnd in [r for r in state["rounds"] if r["stage"] == "league"]:
        for match in list(rnd["matches"]):
            when = play(state, rnd, match, a=True, b=False)
        service.reconcile(state, when)


def test_signed_in_event_list_does_not_create_demo_players_or_event(client, db):
    assert client.get("/api/tournaments").status_code == 401
    assert client.get("/api/tournaments", headers={"X-Test-User": "1"}).json() == {"items": []}
    assert db.query(TournamentEvent).count() == 0


def test_admin_configuration_is_not_student_registration(client, db):
    body = config()
    assert client.post("/api/tournaments/admin/events", json=body).status_code == 401
    assert client.post("/api/tournaments/admin/events", json=body, headers={"X-Test-User": "1"}).status_code == 403
    response = client.post("/api/tournaments/admin/events", json=body, headers={"X-Test-User": "99"})
    assert response.status_code == 201
    assert response.json()["registration_status"] == "closed"
    assert client.post(f"/api/tournaments/{response.json()['id']}/register", headers={"X-Test-User": "1"}).status_code == 404


def test_public_boards_contain_no_packets_attempts_or_phone_names(client, db):
    event_id = store(db, active(db))
    assert client.get(f"/api/tournaments/{event_id}").status_code == 401
    body = client.get(f"/api/tournaments/{event_id}", headers={"X-Test-User": "20"}).json()
    raw = json.dumps(body)
    assert "answer" not in raw and "questions" not in raw and "0912" not in raw and "PRIVATE" not in raw
    assert body["standings"][0]["name"] == "بازیکن 1"
    assert body["rounds"][0]["question_count"] == 2
    assert client.get(f"/api/tournaments/{event_id}/me").status_code == 401
    outsider = client.get(f"/api/tournaments/{event_id}/me", headers={"X-Test-User": "20"}).json()
    assert outsider == {"player_id": None, "matches": []}


@pytest.mark.parametrize("change", ["private", "unverified", "quarantined", "grade", "major"])
def test_packets_require_shared_active_verified_compatible_stock(db, change):
    row = db.get(BankQuestion, 1)
    if change == "private": row.owner_id = 1
    if change == "unverified": row.verified = False
    if change == "quarantined": row.status = "reported"
    if change == "grade": row.grade = "یازدهم"
    if change == "major": row.major = "علوم انسانی"
    db.commit()
    with pytest.raises(HTTPException):
        draft(db)


def test_activation_revalidates_stock_then_freezes_packet(db):
    state = draft(db)
    row = db.get(BankQuestion, 1)
    row.verified = False
    db.commit()
    with pytest.raises(HTTPException):
        service.activate(state, db, BASE)
    row.verified = True
    db.commit()
    service.activate(state, db, BASE)
    row.content = json.dumps({"text": "changed later", "options": ["A"] * 4, "answer": 1})
    db.commit()
    assert state["rounds"][0]["questions"][0]["text"] == "Synthetic question 1"
    assert state["rounds"][0]["questions"][0]["answer"] == 0


def test_no_duplicate_players_questions_or_unready_activation(db):
    body = config()
    body["participant_ids"].append(1)
    with pytest.raises(HTTPException): service.build_draft(db, body)
    body = config()
    body["packets"]["final"] = body["packets"]["league-1"]
    with pytest.raises(HTTPException): service.build_draft(db, body)
    state = draft(db)
    state["rounds"][-1]["questions"] = []
    with pytest.raises(HTTPException): service.activate(state, db, BASE)
    state = draft(db, players=7)
    with pytest.raises(HTTPException): service.activate(state, db, BASE)


def test_schedule_requires_timezone_nonoverlap_and_usable_attendance_window(db):
    body = config()
    body["duration_minutes"] = 90
    body["round_interval_hours"] = 1
    with pytest.raises(HTTPException): service.build_draft(db, body)
    body = config()
    body["duration_minutes"] = 2
    with pytest.raises(HTTPException): service.build_draft(db, body)
    with pytest.raises(ValueError): tournaments.EventConfig(**{**config(), "starts_at": "2030-01-01T20:00:00"})


def test_start_is_time_gated_owned_and_reuses_immutable_attempt(client, db, clock):
    state = active(db)
    event_id = store(db, state)
    match = state["rounds"][0]["matches"][0]
    path = f"/api/tournaments/{event_id}/matches/{match['id']}/start"
    assert client.post(path, headers={"X-Test-User": "1"}).status_code == 409
    clock[0] = BASE + timedelta(days=1, seconds=2)
    assert client.post(path, headers={"X-Test-User": "20"}).status_code == 403
    first = client.post(path, headers={"X-Test-User": str(match["a"])}).json()
    clock[0] += timedelta(seconds=5)
    second = client.post(path, headers={"X-Test-User": str(match["a"])}).json()
    assert first["started_at"] == second["started_at"]
    assert first["deadline_at"] == second["deadline_at"]
    assert first["questions"] == second["questions"]
    assert all("answer" not in q and "explanation" not in q for q in first["questions"])


def test_one_player_submission_does_not_finalize_or_publish_score(db):
    state = active(db)
    rnd = state["rounds"][0]
    match = rnd["matches"][0]
    now = service.instant(rnd["starts_at"]) + timedelta(seconds=1)
    service.start_match(state, now, 1, match["id"], match["a"])
    service.submit_match(state, now, match["id"], match["a"], answer(rnd))
    service.reconcile(state, now)
    assert match["status"] == "live"
    visible = service.public_event(1, state)["rounds"][0]["matches"][0]
    assert visible["score_a"] is None and visible["winner_id"] is None
    assert not state["rounds"][1]["matches"]


@pytest.mark.parametrize("payload", [{"1": True}, {"1": 4}, {"99999": 0}])
def test_submit_rejects_bool_out_of_range_and_unknown_questions(client, db, clock, payload):
    state = active(db)
    event_id = store(db, state)
    match = state["rounds"][0]["matches"][0]
    clock[0] = BASE + timedelta(days=1, seconds=1)
    prefix = f"/api/tournaments/{event_id}/matches/{match['id']}"
    client.post(prefix + "/start", headers={"X-Test-User": str(match["a"])})
    assert client.post(prefix + "/submit", json={"answers": payload}, headers={"X-Test-User": str(match["a"])}).status_code == 422


def test_terminal_submission_is_idempotent_and_normal_rating_unchanged(db):
    state = active(db)
    rnd, match = state["rounds"][0], state["rounds"][0]["matches"][0]
    when = play(state, rnd, match)
    first = service.submit_match(state, when, match["id"], match["a"], answer(rnd, True))
    again = service.submit_match(state, when, match["id"], match["a"], answer(rnd, False))
    assert first == again
    assert engine.standings(state)[0]["points"] == 3
    assert db.get(User, match["a"]).rating == 1000


def test_autosave_resume_rejects_stale_revision_and_timeout_uses_saved_answers(client, db, clock):
    state = active(db)
    event_id = store(db, state)
    rnd, match = state["rounds"][0], state["rounds"][0]["matches"][0]
    path = f"/api/tournaments/{event_id}/matches/{match['id']}"
    headers = {"X-Test-User": str(match["a"])}
    clock[0] = service.instant(rnd["starts_at"]) + timedelta(seconds=1)
    client.post(path + "/start", headers=headers)
    saved = {"answers": answer(rnd), "revision": 2}
    assert client.put(path + "/answers", headers=headers, json=saved).status_code == 200
    assert client.put(path + "/answers", headers=headers, json=saved).status_code == 200
    assert client.put(path + "/answers", headers=headers, json={"answers": {}, "revision": 1}).status_code == 409
    assert client.put(path + "/answers", headers=headers, json={"answers": {}, "revision": 2}).status_code == 409
    resume = client.post(path + "/start", headers=headers).json()
    assert resume["saved_answers"] == answer(rnd) and resume["answers_revision"] == 2
    clock[0] = service.instant(rnd["ends_at"]) + timedelta(seconds=1)
    result = client.post(path + "/submit", headers=headers, json={"answers": answer(rnd, False)}).json()
    assert result["submitted"] and result["score"] == 100
    assert client.put(path + "/answers", headers=headers, json={"answers": {}, "revision": 3}).status_code == 409


def test_negative_scoring_attendee_beats_no_show_and_double_absence_gives_no_points(db):
    state = active(db)
    rnd = state["rounds"][0]
    first, absent = rnd["matches"][:2]
    now = service.instant(rnd["starts_at"]) + timedelta(seconds=1)
    service.start_match(state, now, 1, first["id"], first["a"])
    service.submit_match(state, now, first["id"], first["a"], answer(rnd, False))
    service.reconcile(state, service.instant(rnd["ends_at"]))
    assert first["winner_id"] == first["a"] and first["score_a"] < 0 and first["score_b"] is None
    assert absent["double_forfeit"] and absent["winner_id"] is None
    table = {row["player_id"]: row for row in engine.standings(state)}
    assert table[first["a"]]["points"] == 3
    assert table[absent["a"]]["points"] == table[absent["b"]]["points"] == 0


def test_five_round_swiss_pairs_all_32_once_per_round_with_no_rematches(db):
    state = active(db, players=32, rounds=5, playoff=8)
    seen = set()
    for rnd in [r for r in state["rounds"] if r["stage"] == "league"]:
        participants = []
        for match in rnd["matches"]:
            pair = frozenset((match["a"], match["b"]))
            assert pair not in seen
            seen.add(pair)
            participants.extend(pair)
            now = play(state, rnd, match, a=match["a"] % 3 == 0, b=match["b"] % 3 == 0)
        assert len(participants) == len(set(participants)) == 32
        service.reconcile(state, now)
    assert len(seen) == 80


def test_eight_seed_bracket_has_expected_neighbors():
    assert engine.knockout_pairs(list(range(1, 9))) == [(1, 8), (4, 5), (2, 7), (3, 6)]


def test_complete_cutoff_tie_does_not_qualify_by_user_id(db):
    state = active(db, rounds=1)
    rnd = state["rounds"][0]
    for match in rnd["matches"]:
        now = play(state, rnd, match, a=True, b=True)
    service.reconcile(state, now)
    assert state["status"] == "awaiting_tiebreak"
    assert len(engine.cutoff_ties(state)) == 8
    assert not next(r for r in state["rounds"] if r["stage"] == "semifinal")["matches"]


def test_cutoff_uses_fresh_common_exam_and_prepares_only_real_qualifiers(db):
    state = active(db, rounds=1)
    for match in state["rounds"][0]["matches"]:
        now = play(state, state["rounds"][0], match, a=True, b=True)
    service.reconcile(state, now)
    payload = {"bank_question_ids": [101, 102], "starts_at": service.iso(now + timedelta(hours=1)), "duration_minutes": 10}
    service.prepare_tiebreak(db, state, payload, now)
    tb = state["rounds"][-1]
    for match in tb["matches"]:
        at = service.instant(tb["starts_at"]) + timedelta(seconds=1)
        service.start_match(state, at, 1, match["id"], match["a"])
        service.submit_match(state, at, match["id"], match["a"], answer(tb, match["a"] <= 4))
    service.reconcile(state, at)
    semi = next(r for r in state["rounds"] if r["stage"] == "semifinal")
    assert state["status"] == "knockout"
    assert {m[side] for m in semi["matches"] for side in ("a", "b")} == {1, 2, 3, 4}


def test_knockout_draw_waits_for_new_questions_and_late_tiebreak_shifts_downstream(db):
    state = active(db, players=8, rounds=1, playoff=8)
    league = state["rounds"][0]
    for match in league["matches"]:
        now = play(state, league, match)
    service.reconcile(state, now)
    quarter = next(r for r in state["rounds"] if r["stage"] == "quarterfinal")
    for match in quarter["matches"]:
        now = play(state, quarter, match, a=True, b=match["slot"] == 1)
    service.reconcile(state, now)
    tied = quarter["matches"][0]
    assert tied["status"] == "awaiting_tiebreak"
    with pytest.raises(HTTPException):
        service.prepare_tiebreak(db, state, {"match_id": tied["id"], "bank_question_ids": [1, 2],
                "starts_at": service.iso(now + timedelta(days=5)), "duration_minutes": 10}, now)
    tb_start = now + timedelta(days=5)
    service.prepare_tiebreak(db, state, {"match_id": tied["id"], "bank_question_ids": [101, 102],
                "starts_at": service.iso(tb_start), "duration_minutes": 10}, now)
    for player, correct in ((tied["a"], True), (tied["b"], False)):
        service.start_match(state, tb_start, 1, tied["id"], player)
        service.submit_match(state, tb_start, tied["id"], player, {q["id"]: 0 if correct else 1 for q in tied["questions"]})
    service.reconcile(state, tb_start)
    semi = next(r for r in state["rounds"] if r["stage"] == "semifinal")
    assert len(semi["matches"]) == 2
    assert service.instant(semi["starts_at"]) > tb_start
    assert all(m["status"] == "scheduled" for m in semi["matches"])


def test_standings_do_not_collapse_distinct_exact_scores_after_rounding(db):
    state = active(db, rounds=1)
    rnd = state["rounds"][0]
    # A 99-question packet and a 100-question packet can round distinct values
    # alike; exact Fraction ranking remains different before presentation.
    first, second = rnd["matches"][:2]
    for match in (first, second):
        match.update(status="completed", winner_id=match["a"], score_a=1.0, score_b=0)
        match["questions"] = [rnd["questions"][0]] * (99 if match is first else 100)
        match["attempts"] = {str(match["a"]): {"score": {"units": 3}}, str(match["b"]): {"score": {"units": 0}}}
    rows = {row["player_id"]: row for row in engine.standings(state)}
    assert rows[first["a"]]["_key"] != rows[second["a"]]["_key"]


def test_knockout_progression_completes_final_and_bronze(db):
    state = active(db, rounds=1, playoff=8)
    for stage in ("league", "quarterfinal", "semifinal", "final", "third_place"):
        rnd = next(r for r in state["rounds"] if r["stage"] == stage)
        for match in rnd["matches"]:
            now = play(state, rnd, match)
        service.reconcile(state, now)
    assert state["status"] == "completed"
    assert len(next(r for r in state["rounds"] if r["stage"] == "final")["matches"]) == 1
    assert len(next(r for r in state["rounds"] if r["stage"] == "third_place")["matches"]) == 1


def test_double_absence_knockout_can_be_replayed_without_arbitrary_winner(db):
    state = active(db, rounds=1, playoff=8)
    league = state["rounds"][0]
    for match in league["matches"]:
        now = play(state, league, match)
    service.reconcile(state, now)
    rnd = next(r for r in state["rounds"] if r["stage"] == "quarterfinal")
    for match in rnd["matches"][1:]:
        play(state, rnd, match)
    after = service.instant(rnd["ends_at"]) + timedelta(seconds=1)
    service.reconcile(state, after)
    missing = rnd["matches"][0]
    assert missing["double_forfeit"] and missing["winner_id"] is None
    assert state["status"] == "awaiting_tiebreak"
    service.prepare_tiebreak(db, state, {"match_id": missing["id"], "bank_question_ids": [101, 102],
            "starts_at": service.iso(after + timedelta(days=1)), "duration_minutes": 10}, after)
    assert missing["status"] == "scheduled" and missing["winner_id"] is None
    assert not missing["double_forfeit"]


def test_simultaneous_starts_and_repeated_submissions_do_not_lose_attempts(db, clock, tmp_path):
    state = active(db)
    match = state["rounds"][0]["matches"][0]
    clock[0] = service.instant(state["rounds"][0]["starts_at"]) + timedelta(seconds=1)
    file_engine = create_engine("sqlite:///" + (tmp_path / "cas.db").as_posix(),
                                connect_args={"check_same_thread": False, "timeout": 10})
    Base.metadata.create_all(file_engine)
    with Session(file_engine) as session:
        event_id = store(session, state)

    def start(user_id):
        with Session(file_engine) as session:
            return service.mutate(session, event_id, lambda state, now: service.start_match(state, now, event_id, match["id"], user_id))[1]

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(start, [match["a"], match["b"], match["a"], match["b"]]))
    assert len({r["deadline_at"] for r in responses}) == 1
    with Session(file_engine) as session:
        saved = json.loads(session.get(TournamentEvent, event_id).data)
        assert len(saved["rounds"][0]["matches"][0]["attempts"]) == 2

    def submit(user_id):
        with Session(file_engine) as session:
            return service.mutate(session, event_id, lambda state, now: service.submit_match(
                state, now, match["id"], user_id, answer(state["rounds"][0], user_id == match["a"])))[1]

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(submit, [match["a"], match["b"], match["a"], match["b"]]))
    with Session(file_engine) as session:
        saved = json.loads(session.get(TournamentEvent, event_id).data)
        finished = saved["rounds"][0]["matches"][0]
        assert finished["status"] == "completed" and finished["winner_id"] == match["a"]
        assert sum(row["points"] for row in engine.standings(saved)) == 3
    file_engine.dispose()


def test_account_wipe_anonymizes_results_erases_private_answers_and_removes_old_access(db):
    state = active(db)
    rnd = state["rounds"][0]
    played, live = rnd["matches"][:2]
    now = play(state, rnd, played)
    service.start_match(state, now, 1, live["id"], live["a"])
    service.save_answers(state, now, live["id"], live["a"], answer(rnd), 1)
    event_id = store(db, state)
    assert service.anonymize_participant(db, played["b"]) == 1
    assert service.anonymize_participant(db, live["a"]) == 1
    db.commit()
    saved = json.loads(db.get(TournamentEvent, event_id).data)
    assert all(p["id"] not in (played["b"], live["a"]) for p in saved["players"])
    assert len([p for p in saved["players"] if p["name"] == "بازیکن حذف‌شده"]) == 2
    completed = saved["rounds"][0]["matches"][0]
    old_attempt = completed["attempts"][str(completed["b"])]
    assert "answers" not in old_attempt and old_attempt["score"]["units"] < 0
    assert str(saved["rounds"][0]["matches"][1]["a"]) not in saved["rounds"][0]["matches"][1]["attempts"]
    # Even if a new account later receives the same numeric account ID, it
    # sees neither the old private schedule nor its question session.
    assert service.my_matches(event_id, saved, played["b"])["player_id"] is None
    with pytest.raises(HTTPException):
        service.start_match(saved, now, event_id, played["id"], played["b"])


def test_tournament_anonymization_obeys_callers_rollback(db):
    event_id = store(db, active(db))
    assert service.anonymize_participant(db, 2) == 1
    db.rollback()
    saved = json.loads(db.get(TournamentEvent, event_id).data)
    assert next(p for p in saved["players"] if p["id"] == 2)["name"] == "Student 2"


def test_activation_rejects_round_counts_that_can_exhaust_legal_pairings(db):
    state = service.build_draft(db, config(players=8, rounds=6))
    with pytest.raises(HTTPException) as failure:
        service.activate(state, db, BASE)
    assert failure.value.status_code == 409
    assert "نصف شرکت‌کنندگان" in failure.value.detail


def test_full_account_wipe_calls_tournament_cleanup(db, monkeypatch, tmp_path):
    import sys
    from types import ModuleType, SimpleNamespace
    from app.routers import admin

    # The account-wipe flow's external vector/file stores are isolated, as in
    # wipe_user_data_test. Exercise its real SQL deletes and tournament hook.
    vector = ModuleType("app.rag.vector_store")
    store_stub = SimpleNamespace(collection=SimpleNamespace(delete=lambda **kwargs: None))
    for name in ("get_vector_store", "get_image_vector_store", "get_question_vector_store"):
        setattr(vector, name, lambda: store_stub)
    hybrid = ModuleType("app.rag.hybrid_search")
    hybrid.get_hybrid_search = lambda: SimpleNamespace(refresh=lambda user_id: None)
    monkeypatch.setitem(sys.modules, "app.rag.vector_store", vector)
    monkeypatch.setitem(sys.modules, "app.rag.hybrid_search", hybrid)
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(
        UPLOAD_DIR=str(tmp_path / "uploads"), IMAGES_DIR=str(tmp_path / "images")))
    event_id = store(db, active(db))
    counts = admin._wipe_user_data(2, None, db)
    assert counts["tournament_entries"] == 1
    assert db.get(User, 2) is None
    saved = json.loads(db.get(TournamentEvent, event_id).data)
    assert not any(player["id"] == 2 for player in saved["players"])
    assert any(player["name"] == "بازیکن حذف‌شده" for player in saved["players"])


def test_swiss_refines_avoidable_score_gaps_without_rematching():
    previous = [
        ([(1, 5), (3, 4), (2, 6), (7, 8)], [None, 4, 6, None]),
        ([(1, 6), (2, 7), (3, 8), (4, 5)], [1, 7, 3, 5]),
        ([(1, 7), (2, 8), (3, 5), (4, 6)], [7, 2, 5, 4]),
    ]
    state = {"players": [{"id": i, "name": f"Student {i}"} for i in range(1, 9)],
             "rounds": [], "playoff_size": 4}
    already_met = set()
    for pairs, winners in previous:
        rnd = {"stage": "league", "questions": [{"id": "q", "answer": 0}], "matches": []}
        for (a, b), winner in zip(pairs, winners):
            already_met.add(frozenset((a, b)))
            rnd["matches"].append({
                "a": a, "b": b, "status": "completed", "winner_id": winner,
                "attempts": {str(player): {"score": {"units": 0 if winner is None else 3 if player == winner else -1}}
                             for player in (a, b)},
            })
        state["rounds"].append(rnd)

    points = {row["player_id"]: row["points"] for row in engine.standings(state)}
    assert points == {5: 7, 7: 7, 4: 6, 1: 4, 3: 3, 6: 3, 2: 3, 8: 1}
    pairs = engine.swiss_pairs(state)
    assert pairs == engine.swiss_pairs(deepcopy(state))
    assert sorted(player for pair in pairs for player in pair) == list(range(1, 9))
    assert all(frozenset(pair) not in already_met for pair in pairs)
    # The first complete legal matching used to pair 6 points against 1 point,
    # despite a two-pair swap allowing every opponent gap to stay at most 3.
    # This refinement promises a local improvement, not a global optimum.
    gaps = [abs(points[a] - points[b]) for a, b in pairs]
    assert max(gaps) <= 3
    objective = (max(gaps), sum(gaps))
    for i, (a, b) in enumerate(pairs):
        for j in range(i + 1, len(pairs)):
            c, d = pairs[j]
            for replacement in (((a, c), (b, d)), ((a, d), (b, c))):
                if any(frozenset(pair) in already_met for pair in replacement):
                    continue
                candidate = [pair for k, pair in enumerate(pairs) if k not in (i, j)] + list(replacement)
                candidate_gaps = [abs(points[x] - points[y]) for x, y in candidate]
                assert (max(candidate_gaps), sum(candidate_gaps)) >= objective
