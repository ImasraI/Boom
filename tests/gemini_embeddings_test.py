import json
import math
from types import SimpleNamespace

import chromadb
import httpx
import pytest
from chromadb.config import Settings as ChromaSettings

from app.rag.embedding_migration import activate_gemini, migrate_collection, migrate_collection_parallel
from app.rag.gemini_embeddings import EmbeddingError, GeminiEmbeddingModel, EmbeddingRateLimiter, text_collection_name
from app.rag.embedding_progress import checked_status, MigrationLock, worker_alive, write_status


def fake_embedding_time(monkeypatch, delays=None):
    clock = [0.0]
    def sleep(seconds):
        if delays is not None:
            delays.append(seconds)
        clock[0] += max(0, seconds)
    monkeypatch.setattr("app.rag.gemini_embeddings.time", SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))


def make_model(handler, **kwargs):
    model = GeminiEmbeddingModel("private-api-key", dimensions=128, requests_per_minute=100000, **kwargs)
    model.client.close()
    model.client = httpx.Client(transport=httpx.MockTransport(handler))
    return model


def test_separate_query_and_document_prompts_and_batch_order():
    requests = []
    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        if "requests" in data:
            return httpx.Response(200, json={"embeddings": [{"values": [i + 1, 1] + [0] * 126}
                                                           for i in range(len(data["requests"]))]})
        return httpx.Response(200, json={"embedding": {"values": [1] * 128}})
    model = make_model(handler, batch_size=2)
    vectors = model.embed_documents(["تابع", "حد", "شیمی"])
    query = model.probe_query("حد تابع چیست؟")
    assert len(vectors) == 3 and len(query) == 128
    assert all(math.isclose(sum(v * v for v in vector), 1) for vector in vectors)
    assert requests[0]["requests"][0]["content"]["parts"] == [{"text": "title: none | text: تابع"}]
    assert requests[0]["requests"][1]["content"]["parts"] == [{"text": "title: none | text: حد"}]
    assert requests[2]["content"]["parts"] == [{"text": "task: search result | query: حد تابع چیست؟"}]
    assert requests[2]["outputDimensionality"] == 128 and "taskType" not in requests[2]
    model.close()


@pytest.mark.parametrize("body", [[], {"embeddings": []}, {"embeddings": [{"values": [1, 2]}]},
                                  {"embeddings": [{"values": [0] * 128}]},
                                  {"embeddings": [{"values": [True] * 128}]},
                                  {"embeddings": [{"values": ["bad"] * 128}]}])
def test_malformed_vectors_are_not_ingested(body):
    model = make_model(lambda request: httpx.Response(200, json=body))
    with pytest.raises(EmbeddingError):
        model.embed_documents(["تابع"])
    model.close()


def test_daily_quota_stops_without_retry_and_does_not_leak_response(caplog):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "RequestsPerDay private-api-key private-text limit: 0"}})
    model = make_model(handler)
    assert model.embed_query("private-text") == []
    assert len(calls) == 1
    assert "daily quota exhausted" in caplog.text
    assert "private-text" not in caplog.text and "private-api-key" not in caplog.text
    with pytest.raises(EmbeddingError):
        model.embed_documents(["private-text"])
    assert len(calls) == 1  # Remember the terminal refusal across subsequent operations.
    model.close()


def test_retry_transient_errors_only(monkeypatch):
    fake_embedding_time(monkeypatch)
    codes = iter([503, 429, 200])
    model = make_model(lambda request: httpx.Response(next(codes), json={"embedding": {"values": [1] * 128}}))
    assert len(model.probe_query("تابع")) == 128
    model.close()


def test_respects_provider_retry_delay(monkeypatch):
    delays = []
    fake_embedding_time(monkeypatch, delays)
    responses = iter([httpx.Response(429, json={"error": {"details": [{"retryDelay": "45s"}]}}),
                      httpx.Response(200, json={"embedding": {"values": [1] * 128}})])
    model = make_model(lambda request: next(responses))
    assert len(model.probe_query("تابع")) == 128
    assert 45 in delays
    model.close()


