"""Prevent tests using the shared SessionLocal from touching a real student's DB."""
import os
import tempfile
import pytest
from pathlib import Path

_test_db_dir = tempfile.TemporaryDirectory(prefix="boom-pytest-", ignore_cleanup_errors=True)
os.environ["BOOM_DATABASE_URL"] = "sqlite:///" + (Path(_test_db_dir.name) / "tests.db").as_posix()
# Tests stub provider requests; a developer's production pacing must not sleep.
os.environ["POOL_GENERATION_REQUESTS_PER_MINUTE"] = "0"
# Legacy generation tests explicitly exercise the optional live branch.
os.environ["POOL_ALLOW_LIVE_GENERATION"] = "true"


@pytest.fixture(autouse=True)
def isolate_access_health(monkeypatch):
    from app.rag import provider_quota
    monkeypatch.setattr(provider_quota, '_state_file', lambda: None)
    states = (provider_quota._ACCESS_BLOCKS, provider_quota._BLOCKS,
              provider_quota._RATE_BLOCKS, provider_quota._LOADED_PATHS)
    for state in states: state.clear()
    yield
    for state in states: state.clear()


@pytest.fixture(autouse=True)
def isolate_selected_pool_state(monkeypatch, tmp_path):
    from app.rag import pool_service
    monkeypatch.setattr(pool_service, '_path', lambda: tmp_path / 'pool-run.json')
    monkeypatch.setattr(pool_service, '_thread', None)
    pool_service._shutdown.clear()
    pool_service._wake.clear()
    yield
    pool_service._shutdown.set()
    pool_service._wake.set()


@pytest.fixture(autouse=True)
def isolate_provider_usage(monkeypatch, tmp_path):
    # Mocked completions must never inflate the developer's real token audit.
    from app.rag import pool_usage
    monkeypatch.setattr(pool_usage, '_directory', lambda: tmp_path / 'provider-usage')


def pytest_sessionfinish(session, exitstatus):
    from sqlalchemy.orm import close_all_sessions
    from app.auth.database import engine
    close_all_sessions()
    engine.dispose()
