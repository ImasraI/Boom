"""Daily provider exhaustion must stop work and still serve ready mocks."""
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.rag import llm, mock_generation, pool_core, provider_quota as quota
from app.routers import mocks, admin


@pytest.fixture(autouse=True)
def clean_health(monkeypatch):
    monkeypatch.setattr(mocks.question_bank, "assemble", lambda *a, **kw: [])
    quota._BLOCKS.clear()
    pool_core.begin_progress("test")
    pool_core.finish_progress()
    yield
    quota._BLOCKS.clear()
    pool_core.finish_progress()


def test_pacific_midnight_reset_tracks_summer_and_winter():
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        pytest.skip("System IANA timezone data is absent; conservative fallback is tested separately")
    assert quota.next_gemini_reset(datetime(2026, 10, 5, 6, tzinfo=timezone.utc)) == datetime(2026, 10, 5, 7, tzinfo=timezone.utc)
    assert quota.next_gemini_reset(datetime(2026, 12, 5, 6, tzinfo=timezone.utc)) == datetime(2026, 12, 5, 8, tzinfo=timezone.utc)


def test_reset_without_timezone_data_never_retries_early(monkeypatch):
    def missing_zone(_name):
        raise quota.ZoneInfoNotFoundError("No IANA data")
    monkeypatch.setattr(quota, "ZoneInfo", missing_zone)
    assert quota.next_gemini_reset(datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    assert quota.next_gemini_reset(datetime(2026, 12, 5, 8, 30, tzinfo=timezone.utc)) == datetime(2026, 12, 6, 8, tzinfo=timezone.utc)


def test_exhausted_quota_is_remembered_across_new_clients_and_expires(monkeypatch):
    calls = []
    def exhausted(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}})
    def client(key="test-key"):
        instance = llm.GeminiLLMClient(key, "https://provider.example/v1", "test-model", 0, 20)
        instance.client.close()
        instance.client = httpx.Client(transport=httpx.MockTransport(exhausted))
        return instance
    first, second = client(), client()
    assert first.generate([]) == second.generate([]) == ""
    assert len(calls) == 1
    changed = client("changed-key")
    assert changed.generate([]) == ""
    assert len(calls) == 2
    quota._BLOCKS[first._quota_identity] = (0, "expired")
    assert second.generate([]) == ""
    assert len(calls) == 3
    for instance in (first, second, changed):
        instance.client.close()


def test_daily_quota_stops_remaining_subjects(monkeypatch):
    calls = []
    def refuse(user_id, row, *args, report=None, **kwargs):
        calls.append(row["name"])
        report("provider_error", {"message": "HTTP 429 daily quota exhausted"})
        return []
    monkeypatch.setattr(mock_generation, "_generate_subject_questions", refuse)
    assert mock_generation.generate_booklet(1, [{"name": s, "questions": 5} for s in ("ریاضی", "فیزیک", "شیمی")]) == []
    assert calls == ["ریاضی"]


def test_daily_quota_stops_pool_after_one_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(pool_core, "pool_deficit", lambda *a, **k: 20)
    def refuse(*args):
        calls.append(1)
        pool_core.note_provider_error("HTTP 429 daily quota exhausted")
        return False
    monkeypatch.setattr(pool_core, "generate_one", refuse)
    assert pool_core.sweep(None, 20, majors=["riazi"], difficulties=["easy"]) == 0
    assert len(calls) == 1


def test_verifier_stops_after_replacement_exhausts_daily_quota(monkeypatch):
    client = SimpleNamespace(last_error="")
    calls, events = [], []
    questions = [{"_id": i, "text": f"question {i}", "subject": "شیمی", "answer": 0} for i in range(3)]
    monkeypatch.setattr(mock_generation, "get_pool_llm_client", lambda: client)
    monkeypatch.setattr(mock_generation, "get_pool_verifier_client", lambda: client)
    monkeypatch.setattr(mock_generation, "_batch_verdicts", lambda *args: iter((q, 1) for q in questions))
    def refuse(*args):
        calls.append(1)
        client.last_error = "HTTP 429 daily quota exhausted"
        return None
    monkeypatch.setattr(mock_generation, "_generate_replacement", refuse)
    assert mock_generation.verify_and_repair_booklet(questions, 1, report=lambda event, data: events.append(event)) == []
    assert calls == [1] and "provider_error" in events


