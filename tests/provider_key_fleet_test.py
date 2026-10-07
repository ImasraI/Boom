"""Key fleets respect cooldowns, account isolation, and successful usage."""
import time
import httpx
import pytest
from app.config import Settings
from app.rag import llm, provider_quota as quota
from app.rag.embeddings import FallbackEmbeddingModel
from app.rag.gemini_embeddings import GeminiEmbeddingModel


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(quota, '_state_file', lambda: None)
    for state in (quota._BLOCKS, quota._ACCESS_BLOCKS, quota._RATE_BLOCKS): state.clear()
    yield
    for state in (quota._BLOCKS, quota._ACCESS_BLOCKS, quota._RATE_BLOCKS): state.clear()


def fleet(monkeypatch):
    settings = Settings(_env_file=None, LLM_PROVIDER='groq', LLM_API_KEY='chat-only',
        POOL_LLM_PROVIDER='groq', POOL_LLM_API_KEY='draft-one',
        POOL_GROQ_API_KEYS='draft-two,draft-three,draft-two',
        POOL_LLM_MODEL_NAME='openai/gpt-oss-120b', POOL_LLM_FALLBACK_PROVIDERS='')
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    import app.config
    monkeypatch.setattr(app.config, 'get_settings', lambda: settings)
    return settings, llm.get_pool_llm_client()


def install(client, responses):
    requests = []
    replies = iter(responses)
    def handler(request):
        requests.append(request)
        return next(replies)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    return requests


def success():
    return httpx.Response(200, json={'choices':[{'message':{'content':'ready'}}],
        'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}})


def limited(period='minute'):
    return httpx.Response(429, headers={'retry-after':'60'},
        json={'error':{'message':f'tokens per {period} exhausted'}})


def test_groq_fleet_switches_minute_and_daily_limits_without_sleep(monkeypatch):
    settings, client = fleet(monkeypatch)
    monkeypatch.setattr(llm.time, 'sleep', lambda _: pytest.fail('No sleep before a configured backup'))
    assert len(client._clients) == 3
    first = install(client._clients[0], [limited()])
    second = install(client._clients[1], [limited('day')])
    third = install(client._clients[2], [success()])
    assert client.generate([]) == 'ready'
    assert len(first) == len(second) == len(third) == 1
    assert client.last_usage.total_tokens == 14
    assert client._clients[0].last_error_code == 'provider_rate_limit'
    assert client._clients[1].last_error_code == 'provider_daily_quota'
    # Newly-created clients must not probe the same unavailable keys again.
    fresh = llm.get_pool_llm_client()
    requests = [install(child, [success()]) for child in fresh._clients]
    assert fresh.generate([]) == 'ready'
    assert [len(calls) for calls in requests] == [0,0,1]


def test_recovered_key_can_be_used_after_last_key_is_limited(monkeypatch):
    _, client = fleet(monkeypatch)
    client._idx = 2
    install(client._clients[2], [limited()])
    primary = install(client._clients[0], [success()])
    assert client.generate([]) == 'ready'
    assert client.active_label == 'groq' and len(primary) == 1


def test_all_groq_daily_limits_stop_restock_until_reset(monkeypatch):
    settings, client = fleet(monkeypatch)
    for child in client._clients:
        quota.block_daily_quota(child._quota_identity, 'daily quota', retry_seconds=120)
    health = quota.pool_quota_status()
    assert health['blocked'] and health['code'] == 'provider_daily_quota'
    assert health['retry_after'] <= 120
    assert 'draft-' not in repr(health)


def test_all_minute_limited_keys_return_earliest_cooldown(monkeypatch):
    _, client = fleet(monkeypatch)
    for seconds, child in zip((120, 90, 60), client._clients):
        quota.block_rate_limit(child._quota_identity, seconds)
    status = quota.pool_quota_status()
    assert status['blocked'] and status['code']=='provider_rate_limit'
    assert 59 <= status['retry_after'] <= 60


def test_chat_stream_switches_before_emitting_and_keeps_usage(monkeypatch):
    _, client = fleet(monkeypatch)
    install(client._clients[0], [httpx.Response(401)])
    install(client._clients[1], [success()])
    assert list(client.generate_stream([])) == ['ready']
    assert client.last_usage.total_tokens == 14


@pytest.mark.parametrize('status', [401,429])
def test_embedding_query_backup_keeps_vector_dimensions(status):
    clients = [GeminiEmbeddingModel(key, dimensions=128) for key in ('embedding-one','embedding-two')]
    response = limited('day') if status == 429 else httpx.Response(status)
    # Native quota IDs differ, but the structured daily response is recognized.
    first = install(clients[0], [response])
    second = install(clients[1], [httpx.Response(200,json={'embedding':{'values':[1.0]*128}})])
    model = FallbackEmbeddingModel(clients)
    vector = model.embed_query('test query')
    assert len(vector) == 128 and len(first) == len(second) == 1
    assert sum(v*v for v in vector) == pytest.approx(1)
