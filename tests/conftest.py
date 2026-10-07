"""Prevent tests using the shared SessionLocal from touching a real student's DB."""
import os
import tempfile
import pytest
from pathlib import Path

_test_db_dir = tempfile.TemporaryDirectory(prefix="boom-pytest-", ignore_cleanup_errors=True)
os.environ["BOOM_DATABASE_URL"] = "sqlite:///" + (Path(_test_db_dir.name) / "tests.db").as_posix()
# Tests stub provider requests; a developer's production pacing must not sleep.
os.environ["POOL_GENERATION_REQUESTS_PER_MINUTE"] = "0"


@pytest.fixture(autouse=True)
def isolate_access_health():
    from app.rag import provider_quota
    provider_quota._ACCESS_BLOCKS.clear()
    yield
    provider_quota._ACCESS_BLOCKS.clear()


def pytest_sessionfinish(session, exitstatus):
    from sqlalchemy.orm import close_all_sessions
    from app.auth.database import engine
    close_all_sessions()
    engine.dispose()
