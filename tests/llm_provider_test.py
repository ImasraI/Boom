"""Tests for the Cerebras client and per-task LLM provider routing.

Covers app/rag/llm.py:
  - CerebrasLLMClient: last_usage bookkeeping, Retry-After honored on 429,
    immediate stop on non-retryable HTTP errors, connect-phase-only stream
    retry, and reasoning-model payload shaping (gpt-oss analysis tokens).
  - get_pool_llm_client(): POOL_LLM_PROVIDER lets mock generation run on a
    different provider than the chatbot (e.g. Cerebras main + Gemini pool).
  - get_llm_client() gemini branch wires settings.GEMINI_PROXY through.
"""

import sys
import json
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import httpx

from app.rag import llm as llm_mod
from app.rag.llm import (
    CerebrasLLMClient,
    GeminiLLMClient,
    GroqLLMClient,
    MockLLMClient,
    get_llm_client,
    get_pool_llm_client,
)


OK_BODY = {
    "choices": [
        {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

STREAM_BODY = (
    b"data: " + json.dumps({"choices": [{"delta": {"content": "hello"}}]}).encode()
    + b"\n\n" + b"data: [DONE]\n\n"
)


def _settings(**over):
    base = dict(
        LLM_PROVIDER="cerebras",
        LLM_API_KEY="main-key",
        LLM_MODEL_NAME="main-model",
        LLM_TEMPERATURE=0.2,
        LLM_MAX_TOKENS=100,
        CEREBRAS_API_KEY="cerebras-key",
        CEREBRAS_BASE_URL="https://api.cerebras.ai/v1",
        CEREBRAS_MODEL_NAME="gpt-oss-120b",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL_NAME="gemini-3.6-flash",
        GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai",
        GEMINI_PROXY="http://127.0.0.1:10809",
        POOL_LLM_PROVIDER="",
        POOL_LLM_API_KEY="",
        POOL_LLM_MODEL_NAME="",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _cerebras_client(monkeypatch, handler, sleeps):
    client = CerebrasLLMClient(
        api_key="test-key", base_url="https://api.cerebras.ai/v1",
        model="gpt-oss-120b", temperature=0.1, max_tokens=50,
    )
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "time", SimpleNamespace(sleep=sleeps.append))
    return client


# --------------------------- CerebrasLLMClient ---------------------------

def test_cerebras_generate_sets_last_usage(monkeypatch):
    sleeps = []

    def handler(request):
        return httpx.Response(200, json=OK_BODY)

    client = _cerebras_client(monkeypatch, handler, sleeps)
    assert client.last_usage.total_tokens == 0  # zero until first success
    out = client.generate([{"role": "user", "content": "salam"}])
    assert out == "ok"
    assert client.last_usage == (10, 5, 15)


def test_cerebras_generate_resets_usage_after_failure(monkeypatch):
    """A failed call after a successful one must not report stale tokens."""
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(200, json=OK_BODY)
        return httpx.Response(500, json={"detail": "boom"})

    client = _cerebras_client(monkeypatch, handler, sleeps)
    client.generate([{"role": "user", "content": "one"}])
    assert client.last_usage.total_tokens == 15
    client.generate([{"role": "user", "content": "two"}])  # 500s until exhausted
    assert client.last_usage.total_tokens == 0


def test_cerebras_generate_honors_retry_after_on_429(monkeypatch):
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] <= 2:
            return httpx.Response(429, headers={"Retry-After": "30"})
        return httpx.Response(200, json=OK_BODY)

    client = _cerebras_client(monkeypatch, handler, sleeps)
    out = client.generate([{"role": "user", "content": "salam"}])
    assert out == "ok"
    assert state["n"] == 3
    assert sleeps == [30.0, 30.0]  # Retry-After honored, not the 2/4s backoff


def test_cerebras_generate_stops_on_non_retryable_error(monkeypatch):
    """401 is permanent: no retry sleeps, empty string immediately."""
    sleeps = []

    def handler(request):
        return httpx.Response(401, json={"detail": "bad key"})

    client = _cerebras_client(monkeypatch, handler, sleeps)
    out = client.generate([{"role": "user", "content": "salam"}])
    assert out == ""
    assert sleeps == []


def test_cerebras_reasoning_payload_shape():
    client = CerebrasLLMClient(
        api_key="k", base_url="https://api.cerebras.ai/v1",
        model="gpt-oss-120b", temperature=0.2, max_tokens=150,
    )
    payload = client._prepare_payload(
        [{"role": "user", "content": "hi"}], max_tokens=150
    )
    assert payload["reasoning_effort"] == "low"
    # A small budget must be lifted above the analysis-token floor.
    assert payload["max_completion_tokens"] == 1024
    assert "max_tokens" not in payload

    client_plain = CerebrasLLMClient(
        api_key="k", base_url="https://api.cerebras.ai/v1",
        model="llama3.1-8b", temperature=0.2, max_tokens=150,
    )
    payload_plain = client_plain._prepare_payload(
        [{"role": "user", "content": "hi"}], max_tokens=150
    )
    assert payload_plain["max_tokens"] == 150
    assert "reasoning_effort" not in payload_plain


def test_cerebras_stream_connection_retry(monkeypatch):
    """429 before any yield: retry the connection, then stream the body."""
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "10"})
        return httpx.Response(200, content=STREAM_BODY)

    client = _cerebras_client(monkeypatch, handler, sleeps)
    chunks = list(client.generate_stream([{"role": "user", "content": "salam"}]))
    assert chunks == ["hello"]
    assert state["n"] == 2
    assert sleeps == [10.0]


