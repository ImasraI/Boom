"""Pool backups must honor remembered daily limits and never expose credentials."""
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.rag import llm, provider_quota as quota


def settings(**overrides):
    values = dict(LLM_PROVIDER="groq", LLM_API_KEY="chat-secret", LLM_MODEL_NAME="chat-model",
                  LLM_BASE_URL="https://api.groq.com/openai/v1", LLM_TEMPERATURE=0.2,
                  LLM_MAX_TOKENS=100, POOL_LLM_PROVIDER="gemini",
                  POOL_LLM_API_KEY="primary-secret", POOL_LLM_MODEL_NAME="pool-model",
                  POOL_GEMINI_API_KEYS="backup-secret", POOL_LLM_FALLBACK_PROVIDERS="",
                  GEMINI_API_KEY="vision-secret", GEMINI_MODEL_NAME="vision-model",
                  GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai",
                  GEMINI_PROXY="", CEREBRAS_API_KEY="", CEREBRAS_MODEL_NAME="cerebras-model",
                  CEREBRAS_BASE_URL="https://api.cerebras.ai/v1")
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def isolated_quota(monkeypatch):
    monkeypatch.setattr(quota, "_state_file", lambda: None)
    quota._BLOCKS.clear()
    quota._LOADED_PATHS.clear()
    yield
    quota._BLOCKS.clear()
    quota._LOADED_PATHS.clear()


def configure(monkeypatch, config):
    monkeypatch.setattr(llm, "get_settings", lambda: config)
    import app.config
    monkeypatch.setattr(app.config, "get_settings", lambda: config)


def install_transport(client, responses):
    calls = []
    replies = iter(responses)
    def handler(request):
        calls.append(request)
        return next(replies)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    return calls


def success():
    return httpx.Response(200, json={"choices":[{"message":{"content":"verified reply"}}],
                                    "usage":{"prompt_tokens":8,"completion_tokens":4,"total_tokens":12}})


