"""Tests for the RAG trace layer (app/rag/trace.py) and its admin API.

The trace viewer is only trustworthy if the numbers it shows are the numbers
the pipeline used: which chunk each search returned, at which rank, what RRF
contributed per list, and why the reranker was skipped. These tests drive the
recording helpers directly (no Chroma, no LLM, no network) and assert both the
recorded shape and the production no-op behaviour.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import trace as trace_mod
from app.rag.hybrid_search import HybridSearch, reciprocal_rank_fusion
from app.rag.lexical_search import LexicalIndex


@pytest.fixture(autouse=True)
def _clean_store():
    trace_mod.store.clear()
    yield
    trace_mod.store.clear()


def _hit(chunk_id, name, content, score=0.5, chunk_index=0):
    return {"id": chunk_id, "document_name": name, "chunk_index": chunk_index,
            "content": content, "score": score, "hybrid_score": score}


def test_stream_trace_survives_anyio_threadpool_advancement_and_close(monkeypatch):
    """StreamingResponse copies ContextVars for each synchronous next()."""
    import anyio
    from app.rag import pipeline
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(TOP_K=4))

    def pieces(question, user_id, *_):
        for index in range(2):
            assert trace_mod.active_trace().user_id == user_id
            with trace_mod.stage("piece", "بخش پاسخ") as part:
                part["meta"]["index"] = index
                yield f"{user_id}:{index}"
    monkeypatch.setattr(pipeline, "_answer_question_stream_impl", pieces)
    ended = object()
    def advance(iterator):
        result = next(iterator, ended)
        # Worker context is clean between two chunks and two users.
        assert trace_mod.active_trace() is None
        return result

    async def run():
        first = pipeline.answer_question_stream("first", 901)
        second = pipeline.answer_question_stream("second", 902)
        assert await anyio.to_thread.run_sync(advance, first) == "901:0"
        assert await anyio.to_thread.run_sync(advance, second) == "902:0"
        assert await anyio.to_thread.run_sync(advance, first) == "901:1"
        assert await anyio.to_thread.run_sync(advance, first) is ended
        await anyio.to_thread.run_sync(second.close)
        assert trace_mod.active_trace() is None
    anyio.run(run)
    runs = {item["user_id"]: trace_mod.store.get(item["id"])
            for item in trace_mod.store.list()}
    assert set(runs) == {901, 902}
    assert len(runs[901]["stages"]) == 2
    assert len(runs[902]["stages"]) == 1
    assert all(run["status"] != "running" for run in runs.values())


# --- the collector itself --------------------------------------------------

def test_stage_and_note_are_noops_without_a_trace():
    """The production chat path must not build rows it will not keep."""
    assert trace_mod.active_trace() is None
    with trace_mod.stage("anything", "برچسب") as st:
        st["rows"].append({"x": 1})  # throwaway dict, must not explode
    trace_mod.note(sources=3)  # no active trace -> silent
    assert trace_mod.active_trace() is None


def test_store_is_bounded_newest_first_and_kind_filtered():
    for index in range(trace_mod.TRACE_LIMIT + 10):
        trace = trace_mod.begin_trace("chat", question=f"سوال {index}")
        trace.finish()
    listing = trace_mod.store.list(kind="all", limit=100)
    assert len(listing) == trace_mod.TRACE_LIMIT
    # newest first, and the oldest 10 were evicted
    assert listing[0]["question"] == f"سوال {trace_mod.TRACE_LIMIT + 9}"
    assert all(item["stages"] == [] for item in listing)

    other = trace_mod.begin_trace("mock", question="دفترچه")
    other.finish()
    # The buffer stays bounded in total: the new mock evicted the oldest chat.
    counts = trace_mod.store.counts()
    assert counts == {"chat": trace_mod.TRACE_LIMIT - 1, "mock": 1}
    assert len(trace_mod.store.list(kind="mock", limit=10)) == 1
    assert trace_mod.store.clear("mock") == 1
    assert trace_mod.store.counts() == {"chat": trace_mod.TRACE_LIMIT - 1}


def test_begin_trace_is_visible_before_it_finishes():
    """A long generation run must appear in the viewer while it is running."""
    trace = trace_mod.begin_trace("mock", question="در حال ساخت")
    assert trace_mod.store.list(limit=1)[0]["status"] == "running"
    trace.note(chunks=2)
    trace.finish()
    detail = trace_mod.store.get(trace.id)
    assert detail["status"] == "ok"
    assert detail["summary"]["chunks"] == 2


def test_nested_traces_collapse_into_the_running_one():
    with trace_mod.record_trace("chat", question="بیرونی") as outer:
        with trace_mod.record_trace("mock", question="درونی") as inner:
            assert inner is outer
        with trace_mod.stage("s", "لایه") as st:
            st["rows"] = [{"a": 1}]
    assert trace_mod.store.counts() == {"chat": 1}
    detail = trace_mod.store.get(outer.id)
    assert [s["name"] for s in detail["stages"]] == ["s"]
    assert detail["status"] == "ok"


def test_failure_is_recorded_with_its_reason():
    with pytest.raises(RuntimeError):
        with trace_mod.record_trace("chat", question="خطا"):
            raise RuntimeError("provider exploded")
    latest = trace_mod.store.list(limit=1)[0]
    detail = trace_mod.store.get(latest["id"])
    assert detail["status"] == "error"
    assert "provider exploded" in detail["error"]


# --- retrieval stages ------------------------------------------------------

def test_rrf_details_expose_per_list_ranks_and_contributions():
    """A chunk can win on BM25 only, on vector only, or on both agreeing."""
    semantic = [_hit("a", "کتاب", "الف"), _hit("b", "کتاب", "ب")]
    lexical = [_hit("b", "کتاب", "ب"), _hit("c", "کتاب", "ج")]
    details = {}
    fused = reciprocal_rank_fusion([semantic, lexical], top_k=5, details=details)

    assert [row["id"] for row in fused] == ["b", "a", "c"]
    # b was 2nd on the vector side and 1st on BM25 -> wins on agreement.
    assert details["b"]["ranks"] == [2, 1]
    assert details["a"]["ranks"] == [1, None]
    assert details["c"]["ranks"] == [None, 2]
    assert details["b"]["parts"][0] == round(1 / 62, 6)
    assert details["b"]["parts"][1] == round(1 / 61, 6)
    assert fused[0]["rrf_score"] == pytest.approx(1 / 62 + 1 / 61)


def test_lexical_search_records_bm25_internals():
    index = LexicalIndex()
    index.build([
        {"id": "c1", "document_name": "فیزیک ۱", "chunk_index": 0,
         "content": "شتاب گرانش روی سطح زمین کمتر است"},
        {"id": "c2", "document_name": "فیزیک ۱", "chunk_index": 1,
         "content": "نیروی اصطکاک و ضریب آن"},
    ])
    with trace_mod.record_trace("playground", question="شتاب گرانش") as trace:
        index.search("شتاب گرانش", top_k=2)

    stage = next(s for s in trace.stages if s["name"] == "lexical_search")
    assert stage["meta"]["indexed_chunks"] == 2
    assert stage["meta"]["k1"] == 1.5
    assert stage["meta"]["b"] == 0.75
    assert "شتاب" in stage["meta"]["query_tokens"]
    assert "شتاب" in stage["meta"]["term_idf"]
    assert stage["meta"]["hits"] == 1
    assert stage["meta"]["scored_chunks"] == 1
    assert stage["rows"][0]["rank"] == 1
    assert stage["rows"][0]["chunk"] == 0
    assert "شتاب" in stage["rows"][0]["terms"]


class FakeVectorStore:
    """Minimal Chroma stand-in: enough for HybridSearch.refresh + search."""

    def __init__(self, documents):
        self._documents = documents
        store = self

        class FakeCollection:
            name = "test-collection"

            def get(self, where=None, include=None):
                return {
                    "ids": [d["id"] for d in store._documents],
                    "documents": [d["content"] for d in store._documents],
                    "metadatas": [{"document_name": d["document_name"],
                                   "chunk_index": d["chunk_index"]}
                                  for d in store._documents],
                }

        self.collection = FakeCollection()

    def similarity_search(self, query_embedding, top_k, user_id):
        return [_hit(d["id"], d["document_name"], d["content"], score=0.9 - i * 0.1,
                     chunk_index=d["chunk_index"])
                for i, d in enumerate(self._documents[:top_k])]


def test_hybrid_search_records_every_retrieval_stage(monkeypatch):
    monkeypatch.setattr("app.rag.hybrid_search.rerank_enabled", lambda: False)
    store = FakeVectorStore([
        {"id": "c1", "document_name": "فیزیک ۱", "chunk_index": 0, "content": "نیم‌ساز زاویه"},
        {"id": "c2", "document_name": "فیزیک ۱", "chunk_index": 1, "content": "شتاب گرانش"},
    ])
    search = HybridSearch(store)

    with trace_mod.record_trace("playground", question="نیم‌ساز زاویه") as trace:
        results = search.search("نیم‌ساز زاویه", [0.1] * 4, user_id=1, top_k=2, label="books")

    assert results
    names = [s["name"] for s in trace.stages]
    assert names == ["books · semantic_search", "books · lexical_search",
                     "books · rrf_fusion", "books · rerank"]
    semantic = trace.stages[0]
    assert semantic["meta"]["hits"] == 2
    assert "collection.query" in semantic["command"]

    fusion = trace.stages[2]
    assert fusion["meta"]["list_1"] == "برداری"
    assert fusion["meta"]["list_2"] == "واژگانی (BM25)"
    assert {c["key"] for c in fusion["columns"]} >= {"rank_vector", "rank_lexical", "rrf"}

    rerank = trace.stages[3]
    assert "RERANK_ENABLED=false" in rerank["meta"]["skipped"]


def test_rerank_stage_reports_moves_when_it_runs(monkeypatch):
    class FakeReranker:
        available = True

        def rerank(self, query, results, top_k=None):
            # Reverse the fused order, so every move is visible in the table.
            flipped = [dict(r, rerank_score=1.0 - i * 0.1)
                       for i, r in enumerate(reversed(results))]
            return flipped[:top_k] if top_k else flipped

    monkeypatch.setattr("app.rag.hybrid_search.rerank_enabled", lambda: True)
    monkeypatch.setattr("app.rag.hybrid_search.get_reranker", lambda: FakeReranker())
    # search() imports get_settings locally from app.config at call time.
    monkeypatch.setattr("app.config.get_settings",
                        lambda: SimpleNamespace(RERANK_CANDIDATES=4, DEMO_USER_ID=1,
                                                RERANK_MODEL_NAME="test-reranker"))
    store = FakeVectorStore([
        {"id": "c1", "document_name": "کتاب", "chunk_index": 0, "content": "الف"},
        {"id": "c2", "document_name": "کتاب", "chunk_index": 1, "content": "ب"},
    ])
    search = HybridSearch(store)

    with trace_mod.record_trace("playground", question="الف") as trace:
        results = search.search("الف", [0.1] * 4, user_id=1, top_k=1)

    rerank = next(s for s in trace.stages if s["name"] == "rerank")
    assert rerank["meta"]["candidate_pairs"] == 2
    assert rerank["meta"]["kept"] == 1
    assert rerank["rows"][0]["rank"] == 1
    # The table must show where the chunk came from and how it moved.
    assert rerank["rows"][0]["old_rank"] == 2
    assert rerank["rows"][0]["move"] == 1
    assert rerank["rows"][0]["rerank_score"] == 1.0
    assert results[0]["rerank_score"] == 1.0


# --- chat pipeline ---------------------------------------------------------

def _offline_pipeline(monkeypatch, pipeline, answer="پاسخ [منبع 1]"):
    settings = SimpleNamespace(TOP_K=2, IMAGE_TOP_K=2, DEMO_USER_ID=1)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_embedding_model",
                        lambda: SimpleNamespace(embed_query=lambda q: [0.1] * 4))
    hits = [_hit("c1", "فیزیک ۱ خیلی سبز", "نیم‌ساز زاویه را نصف می‌کند", score=0.7, chunk_index=3)]
    monkeypatch.setattr(pipeline, "get_hybrid_search",
                        lambda: SimpleNamespace(search=lambda **kw: list(hits)))
    monkeypatch.setattr(pipeline, "_retrieve_question_bank_chunks", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "_retrieve_image_hits", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "get_vision_llm_client", lambda: pipeline.MockLLMClient())
    client = SimpleNamespace(last_usage=SimpleNamespace(total_tokens=5),
                             generate=lambda messages, **kw: answer)
    monkeypatch.setattr(pipeline, "get_llm_client", lambda: client)
    return settings


def test_answer_question_records_the_whole_path(monkeypatch):
    from app.rag import pipeline

    _offline_pipeline(monkeypatch, pipeline)
    pipeline.answer_question("نیم‌ساز زاویه چیست؟", user_id=1)

    latest = trace_mod.store.list(limit=1)[0]
    assert latest["kind"] == "chat"
    detail = trace_mod.store.get(latest["id"])
    names = [stage["name"] for stage in detail["stages"]]
    assert names == ["query_rewrite", "embed_query", "image_search", "llm_generate",
                     "final_answer"]
    assert detail["status"] == "ok"

    # "how the question was made": original question in, rewritten query out.
    rewrite = detail["stages"][0]
    assert rewrite["meta"]["original"] == "نیم‌ساز زاویه چیست؟"
    embed = detail["stages"][1]
    assert embed["meta"]["dimensions"] == 4
    generate = detail["stages"][3]
    assert "messages" in generate["command"] or "generate" in generate["command"]
    assert "متن‌های مرجع" in generate["text"]["prompt"]

    final = detail["stages"][4]
    assert final["rows"][0]["doc"] == "فیزیک ۱ خیلی سبز"
    assert final["rows"][0]["chunk"] == 3
    assert final["meta"]["confidence_level"] in {"low", "medium", "high"}
    assert detail["summary"]["sources"] == 1


def test_simple_message_trace_shows_the_gate_and_no_retrieval(monkeypatch):
    from app.rag import pipeline

    settings = SimpleNamespace(TOP_K=2, IMAGE_TOP_K=2, DEMO_USER_ID=1)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_llm_client",
                        lambda: SimpleNamespace(last_usage=SimpleNamespace(total_tokens=1),
                                                generate=lambda messages: "سلام!"))
    pipeline.answer_question("سلام", user_id=1)

    detail = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    names = [stage["name"] for stage in detail["stages"]]
    assert names == ["simple_message_gate", "llm_generate", "final_answer"]
    assert detail["stages"][0]["meta"]["retrieval_skipped"] is True
    assert detail["stages"][2]["rows"] == []


def test_failed_retrieval_still_leaves_an_inspectable_trace(monkeypatch):
    from app.rag import pipeline

    _offline_pipeline(monkeypatch, pipeline)
    monkeypatch.setattr(pipeline, "get_embedding_model",
                        lambda: SimpleNamespace(embed_query=lambda q: 1 / 0))

    with pytest.raises(ZeroDivisionError):
        pipeline.answer_question("نیم‌ساز زاویه چیست؟", user_id=1)

    detail = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    assert detail["status"] == "error"
    assert "ZeroDivisionError" in detail["error"]


def test_empty_model_answer_is_flagged_instead_of_showing_zero_characters(monkeypatch):
    """Regression: the router swaps an empty model answer for a fallback message.

    The trace must say the model returned nothing - otherwise the viewer shows
    "۰ کاراکتر پاسخ" beside a reply the student actually received, which reads
    like a broken inspector rather than an empty provider response.
    """
    from app.rag import pipeline

    _offline_pipeline(monkeypatch, pipeline, answer="")
    result = pipeline.answer_question("نیم‌ساز زاویه چیست؟", user_id=1)
    assert result["answer"] == ""

    detail = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    final = next(s for s in detail["stages"] if s["name"] == "final_answer")
    assert final["meta"]["answer_characters"] == 0
    assert final["meta"]["empty_answer"] is True
    assert detail["summary"]["empty_answer"] is True
    assert detail["status"] == "error"
    assert "پیام جایگزین" in detail["error"]

    # A real answer keeps the flag and the status off.
    trace_mod.store.clear()
    _offline_pipeline(monkeypatch, pipeline, answer="پاسخ [منبع 1]")
    pipeline.answer_question("نیم‌ساز زاویه چیست؟", user_id=1)
    clean = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    assert "empty_answer" not in clean["summary"]
    assert clean["status"] == "ok"


def test_explain_retrieval_stops_before_the_model(monkeypatch):
    """The playground must never spend an answer-generation call."""
    from app.rag import pipeline

    _offline_pipeline(monkeypatch, pipeline)

    def no_llm():
        raise AssertionError("the playground must not call the answering model")

    monkeypatch.setattr(pipeline, "get_llm_client", no_llm)
    trace = pipeline.explain_retrieval("نیم‌ساز زاویه چیست؟", user_id=1)

    assert trace["kind"] == "playground"
    names = [stage["name"] for stage in trace["stages"]]
    assert "llm_generate" not in names
    rewrite = next(s for s in trace["stages"] if s["name"] == "query_rewrite")
    assert "غیرفعال" in rewrite["meta"]["skipped"]
    assert trace["summary"]["chunks"] == 1


# --- evaluator + ingestion kinds the panel offers as filters ---------------

def test_blind_verification_run_is_its_own_evaluation_trace(monkeypatch):
    """The evaluator the panel advertises must be reachable from the UI.

    Verification runs from the mock/arena routers *after* generation returns,
    so it is a top-level call and gets its own trace - not a collapsed stage
    inside the booklet trace. The panel's "ارزیابی سوأل" filter therefore
    fills up whenever a booklet is independently re-solved.
    """
    import json

    from app.rag import mock_generation as mg

    class Solver:
        """Solves the batch prompt, then answers the real audit protocol.

        The audit is deliberately NOT stubbed: the stage it records is the
        thing under test here.
        """

        last_error = ""

        def generate(self, messages, max_tokens=None, timeout=None, images=None):
            prompt = messages[-1]["content"]
            if prompt.startswith("QUALITY_AUDIT_V1"):
                return json.dumps({"valid": True, "reason": "کلید و توضیح سازگارند"},
                                  ensure_ascii=False)
            return json.dumps({"answers": {"1": 0}})

    solver = Solver()
    monkeypatch.setattr(mg, "get_pool_verifier_client", lambda: solver)
    monkeypatch.setattr(mg, "_VERIFY_BATCH_SIZE", 10)

    questions = [{"_id": 1, "subject": "ریاضی", "topic": "", "text": "سوال ۱",
                  "options": ["الف", "ب", "ج", "د"], "answer": 0,
                  "explanation": ""}]
    kept = mg.verify_and_repair_booklet(questions, user_id=2, timeout=10)
    assert kept and kept[0]["verification_status"] == "verified"

    detail = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    assert detail["kind"] == "evaluation"
    assert detail["kind_label"] == trace_mod.KIND_LABELS["evaluation"]
    names = [stage["name"] for stage in detail["stages"]]
    assert names == ["verify_batch", "verify_llm", "quality_audit"]
    batch, solve, audit = detail["stages"]

    # The blind solve: solver index vs stored key, per question, in a table.
    assert batch["rows"][0]["stored"] == 0
    assert batch["rows"][0]["solver"] == 0
    assert batch["rows"][0]["match"] is True
    # ...and it provably did not see the key it is validating.
    assert "بدون کلید" in solve["meta"]["sees"]
    assert json.loads(solve["text"]["raw"]) == {"answers": {"1": 0}}

    assert "ارزیابی" in audit["label"]
    assert audit["meta"]["stored_answer"] == 0
    assert "QUALITY_AUDIT_V1" in audit["text"]["prompt"]
    assert "کلید و توضیح سازگارند" in audit["text"]["raw"]

    assert detail["summary"]["audit"] == "True"
    assert detail["summary"]["audit_reason"] == "کلید و توضیح سازگارند"
    assert detail["summary"]["verified"] == 1
    assert detail["summary"]["questions"] == 1
    assert detail["status"] == "ok"


def test_ingest_trace_lists_the_chunks_it_stored(monkeypatch):
    from app.rag import pipeline

    stored = {}

    class Store:
        def add_chunks(self, document_name, chunks, embeddings, user_id=None):
            stored.update(document=document_name, chunks=len(chunks), user_id=user_id)
            return len(chunks)

    monkeypatch.setattr(pipeline, "get_vector_store", lambda: Store())
    monkeypatch.setattr(
        pipeline, "get_embedding_model",
        lambda: SimpleNamespace(embed_documents=lambda chunks: [[0.1] * 4 for _ in chunks]))
    monkeypatch.setattr(
        pipeline, "get_hybrid_search",
        lambda: SimpleNamespace(refresh=lambda user_id: None))

    total = pipeline.ingest_document("فیزیک ۱ خیلی سبز", "نیم‌ساز " * 400, user_id=3)
    assert total > 0
    assert stored["chunks"] == total and stored["user_id"] == 3

    detail = trace_mod.store.get(trace_mod.store.list(limit=1)[0]["id"])
    assert detail["kind"] == "ingest"
    assert detail["kind_label"] == trace_mod.KIND_LABELS["ingest"]
    assert detail["title"] == "فیزیک ۱ خیلی سبز"
    assert detail["summary"]["stored"] == total
    stage = detail["stages"][0]
    assert stage["name"] == "ingest_embed"
    assert stage["meta"]["chunks"] == total
    assert stage["meta"]["stored_chunks"] == total
    assert stage["command"] == "embed_documents(chunks) → vector_store.add_chunks(...)"
    assert len(stage["rows"]) == total
    assert stage["rows"][0]["preview"]


# --- admin API surface -----------------------------------------------------

def test_rag_inspector_router_is_admin_gated():
    from app.routers import rag_trace

    gate = [dep.dependency for dep in rag_trace.router.dependencies]
    assert any(getattr(fn, "__name__", "") == "require_admin" for fn in gate), gate
    paths = {route.path for route in rag_trace.router.routes}
    assert paths == {
        "/api/admin/rag/config",
        "/api/admin/rag/traces",
        "/api/admin/rag/traces/{trace_id}",
        # The lazy vector map of one run: read-only, and behind the same gate.
        "/api/admin/rag/traces/{trace_id}/embedding-map",
        "/api/admin/rag/playground",
    }


def test_trace_endpoints_return_stored_traces(monkeypatch):
    from app.routers import rag_trace

    with trace_mod.record_trace("chat", title="سوال", user_id=1) as trace:
        with trace_mod.stage("lexical_search", "جست‌وجوی واژگانی") as st:
            st["rows"] = [{"rank": 1}]

    # No HTTP layer needed: the handlers read the same process-local store the
    # pipeline writes to (that is the point of the in-memory buffer).
    listing = rag_trace.list_traces(response=SimpleNamespace(headers={}), kind="all", limit=25)
    assert listing["traces"][0]["id"] == trace.id
    assert listing["traces"][0]["stages"] == []

    detail = rag_trace.get_trace(trace.id, response=SimpleNamespace(headers={}))
    assert detail["trace"]["stages"][0]["name"] == "lexical_search"

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        rag_trace.get_trace("missing-id", response=SimpleNamespace(headers={}))
    assert excinfo.value.status_code == 404

    cleared = rag_trace.clear_traces(response=SimpleNamespace(headers={}), kind="all")
    assert cleared["removed"] == 1
    assert trace_mod.store.list(limit=5) == []


def test_playground_endpoint_returns_a_trace_without_a_model(monkeypatch):
    from app.rag import pipeline
    from app.routers import rag_trace

    _offline_pipeline(monkeypatch, pipeline)
    monkeypatch.setattr(pipeline, "get_llm_client",
                        lambda: pytest.fail("playground called the answering model"))

    result = rag_trace.playground(
        rag_trace.PlaygroundRequest(question="نیم‌ساز زاویه چیست؟", user_id=1,
                                    rewrite=False, include_images=True),
        response=SimpleNamespace(headers={}),
    )
    assert result["trace"]["kind"] == "playground"
    assert "error" not in result


def test_failed_playground_run_serves_its_own_trace_not_the_newest(monkeypatch):
    """Regression: the failure branch served whichever playground trace was newest.

    Two admin runs interleave: while request A is still retrieving, request B
    starts *and finishes*, so the newest playground trace belongs to B. A's
    failure must still be explained by A's own run - the stages that show where
    it broke - not by B's successful trace.
    """
    from app.rag import pipeline
    from app.routers import rag_trace

    _offline_pipeline(monkeypatch, pipeline)
    interleaved = {}

    def failing_embed(*args, **kwargs):
        other = trace_mod.begin_trace("playground", title="پرسش هم‌زمان",
                                      question="پرسش هم‌زمان")
        with other.stage("embed_query", "بردارسازی پرسش") as st:
            st["meta"] = {"dimensions": 4}
        other.finish()
        interleaved["other"] = other.id
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr(pipeline, "_embed_traced", failing_embed)

    result = rag_trace.playground(
        rag_trace.PlaygroundRequest(question="پرسش شکست‌خورده", user_id=1, rewrite=False),
        response=SimpleNamespace(headers={}),
    )

    served = result["trace"]
    assert served["id"] != interleaved["other"]
    # The newest trace really is the other request's, so the old lookup would fail here.
    assert trace_mod.store.list(limit=1)[0]["id"] == interleaved["other"]
    assert served["question"] == "پرسش شکست‌خورده"
    assert served["status"] == "error"
    assert "ZeroDivisionError" in result["error"]
    # ...and the other request's run is intact, not overwritten by this one.
    untouched = trace_mod.store.get(interleaved["other"])
    assert untouched["status"] == "ok"
    assert [stage["name"] for stage in untouched["stages"]] == ["embed_query"]
    assert [stage["name"] for stage in served["stages"]] == ["query_rewrite"]


# --- payload bounds + credential redaction ---------------------------------

def test_a_hundred_thousand_character_prompt_is_capped_before_it_is_served():
    """Regression: the store bounded how many traces it kept, not how big they were."""
    import json

    trace = trace_mod.begin_trace("chat", question="س" * 5000)
    with trace.stage("llm_generate", "تولید پاسخ") as stage:
        stage["text"]["prompt"] = "الف" + "ب" * 100_018  # 100,019 characters
        stage["text"]["raw"] = "پ" * 30_000
        stage["command"] = "x" * 9000
        stage["meta"]["note"] = "م" * 9000
        stage["columns"] = [{"key": f"c{i}", "label": "ل" * 500} for i in range(40)]
        stage["rows"] = [{"n": i, "text": "ر" * 400}
                         for i in range(trace_mod.ROW_LIMIT + 60)]
    trace.fail("e" * 5000)
    trace.finish()
    detail = trace_mod.store.get(trace.id)
    served = json.dumps(detail, ensure_ascii=False)

    assert len(detail["question"]) <= trace_mod.QUESTION_LIMIT
    assert len(detail["error"]) <= trace_mod.ERROR_LIMIT
    assert len(detail["title"]) <= trace_mod.TITLE_LIMIT

    stage = detail["stages"][0]
    assert stage["text"]["prompt"].startswith("الف")
    assert len(stage["text"]["prompt"]) <= trace_mod.FIELD_LIMIT
    assert len(stage["text"]["raw"]) <= trace_mod.FIELD_LIMIT
    assert len(stage["command"]) <= trace_mod.TEXT_LIMIT
    assert len(stage["meta"]["note"]) <= trace_mod.TEXT_LIMIT
    assert len(stage["columns"]) == 40
    assert all(len(column["label"]) <= trace_mod.TITLE_LIMIT
               for column in stage["columns"])
    assert len(stage["rows"]) <= trace_mod.ROW_LIMIT
    # The long prompt is gone from what is served, not merely trimmed by a bit.
    assert "ب" * trace_mod.FIELD_LIMIT not in served
    assert detail["payload_characters"] <= trace_mod.TRACE_PAYLOAD_LIMIT


def test_one_trace_cannot_serve_an_unbounded_payload():
    """Per-field caps are not enough: many fat stages still add up."""
    import json

    trace = trace_mod.begin_trace("chat", question="پرسش سنگین")
    for group in range(40):
        with trace.stage(f"stage_{group}", "مرحلهٔ سنگین") as stage:
            stage["rows"] = [{"n": index, "text": "ر" * 650} for index in range(20)]
    trace.finish()
    detail = trace_mod.store.get(trace.id)

    # No stage is dropped silently - a stage that ran must stay visible...
    assert len(detail["stages"]) == 40
    # ...but the whole record stays inside the per-trace bound, and says so.
    assert detail["payload_characters"] <= trace_mod.TRACE_PAYLOAD_LIMIT
    assert len(json.dumps(detail["stages"], ensure_ascii=False)) <= trace_mod.TRACE_PAYLOAD_LIMIT
    assert detail["summary"]["payload_truncated"] is True
    assert any(stage["meta"].get("truncated_rows") for stage in detail["stages"])


def test_credentials_are_redacted_from_every_served_field():
    """A key reaches the viewer through URLs, errors, prompts and the question."""
    import json

    key = "gsk_" + "D" * 20  # dummy, shaped like a Groq key
    bearer = '.'.join(('eyJhbGciOiJIUzI1NiJ9', '')) + "dummy" * 4
    userinfo = f"https://admin:{key}@embeddings.local/v1"
    trace = trace_mod.begin_trace(
        "chat", title=f"خطای سرویس {userinfo}", question=f"چرا کلید {key} کار نمی‌کند؟",
    )
    with trace.stage("llm_generate", "تولید پاسخ") as stage:
        stage["command"] = f"POST https://api.groq.com/openai/v1/chat/completions?api_key={key}"
        stage["meta"] = {"base_url": userinfo,
                         "error": f"401 Unauthorized — Authorization: Bearer {bearer}"}
        stage["text"]["prompt"] = f"Authorization: Bearer {bearer}\nکلید: {key}"
        stage["rows"] = [{"doc": "کتاب", "preview": f"token={key}&page=2"}]
    trace.fail(f"provider error: {userinfo}?access_token={key}")
    trace.finish()
    detail = trace_mod.store.get(trace.id)
    served = json.dumps(detail, ensure_ascii=False)

    assert key not in served
    assert bearer not in served
    assert trace_mod.REDACTED in served

    stage = detail["stages"][0]
    assert f"api_key={trace_mod.REDACTED}" in stage["command"]
    assert stage["meta"]["base_url"] == f"https://{trace_mod.REDACTED}@embeddings.local/v1"
    assert f"Bearer {trace_mod.REDACTED}" in stage["meta"]["error"]
    assert trace_mod.REDACTED in stage["text"]["prompt"]
    assert trace_mod.REDACTED in stage["rows"][0]["preview"]
    assert trace_mod.REDACTED in detail["title"]
    assert trace_mod.REDACTED in detail["question"]
    assert trace_mod.REDACTED in detail["error"]


# --- stage timings ---------------------------------------------------------

def test_lexical_search_time_covers_idf_scoring_and_sorting(monkeypatch):
    """Regression: the timer closed after tokenisation, so a slow search read 0.0 ms."""
    import builtins
    import time

    from app.rag import lexical_search

    index = LexicalIndex()
    index.build([
        {"id": "c1", "document_name": "فیزیک ۱", "chunk_index": 0,
         "content": "شتاب گرانش روی سطح زمین کمتر است"},
        {"id": "c2", "document_name": "فیزیک ۱", "chunk_index": 1,
         "content": "شتاب و نیروی اصطکاک"},
        {"id": "c3", "document_name": "فیزیک ۲", "chunk_index": 2,
         "content": "ضریب اصطکاک ایستایی"},
    ])

    real_sum = builtins.sum
    calls = {"n": 0}

    def slow_sum(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:  # injected delay inside the scoring loop
            time.sleep(0.075)
        return real_sum(*args, **kwargs)

    # sums the length-normalisation term per scored chunk, i.e. well after
    # tokenisation: exactly the work the old timer stopped before.
    monkeypatch.setattr(lexical_search, "sum", slow_sum, raising=False)

    with trace_mod.record_trace("playground", question="شتاب گرانش") as trace:
        results = index.search("شتاب گرانش", top_k=3)

    stage = next(s for s in trace.stages if s["name"] == "lexical_search")
    assert calls["n"] >= 1
    assert stage["ms"] >= 74.0, stage["ms"]
    # The delay changed nothing about the ranking, only about the reported time.
    assert [row["id"] for row in results] == ["c1", "c2"]
    assert stage["meta"]["hits"] == 2


# --- config read must not load models --------------------------------------

def test_rag_config_reports_the_reranker_without_loading_it(monkeypatch):
    """Regression: reading the config probed ``available`` and loaded the model."""
    from app.rag import reranker
    from app.routers import rag_trace

    def must_not_load(self):
        raise AssertionError("reading the RAG config must not load the reranker")

    monkeypatch.setattr(reranker.CrossEncoderReranker, "_load", must_not_load)
    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    reranker.get_reranker.cache_clear()
    try:
        response = SimpleNamespace(headers={})
        config = rag_trace.rag_config(response=response)
        assert config["rerank_enabled"] is True
        assert config["rerank_state"] == "unloaded"
        assert config["rerank_available"] is False

        entry = reranker.get_reranker()
        entry._model = object()
        loaded = rag_trace.rag_config(response=response)
        assert loaded["rerank_state"] == "loaded"
        assert loaded["rerank_available"] is True

        # A failed load stays failed instead of reading as "not yet loaded".
        entry._model = None
        entry._failed = True
        failed = rag_trace.rag_config(response=response)
        assert failed["rerank_state"] == "failed"
        assert failed["rerank_available"] is False

        monkeypatch.setattr(reranker, "rerank_enabled", lambda: False)
        assert rag_trace.rag_config(response=response)["rerank_state"] == "disabled"
    finally:
        reranker.get_reranker.cache_clear()


# --- the playground runs the chat's own retrieval assembly -----------------

def test_explain_retrieval_assembles_question_bank_first_without_duplicates(monkeypatch):
    """Question bank first, one entry per chunk id, images with the OCR fallback."""
    from app.rag import pipeline

    settings = SimpleNamespace(TOP_K=4, IMAGE_TOP_K=2, DEMO_USER_ID=1)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_embedding_model",
                        lambda: SimpleNamespace(embed_query=lambda query: [0.1] * 4))
    book_hits = [_hit("c1", "کتاب", "کتاب تکرارشده"),
                 _hit("c2", "کتاب", "کتاب دوم"),
                 _hit("shared", "کتاب", "در هر دو مجموعه هست")]
    qa_hits = [_hit("qa1", "بانک", "سؤال ۱", score=0.9),
               _hit("shared", "بانک", "در هر دو مجموعه هست")]
    monkeypatch.setattr(pipeline, "get_hybrid_search",
                        lambda: SimpleNamespace(search=lambda **kw: list(book_hits)))
    monkeypatch.setattr(pipeline, "_retrieve_question_bank_chunks",
                        lambda *a, **k: list(qa_hits))
    monkeypatch.setattr(pipeline, "_retrieve_image_hits", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "_resolve_ocr_page_images",
                        lambda chunks, user_id: [_hit("page7", "فیزیک ۱.pdf", "[صفحه ۷]")])
    monkeypatch.setattr(pipeline, "get_llm_client",
                        lambda: pytest.fail("the playground must not call the answering model"))

    trace = pipeline.explain_retrieval("سؤال؟", user_id=1, include_images=True)
    names = [stage["name"] for stage in trace["stages"]]
    assert names == ["query_rewrite", "embed_query", "image_search", "retrieval_assembly"]

    assembly = next(s for s in trace["stages"] if s["name"] == "retrieval_assembly")
    rows = assembly["rows"]
    # question bank first, then books, one entry per chunk id, ranked 1..n
    assert [row["origin"] for row in rows] == ["بانک سؤال", "بانک سؤال", "کتاب‌ها", "کتاب‌ها"]
    assert [row["id"] for row in rows] == ["qa1", "shared", "c1", "c2"]
    assert [row["rank"] for row in rows] == [1, 2, 3, 4]
    assert assembly["meta"]["final_chunks"] == 4
    assert assembly["meta"]["from_question_bank"] == 2
    assert assembly["meta"]["from_books"] == 2
    assert assembly["meta"]["deduplicated_chunks"] == 1
    assert assembly["meta"]["question_bank_hits"] == 2
    assert assembly["meta"]["book_hits"] == 3
    assert trace["summary"]["chunks"] == 4

    # No page images from the vector search -> the OCR chunk becomes the page image.
    image = next(s for s in trace["stages"] if s["name"] == "image_search")
    assert image["meta"]["source"] == "تبدیل تکه‌های OCR به تصویر صفحه"
    assert image["meta"]["hits"] == 1
    assert trace["summary"]["image_source"] == "تبدیل تکه‌های OCR به تصویر صفحه"


def test_chat_and_playground_share_one_retrieval_assembly(monkeypatch):
    """The inspector must show the chunk set a real answer was built from."""
    from app.rag import pipeline

    _offline_pipeline(monkeypatch, pipeline)
    calls = []
    real = pipeline._assemble_retrieval

    def recorder(*args, **kwargs):
        # The chat path passes no flags: it takes the assembly's defaults.
        calls.append((kwargs.get("include_question_bank", True),
                      kwargs.get("include_images", True)))
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_assemble_retrieval", recorder)
    pipeline.answer_question("نیم‌ساز زاویه چیست؟", user_id=1)
    pipeline.explain_retrieval("نیم‌ساز زاویه چیست؟", user_id=1,
                              include_question_bank=False, include_images=False)

    # Both paths go through the same helper, and the playground's controls only
    # switch its optional shelves off - they never reroute the assembly.
    assert calls == [(True, True), (False, False)]
    playground = trace_mod.store.get(trace_mod.store.list(kind="playground", limit=1)[0]["id"])
    names = [stage["name"] for stage in playground["stages"]]
    assert "retrieval_assembly" in names and "qbank_search" not in names
    assert "llm_generate" not in names


@pytest.mark.parametrize("render", [
    lambda secret: secret,
    lambda secret: f"X-API-Key: {secret}",
    lambda secret: '{"api_key": "' + secret + '"}',
    lambda secret: "https://provider.invalid/?%61pi_key=" + secret + "&page=2",
    lambda secret: "https://provider.invalid/#access_token=" + secret,
])
def test_trace_masks_new_gemini_and_unshaped_credentials(render):
    import json
    dummy = "AQ." + "D" * 48
    assert dummy not in trace_mod.redact(render(dummy))
    unshaped = "D" * 32
    if render(unshaped) != unshaped:
        assert unshaped not in trace_mod.redact(render(unshaped))
    trace = trace_mod.begin_trace("playground", meta={"api_key": unshaped})
    with trace.stage("provider", "Provider") as stage:
        stage["text"]["prompt"] = render(dummy)
        stage["meta"] = {"x-api-key": unshaped, dummy: "dummy field"}
        assert dummy not in json.dumps(stage, ensure_ascii=False)
        assert unshaped not in json.dumps(stage, ensure_ascii=False)
    assert unshaped not in json.dumps(trace.to_dict(), ensure_ascii=False)


def test_literal_jwt_is_redacted_without_an_authorization_header():
    import json
    jwt = ".".join(("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjMifQ", "dummySignature123"))
    trace = trace_mod.begin_trace("chat", question=f"Token pasted: {jwt}")
    with trace.stage("provider", "Provider") as stage:
        stage["meta"]["raw_error"] = jwt
        stage["text"]["prompt"] = jwt
    assert jwt not in json.dumps(trace.to_dict(), ensure_ascii=False)


def test_playground_error_response_and_log_use_the_redacted_message(monkeypatch):
    import json
    from app.rag import pipeline
    from app.routers import rag_trace
    dummy = "gsk_" + "D" * 40
    trace = trace_mod.begin_trace("playground", question="dummy")
    trace.fail("Provider refused " + dummy)
    trace.finish()
    logs = []
    monkeypatch.setattr(rag_trace.logger, "warning", lambda fmt, *args: logs.append(fmt % args))
    def fail(*args, **kwargs):
        raise pipeline.RetrievalRunError(trace.id, "Provider refused " + dummy)
    monkeypatch.setattr(pipeline, "explain_retrieval", fail)
    result = rag_trace.playground(rag_trace.PlaygroundRequest(question="dummy"),
                                 response=SimpleNamespace(headers={}))
    assert dummy not in json.dumps(result, ensure_ascii=False)
    assert dummy not in " ".join(logs)
    assert "Provider refused" in result["error"]
    def early_fail(*args, **kwargs):
        raise RuntimeError("Early failure " + dummy)
    monkeypatch.setattr(pipeline, "explain_retrieval", early_fail)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        rag_trace.playground(rag_trace.PlaygroundRequest(question="dummy"),
                            response=SimpleNamespace(headers={}))
    assert dummy not in " ".join(logs)


def test_running_trace_bounds_mutations_depth_and_collections_before_storage():
    import json
    trace = trace_mod.begin_trace("mock", meta={f"k{i}": "x" * 700 for i in range(200)})
    with trace.stage("draft_llm", "Draft") as stage:
        stage["text"]["prompt"] = "x" * 100_000
        stage["meta"]["nested"] = {"loop": None}
        cyclic = {}; cyclic["self"] = cyclic
        stage["meta"]["cyclic"] = cyclic
        stage["rows"] = [{"index": i, "preview": "x" * 700} for i in range(2000)]
        stage["rows"].extend([{"extra": i} for i in range(2000)])
        stage["meta"].update({f"m{i}": "x" * 700 for i in range(2000)})
        assert len(stage["text"].get("prompt", "")) <= trace_mod.FIELD_LIMIT
        assert len(stage["meta"]) <= trace_mod.COLLECTION_LIMIT
        assert len(stage["rows"]) <= trace_mod.ROW_LIMIT
        assert len(json.dumps(trace.stages, ensure_ascii=False)) <= trace_mod.TRACE_PAYLOAD_LIMIT
        assert len(json.dumps(trace.to_dict(), ensure_ascii=False)) <= trace_mod.TRACE_PAYLOAD_LIMIT


def test_metadata_heavy_many_stage_trace_has_a_hard_whole_record_limit():
    import json
    trace = trace_mod.begin_trace("mock")
    for index in range(trace_mod.STAGE_LIMIT + 30):
        with trace.stage(f"draft_{index}", "Draft") as stage:
            stage["meta"] = {f"field_{j}": "x" * 700 for j in range(4)}
            stage["text"]["prompt"] = "x" * 4000
    assert len(trace.stages) <= trace_mod.STAGE_LIMIT
    assert trace.summary["omitted_stages"] == 30
    assert len(json.dumps(trace.stages, ensure_ascii=False)) <= trace_mod.TRACE_PAYLOAD_LIMIT
    for running in (True, False):
        if not running: trace.finish()
        data = trace.to_dict()
        assert data["summary"]["payload_truncated"] is True
        assert len(json.dumps(data, ensure_ascii=False)) <= trace_mod.TRACE_PAYLOAD_LIMIT
        assert data["payload_characters"] <= trace_mod.TRACE_PAYLOAD_LIMIT
