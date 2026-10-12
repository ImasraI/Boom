import json

import pytest

from app.rag import mock_generation as mg, question_quality as quality
from app.rag.llm import GroqLLMClient, GeminiLLMClient


def question(**overrides):
    return {"text": "حاصل ۲+۲؟", "subject": "ریاضی", "topic": "عدد",
            "options": ["4", "3", "2", "1"], "answer": 0,
            "explanation": "۲+۲=۴", "_id": 1, **overrides}


class Client:
    last_error = ""
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []
    def generate(self, messages, **kwargs):
        self.calls.append((messages[-1]["content"], kwargs))
        return next(self.replies)


@pytest.mark.parametrize("reply", ['not json', '{"answers":{}}',
    '{"answers":{"1":true}}', '{"answers":{"1":4}}', '{"answers":{"1":"0"}}'])
def test_invalid_verifier_protocol_defers_instead_of_rejecting(reply):
    client = Client(reply)
    assert mg._verify_batch(client, [question()], 10) is None
    assert len(client.calls) == 1


def test_matching_key_does_not_certify_an_incorrect_explanation():
    client = Client('{"answers":{"1":0}}', '{"valid":false,"reason":"توضیح می‌گوید ۲+۲=۵"}')
    result = mg._verify_batch(client, [question(explanation="۲+۲=۵")], 10)
    assert result[1] is None and result.details[1]["status"] == "rejected"
    assert result.details[1]["solver_answer"] == 0


def test_blind_solver_and_auditor_must_both_agree():
    client = Client('{"answers":{"1":0}}', '{"valid":true,"reason":"۲+۲=۴، فقط گزینه اول درست است"}')
    result = mg._verify_batch(client, [question()], 10)
    assert result[1] == 0 and not result.deferred
    assert "۲+۲=۴" not in client.calls[0][0]  # explanation hidden from solver
    assert "۲+۲=۴" in client.calls[1][0]
    assert all(kwargs["max_tokens"] >= 8192 and kwargs["timeout"] >= 300 for _, kwargs in client.calls)


@pytest.mark.parametrize("audit", ['{"valid":true,"reason":"کلید درست است"}',
    '{"valid":null,"reason":"بازبین مطمئن نیست"}', 'invalid json', '{"valid":false}'])
def test_disagreement_or_failed_audit_remains_pending(audit):
    result = mg._verify_batch(Client('{"answers":{"1":1}}', audit), [question()], 10)
    assert 1 in result.deferred and result.details[1]["status"] == "pending"


@pytest.mark.parametrize("options", [["10/28", "20/56", "15/28", "1"],
    ["۰٫۵", "۰٫۵", "3", "4"], ["$\\frac{1}{2}$", "0.5", "3", "4"]])
def test_equivalent_choices_are_rejected(options):
    result = mg._verify_batch(Client('{"answers":{"1":0}}'), [question(options=options)], 10)
    assert result.details[1]["reason"] == "equivalent_options"
    assert not result.deferred


def test_high_reasoning_reaches_both_provider_payloads_without_changing_chat():
    clients = [GroqLLMClient(api_key="test", model="openai/gpt-oss-120b", temperature=0.2, max_tokens=1000),
               GeminiLLMClient(api_key="test", base_url="https://generativelanguage.googleapis.com/v1beta/openai", model="gemini-3.6-flash", temperature=0.2, max_tokens=1000)]
    try:
        assert clients[0]._prepare_payload([], 200)["reasoning_effort"] == "low"
        for client in clients:
            client.reasoning_effort = "high"
            client.json_mode = True
            client.minimum_completion_tokens = 8192
            payload = client._prepare_payload([], 200)
            assert payload["reasoning_effort"] == "high"
            assert payload.get("max_completion_tokens", payload.get("max_tokens")) == 8192
            assert payload["response_format"] == {"type": "json_object"}
    finally:
        for client in clients:
            client.client.close()


def test_gemini_truncated_json_retries_with_more_output_and_keeps_high_reasoning(monkeypatch):
    import httpx
    import app.rag.llm as llm
    requests = []
    def reply(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={"choices": [{"finish_reason": "length" if len(requests) == 1 else "stop",
            "message": {"content": '{"answers":' if len(requests) == 1 else '{"answers":{"1":0}}'}}]})
    monkeypatch.setattr(llm, "blocked_quota", lambda identity: None)
    monkeypatch.setattr(llm, "blocked_access", lambda identity: None)
    client = GeminiLLMClient(api_key="test", base_url="https://test.invalid", model="gemini-3.6-flash", temperature=0.0, max_tokens=8192)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(reply))
    client.reasoning_effort = "high"; client.json_mode = True
    try:
        assert client.generate([{"role":"user","content":"Return JSON"}]) == '{"answers":{"1":0}}'
        assert [r["max_tokens"] for r in requests] == [8192, 16384]
        assert all(r["reasoning_effort"] == "high" for r in requests)
    finally:
        client.client.close()