def daily_limit():
    return httpx.Response(429, json={"error":{"details":[
        {"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}})


@pytest.mark.parametrize('status',[401,403])
def test_rejected_primary_uses_backup_without_retrying_same_key(monkeypatch,status):
    configure(monkeypatch,settings())
    client=llm.get_pool_llm_client()
    primary=install_transport(client._clients[0],[httpx.Response(status,json={'error':'rejected'})])
    backup=install_transport(client._clients[1],[success(),success()])
    assert client.generate([])==client.generate([])=='verified reply'
    assert len(primary)==1 and len(backup)==2
    assert quota.blocked_access(client._clients[0]._quota_identity)==f'HTTP {status}'
    for child in client._clients: child.client.close()


def test_access_denial_survives_restart_without_storing_credentials(monkeypatch,tmp_path):
    config=settings()
    configure(monkeypatch,config)
    state=tmp_path/'limits.json'
    monkeypatch.setattr(quota,'_state_file',lambda:state)
    identity=quota.quota_identity(config.GEMINI_BASE_URL,config.POOL_LLM_MODEL_NAME,config.POOL_LLM_API_KEY)
    quota.block_access(identity,401)
    quota._ACCESS_BLOCKS.clear();quota._LOADED_PATHS.clear()
    client=llm.get_pool_llm_client()
    primary=install_transport(client._clients[0],[])
    backup=install_transport(client._clients[1],[success()])
    assert client.generate([])=='verified reply' and not primary and len(backup)==1
    assert 'primary-secret' not in state.read_text() and 'backup-secret' not in state.read_text()
    for child in client._clients: child.client.close()


def test_all_access_denials_need_changed_credentials_not_a_daily_retry(monkeypatch):
    config=settings()
    configure(monkeypatch,config)
    for key in quota.pool_gemini_keys(config):
        quota.block_access(quota.quota_identity(config.GEMINI_BASE_URL,config.POOL_LLM_MODEL_NAME,key),401)
    status=quota.pool_quota_status()
    assert status['blocked'] and status['code']=='provider_access_denied' and 'retry_at' not in status
    config.POOL_GEMINI_API_KEYS='new-credential'
    assert not quota.pool_quota_status()['blocked']


def test_access_denied_primary_waits_only_for_daily_blocked_backup(monkeypatch):
    config=settings()
    configure(monkeypatch,config)
    quota.block_access(quota.quota_identity(config.GEMINI_BASE_URL,config.POOL_LLM_MODEL_NAME,config.POOL_LLM_API_KEY),401)
    quota.block_daily_quota(quota.quota_identity(config.GEMINI_BASE_URL,config.POOL_LLM_MODEL_NAME,'backup-secret'),'daily quota')
    status=quota.pool_quota_status()
    assert status['blocked'] and status['code']=='provider_daily_quota' and status['retry_after']>0


def test_daily_refusal_switches_to_backup_and_keeps_successful_usage(monkeypatch):
    configure(monkeypatch, settings())
    client = llm.get_pool_llm_client()
    first_calls = install_transport(client._clients[0], [daily_limit()])
    backup_calls = install_transport(client._clients[1], [success(), success()])
    assert client.generate([]) == client.generate([]) == "verified reply"
    assert len(first_calls) == 1 and len(backup_calls) == 2
    assert client.last_usage.total_tokens == 12
    assert client.last_error == "" and client.active_label == "gemini backup 1"
    for child in client._clients:
        child.client.close()


def test_persisted_primary_block_skips_network_and_does_not_hide_backup(monkeypatch, tmp_path, caplog):
    config = settings()
    configure(monkeypatch, config)
    state = tmp_path / "limits.json"
    monkeypatch.setattr(quota, "_state_file", lambda: state)
    identity = quota.quota_identity(config.GEMINI_BASE_URL, config.POOL_LLM_MODEL_NAME, config.POOL_LLM_API_KEY)
    quota.block_daily_quota(identity, "daily quota includes primary-secret")
    quota._BLOCKS.clear()
    quota._LOADED_PATHS.clear()  # simulate a restart: persisted reason is localized
    assert quota.pool_quota_status() == {"blocked":False}
    client = llm.get_pool_llm_client()
    primary_calls = install_transport(client._clients[0], [])
    backup_calls = install_transport(client._clients[1], [success()])
    assert client.generate([]) == "verified reply"
    assert not primary_calls and len(backup_calls) == 1
    assert "primary-secret" not in state.read_text() + caplog.text
    assert "backup-secret" not in caplog.text + repr(client._labels)
    for child in client._clients:
        child.client.close()


def test_all_daily_limits_stop_new_runs_until_earliest_reset(monkeypatch):
    config = settings(POOL_LLM_FALLBACK_PROVIDERS="gemini,unknown,cerebras", CEREBRAS_API_KEY="")
    configure(monkeypatch, config)
    now = datetime.now(timezone.utc).timestamp()
    for key, seconds in [("primary-secret",120),("backup-secret",60)]:
        identity = quota.quota_identity(config.GEMINI_BASE_URL, config.POOL_LLM_MODEL_NAME, key)
        quota._BLOCKS[identity] = (now+seconds, quota.DAILY_QUOTA_MESSAGE)
    status = quota.pool_quota_status()
    assert status["blocked"] and status["code"] == "provider_daily_quota"
    assert 58 <= status["retry_after"] <= 60
    assert datetime.fromisoformat(status["retry_at"]).timestamp() == now+60
    assert "secret" not in repr(status)
    client = llm.get_pool_llm_client()
    calls = [install_transport(child, []) for child in client._clients]
    assert client.generate([]) == ""
    assert all(not called for called in calls)
    assert client.last_usage == llm.ZERO_USAGE
    for child in client._clients:
        child.client.close()


def test_backup_keys_are_deduplicated_and_not_taken_from_chat_or_vision(monkeypatch):
    config = settings(POOL_GEMINI_API_KEYS=" primary-secret, backup-secret, backup-secret, , second-secret ")
    configure(monkeypatch, config)
    assert quota.pool_gemini_keys(config) == ["primary-secret","backup-secret","second-secret"]
    client = llm.get_pool_llm_client()
    assert len(client._clients) == 3
    assert [child.model for child in client._clients] == ["pool-model"]*3
    assert [child.client.headers["Authorization"] for child in client._clients] == [
        "Bearer primary-secret","Bearer backup-secret","Bearer second-secret"]
    for child in client._clients:
        child.client.close()


def test_minute_limit_uses_backoff_without_spending_backup(monkeypatch):
    configure(monkeypatch, settings())
    waits = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    client = llm.get_pool_llm_client()
    minute = httpx.Response(429, headers={"Retry-After":"2"}, json={"error":{"message":"per minute rate limit"}})
    primary_calls = install_transport(client._clients[0], [minute]*4)
    backup_calls = install_transport(client._clients[1], [])
    assert client.generate([]) == ""
    assert len(primary_calls) == 4 and not backup_calls
    assert waits and not quota.pool_quota_status()["blocked"]
    assert client._clients[0].last_error_code == ""
    for child in client._clients:
        child.client.close()


def test_explicit_usable_provider_fallback_keeps_restock_available(monkeypatch):
    config = settings(POOL_LLM_FALLBACK_PROVIDERS="groq")
    configure(monkeypatch, config)
    for key in quota.pool_gemini_keys(config):
        quota.block_daily_quota(quota.quota_identity(config.GEMINI_BASE_URL, config.POOL_LLM_MODEL_NAME, key), "daily quota")
    assert quota.pool_quota_status() == {"blocked":False}
    client = llm.get_pool_llm_client()
    assert client._labels == ["gemini","gemini backup 1","groq"]
    for child in client._clients:
        child.client.close()


def test_no_backup_and_non_gemini_primary_keep_existing_factory(monkeypatch):
    configure(monkeypatch, settings(POOL_GEMINI_API_KEYS=""))
    primary = llm.get_pool_llm_client()
    assert isinstance(primary, llm.GeminiLLMClient)
    primary.client.close()
    configure(monkeypatch, settings(POOL_LLM_PROVIDER="groq"))
    primary = llm.get_pool_llm_client()
    assert isinstance(primary, llm.GroqLLMClient)
    primary.client.close()


def test_backup_only_configuration_uses_the_first_real_credential(monkeypatch):
    configure(monkeypatch, settings(POOL_LLM_API_KEY="", GEMINI_API_KEY=""))
    client = llm.get_pool_llm_client()
    assert isinstance(client, llm.GeminiLLMClient)
    assert client.client.headers["Authorization"] == "Bearer backup-secret"
    client.client.close()


def test_provider_error_redacts_keys_before_admin_reporting():
    sensitive = "AQ." + "X"*45
    reason, terminal = llm._quota_reason(httpx.Response(429, json={"error":{
        "message":"daily quota for credential "+sensitive}}))
    assert terminal and sensitive not in reason and "[redacted]" in reason


def test_quota_guard_and_factory_resolve_whitespace_overrides_the_same_way(monkeypatch):
    config = settings(LLM_PROVIDER="gemini", POOL_LLM_PROVIDER="  ", POOL_LLM_MODEL_NAME=" ",
                      POOL_LLM_API_KEY="  ", POOL_GEMINI_API_KEYS="")
    configure(monkeypatch, config)
    client = llm.get_pool_llm_client()
    assert client.model == "vision-model"
    assert client.client.headers["Authorization"] == "Bearer vision-secret"
    quota.block_daily_quota(client._quota_identity, "daily quota")
    assert quota.pool_quota_status()["blocked"]
    client.client.close()
