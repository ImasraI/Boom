"""Actual response usage survives retries/fallbacks without saving any content."""
import json
from types import SimpleNamespace
import httpx
import pytest
from app.rag import llm, pool_usage as audit, mock_generation as mg


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, '_directory', lambda: tmp_path)
    monkeypatch.setattr(llm, 'blocked_access', lambda *a: '')
    monkeypatch.setattr(llm, 'blocked_quota', lambda *a: None)
    monkeypatch.setattr(llm, 'time', SimpleNamespace(sleep=lambda *a: None))
    return tmp_path


def response(content='ok', prompt=100, completion=20, finish='stop'):
    return dict(choices=[{'message':{'content':content},'finish_reason':finish}],
        usage={'prompt_tokens':prompt,'completion_tokens':completion,'total_tokens':prompt+completion})


def client(handler):
    instance=llm.GroqLLMClient(api_key='test-credential', model='openai/gpt-oss-120b',
                            temperature=0.1,max_tokens=100)
    instance.client.close()
    instance.client=httpx.Client(transport=httpx.MockTransport(handler))
    return instance


def test_empty_billed_response_and_retry_are_both_counted_but_no_secrets(isolated):
    replies=[response('', 100, 80, 'length'), response('private answer', 100, 30)]
    provider=client(lambda req: httpx.Response(200,json=replies.pop(0)))
    with audit.stage('drafting'):
        assert provider.generate([{'role':'user','content':'private prompt'}])=='private answer'
    group=audit.summary()['groups'][0]
    assert (group['responses'],group['empty_responses'],group['total_tokens'])==(2,1,310)
    assert group['stage']=='drafting'
    saved=next(isolated.glob('*.jsonl')).read_text()
    assert not any(secret in saved for secret in ('private answer','private prompt','test-credential'))


def test_quota_refusal_is_not_reported_as_token_spend():
    provider=client(lambda req: httpx.Response(429,json={'error':{'message':'rate limited'}}))
    with audit.stage('drafting'):
        assert not provider.generate([])
    assert audit.summary()['groups']==[]


def test_unknown_usage_and_corrupt_line_do_not_fake_zero_cost(isolated):
    audit.record_response('gemini','gemini-test', {'choices':[{'message':{'content':'ok'}}]})
    with next(isolated.glob('*.jsonl')).open('a') as f: f.write('broken line\n')
    group=audit.summary()['groups'][0]
    assert group['responses']==1 and group['unmeasured_responses']==1
    assert not audit.summary()['historical_backfill']


def test_stages_are_reset_after_failures_and_nested_calls():
    assert audit.current_stage()=='chat_planning'
    with audit.stage('repair'):
        audit.record_response('groq','model',response())
        with pytest.raises(RuntimeError), audit.stage('repair_verification'):
            audit.record_response('gemini','model',response())
            raise RuntimeError()
        assert audit.current_stage()=='repair'
    assert audit.current_stage()=='chat_planning'
    assert {r['stage'] for r in audit.summary()['groups']}=={'repair','repair_verification'}


def test_repair_stage_is_preserved_by_drafting_helper(monkeypatch):
    monkeypatch.setattr(mg,'wait_for_draft_slot',lambda *a,**kw: None)
    provider=client(lambda req: httpx.Response(200,json=response()))
    with audit.stage('repair'):
        mg._draft_generate(provider,'prompt',100,5)
    assert audit.summary()['groups'][0]['stage']=='repair'


def test_stream_records_final_groq_usage_once():
    chunks=[{'choices':[{'delta':{'content':'hello'}}]},
            {'choices':[], 'x_groq':{'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}}}]
    wire=''.join('data: '+json.dumps(row)+'\n\n' for row in chunks)+'data: [DONE]\n\n'
    provider=client(lambda req: httpx.Response(200,content=wire))
    assert list(provider.generate_stream([]))==['hello']
    group=audit.summary()['groups'][0]
    assert (group['responses'],group['empty_responses'],group['total_tokens'])==(1,0,14)
    assert provider.last_usage.total_tokens==14


def test_fallback_success_remains_separate_from_billed_empty_response():
    a=client(lambda req: httpx.Response(200,json=response('', 100, 10)))
    b=client(lambda req: httpx.Response(200,json=response('ok', 200, 40)))
    with audit.stage('verification'):
        assert not a.generate([])
        assert b.generate([])=='ok'
    group=audit.summary()['groups'][0]
    assert group['responses']==5 and group['total_tokens']==680
