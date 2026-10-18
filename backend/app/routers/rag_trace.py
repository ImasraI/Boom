"""Admin-only RAG inspector API ("بررسی RAG").

Serves the in-memory traces recorded by ``app.rag.trace``: what a chat answer,
a mock generation run, an evaluation or an ingestion actually did, stage by
stage, including the chunks each search returned and the prompts sent.

Endpoints (all gated by ``deps.require_admin``):
  GET    /api/admin/rag/config                 pipeline knobs + trace limits
  GET    /api/admin/rag/traces?kind=&limit=    newest-first list (no stages)
  GET    /api/admin/rag/traces/{id}            one trace, every stage
  GET    /api/admin/rag/traces/{id}/embedding-map  2-D map of the query embedding
  DELETE /api/admin/rag/traces?kind=           drop the buffer (or one kind)
  POST   /api/admin/rag/playground             retrieval-only rerun of a question

Traces hold chunk text and prompts, so every response is ``no-store`` and the
whole router is admin-gated. Nothing here is persisted: a restart starts empty.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth.deps import require_admin
from ..config import get_settings
from ..rag import trace as trace_mod
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin/rag", tags=["admin-rag"],
                   dependencies=[Depends(require_admin)])

STORED_ONLY = "متن‌ها و پرسش‌ها در حافظهٔ موقتی سرور نگه داشته می‌شوند و با ری‌استارت پاک می‌شوند."

MISSING_TRACE = ("این رد در حافظهٔ سرور نیست؛ شاید ری‌استارت شده یا از ۵۰ مورد آخر حذف شده است.")


class PlaygroundRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[int] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    # Off by default: rewriting costs an LLM call on the chat key.
    rewrite: bool = False
    include_question_bank: bool = True
    include_images: bool = False


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/config")
def rag_config(response: Response):
    """The knobs the retrieval pipeline actually runs with right now."""
    _no_store(response)
    settings = get_settings()
    from ..rag.reranker import get_reranker, rerank_enabled

    reranker = get_reranker()
    return {
        "default_user_id": int(settings.DEMO_USER_ID),
        "top_k": settings.TOP_K,
        "image_top_k": settings.IMAGE_TOP_K,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL_NAME,
        "vision_provider": settings.VISION_LLM_PROVIDER,
        "vision_model": settings.VISION_LLM_MODEL_NAME,
        "rerank_enabled": rerank_enabled(),
        # Reading the config must not pull the cross-encoder into memory: the
        # model loads on the first search that needs it. One of
        # disabled / unloaded / loaded / failed, truthfully.
        "rerank_state": reranker.state(),
        "rerank_available": reranker.loaded,
        "rerank_model": settings.RERANK_MODEL_NAME,
        "rerank_candidates": settings.RERANK_CANDIDATES,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "trace_limit": trace_mod.store.limit,
        "kinds": trace_mod.KIND_LABELS,
        "notice": STORED_ONLY,
    }


@router.get("/traces")
def list_traces(response: Response, kind: str = "all", limit: int = 25):
    """Newest-first traces without their stages (the list the panel renders)."""
    _no_store(response)
    limit = max(1, min(int(limit), trace_mod.store.limit))
    return {
        "traces": trace_mod.store.list(kind=kind, limit=limit),
        "counts": trace_mod.store.counts(),
        "limit": trace_mod.store.limit,
        "kinds": trace_mod.KIND_LABELS,
    }


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, response: Response):
    _no_store(response)
    trace = trace_mod.store.get(trace_id)
    if trace is None:
        # Traces are in memory only, so an old id (or a restart) simply misses.
        raise HTTPException(404, MISSING_TRACE)
    return {"trace": trace}


@router.get("/traces/{trace_id}/embedding-map")
def trace_embedding_map(trace_id: str, response: Response):
    """Where the query sits among this run's retrieved chunks.

    Built on demand: the vectors are read from Chroma (and the query's place
    among them follows from the recorded cosine similarities), so opening a
    trace is the only thing that pays for this - never the chat path, and never
    a second embedding call. An empty ``maps`` list means the run recorded no
    cosine-scored vector search, or too few of its vectors are still stored.
    """
    _no_store(response)
    trace = trace_mod.store.get(trace_id)
    if trace is None:
        raise HTTPException(404, MISSING_TRACE)
    from ..rag.embedding_map import build_embedding_maps

    return build_embedding_maps(trace)


@router.delete("/traces")
def clear_traces(response: Response, kind: str = "all"):
    _no_store(response)
    removed = trace_mod.store.clear(None if kind in ("", "all") else kind)
    return {"removed": removed, "counts": trace_mod.store.counts()}


@router.post("/playground")
def playground(payload: PlaygroundRequest, response: Response):
    """Re-run retrieval for a question without generating an answer."""
    _no_store(response)
    from ..rag.pipeline import RetrievalRunError, explain_retrieval

    settings = get_settings()
    user_id = payload.user_id if payload.user_id is not None else int(settings.DEMO_USER_ID)
    try:
        return {"trace": explain_retrieval(
            payload.question,
            user_id,
            top_k=payload.top_k,
            rewrite=payload.rewrite,
            include_question_bank=payload.include_question_bank,
            include_images=payload.include_images,
        )}
    except RetrievalRunError as exc:
        # The failing run is already recorded; serve THAT trace. Looking up the
        # newest playground trace instead would show another request's question
        # whenever two runs interleave.
        message = trace_mod.clip(trace_mod.redact(exc), trace_mod.ERROR_LIMIT)
        logger.warning("RAG playground run failed: %s", message)
        recorded = trace_mod.store.get(exc.trace_id)
        if recorded is not None:
            return {"trace": recorded, "error": message}
        raise HTTPException(502, "اجرای بازیابی ناموفق بود؛ تنظیمات مدل و ایندکس را بررسی کنید.") from None
    except Exception as exc:
        # Failed before anything was traced, so there is no run to show.
        logger.warning("RAG playground run failed before recording: %s",
                       trace_mod.clip(trace_mod.redact(exc), trace_mod.ERROR_LIMIT))
        raise HTTPException(502, "اجرای بازیابی ناموفق بود؛ تنظیمات مدل و ایندکس را بررسی کنید.") from None
