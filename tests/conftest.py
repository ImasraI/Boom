"""Prevent tests using the shared SessionLocal from touching a real student's DB."""
import os
import tempfile
from pathlib import Path

_test_db_dir = tempfile.TemporaryDirectory(prefix="boom-pytest-", ignore_cleanup_errors=True)
os.environ["BOOM_DATABASE_URL"] = "sqlite:///" + (Path(_test_db_dir.name) / "tests.db").as_posix()


def pytest_sessionfinish(session, exitstatus):
    from sqlalchemy.orm import close_all_sessions
    from app.auth.database import engine
    close_all_sessions()
    engine.dispose()
