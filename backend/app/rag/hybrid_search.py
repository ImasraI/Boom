"""
Hybrid search layer.

Combines semantic search results from ChromaDB
with lexical search results using Reciprocal Rank Fusion.

Both the semantic and lexical sides are scoped per user_id so
one account can never retrieve chunks from another account's
documents.
"""

from typing import Any, Dict, List, Optional

from app.rag.lexical_search import LexicalIndex
from app.rag.reranker import get_reranker, rerank_enabled
from functools import lru_cache
from app.rag.trace import clip, stage as trace_stage
from app.rag.vector_store import get_vector_store
from app.utils.logger import get_logger

logger = get_logger(__name__)


# Table layout shared by every retrieval stage in the trace viewer. The chunk
# id is what lets an admin follow ONE chunk through vector → BM25 → RRF →
# rerank and see which stage promoted or dropped it.
def _hit_columns(score_label: str = "امتیاز") -> List[Dict[str, str]]:
    return [
        {"key": "rank", "label": "رتبه"},
        {"key": "id", "label": "شناسه تکه"},
        {"key": "doc", "label": "سند"},
        {"key": "chunk", "label": "تکه"},
        {"key": "score", "label": score_label},
        {"key": "preview", "label": "متن تکه"},
    ]


def _hit_rows(results: List[Dict[str, Any]], *, score_key: str,
              limit: int = 25) -> List[Dict[str, Any]]:
    rows = []
    for rank, result in enumerate(results[:limit], start=1):
        rows.append({
            "rank": rank,
            "id": str(result.get("id") or ""),
            "doc": str(result.get("document_name") or ""),
            "chunk": result.get("chunk_index", ""),
            "score": round(float(result.get(score_key) or 0.0), 4),
            "preview": clip(result.get("content") or ""),
        })
    return rows


