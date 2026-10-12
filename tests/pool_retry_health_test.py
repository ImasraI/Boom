"""Provider health must use the model and reset time that actually failed."""
import json
import time

import httpx
import pytest

from app.config import Settings
from app.rag import llm, provider_quota, pool_credentials


@pytest.mark.parametrize('message,header,expected', [
    ('tokens per day. Please try again in 19m59.664s.', '3', 1199.664),
    ('tokens per day. Please try again in 1h2m3.5s.', '60', 3723.5),
    ('tokens per day. Please try again in 10s.', '90', 90),
    ('tokens per day exhausted', '', 86400),
    ('tokens per day. Please try again in infinity.', 'invalid', 86400),
])
def test_daily_body_delay_takes_precedence_over_short_minute_header(message, header, expected):
    response = httpx.Response(429, headers={'retry-after':header}, json={'error':{'message':message}})
    assert llm._daily_retry_seconds(response) == pytest.approx(expected)


def test_groq_remembers_full_daily_body_delay_across_clients(monkeypatch):
    calls = []
    def refused(request):
        calls.append(1)
        return httpx.Response(429, headers={'retry-after':'3'}, json={
            'error':{'message':'tokens per day limit reached. Please try again in 20m.'}})
    clients = [llm.GroqLLMClient('offline-test-key', 'offline-test-model', 0, 100) for _ in range(2)]
    try:
        for client in clients:
            client.client.close()
            client.client = httpx.Client(transport=httpx.MockTransport(refused))
            assert client.generate([]) == ''
        assert len(calls) == 1
        until, _ = provider_quota.blocked_quota(clients[0]._quota_identity)
        assert 1190 < until - time.time() <= 1200
    finally:
        for client in clients: client.client.close()


def test_inactive_gemini_keys_are_not_checked_under_the_groq_model(monkeypatch):
    settings = Settings(_env_file=None, POOL_LLM_PROVIDER='groq', POOL_LLM_MODEL_NAME='groq-test-model',
        POOL_LLM_API_KEY='groq-offline', POOL_VERIFY_LLM_PROVIDER='gemini',
        POOL_VERIFY_LLM_MODEL_NAME='gemini-test-model', GEMINI_MODEL_NAME='gemini-test-model',
        POOL_VERIFY_LLM_API_KEY='same-gemini-key', POOL_GEMINI_API_KEYS='same-gemini-key',
        POOL_VERIFY_GEMINI_API_KEYS='', GEMINI_API_KEY='', POOL_VERIFY_FALLBACK_PROVIDERS='')
    monkeypatch.setattr(pool_credentials, 'get_settings', lambda: settings)
    identity = provider_quota.quota_identity(settings.GEMINI_BASE_URL, settings.GEMINI_MODEL_NAME, 'same-gemini-key')
    provider_quota.block_daily_quota(identity, 'daily', retry_seconds=3600)
    result = pool_credentials.snapshot()
    group = next(g for g in result['groups'] if g['provider']=='gemini' and g['stage']=='generation')
    assert not group['active'] and group['daily_limited']==1 and group['available']==0
    assert 'same-gemini-key' not in json.dumps(result)
