"""Tests for cooperative pool-restock cancellation (admin panel).

A restock sweep runs many multi-minute LLM booklets in a background thread;
the admin cancel button must stop it at a booklet boundary, keep everything
already produced, and reset cleanly for the next run.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import pool_core


@pytest.fixture(autouse=True)
def _reset_cancel_flag():
    pool_core.clear_cancel()
    yield
    pool_core.clear_cancel()


def test_cancel_flag_roundtrip():
    assert pool_core.cancel_requested() is False
    pool_core.request_cancel()
    assert pool_core.cancel_requested() is True
    pool_core.clear_cancel()
    assert pool_core.cancel_requested() is False


def test_sweep_stops_at_booklet_boundary_when_canceled(monkeypatch, tmp_path):
    """Cancel set before the sweep: zero booklets generated, produced=0."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.auth.database import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 3)

    generated = []

    def fake_generate_one(db_, major, difficulty):
        generated.append((major, difficulty))
        return True

    monkeypatch.setattr(pool_core, "generate_one", fake_generate_one)

    pool_core.request_cancel()
    produced = pool_core.sweep(db, target=3)
    assert produced == 0
    assert generated == []  # stopped before generating anything


def test_sweep_keeps_completed_booklet_then_stops(monkeypatch, tmp_path):
    """Cancel lands mid-sweep: the finished booklet stays, the rest is
    skipped - this is the exact behavior the admin button promises."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.auth.database import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 3)

    state = {"n": 0}

    def fake_generate_one(db_, major, difficulty):
        state["n"] += 1
        if state["n"] == 1:
            # The admin clicks cancel while booklet 1 is generating; the
            # flag is set by the time booklet 2 would start.
            pool_core.request_cancel()
            return True
        return True

    monkeypatch.setattr(pool_core, "generate_one", fake_generate_one)

    produced = pool_core.sweep(db, target=3)
    assert produced == 1  # booklet kept, remaining two skipped
    assert state["n"] == 1


def test_sweep_runs_normally_without_cancel(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.auth.database import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 2)
    monkeypatch.setattr(pool_core, "generate_one", lambda *a, **k: True)

    assert pool_core.sweep(db, target=2) > 0
    assert pool_core.cancel_requested() is False