def test_invalid_key_is_not_retried_or_logged(caplog):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"message": "private-api-key private-text"}})
    model = make_model(handler)
    assert model.embed_query("private-text") == []
    assert len(calls) == 1
    assert "private-text" not in caplog.text and "private-api-key" not in caplog.text
    model.close()


def test_auto_rate_uses_actual_minute_quota_and_shares_cooldown(monkeypatch):
    fake_embedding_time(monkeypatch)
    updates = []
    responses = iter([httpx.Response(429, json={"error": {"message": "private-api-key private-text", "details": [
        {"violations": [{"quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests",
                         "quotaId": "EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier", "quotaValue": "100",
                         "quotaDimensions": {"private": "private-text"}}]}, {"retryDelay": "20s"}]}}),
        httpx.Response(200, json={"embeddings": [{"values": [1] * 128}] * 8})])
    limiter = EmbeddingRateLimiter(100, adaptive=True)
    model = make_model(lambda request: next(responses), rate_limiter=limiter, on_activity=updates.append)
    assert len(model.embed_documents(["private-text"] * 8)) == 8
    assert 60 / limiter.interval == pytest.approx(11.25)
    assert any(event.get("quota_limits", [{}])[0].get("value") == 100 for event in updates)
    assert "private-api-key" not in str(updates) and "private-text" not in str(updates)
    for _ in range(20): limiter.succeeded()
    assert 60 / limiter.interval <= 11.25
    model.close()


def test_auto_rate_daily_quota_is_terminal_and_reports_provider_wait():
    updates, calls = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"details": [{"violations": [
            {"quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests",
             "quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "1000"}]},
            {"retryDelay": "3600s"}]}})
    limiter = EmbeddingRateLimiter(100, adaptive=True)
    model = make_model(handler, rate_limiter=limiter, on_activity=updates.append)
    with pytest.raises(EmbeddingError, match="daily quota exhausted"):
        model.probe_query("private-text")
    assert len(calls) == 1 and 60 / limiter.interval == 100
    assert updates[-1]["phase"] == "daily_quota_exhausted" and updates[-1]["wait_seconds"] == 3600
    model.close()


def test_001_task_type_and_normalization():
    sent = []
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"embedding": {"values": [2] * 128}})
    model = make_model(handler, model_name="gemini-embedding-001")
    result = model.probe_query("تابع")
    assert sent[0]["taskType"] == "RETRIEVAL_QUERY"
    assert sent[0]["content"]["parts"][0]["text"] == "تابع"
    assert math.isclose(sum(v * v for v in result), 1)
    model.close()


def test_namespace_prevents_same_dimension_different_model_mix():
    settings = SimpleNamespace(EMBEDDING_PROVIDER="gemini", EMBEDDING_MODEL_NAME="gemini-embedding-2", EMBEDDING_DIMENSIONS=768)
    first = text_collection_name(settings, "documents")
    settings.EMBEDDING_MODEL_NAME = "gemini-embedding-001"
    assert first != text_collection_name(settings, "documents")
    settings.EMBEDDING_DIMENSIONS = 1536
    assert "1536" in text_collection_name(settings, "documents")
    settings.EMBEDDING_PROVIDER = "ollama"
    assert text_collection_name(settings, "documents") == "documents"


