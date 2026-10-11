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
            client.minimum_completion_tokens = 8192
            payload = client._prepare_payload([], 200)
            assert payload["reasoning_effort"] == "high"
            assert payload.get("max_completion_tokens", payload.get("max_tokens")) == 8192
    finally:
        for client in clients:
            client.client.close()
