"""Explicit Gemini draft backups never borrow chat or verifier credentials."""
import httpx
import pytest
from app.config import Settings
from app.rag import llm, provider_quota as quota, pool_credentials


@pytest.fixture
def configured(monkeypatch):
    settings=Settings(_env_file=None,LLM_PROVIDER='groq',LLM_API_KEY='chat-only',
        POOL_LLM_PROVIDER='groq',POOL_LLM_API_KEY='groq-draft',POOL_GROQ_API_KEYS='',
        POOL_LLM_MODEL_NAME='openai/gpt-oss-120b',POOL_LLM_FALLBACK_PROVIDERS='gemini',
        POOL_GEMINI_API_KEYS='gemini-draft-one,gemini-draft-two',GEMINI_API_KEY='vision-only',
        GEMINI_MODEL_NAME='gemini-test-model',GEMINI_PROXY='',
        GEMINI_BASE_URL='https://provider.example/v1',POOL_VERIFY_LLM_PROVIDER='gemini',
        POOL_VERIFY_LLM_API_KEY='verifier-only',POOL_VERIFY_LLM_MODEL_NAME='gemini-test-model',
        POOL_VERIFY_GEMINI_API_KEYS='',POOL_VERIFY_FALLBACK_PROVIDERS='')
    monkeypatch.setattr(llm,'get_settings',lambda:settings)
    monkeypatch.setattr(pool_credentials,'get_settings',lambda:settings)
    return settings


def install(child, response):
    calls=[]
    def respond(request):calls.append(request);return response
    child.client.close();child.client=httpx.Client(transport=httpx.MockTransport(respond))
    return calls


def test_daily_limited_groq_uses_only_explicit_gemini_generation_fleet(configured):
    client=llm.get_pool_llm_client()
    try:
        assert [c.model for c in client._clients]==['openai/gpt-oss-120b','gemini-test-model','gemini-test-model']
        assert [c.client.headers['authorization'] for c in client._clients]==[
            'Bearer groq-draft','Bearer gemini-draft-one','Bearer gemini-draft-two']
        first=install(client._clients[0],httpx.Response(429,json={'error':{'message':'tokens per day exhausted'}}))
        second=install(client._clients[1],httpx.Response(429,json={'error':{'details':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}}))
        third=install(client._clients[2],httpx.Response(200,json={'choices':[{'message':{'content':'ready'}}]}))
        assert client.generate([])=='ready'
        assert [len(c) for c in (first,second,third)]==[1,1,1]
        for child in client._clients:
            assert child.reasoning_effort=='high' and child.minimum_completion_tokens>=8192
    finally:
        for child in client._clients:child.client.close()


def test_generation_health_recognizes_available_backup_without_provider_probe(configured):
    identity=quota.quota_identity('https://api.groq.com/openai/v1',configured.POOL_LLM_MODEL_NAME,'groq-draft')
    quota.block_daily_quota(identity,'daily',retry_seconds=600)
    status=quota.pool_generation_status(configured)
    assert not status['blocked'] and status['provider']=='gemini' and status['fallback']


def test_backup_health_and_admin_counts_use_gemini_model(configured):
    quota.block_daily_quota(quota.quota_identity('https://api.groq.com/openai/v1',configured.POOL_LLM_MODEL_NAME,'groq-draft'),'daily',retry_seconds=600)
    for key in ('gemini-draft-one','gemini-draft-two'):
        quota.block_daily_quota(quota.quota_identity(configured.GEMINI_BASE_URL,configured.GEMINI_MODEL_NAME,key),'daily',retry_seconds=300)
    status=quota.pool_generation_status(configured)
    assert status['blocked'] and status['provider']=='gemini' and status['retry_after']<=300
    group=next(g for g in pool_credentials.snapshot()['groups'] if g['provider']=='gemini' and g['stage']=='generation')
    assert group['active'] and group['daily_limited']==2 and group['available']==0


def test_missing_generation_fleet_does_not_borrow_other_gemini_keys(configured):
    configured.POOL_GEMINI_API_KEYS=''
    assert quota.pool_gemini_generation_keys(configured)==[]
    client=llm.get_pool_llm_client()
    try:
        assert isinstance(client,llm.GroqLLMClient)
    finally:client.client.close()
