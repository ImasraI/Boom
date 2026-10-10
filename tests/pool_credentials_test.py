import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.auth.deps import require_admin
from app.rag import pool_credentials as credentials, pool_service, provider_quota
from app.routers import admin


def secret(provider="groq", letter="A"):
    return ("gsk_" if provider == "groq" else "AQ.") + letter * 48


@pytest.fixture
def setup(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text("SECRET_KEY='preserve-this-secret'\nPOOL_LLM_PROVIDER=groq\n"
                    "POOL_VERIFY_LLM_PROVIDER=gemini\n# keep this comment\n", encoding="utf-8")
    for name in ("POOL_GROQ_API_KEYS", "POOL_GEMINI_API_KEYS", "POOL_VERIFY_GEMINI_API_KEYS",
                 "POOL_LLM_API_KEY", "POOL_VERIFY_LLM_API_KEY", "LLM_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "_env_path", lambda: path)
    monkeypatch.setattr(credentials, "get_settings", lambda: Settings(_env_file=path))
    app = FastAPI()
    app.include_router(admin.router)
    client = TestClient(app)
    return path, app, client


def allow_admin(app):
    app.dependency_overrides[require_admin] = lambda: {"is_admin": True}


def test_credential_routes_reject_unauthenticated_and_non_admin(setup):
    path, app, client = setup
    before = path.read_bytes()
    for method in ("get", "post"):
        response = getattr(client, method)("/api/admin/pool/credentials")
        assert response.status_code == 401
    def forbidden():
        raise HTTPException(403, "admin only")
    app.dependency_overrides[require_admin] = forbidden
    assert client.post("/api/admin/pool/credentials", json={"key": secret()}).status_code == 403
    assert path.read_bytes() == before


def test_add_persists_private_key_and_wakes_run_without_changing_settings(setup):
    path, app, client = setup
    allow_admin(app)
    key = secret()
    response = client.post("/api/admin/pool/credentials", json={"provider": "groq", "stage": "generation", "key": key})
    assert response.status_code == 200 and response.json()["added"]
    assert key not in response.text
    assert response.headers["cache-control"] == "no-store"
    stored = dotenv_values(path)
    assert stored["POOL_GROQ_API_KEYS"] == key
    assert stored["SECRET_KEY"] == "preserve-this-secret"
    assert stored["POOL_LLM_PROVIDER"] == "groq"
    assert "# keep this comment" in path.read_text()
    assert pool_service._wake.is_set()
    assert pool_service.snapshot()["enabled"] is False
    assert credentials.get_settings().POOL_GROQ_API_KEYS == key
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    again = client.post("/api/admin/pool/credentials", json={"provider": "groq", "stage": "generation", "key": key})
    assert again.json()["added"] is False
    assert dotenv_values(path)["POOL_GROQ_API_KEYS"] == key


@pytest.mark.parametrize("payload", [
    {"provider": "groq", "stage": "verification", "key": secret()},
    {"provider": [], "stage": "generation", "key": secret()},
    {"provider": "groq", "stage": "generation", "key": [secret()]},
    {"provider": "gemini", "stage": "verification", "key": secret()},
    {"provider": "groq", "stage": "generation", "key": secret() + "\nSECRET_KEY=changed"},
    [secret()],
])
def test_invalid_secret_payload_is_not_echoed_or_written(setup, payload):
    path, app, client = setup
    allow_admin(app)
    before = path.read_bytes()
    response = client.post("/api/admin/pool/credentials", json=payload)
    assert response.status_code == 400
    assert secret() not in response.text
    assert path.read_bytes() == before


def test_invalid_json_is_generic(setup):
    path, app, client = setup
    allow_admin(app)
    response = client.post("/api/admin/pool/credentials", content='{"key":"' + secret(), headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and secret() not in response.text


def test_new_verifier_key_preserves_existing_quota_and_saved_selection(setup):
    path, app, client = setup
    old, new = secret("gemini", "B"), secret("gemini", "C")
    credentials.add("gemini", "verification", old)
    settings = credentials.get_settings()
    identity = provider_quota.quota_identity(settings.GEMINI_BASE_URL, settings.GEMINI_MODEL_NAME, old)
    provider_quota._BLOCKS[identity] = (time.time() + 3600, "daily limit")
    selection = {"enabled": True, "config": {"majors": ["riazi"]}, "produced": 7, "status": "waiting_for_quota"}
    pool_service._save(selection)
    result = credentials.add("gemini", "verification", new)
    group = next(g for g in result["groups"] if g["stage"] == "verification")
    assert group["daily_limited"] == 1 and group["available"] == 1 and group["active"]
    assert result["health"]["blocked"] is False
    assert provider_quota.blocked_quota(identity)
    assert pool_service.snapshot() == selection
    assert old not in json.dumps(result) and new not in json.dumps(result)


def test_adding_groq_does_not_unblock_exhausted_gemini_verification(setup):
    path, app, client = setup
    verifier = secret("gemini", "B")
    credentials.add("gemini", "verification", verifier)
    settings = credentials.get_settings()
    identity = provider_quota.quota_identity(settings.GEMINI_BASE_URL, settings.GEMINI_MODEL_NAME, verifier)
    provider_quota._BLOCKS[identity] = (time.time() + 3600, "daily limit")
    result = credentials.add("groq", "generation", secret())
    assert result["added"]
    assert result["health"]["blocked"]
    assert result["health"]["provider"] == "gemini"
    assert result["health"]["stage"] == "verification"
    assert result["health"]["retry_at"]
    # A genuinely available verifier key wakes the same saved run and clears
    # the overall blocker, without clearing the exhausted key's history.
    result = credentials.add("gemini", "verification", secret("gemini", "C"))
    assert result["health"]["blocked"] is False
    assert provider_quota.blocked_quota(identity)


def test_concurrent_additions_are_not_lost(setup):
    path, app, client = setup
    keys = [secret(letter=letter) for letter in "ABCDE"]
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda key: credentials.add("groq", "generation", key), keys))
    assert all(result["added"] for result in results)
    assert set(dotenv_values(path)["POOL_GROQ_API_KEYS"].split(",")) == set(keys)


def test_env_override_and_existing_file_keys_are_both_preserved(setup, monkeypatch):
    path, app, client = setup
    first, second, third = [secret(letter=letter) for letter in "ABC"]
    path.write_text(path.read_text() + f"POOL_GROQ_API_KEYS='{first}'\n")
    monkeypatch.setenv("POOL_GROQ_API_KEYS", second)
    credentials.add("groq", "generation", third)
    assert set(dotenv_values(path)["POOL_GROQ_API_KEYS"].split(",")) == {first, second, third}
    assert set(credentials.get_settings().POOL_GROQ_API_KEYS.split(",")) == {first, second, third}


def test_file_error_never_echoes_secret(setup, monkeypatch):
    path, app, client = setup
    allow_admin(app)
    monkeypatch.setattr(credentials.os, "replace", lambda *args: (_ for _ in ()).throw(OSError(secret())))
    response = client.post("/api/admin/pool/credentials", json={"provider": "groq", "stage": "generation", "key": secret()})
    assert response.status_code == 503 and secret() not in response.text
    assert "POOL_GROQ_API_KEYS" not in path.read_text()
    assert not list(path.parent.glob(".env.pool-keys-*"))


def test_new_keys_are_used_by_new_pool_clients_without_restart(setup, monkeypatch):
    from app.rag import llm
    path, app, client = setup
    groq, gemini = secret(), secret("gemini")
    credentials.add("groq", "generation", groq)
    credentials.add("gemini", "verification", gemini)
    monkeypatch.setattr(llm, "get_settings", credentials.get_settings)
    seen = []
    def factory(**kwargs):
        seen.append(kwargs)
        return llm.MockLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", factory)
    llm.get_pool_llm_client()
    llm.get_pool_verifier_client()
    assert any(call.get("provider") == "groq" and call.get("api_key") == groq for call in seen)
    assert any(call.get("provider") == "gemini" and call.get("api_key") == gemini for call in seen)
