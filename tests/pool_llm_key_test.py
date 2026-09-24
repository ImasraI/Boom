"""Tests for the separate pool LLM key (mock generation vs everything else).

Mock/pool booklet generation makes many large LLM calls and used to share
one key with the chatbot and planning - pool bursts 429'd user-facing chat.
POOL_LLM_API_KEY gives generation its own quota; an empty value must keep
the old shared-key behavior.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import llm as llm_mod
from app.rag import mock_generation
from app.rag.llm import GroqLLMClient, MockLLMClient, get_llm_client, get_pool_llm_client


def _settings(**over):
    base = dict(
        LLM_PROVIDER="groq",
        LLM_API_KEY="main-key",
        LLM_MODEL_NAME="main-model",
        LLM_TEMPERATURE=0.2,
        LLM_MAX_TOKENS=100,
        GEMINI_API_KEY="",
        GEMINI_MODEL_NAME="",
        GEMINI_BASE_URL="",
        POOL_LLM_API_KEY="",
        POOL_LLM_MODEL_NAME="",
        POOL_LLM_PROVIDER="",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _auth_key(client: GroqLLMClient) -> str:
    """The bearer key a Groq client would send (stored in httpx headers)."""
    return client.client.headers["authorization"].removeprefix("Bearer ")


def test_pool_key_empty_falls_back_to_shared_key(monkeypatch):
    """POOL_LLM_API_KEY unset -> pool uses the main key/model (old behavior)."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings())
    client = get_pool_llm_client()
    assert isinstance(client, GroqLLMClient)
    assert _auth_key(client) == "main-key"
    assert client.model == "main-model"


def test_pool_key_used_for_generation(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_API_KEY="pool-key"))
    client = get_pool_llm_client()
    assert isinstance(client, GroqLLMClient)
    assert _auth_key(client) == "pool-key"
    assert client.model == "main-model"  # model falls back to the main one


def test_pool_key_with_model_override(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_API_KEY="pool-key", POOL_LLM_MODEL_NAME="pool-model"))
    client = get_pool_llm_client()
    assert _auth_key(client) == "pool-key"
    assert client.model == "pool-model"


def test_chat_client_ignores_pool_key(monkeypatch):
    """The chatbot/planning factory must never pick up the pool key."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_API_KEY="pool-key"))
    client = get_llm_client()
    assert _auth_key(client) == "main-key"


def test_missing_pool_key_falls_back_to_mock_not_shared(monkeypatch):
    """Groq + empty effective key -> mock (same rule as the main path)."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        LLM_API_KEY="", POOL_LLM_API_KEY="   "))  # whitespace-only = unset
    assert isinstance(get_pool_llm_client(), MockLLMClient)


def test_booklet_generation_uses_pool_client(monkeypatch):
    """_generate_subject_questions (the per-subject booklet call) must go
    through get_pool_llm_client, not the shared-key factory."""
    used = {}

    class FakeClient:
        def generate(self, messages, max_tokens=None, timeout=None):
            used["ok"] = True
            return ""

    monkeypatch.setattr(mock_generation, "get_pool_llm_client",
                        lambda: FakeClient())
    monkeypatch.setattr(mock_generation, "retrieve_book_context",
                        lambda *a, **k: "")
    monkeypatch.setattr(mock_generation, "build_booklet_prompt",
                        lambda *a, **k: "p")
    monkeypatch.setattr(mock_generation, "parse_booklet", lambda raw: [])

    mock_generation._generate_subject_questions(
        user_id=1,
        row={"name": "ریاضی", "questions": 5},
        topics=["حد"],
        difficulty="easy",
        max_tokens=500,
        timeout=30,
    )
    assert used.get("ok") is True