def test_resumable_migration_preserves_source_owners_and_citations(tmp_path):
    client = chromadb.PersistentClient(str(tmp_path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False))
    source = client.create_collection("documents", embedding_function=None)
    source.add(ids=["one", "two", "three"], documents=["تابع", "حد", "شیمی"],
               embeddings=[[1, 0], [0, 1], [1, 1]],
               metadatas=[{"user_id": 1, "book": "ریاضی", "page": 12, "question_number": 30},
                          {"user_id": 7}, {"user_id": 8}])
    class FakeModel:
        model = "gemini-embedding-2"
        dimensions = 128
        fingerprint = "gemini:gemini-embedding-2:128:retrieval_v1"
        batch_size = 1
        calls = 0
        fail_on = 2
        def embed_documents(self, texts):
            self.calls += 1
            if self.calls == self.fail_on:
                raise EmbeddingError("daily quota exhausted")
            return [[1] * 128 for text in texts]
    model = FakeModel()
    with pytest.raises(EmbeddingError):
        migrate_collection(client, "documents", model)
    model.calls, model.fail_on = 0, 0
    result = migrate_collection(client, "documents", model)
    assert model.calls == 2 and result["chunks"] == 3
    target = client.get_collection(result["target"], embedding_function=None)
    assert source.count() == 3
    assert list(source.get(ids=["one"], include=["embeddings"])["embeddings"][0]) == [1, 0]
    meta = target.get(ids=["one"], include=["metadatas"])["metadatas"][0]
    assert (meta["user_id"], meta["book"], meta["page"], meta["question_number"]) == (1, "ریاضی", 12, 30)
    model.calls = 0
    migrate_collection(client, "documents", model)
    assert model.calls == 0
    source.update(ids=["two"], documents=["حد جدید"], embeddings=[[0, 1]])
    migrate_collection(client, "documents", model)
    assert model.calls == 1
    assert target.get(ids=["two"], include=["documents"])["documents"] == ["حد جدید"]


