"""Tests for Groq 429 (rate-limit) retry behavior in app/rag/llm.py.

Regression: Groq free-tier per-minute limits return 429 with a Retry-After
of ~60s, but the retry loop only waited 2-6s, so every attempt failed and
chats ended with the empty-answer fallback («پاسخی از مدل زبانی دریافت
نشد»). The client must honor the Retry-After header (capped) and the
streaming path must retry its connection phase too.
"""

import sys
import json
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import httpx

from app.rag import llm as llm_mod
from app.rag.llm import GroqLLMClient, _retry_after_seconds


OK_BODY = {
    "choices": [
        {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

STREAM_BODY = (
    b'data: ' + json.dumps({"choices": [{"delta": {"content": "hello"}}]}).encode()
    + b"\n\n" + b"data: [DONE]\n\n"
)


def _client(monkeypatch, handler, sleeps):
    """GroqLLMClient wired to a mock transport with a sleep recorder."""
    client = GroqLLMClient(
        api_key="test-key", model="llama-3.1-8b-instant",
        temperature=0.1, max_tokens=50,
    )
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod, "time", SimpleNamespace(sleep=sleeps.append))
    return client


def test_retry_after_helper_parses_and_caps():
    r429 = httpx.Response(429, headers={"Retry-After": "99999"})
    assert _retry_after_seconds(r429, fallback=4.0) == 90.0  # capped
    assert _retry_after_seconds(
        httpx.Response(429, headers={"Retry-After": "15"}), fallback=4.0
    ) == 15.0
    assert _retry_after_seconds(
        httpx.Response(429, headers={"Retry-After": "garbage"}), fallback=4.0
    ) == 4.0  # invalid header -> fallback
    assert _retry_after_seconds(httpx.Response(429), fallback=4.0) == 4.0


def test_generate_honors_retry_after_on_429(monkeypatch):
    """Two 429s with Retry-After: 60, then success -> sleeps must be 60s."""
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] <= 2:
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(200, json=OK_BODY)

    client = _client(monkeypatch, handler, sleeps)
    out = client.generate([{"role": "user", "content": "salam"}])
    assert out == "ok"
    assert state["n"] == 3
    assert sleeps == [60.0, 60.0]  # was [2, 4] before the fix -> all failed


def test_generate_gives_up_after_four_attempts(monkeypatch):
    """Persistent 429: exactly 4 attempts, returns empty string."""
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "60"})

    client = _client(monkeypatch, handler, sleeps)
    out = client.generate([{"role": "user", "content": "salam"}])
    assert out == ""
    assert state["n"] == 4


def test_generate_stream_retries_connect_phase_on_429(monkeypatch):
    """Stream 429s before any content is yielded: retry, no duplicates."""
    sleeps = []
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(200, content=STREAM_BODY)

    client = _client(monkeypatch, handler, sleeps)
    chunks = list(client.generate_stream([{"role": "user", "content": "salam"}]))
    assert chunks == ["hello"]
    assert state["n"] == 2
    assert sleeps == [60.0]


def test_generate_stream_non_429_error_yields_error_line(monkeypatch):
    """Non-429 HTTP errors are not retried; the error surfaces once."""
    sleeps = []

    def handler(request):
        return httpx.Response(500)

    client = _client(monkeypatch, handler, sleeps)
    chunks = list(client.generate_stream([{"role": "user", "content": "salam"}]))
    assert len(chunks) == 1 and chunks[0].startswith("خطا:")
    assert sleeps == []