def test_admin_does_not_start_a_second_run_while_automatic_worker_is_active(monkeypatch):
    monkeypatch.setattr(admin, "require_pool_available", lambda: None)
    monkeypatch.setattr(admin, "_restock_running", False)
    pool_core.begin_progress("automatic")
    monkeypatch.setattr(admin.threading, "Thread", lambda **kwargs: pytest.fail("Must not launch another worker"))
    with pytest.raises(HTTPException) as exc:
        admin.pool_restock(None)
    assert exc.value.status_code == 409
    assert pool_core.progress_snapshot()["label"] == "automatic"


def test_failed_live_mock_returns_readable_provider_error_and_refunds_quota(monkeypatch):
    accounting = []
    monkeypatch.setattr(mocks, "consume_ai_use", lambda *a: accounting.append("reserve"))
    monkeypatch.setattr(mocks, "release_ai_use", lambda *a: accounting.append("refund"))
    monkeypatch.setattr(mocks, "require_pool_available", lambda: None)
    def refuse(*a, report=None, **kwargs):
        report("provider_error", {"message": "HTTP 429 daily quota exhausted"})
        return []
    monkeypatch.setattr(mock_generation, "generate_booklet", refuse)
    with pytest.raises(HTTPException) as error:
        db = SimpleNamespace(execute=lambda *a: SimpleNamespace(scalar_one_or_none=lambda: None))
        mocks.generate_mock(mocks.MockConfig(questions_per_subject=1), SimpleNamespace(id=1), db)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "provider_daily_quota"
    assert accounting == ["reserve", "refund"]


def test_ready_mock_is_served_even_if_provider_is_blocked(monkeypatch):
    ready = SimpleNamespace(id=15, title="ready", duration_minutes=60, questions='[{"answer":2}]')
    monkeypatch.setattr(mocks, "_claim_pool_mock", lambda *a: ready)
    def blocked():
        raise AssertionError("Serving ready stock must not require a provider")
    monkeypatch.setattr(mocks, "require_pool_available", blocked)
    db = SimpleNamespace(execute=lambda *a: SimpleNamespace(scalar_one_or_none=lambda: None))
    result = mocks._generate_reserved_mock(mocks.MockConfig(), SimpleNamespace(id=1), db)
    assert result["mock_id"] == 15
    assert "answer" not in result


def test_blocked_restock_does_not_launch_a_thread(monkeypatch):
    def blocked():
        raise HTTPException(503, quota.DAILY_QUOTA_MESSAGE)
    monkeypatch.setattr(admin, "require_pool_available", blocked)
    monkeypatch.setattr(admin.threading, "Thread", lambda **kw: pytest.fail("Do not launch blocked work"))
    with pytest.raises(HTTPException) as error:
        admin.pool_restock(None)
    assert error.value.status_code == 503


def test_daily_quota_survives_restart_without_saving_credentials_or_responses(monkeypatch, tmp_path):
    path = tmp_path / "provider-quota.json"
    monkeypatch.setattr(quota, "_state_file", lambda: path)
    quota._LOADED_PATHS.clear()
    identity = quota.quota_identity("https://provider.example", "test-model", "test-secret")
    quota.block_daily_quota(identity, "daily quota; sensitive provider response test-secret")
    saved = path.read_text()
    assert "test-secret" not in saved and "sensitive" not in saved
    quota._BLOCKS.clear(); quota._LOADED_PATHS.clear()
    assert quota.blocked_quota(identity) is not None


def test_expired_persisted_quota_and_changed_credentials_are_not_blocked(monkeypatch, tmp_path):
    import json
    path = tmp_path / "provider-quota.json"
    old = quota.quota_identity("https://provider.example", "test-model", "old-secret")
    new = quota.quota_identity("https://provider.example", "test-model", "new-secret")
    path.write_text(json.dumps({old: 0}))
    monkeypatch.setattr(quota, "_state_file", lambda: path)
    quota._LOADED_PATHS.clear()
    assert quota.blocked_quota(old) is None and quota.blocked_quota(new) is None
