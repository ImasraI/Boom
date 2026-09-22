"""
Cross-encoder reranking on top of hybrid retrieval.

Uses ``BAAI/bge-reranker-base`` (multilingual, works well on Persian) via
sentence-transformers. The model runs on CPU (the project's torch build is
CPU-only) and takes ~2-4s for 20 candidate pairs - acceptable for chat
retrieval, and it measurably lifts the right question to rank 1.

The wrapper degrades gracefully: if sentence-transformers or the model is
unavailable, reranking is skipped and hybrid results pass through.

Example:
    >>> from app.rag.reranker import get_reranker
    >>> get_reranker().rerank("نیمساز زاویه A", hybrid_results, top_k=4)
"""

from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._failed = False

    def _load(self):
        if self._model is not None or self._failed:
            return self._model
        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker model %s (CPU)...", self.model_name)
            self._model = CrossEncoder(self.model_name, max_length=512)
            logger.info("Reranker model loaded.")
        except Exception as e:
            logger.warning("Reranker unavailable (%s); reranking disabled.", e)
            self._failed = True
        return self._model

    @property
    def available(self) -> bool:
        return self._load() is not None

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        text_key: str = "content",
    ) -> List[Dict[str, Any]]:
        """Re-score ``results`` against ``query``; returns sorted by relevance."""
        if not results:
            return results
        model = self._load()
        if model is None:
            return results[:top_k] if top_k else results

        pairs = [[query, r.get(text_key, "")[:2000]] for r in results]
        try:
            scores = model.predict(pairs)
        except Exception as e:
            logger.warning("Rerank prediction failed: %s", e)
            return results[:top_k] if top_k else results

        scored = []
        for r, s in zip(results, scores):
            out = dict(r)
            out["rerank_score"] = round(float(s), 4)
            out["score"] = out["rerank_score"]
            scored.append(out)
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k] if top_k else scored


@lru_cache
def get_reranker() -> CrossEncoderReranker:
    settings = get_settings()
    return CrossEncoderReranker(settings.RERANK_MODEL_NAME)


def rerank_enabled() -> bool:
    return bool(get_settings().RERANK_ENABLED)
