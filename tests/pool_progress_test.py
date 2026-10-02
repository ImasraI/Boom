"""Tests for pool-generation progress (the admin panel's progress bar).

Filling empty shelves takes many minutes inside one background run, so the
admin UI needs a live answer to "how far along is this generation?": which
shelf is in flight, how many booklets this run finished, and the aggregate
fill of every shelf against the target.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.database import Base, get_db
from app.auth.deps import require_admin
from app.rag import pool_core
from app.routers import admin


@pytest.fixture(autouse=True)
def _clean_pool_state():
    # The progress record is process-global: a sweep run by an earlier test
    # leaves its completed counters behind, so open and close a fresh run
    # (begin resets planned/produced) around every test.
    pool_core.clear_cancel()
    pool_core.begin_progress("test")
    pool_core.finish_progress()
    yield
    pool_core.clear_cancel()
    pool_core.begin_progress("test")
    pool_core.finish_progress()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_snapshot_is_idle_and_mutators_are_noops_when_nobody_owns_it():
    assert pool_core.progress_snapshot()["active"] is False
    pool_core.add_planned(5)
    pool_core.bump_produced()
    pool_core.set_current("riazi", "konkur")
    snap = pool_core.progress_snapshot()
    assert (snap["active"], snap["planned"], snap["produced"], snap["current"]) == (
        False, 0, 0, None)
    assert snap["elapsed_seconds"] == 0  # a run that never started


def test_begin_progress_is_single_owner():
    assert pool_core.begin_progress("restock") is True
    # A sweep starting inside the admin restock must not steal the record;
    # it reports "not mine" so the outer run finishes it.
    assert pool_core.begin_progress("pool") is False
    pool_core.add_planned(4)
    pool_core.bump_produced()
    pool_core.bump_produced()
    snap = pool_core.progress_snapshot()
    assert snap["active"] is True
    assert snap["label"] == "restock"
    assert (snap["planned"], snap["produced"]) == (4, 2)
    assert snap["elapsed_seconds"] >= 0
    pool_core.finish_progress()
    assert pool_core.progress_snapshot()["active"] is False
    assert pool_core.begin_progress("pool") is True  # record is reusable


def test_sweep_reports_live_progress_and_closes_the_run(monkeypatch, db):
    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 2)
    seen = []

    def fake_generate_one(db_, major, difficulty):
        seen.append(pool_core.progress_snapshot())
        return True

    monkeypatch.setattr(pool_core, "generate_one", fake_generate_one)

    assert pool_core.sweep(db, target=2, majors=["riazi"],
                           difficulties=["easy"]) == 2
    # Every booklet was generated under an active, correctly targeted record.
    for snap in seen:
        assert snap["active"] is True
        assert snap["current"] == {"major_key": "riazi", "major": "ریاضی فیزیک",
                                   "difficulty": "easy"}
    assert seen[0]["planned"] == 2
    assert [s["produced"] for s in seen] == [0, 1]
    # The run closes itself: no stale "still generating" bar in the panel.
    final = pool_core.progress_snapshot()
    assert final["active"] is False
    assert final["current"] is None
    assert final["produced"] == 2


def test_sweep_keeps_an_outer_run_open(monkeypatch, db):
    """The admin restock owns the record across pool + duel sweeps."""
    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 1)
    monkeypatch.setattr(pool_core, "generate_one", lambda *a, **k: True)

    assert pool_core.begin_progress("restock") is True
    pool_core.sweep(db, target=1, majors=["riazi"], difficulties=["easy"])
    assert pool_core.progress_snapshot()["active"] is True  # still ours
    pool_core.finish_progress()
    assert pool_core.progress_snapshot()["active"] is False


def test_dry_run_records_no_progress(monkeypatch, db):
    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 3)
    produced = pool_core.sweep(db, target=3, majors=["riazi"],
                               difficulties=["easy"], dry_run=True)
    assert produced == 0
    assert pool_core.progress_snapshot()["active"] is False


def test_admin_pool_endpoint_exposes_the_progress_bar(db):
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_db] = lambda: db

    payload = TestClient(app).get("/api/admin/pool").json()
    progress = payload["progress"]

    assert len(payload["shelves"]) == len(pool_core.POOL_MAJORS) * len(
        pool_core.POOL_DIFFICULTIES)
    assert progress["active"] is False
    assert progress["capacity"] == payload["target"] * len(payload["shelves"])
    assert progress["duel_capacity"] == payload["target"] * len(
        pool_core.POOL_MAJORS)
    # An empty (or full) pool must still report a sane 0..100 headline.
    assert progress["available"] == 0
    assert progress["percent"] == 0
    assert progress["duel_available"] == 0
