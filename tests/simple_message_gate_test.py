"""Tests for the simple-message retrieval gate in app/rag/pipeline.py.

Every chat message used to pay for an LLM query-rewrite call, embeddings and
book/image searches - even «سلام» or «مشتق 2x چی میشه؟», which need no book
retrieval. That waste is exactly how free-tier Groq rate limits (429) got
hit. Simple messages must go straight to the LLM; real study/plan/book
questions must still run full retrieval.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import pipeline


# --- _is_simple_message classification ------------------------------------

@pytest.mark.parametrize("q", [
    "سلام",
    "سلام!",
    "سلام. چطوری؟",
    "ممنون",
    "مرسی!",
    "hi",
    "hello there",
    "خداحافظ",
    "",
    "   ",
])
def test_greetings_are_simple(q):
    assert pipeline._is_simple_message(q) is True


@pytest.mark.parametrize("q", [
    "مشتق 2x چی میشه؟",          # the user's exact example
    "آب چند درجه میجوشه؟",
    "سرعت نور چنده؟",
    "2+2 چقدره؟",
    "معنی استوکیومتری چیه؟",
])
def test_short_selfcontained_questions_are_simple(q):
    assert pipeline._is_simple_message(q) is True


@pytest.mark.parametrize("q", [
    "برنامه هفتگی من رو تنظیم کن",
    "برای کنکور چه کتابی بخونم؟",
    "۲۰ تست فیزیک از کدوم کتاب؟",
    "برنامه امروز چیه؟",
    "فیزیک ۱ خیلی سبز صفحه ۱۵۴ تست‌های ۴۱ تا ۵۶ رو بگو",
    "برای آزمون ماز آماده‌م کن",
])
def test_plan_book_questions_are_not_simple(q):
    assert pipeline._is_simple_message(q) is False


def test_long_questions_are_not_simple():
    assert pipeline._is_simple_message("سلام " * 15) is False


# --- answer_question skips retrieval for simple messages -------------------

def _patch_offline(monkeypatch):
    settings = SimpleNamespace(TOP_K=2, IMAGE_TOP_K=2)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "rewrite_query", lambda q, user_id: q)


def test_simple_message_skips_retrieval(monkeypatch):
    """«سلام» must not touch embeddings/search at all."""
    _patch_offline(monkeypatch)
    calls = []

    def boom(*a, **k):  # any retrieval attempt would explode the test
        calls.append(1)
        raise AssertionError("retrieval machinery ran for a simple message")

    monkeypatch.setattr(pipeline, "get_embedding_model", boom)
    monkeypatch.setattr(pipeline, "get_hybrid_search", boom)

    client = SimpleNamespace(
        last_usage=SimpleNamespace(total_tokens=3),
        generate=lambda messages: "سلام! خوش اومدی.",
    )
    monkeypatch.setattr(pipeline, "get_llm_client", lambda: client)

    result = pipeline.answer_question("سلام", user_id=1)
    assert result["answer"] == "سلام! خوش اومدی."
    assert result["sources"] == []
    assert calls == []


def test_book_question_still_uses_retrieval(monkeypatch):
    """Book questions must go through the grounded path (retrieval runs)."""
    _patch_offline(monkeypatch)
    monkeypatch.setattr(
        pipeline, "get_embedding_model",
        lambda: SimpleNamespace(embed_query=lambda q: [0.0] * 4),
    )
    searched = {}
    monkeypatch.setattr(
        pipeline, "get_hybrid_search",
        lambda: SimpleNamespace(
            search=lambda **kw: (searched.update(kw) or [])
        ),
    )
    monkeypatch.setattr(pipeline, "_retrieve_question_bank_chunks",
                        lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "_retrieve_image_hits", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "get_vision_llm_client",
                        lambda: pipeline.MockLLMClient())

    client = SimpleNamespace(
        last_usage=SimpleNamespace(total_tokens=3),
        generate=lambda messages: "کتاب پیشنهادی: ...",
    )
    monkeypatch.setattr(pipeline, "get_llm_client", lambda: client)

    result = pipeline.answer_question("برای کنکور چه کتابی بخونم؟", user_id=1)
    assert "کتاب" in result["answer"]
    assert searched.get("query_text")  # retrieval actually ran


def test_streaming_simple_message_skips_retrieval(monkeypatch):
    """Streaming «سلام» must go straight to the LLM, no retrieval steps."""
    _patch_offline(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("retrieval machinery ran for a simple message")

    monkeypatch.setattr(pipeline, "get_embedding_model", boom)
    monkeypatch.setattr(pipeline, "get_hybrid_search", boom)

    client = SimpleNamespace(
        last_usage=SimpleNamespace(total_tokens=3),
        generate_stream=lambda messages: iter(["سلام!", " خوش اومدی."]),
    )
    monkeypatch.setattr(pipeline, "get_llm_client", lambda: client)

    events = list(pipeline.answer_question_stream("سلام", user_id=1))
    kinds = [json.loads(e)["type"] for e in events]
    texts = [json.loads(e)["data"] for e in events if json.loads(e)["type"] == "text"]
    assert "sources" in kinds
    assert texts == ["سلام!", " خوش اومدی."]


import json  # noqa: E402  (used by the streaming test above)