# ------------------------- per-task provider routing -------------------------

def test_pool_provider_override_builds_gemini_pool_client(monkeypatch):
    """Main=cerebras, POOL_LLM_PROVIDER=gemini -> pool talks to Gemini."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_PROVIDER="gemini"))
    client = get_pool_llm_client()
    assert isinstance(client, GeminiLLMClient)
    assert client.client.headers["authorization"] == "Bearer gemini-key"
    assert client.proxy == "http://127.0.0.1:10809"


def test_pool_provider_override_builds_groq_pool_client(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_PROVIDER="groq"))
    client = get_pool_llm_client()
    assert isinstance(client, GroqLLMClient)
    assert client.client.headers["authorization"] == "Bearer main-key"


def test_main_client_cerebras(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings())
    client = get_llm_client()
    assert isinstance(client, CerebrasLLMClient)
    assert client.model == "gpt-oss-120b"


def test_cerebras_without_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        CEREBRAS_API_KEY=""))
    assert isinstance(get_llm_client(), MockLLMClient)


# --------------------------- Gemini thinking mode ---------------------------

def test_gemini_thinking_model_pins_reasoning_off():
    """gemini-3.x thinks by default and the hidden tokens eat max_tokens
    (observed: 207/220 budget spent thinking -> empty answer). The client
    must pin reasoning_effort=none for predictable output size/latency."""
    client = GeminiLLMClient(
        api_key="k", base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-3.6-flash", temperature=0.2, max_tokens=300,
    )
    payload = client._prepare_payload([{"role": "user", "content": "hi"}])
    assert payload["reasoning_effort"] == "none"
    assert payload["max_tokens"] == 300


def test_gemini_older_model_keeps_default_payload():
    client = GeminiLLMClient(
        api_key="k", base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-flash", temperature=0.2, max_tokens=300,
    )
    payload = client._prepare_payload([{"role": "user", "content": "hi"}])
    assert "reasoning_effort" not in payload


def test_gemini_proxy_wired_in_factory(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        LLM_PROVIDER="gemini"))
    client = get_llm_client()
    assert isinstance(client, GeminiLLMClient)
    assert client.proxy == "http://127.0.0.1:10809"
