import json
import os
from datetime import datetime, timedelta, timezone

from app.rag.embedding_progress import MigrationLock, checked_status, write_status
from app.rag.embedding_supervisor import quota_retry_at, supervise_migration


def quota_state(now):
    return {"status": "stopped", "worker_pid": -1, "overall_completed": 1887, "overall_total": 1909,
            "workers": {"1": {"phase": "daily_quota_exhausted", "wait_seconds": 60, "updated_at": now.isoformat()}}}


def test_wait_does_not_contact_google_before_reset_and_resumes_saved_chunks(tmp_path):
    clock = [datetime(2026, 10, 4, tzinfo=timezone.utc)]
    path = tmp_path / "status.json"
    write_status(path, quota_state(clock[0]))
    waits, runs = [], []
    def sleep(seconds):
        state = json.loads(path.read_text())
        assert state["status"] == "waiting_for_quota" and state["overall_completed"] == 1887
        assert checked_status(state)["worker_alive"] is True
        second = MigrationLock(tmp_path / "gemini.lock")
        try:
            second.acquire()
            raise AssertionError("Supervisor failed to exclude a manual duplicate migration")
        except BlockingIOError:
            pass
        waits.append(seconds)
        clock[0] += timedelta(seconds=seconds)
    def run():
        assert clock[0] >= datetime(2026, 10, 4, tzinfo=timezone.utc) + timedelta(seconds=65)
        lock = MigrationLock(tmp_path / "gemini.lock")
        lock.acquire()
        lock.close()
        runs.append(True)
        return 0
    assert supervise_migration(run, path, now=lambda: clock[0], sleep=sleep) == 0
    assert sum(waits) == 65 and len(runs) == 1 and max(waits) <= 30


def test_no_retry_for_nonquota_failure(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, {"status": "stopped", "reason": "HTTP403"})
    runs = []
    def run():
        runs.append(True)
        return 1
    assert supervise_migration(run, path) == 1 and len(runs) == 1


def test_existing_live_migration_is_not_overwritten(tmp_path):
    path = tmp_path / "status.json"
    state = {"status": "running", "worker_pid": os.getpid() + 1}
    write_status(path, state)
    import unittest.mock
    with unittest.mock.patch("app.rag.embedding_supervisor.worker_alive", return_value=True):
        assert supervise_migration(lambda: (_ for _ in ()).throw(AssertionError()), path) == 2
    assert json.loads(path.read_text()) == state


def test_restart_supervisor_preserves_existing_retry_deadline():
    now = datetime.now(timezone.utc)
    state = quota_state(now)
    deadline = quota_retry_at(state)
    state.update(status="waiting_for_quota", retry_not_before=deadline.isoformat())
    assert quota_retry_at(state) == deadline


def test_worker_probe_reports_quota_deadline_before_models_are_created(tmp_path, monkeypatch):
    import pytest
    import app.rag.embedding_workers as workers
    from app.rag.gemini_embeddings import EmbeddingError
    directory = tmp_path / "worker1"
    directory.mkdir()
    (directory / "worker.env").write_text('GEMINI_API_KEY=private-key\n', encoding="utf-8")
    class Probe:
        def __init__(self, *args, **kwargs): self.callback = kwargs['on_activity']
        def probe_query(self, query):
            self.callback({'phase':'daily_quota_exhausted','wait_seconds':3600})
            raise EmbeddingError('daily quota exhausted')
        def close(self): pass
    monkeypatch.setattr(workers,'GeminiEmbeddingModel',Probe)
    events=[]
    with pytest.raises(EmbeddingError):
        workers.build_worker_models(tmp_path,1,model_name='gemini-embedding-2',dimensions=128,
            batch_size=8,rpm=100,base_url='https://example.com',activity=lambda worker,event: events.append((worker,event)))
    assert events == [(1,{'phase':'daily_quota_exhausted','wait_seconds':3600})]
    assert 'private-key' not in str(events)