def test_array_draft_and_illegal_latex_escape_are_normalized_without_changing_key():
    raw = r'[{"subject":"ریاضی","topic":"تابع","text":"مجموع مجموعه $\{1,2,3\}$ چند است؟","options":["6","3","2","1"],"answer":0,"explanation":"$1+2+3=6$ و $\\frac{12}{2}=6$"}]'
    result = mg.parse_booklet(raw)
    assert len(result) == 1 and result[0]['answer'] == 0
    assert result[0]['options'] == ['6', '3', '2', '1']
    assert r'\{1,2,3\}' in result[0]['text'] and r'\frac{12}{2}' in result[0]['explanation']


@pytest.mark.parametrize('changes', [{'answer':True}, {'answer':1.9}, {'options':'1234'},
    {'options':['1','2','3','4','5']}])
def test_draft_protocol_does_not_truncate_keys_or_choices(changes):
    assert mg.parse_booklet(json.dumps({'questions':[question(**changes)]})) == []


def test_format_recovery_preserves_commas_inside_text_and_options():
    raw = r'{"questions":[{"subject":"ریاضی","text":"رشته a, } و b, ] را مقایسه کن","options":["a, }","b, ]","3","4",],"answer":0,},]}'
    row = mg.parse_booklet(raw)[0]
    assert row['text'] == 'رشته a, } و b, ] را مقایسه کن'
    assert row['options'][:2] == ['a, }', 'b, ]'] and row['answer'] == 0


@pytest.mark.parametrize('raw', [
    r'{"questions":[{"text":"$\{1,2\}$","options":["3","4","5","6"],"answer":0,}]}',
    '{"answers":{"1":0}}',
])
def test_groq_json_mode_failure_recovers_only_safe_serialization(raw, monkeypatch):
    import httpx
    import app.rag.llm as llm
    monkeypatch.setattr(llm, 'blocked_quota', lambda identity: None)
    monkeypatch.setattr(llm, 'blocked_access', lambda identity: None)
    client = GroqLLMClient(api_key='test-json', model='openai/gpt-oss-120b', temperature=0.2, max_tokens=8192)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400,
        json={'error': {'code': 'json_validate_failed', 'failed_generation': raw}})))
    client.json_mode = True; client.reasoning_effort = 'high'
    try:
        assert json.loads(client.generate([{'role':'user','content':'JSON'}])) == quality.json_value(raw)
        assert not client.last_error and not client.last_error_code
    finally: client.client.close()


def test_groq_incomplete_json_retries_without_downgrading_then_returns_clear_error(monkeypatch):
    import httpx
    import app.rag.llm as llm
    monkeypatch.setattr(llm, 'blocked_quota', lambda identity: None)
    monkeypatch.setattr(llm, 'blocked_access', lambda identity: None)
    monkeypatch.setattr(llm.time, 'sleep', lambda seconds: None)
    requests = []
    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={'error':{'code':'json_validate_failed','failed_generation':'{"questions":['}})
    client = GroqLLMClient(api_key='test-json', model='openai/gpt-oss-120b', temperature=0.2, max_tokens=8192)
    client.client.close(); client.client = httpx.Client(transport=httpx.MockTransport(reply))
    client.json_mode = True; client.reasoning_effort = 'high'
    try:
        assert client.generate([{'role':'user','content':'JSON'}]) == ''
        assert client.last_error_code == 'provider_json_error' and len(requests) == 4
        assert all(r['reasoning_effort']=='high' and r['max_completion_tokens']==8192 for r in requests)
    finally: client.client.close()


def test_pool_request_capacity_failure_switches_explicit_keys_without_lowering_reasoning(monkeypatch):
    import httpx
    import app.rag.llm as llm
    monkeypatch.setattr(llm, 'blocked_quota', lambda identity: None)
    monkeypatch.setattr(llm, 'blocked_access', lambda identity: None)
    clients = [GroqLLMClient(api_key='test-capacity-'+str(i),model='openai/gpt-oss-120b',
                            temperature=0.2,max_tokens=8192) for i in range(2)]
    requests = []
    def refused(request):
        requests.append(json.loads(request.content))
        return httpx.Response(413,json={'error':{'message':'Request exceeds this project capacity'}})
    def accepted(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"answers":{"1":0}}'}}]})
    for client, reply in zip(clients,(refused,accepted)):
        client.client.close();client.client=httpx.Client(transport=httpx.MockTransport(reply))
        client.reasoning_effort='high';client.json_mode=True
    fleet=llm.FallbackLLMClient(clients,['first','second'],switch_on_rate_limit=True)
    try:
        assert fleet.generate([{'role':'user','content':'JSON'}]) == '{"answers":{"1":0}}'
        assert not fleet.last_error and clients[0].last_error_code=='provider_request_too_large'
        assert len(requests)==2 and all(r['reasoning_effort']=='high' for r in requests)
        assert all(r['max_completion_tokens']==8192 for r in requests)
    finally:
        for client in clients:client.client.close()