def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    top_k: int,
    rrf_k: int = 60,
    details: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Combine multiple ranked result lists using RRF.

    RRF does not require semantic and lexical scores
    to have the same numerical scale.

    ``details`` (used by the RAG trace viewer) receives, per chunk, the rank
    and 1/(k+rank) contribution it earned in EACH input list - that is what
    makes an answer explainable: a chunk can win purely on BM25, purely on
    vector distance, or on both agreeing.
    """

    # Final results indexed by chunk ID
    fused: Dict[str, Dict[str, Any]] = {}

    # Process each search result list
    for list_index, result_list in enumerate(result_lists):

        # rank starts at 1
        for rank, result in enumerate(
            result_list,
            start=1,
        ):

            # Use the real Chroma ID if available.
            #
            # For lexical results this ID is also stored
            # when the lexical index is built.
            chunk_id = result.get("id")

            # Fallback ID for old/legacy data
            if not chunk_id:
                chunk_id = (
                    f"{result.get('document_name', '')}"
                    f"::{result.get('chunk_index', '')}"
                )

            # Create entry if this chunk has not
            # appeared in another search result list.
            if chunk_id not in fused:
                fused[chunk_id] = {
                    **result,
                    "rrf_score": 0.0,
                }
            # RRF formula
            fused[chunk_id]["rrf_score"] += (
                1.0
                / (rrf_k + rank)
            )
            if details is not None:
                entry = details.setdefault(
                    chunk_id,
                    {"ranks": [None] * len(result_lists),
                     "parts": [0.0] * len(result_lists)},
                )
                entry["ranks"][list_index] = rank
                entry["parts"][list_index] = round(1.0 / (rrf_k + rank), 6)

    # Sort by final RRF score
    ranked_results = sorted(
        fused.values(),
        key=lambda result: result["rrf_score"],
        reverse=True,
    )

    # Return only final top-K results
    ranked_results = ranked_results[:top_k]

    for result in ranked_results:
        result["hybrid_score"] = round(
            result["rrf_score"],
            4,
        )
        result["score"] = result["hybrid_score"]

    return ranked_results


class HybridSearch:
    """
    Coordinates semantic and lexical retrieval.

    Keeps one in-memory BM25 index per user_id so lexical search
    never mixes chunks across accounts.
    """

    def __init__(
        self,
        vector_store,
    ):
        # Existing ChromaDB VectorStore
        self.vector_store = vector_store

        # One lexical index per user, built lazily
        self._lexical_indexes: Dict[int, LexicalIndex] = {}

    def refresh(self, user_id: int) -> None:
        """
        Rebuild the lexical index for a single user from the
        current contents of ChromaDB.

        Call this after any ingest/delete that affects that user's
        documents.
        """

        # Retrieve all chunks that belong to this user, PLUS the shared
        # corpus (content embedded under DEMO_USER_ID - books/OCR pages).
        try:
            from app.config import get_settings
            owner = int(get_settings().DEMO_USER_ID)
        except Exception:
            owner = user_id
        owners = [user_id] if user_id == owner else [user_id, owner]
        data = self.vector_store.collection.get(
            where={"user_id": {"$in": owners}},
            include=[
                "documents",
                "metadatas",
            ]
        )

        ids = data.get(
            "ids",
            [],
        )

        documents = data.get(
            "documents",
            [],
        )

        metadatas = data.get(
            "metadatas",
            [],
        )

        chunks = []

        # Convert Chroma data into our index format
        for index, content in enumerate(
            documents
        ):

            metadata = (
                metadatas[index]
                if index < len(metadatas)
                else {}
            )

            chunk_id = (
                ids[index]
                if index < len(ids)
                else None
            )

            chunks.append(
                {
                    "id": chunk_id,

                    "content": content,

                    "document_name": metadata.get(
                        "document_name",
                        "",
                    ),

                    "chunk_index": metadata.get(
                        "chunk_index",
                        index,
                    ),
                }
            )

        # Rebuild (or create) this user's lexical index
        index = self._lexical_indexes.setdefault(user_id, LexicalIndex())
        index.build(chunks)

    def _get_lexical_index(self, user_id: int) -> LexicalIndex:
        # Build the index on first use for a user that hasn't
        # been refreshed yet (e.g. right after server restart).
        if user_id not in self._lexical_indexes:
            self.refresh(user_id)

        return self._lexical_indexes[user_id]

    def search(
        self,
        query_text: str,
        query_embedding: List[float],
        user_id: int,
        top_k: int = 4,
        label: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search scoped to a single user's documents.

        1. Semantic search
        2. Lexical search
        3. RRF fusion

        ``label`` only tags the recorded trace stages (e.g. "qbank") so the
        viewer can tell the question-bank search apart from the book search.
        Results are identical either way.
        """

        prefix = f"{label} · " if label else ""

        # Retrieve more candidates from each search
        # before fusion.
        candidate_k = max(
            top_k * 5,
            20,
        )

        # -----------------------------
        # Semantic Search
        # -----------------------------

        if query_embedding:
            with trace_stage(prefix + "semantic_search", "جست‌وجوی برداری (Chroma)") as st:
                semantic_results = self.vector_store.similarity_search(
                    query_embedding=query_embedding,
                    top_k=candidate_k,
                    user_id=user_id,
                )
                st["command"] = (
                    "collection.query(query_embeddings=[{dims} dims], "
                    "n_results={k}, where={{\"user_id\": {{\"$in\": [...]}}}})"
                ).format(dims=len(query_embedding), k=candidate_k)
                st["meta"] = {
                    "collection": str(getattr(self.vector_store.collection, "name", "")),
                    "candidates_requested": candidate_k,
                    "embedding_dimensions": len(query_embedding),
                    "hits": len(semantic_results),
                    "output_count": len(semantic_results),
                    "score": "similarity = 1 - cosine distance",
                }
                st["columns"] = _hit_columns("شباهت کسینوسی")
                st["rows"] = _hit_rows(semantic_results, score_key="score")
        else:
            logger.warning("Empty query embedding; using lexical search only.")
            semantic_results = []
            with trace_stage(prefix + "semantic_search", "جست‌وجوی برداری (Chroma)") as st:
                st["meta"] = {"skipped": "embedding خالی برگشت؛ فقط جست‌وجوی واژگانی اجرا شد", "output_count": 0}

        # -----------------------------
        # Lexical Search
        # -----------------------------

        lexical_index = self._get_lexical_index(user_id)

        lexical_results = (
            lexical_index.search(
                query=query_text,
                top_k=candidate_k,
                label=prefix,
            )
        )

        # -----------------------------
        # Combine results
        # -----------------------------

        # Keep more candidates than top_k so the cross-encoder reranker
        # (if enabled) can reorder a wider pool before we cut down.
        from app.config import get_settings

        settings_rerank = rerank_enabled()
        reranker = get_reranker()
        # Probe availability only when reranking is on: ``available`` loads the
        # cross-encoder (seconds of CPU and a few hundred MB) and a disabled
        # reranker must not pay that on the first search of every process.
        rerank_ready = bool(reranker.available) if settings_rerank else False
        fusion_k = top_k
        if settings_rerank and rerank_ready:
            fusion_k = max(top_k, get_settings().RERANK_CANDIDATES)

        # Per-chunk contribution matrix: which list put this chunk where.
        details: Dict[str, Dict[str, Any]] = {}
        with trace_stage(prefix + "rrf_fusion", "ادغام رتبه‌ها (RRF)") as st:
            fused_results = (
                reciprocal_rank_fusion(
                    [
                        semantic_results,
                        lexical_results,
                    ],
                    top_k=fusion_k,
                    details=details,
                )
            )
            st["command"] = "rrf_score = Σ 1/(60 + rank) for each list that returned the chunk"
            st["meta"] = {
                "rrf_k": 60,
                "list_1": "برداری",
                "list_2": "واژگانی (BM25)",
                "semantic_hits": len(semantic_results),
                "lexical_hits": len(lexical_results),
                "unique_chunks": len(details),
                "candidates_kept": fusion_k,
                "output_count": len(fused_results),
                "top_k_after_rerank": top_k,
            }
            st["columns"] = [
                {"key": "rank", "label": "رتبه نهایی"},
                {"key": "id", "label": "شناسه تکه"},
                {"key": "doc", "label": "سند"},
                {"key": "chunk", "label": "تکه"},
                {"key": "rank_vector", "label": "رتبه برداری"},
                {"key": "rank_lexical", "label": "رتبه واژگانی"},
                {"key": "part_vector", "label": "سهم برداری"},
                {"key": "part_lexical", "label": "سهم واژگانی"},
                {"key": "rrf", "label": "امتیاز RRF"},
            ]
            rows = []
            for rank, result in enumerate(fused_results, start=1):
                chunk_id = result.get("id") or (
                    f"{result.get('document_name', '')}::{result.get('chunk_index', '')}"
                )
                detail = details.get(chunk_id, {"ranks": [None, None], "parts": [0.0, 0.0]})
                rows.append({
                    "rank": rank,
                    "id": str(result.get("id") or ""),
                    "doc": str(result.get("document_name") or ""),
                    "chunk": result.get("chunk_index", ""),
                    "rank_vector": detail["ranks"][0],
                    "rank_lexical": detail["ranks"][1],
                    "part_vector": detail["parts"][0],
                    "part_lexical": detail["parts"][1],
                    "rrf": round(float(result.get("rrf_score") or 0.0), 6),
                })
            st["rows"] = rows

        # -----------------------------
        # Cross-encoder rerank
        # -----------------------------
        if settings_rerank and rerank_ready and fusion_k > top_k:
            before = {str(c.get("id")): rank for rank, c in enumerate(fused_results, start=1)}
            with trace_stage(prefix + "rerank", "بازرتبه‌بندی (Cross-Encoder)") as st:
                fused_results = reranker.rerank(
                    query_text, fused_results, top_k=top_k,
                )
                st["command"] = (
                    "encode(query, chunk) pairs -> cross-encoder relevance, "
                    "sort by score, keep top {k}"
                ).format(k=top_k)
                st["meta"] = {
                    "model": get_settings().RERANK_MODEL_NAME,
                    "candidate_pairs": len(before),
                    "kept": len(fused_results),
                    "output_count": len(fused_results),
                    "score": "logit خروجی کراس‌انکودر (بالاتر = مرتبط‌تر)",
                }
                st["columns"] = [
                    {"key": "rank", "label": "رتبه جدید"},
                    {"key": "old_rank", "label": "رتبه قبل"},
                    {"key": "move", "label": "جابه‌جایی"},
                    {"key": "id", "label": "شناسه تکه"},
                    {"key": "doc", "label": "سند"},
                    {"key": "rerank_score", "label": "امتیاز بازرتبه"},
                    {"key": "hybrid_score", "label": "امتیاز RRF"},
                ]
                rows = []
                for rank, result in enumerate(fused_results, start=1):
                    old_rank = before.get(str(result.get("id")))
                    rows.append({
                        "rank": rank,
                        "old_rank": old_rank,
                        "move": (old_rank - rank) if old_rank else 0,
                        "id": str(result.get("id") or ""),
                        "chunk": result.get("chunk_index", ""),
                        "doc": str(result.get("document_name") or ""),
                        "rerank_score": round(float(result.get("rerank_score") or 0.0), 4),
                        "hybrid_score": round(float(result.get("hybrid_score") or 0.0), 6),
                    })
                st["rows"] = rows
        else:
            if not settings_rerank:
                reason = "RERANK_ENABLED=false در تنظیمات"
            elif not rerank_ready:
                reason = (
                    f"مدل {get_settings().RERANK_MODEL_NAME} بارگذاری نشد "
                    "(sentence-transformers نصب/قابل دسترس نیست)؛ نتیجه‌ها بدون بازرتبه‌بندی برگشتند"
                )
            else:
                reason = "همه کاندیدها از قبل برابر top_k بودند؛ چیزی برای بازرتبه‌بندی نبود"
            with trace_stage(prefix + "rerank", "بازرتبه‌بندی (Cross-Encoder)") as st:
                st["meta"] = {"skipped": reason, "output_count": len(fused_results),
                             "model": get_settings().RERANK_MODEL_NAME}

        return fused_results


@lru_cache
def get_hybrid_search() -> HybridSearch:
    """
    Create and cache the HybridSearch instance.

    The instance itself is a shared singleton, but it keeps
    separate lexical indexes per user internally.
    """

    vector_store = get_vector_store()

    return HybridSearch(vector_store)


@lru_cache
def get_question_hybrid_search() -> HybridSearch:
    """Hybrid search over the structured question-bank collection.

    Backed by the per-page vision transcriptions (questions, options,
    figure descriptions, lesson prose) embedded by app.rag.question_chunks.
    """
    from app.rag.vector_store import get_question_vector_store

    return HybridSearch(get_question_vector_store())
