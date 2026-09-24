"""Tests for graceful degradation when page images are missing on disk.

Regression: boom_chat 500'd with FileNotFoundError when the vector store
returned a page-image hit whose PNG was absent (e.g. data/page_images not
synced to the machine). The chat must instead skip missing images and fall
back to text-only answering.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import pipeline


def _patch_nothing_available(monkeypatch):
    """Strip pipeline down to a deterministic, offline state."""
    settings = SimpleNamespace(TOP_K=2, IMAGE_TOP_K=2)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(
        pipeline, "get_embedding_model",
        lambda: SimpleNamespace(embed_query=lambda q: [0.0] * 4),
    )
    monkeypatch.setattr(
        pipeline, "get_hybrid_search",
        lambda: SimpleNamespace(search=lambda **kw: []),
    )
    monkeypatch.setattr(pipeline, "rewrite_query", lambda q, user_id: q)
    monkeypatch.setattr(pipeline, "_retrieve_question_bank_chunks",
                        lambda *a, **k: [])


HIT = {
    "document_name": "شیمی 1 خیلی سبز.pdf",
    "chunk_index": 107,
    "content": "1/شیمی 1 خیلی سبز.pdf/page_0108.png",
    "score": 0.9,
}


def test_load_page_images_skips_missing(monkeypatch):
    """Mixed hits: existing images load, missing ones are dropped."""
    _patch_nothing_available(monkeypatch)

    def fake_get_object(key):
        if key == "exists/page_0001.png":
            return b"png-bytes"
        raise FileNotFoundError(f"Local file not found: data/{key}")

    monkeypatch.setattr("app.utils.storage.get_object", fake_get_object)

    hits = [
        {"document_name": "a", "chunk_index": 0, "content": "exists/page_0001.png", "score": 1.0},
        HIT,
    ]
    usable, blobs = pipeline._load_page_images(hits)
    assert [h["content"] for h in usable] == ["exists/page_0001.png"]
    assert blobs == [b"png-bytes"]


def test_load_page_images_all_missing(monkeypatch):
    """All hits missing: caller sees empty lists and must go text-only."""
    _patch_nothing_available(monkeypatch)
    monkeypatch.setattr(
        "app.utils.storage.get_object",
        lambda key: (_ for _ in ()).throw(FileNotFoundError(key)),
    )
    usable, blobs = pipeline._load_page_images([HIT])
    assert usable == [] and blobs == []


BOOK_Q = "کتاب شیمی، مبحث استوکیومتری صفحه ۱۰۸ رو توضیح بده"  # grounded: must run retrieval


def test_answer_question_falls_back_to_text_when_images_missing(monkeypatch):
    """The exact user-reported crash: vision hit whose PNG is absent must
    produce a text answer, not FileNotFoundError."""
    _patch_nothing_available(monkeypatch)

    monkeypatch.setattr(pipeline, "_retrieve_image_hits", lambda *a, **k: [HIT])
    monkeypatch.setattr(
        pipeline, "get_vision_llm_client", lambda: object()  # not MockLLMClient
    )
    monkeypatch.setattr(
        "app.utils.storage.get_object",
        lambda key: (_ for _ in ()).throw(FileNotFoundError(f"Local file not found: {key}")),
    )

    text_client = SimpleNamespace(
        last_usage=SimpleNamespace(total_tokens=0),
        generate=lambda messages: "پاسخ متنی بدون تصویر",
    )
    monkeypatch.setattr(pipeline, "get_llm_client", lambda: text_client)

    result = pipeline.answer_question(BOOK_Q, user_id=1)
    assert result["answer"] == "پاسخ متنی بدون تصویر"
    # The dropped image hit must not be cited as a source.
    assert all(
        s.document_name != HIT["document_name"] or s.chunk_index != HIT["chunk_index"]
        for s in result["sources"]
    )


def test_answer_question_uses_vision_when_images_exist(monkeypatch):
    """Sanity: when images load, the vision path still wins."""
    _patch_nothing_available(monkeypatch)

    monkeypatch.setattr(pipeline, "_retrieve_image_hits", lambda *a, **k: [HIT])
    monkeypatch.setattr(
        pipeline, "get_vision_llm_client", lambda: object()  # not MockLLMClient
    )
    monkeypatch.setattr(
        "app.utils.storage.get_object", lambda key: b"png-bytes"
    )

    calls = {}

    class Vision:
        last_usage = SimpleNamespace(total_tokens=7)

        def generate(self, messages, images=None):
            calls["images"] = images
            return "پاسخ تصویری"

    monkeypatch.setattr(pipeline, "get_vision_llm_client", lambda: Vision())

    result = pipeline.answer_question(BOOK_Q, user_id=1)
    assert result["answer"] == "پاسخ تصویری"
    assert calls["images"] == [b"png-bytes"]
