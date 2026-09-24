"""Tests for the admin user-data wipe (DELETE /api/admin/users/{id}/data).

A full wipe must erase every user-owned row, keep the shared mock pool
(student_id=0 sentinel rows) and the signup allowlist, refuse admins and
mismatched confirmations, and clear the in-memory quota counters.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import limits
from app.auth.database import (
    ArenaMatch, ArenaQueueEntry, Base, Conversation, GeneratedMock,
    MockAttempt, PhoneCode, SignupAllowlist, User, WrongAnswer,
)
from app.routers import admin


@pytest.fixture()
def db(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _fake_vector_stores(monkeypatch):
    """Purge calls recorded instead of touching real Chroma."""
    calls = []

    class FakeCollection:
        def delete(self, where=None):
            calls.append(where)

    class FakeStore:
        collection = FakeCollection()

    monkeypatch.setattr(
        "app.rag.vector_store.get_vector_store", lambda: FakeStore())
    monkeypatch.setattr(
        "app.rag.vector_store.get_image_vector_store", lambda: FakeStore())
    monkeypatch.setattr(
        "app.rag.vector_store.get_question_vector_store",
        lambda: FakeStore())

    class FakeSearch:
        def refresh(self, user_id):
            calls.append(("refresh", user_id))

    monkeypatch.setattr(
        "app.rag.hybrid_search.get_hybrid_search", lambda: FakeSearch())
    yield calls


@pytest.fixture(autouse=True)
def _no_file_rm(monkeypatch):
    monkeypatch.setattr(admin.shutil, "rmtree", lambda p: None)
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(UPLOAD_DIR="u", IMAGES_DIR="i"),
    )


@pytest.fixture()
def seeded(db):
    user = User(username="9121112233", phone="9121112233",
                hashed_password="x", phone_verified=True)
    db.add(user)
    db.commit()
    other = User(username="9129998877", phone="9129998877",
                 hashed_password="x")
    db.add(other)
    db.commit()
    db.add(GeneratedMock(student_id=user.id, title="t", questions="[]",
                         status="claimed", difficulty="easy"))
    db.add(GeneratedMock(student_id=0, title="pool", questions="[]",
                         status="pending_use", difficulty="easy"))
    db.add(MockAttempt(mock_id=1, student_id=user.id))
    db.add(ArenaMatch(student_a_id=user.id, student_b_id=other.id))
    db.add(ArenaQueueEntry(student_id=user.id))
    db.add(Conversation(user_id=user.id, role="user", content="c"))
    db.add(WrongAnswer(student_id=user.id, subject="فیزیک"))
    db.add(PhoneCode(phone="9121112233", code_hash="h",
                     expires_at=__import__("datetime").datetime.utcnow()))
    db.add(SignupAllowlist(phone="9121112233", note="n"))
    db.commit()
    return user


def test_wipe_deletes_user_rows_keeps_pool_and_allowlist(db, seeded, _fake_vector_stores):
    limits.reset_user_quota(seeded.id)
    limits._counters._counts[seeded.id] = {"chat": 5, "_tokens": 100}

    result = admin.wipe_user_data(
        seeded.id, admin.WipeUserData(confirm="9121112233"), db)

    assert result["ok"] is True
    assert result["deleted"]["user"] == 1
    assert result["deleted"]["generated_mocks"] == 1   # only the claimed one
    assert result["deleted"]["mock_attempts"] == 1
    assert result["deleted"]["arena_matches"] == 1
    assert result["deleted"]["arena_queue_entries"] == 1
    assert result["deleted"]["conversations"] == 1
    assert result["deleted"]["wrong_answers"] == 1
    assert result["deleted"]["phone_codes"] == 1

    # User and their data are gone...
    assert db.get(User, seeded.id) is None
    # ...but the shared pool row and the allowlist entry survive.
    pool_rows = db.query(GeneratedMock).filter(
        GeneratedMock.status == "pending_use").all()
    assert len(pool_rows) == 1 and pool_rows[0].student_id == 0
    assert db.query(SignupAllowlist).count() == 1
    # The other user is untouched.
    assert db.query(User).filter(User.username == "9129998877").count() == 1
    # Quota counters cleared.
    assert limits._counters.snapshot(seeded.id) == {}
    # Vector purge targeted this user only.
    assert {"user_id": seeded.id} in _fake_vector_stores


def test_wipe_refuses_admin(db, seeded):
    seeded.is_admin = True
    db.commit()
    with pytest.raises(HTTPException) as exc:
        admin.wipe_user_data(seeded.id, admin.WipeUserData(confirm=seeded.username), db)
    assert exc.value.status_code == 403
    assert db.get(User, seeded.id) is not None  # untouched


def test_wipe_refuses_wrong_confirm(db, seeded):
    with pytest.raises(HTTPException) as exc:
        admin.wipe_user_data(seeded.id, admin.WipeUserData(confirm="9120000000"), db)
    assert exc.value.status_code == 400
    assert db.get(User, seeded.id) is not None


def test_wipe_refuses_unknown_user(db):
    with pytest.raises(HTTPException) as exc:
        admin.wipe_user_data(999, admin.WipeUserData(confirm="9120000000"), db)
    assert exc.value.status_code == 404