def test_activation_keeps_secrets_and_backs_up_previous_config(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=keep-secret\nEMBEDDING_API_KEY=old-other-provider-key\nEMBEDDING_PROVIDER=ollama\nEMBEDDING_PROXY=http://old-proxy:1234\n# custom setting\nCHROMA_COLLECTION=documents\n", encoding="utf-8")
    model = SimpleNamespace(model="gemini-embedding-2", dimensions=768,
                            api_key="verified-worker-key", proxy="")
    activate_gemini(env, model, tmp_path / "backups")
    from dotenv import dotenv_values
    values = dotenv_values(env)
    assert values["GEMINI_API_KEY"] == "keep-secret" and values["EMBEDDING_PROVIDER"] == "gemini"
    assert values["EMBEDDING_DIMENSIONS"] == "768" and values["CHROMA_COLLECTION"] == "documents"
    assert values["EMBEDDING_API_KEY"] == "verified-worker-key"
    assert values["EMBEDDING_PROXY"] == ""
    backups = list((tmp_path / "backups").glob("*.env"))
    assert len(backups) == 1 and "EMBEDDING_PROVIDER=ollama" in backups[0].read_text()


def test_worker_health_detects_a_stale_running_status(monkeypatch):
    import os
    assert worker_alive(os.getpid()) is True
    monkeypatch.setattr("app.rag.embedding_progress.worker_alive", lambda pid: False)
    state = checked_status({"status": "running", "worker_pid": 123, "overall_completed": 536})
    assert state["status"] == "interrupted" and state["overall_completed"] == 536
    assert checked_status({"status": "complete", "worker_pid": 123})["status"] == "complete"


def test_migration_lock_blocks_duplicates_and_releases_on_close(tmp_path):
    first = MigrationLock(tmp_path / "gemini.lock")
    second = MigrationLock(tmp_path / "gemini.lock")
    first.acquire()
    try:
        with pytest.raises(BlockingIOError):
            second.acquire()
    finally:
        first.close()
    second.acquire()
    second.close()


def test_status_write_retries_reader_lock_without_exposing_partial_json(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path / "status.json"
    path.write_text('{"overall_completed": 4}', encoding="utf-8")
    original = Path.replace
    attempts = []
    def replace(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            assert json.loads(path.read_text())["overall_completed"] == 4
            raise PermissionError("Windows reader holds the previous status snapshot")
        return original(source, destination)
    monkeypatch.setattr(Path, "replace", replace)
    write_status(path, {"overall_completed": 12, "phase": "running"})
    assert len(attempts) == 3
    assert json.loads(path.read_text())["overall_completed"] == 12
    assert not path.with_suffix(".json.tmp").exists()


def test_provider_activity_reports_waits_without_input_or_keys(monkeypatch):
    fake_embedding_time(monkeypatch)
    updates = []
    responses = iter([httpx.Response(429, json={"error": {"details": [{"retryDelay": "45s"}]}}),
                      httpx.Response(200, json={"embedding": {"values": [1] * 128}})])
    model = make_model(lambda request: next(responses), on_activity=updates.append)
    assert len(model.probe_query("private-question")) == 128
    assert {"phase": "waiting_for_gemini_quota", "wait_seconds": 45} in updates
    assert "private-question" not in str(updates) and "private-api-key" not in str(updates)
    model.close()


def test_parallel_workers_partition_batches_and_only_coordinator_writes(tmp_path):
    import threading
    client = chromadb.PersistentClient(str(tmp_path / "parallel"), settings=ChromaSettings(anonymized_telemetry=False))
    source = client.create_collection("documents", embedding_function=None)
    source.add(ids=[str(i) for i in range(21)], documents=[f"تابع {i}" for i in range(21)],
               metadatas=[{"user_id": i % 3 + 1, "page": i} for i in range(21)], embeddings=[[1, 0]] * 21)
    coordinator = threading.get_ident()
    class GuardedCollection:
        def __init__(self, collection): self.collection = collection
        def __getattr__(self, name):
            value = getattr(self.collection, name)
            if not callable(value): return value
            def guarded(*args, **kwargs):
                assert threading.get_ident() == coordinator
                return value(*args, **kwargs)
            return guarded
    class GuardedClient:
        def get_collection(self, *args, **kwargs): return GuardedCollection(client.get_collection(*args, **kwargs))
        def get_or_create_collection(self, *args, **kwargs): return GuardedCollection(client.get_or_create_collection(*args, **kwargs))
    class FakeModel:
        model = "gemini-embedding-2"
        dimensions = 128
        fingerprint = "same-model"
        batch_size = 2
        def __init__(self): self.texts = []
        def embed_documents(self, texts):
            assert threading.get_ident() != coordinator
            self.texts.extend(texts)
            return [[1] * 128 for text in texts]
    models = [FakeModel() for _ in range(3)]
    result = migrate_collection_parallel(GuardedClient(), "documents", models)
    assert result["chunks"] == 21 and all(model.texts for model in models)
    embedded = [text for model in models for text in model.texts]
    assert len(embedded) == len(set(embedded)) == 21
    for model in models: model.texts.clear()
    migrate_collection_parallel(GuardedClient(), "documents", models)
    assert all(not model.texts for model in models)
    assert source.count() == 21


def test_duplicate_worker_credentials_share_budget_and_refused_keys_are_reported(tmp_path, monkeypatch):
    import app.rag.embedding_workers as workers
    for number, key in [(1, "refused-private-key"), (2, "working-private-key"), (3, "working-private-key")]:
        directory = tmp_path / f"worker{number}"
        directory.mkdir()
        (directory / "worker.env").write_text(f"GEMINI_API_KEY={key}\n", encoding="utf-8")
    class FakeModel:
        def __init__(self, key, *args, **kwargs):
            self.key = key
            self.rate_limiter = kwargs["rate_limiter"]
        def probe_query(self, query):
            if self.key == "refused-private-key": raise EmbeddingError("HTTP 403")
            return [1] * 128
        def close(self): pass
    monkeypatch.setattr(workers, "GeminiEmbeddingModel", FakeModel)
    reports = []
    models = workers.build_worker_models(tmp_path, 3, model_name="gemini-embedding-2", dimensions=128,
                                         batch_size=2, rpm=5, base_url="https://example.com", report=reports.append)
    assert len(models) == 3 and all(model.key == "working-private-key" for model in models)
    assert models[0].rate_limiter is models[1].rate_limiter is models[2].rate_limiter
    assert reports[-1]["distinct_working_keys"] == 1
    assert any(row.get("status") == "refused" for row in reports)
    assert "private-key" not in str(reports)
