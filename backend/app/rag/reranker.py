"""
Cross-encoder reranking on top of hybrid retrieval.

Uses the configured cross-encoder via sentence-transformers. The default
``BAAI/bge-reranker-base`` model documents Chinese/English coverage; Persian
quality and latency must be measured on the target corpus and hardware.
Device selection follows the library/runtime unless explicitly configured.

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

            logger.info("Loading reranker model %s...", self.model_name)
            self._model = CrossEncoder(self.model_name, max_length=512)
            logger.info("Reranker model loaded.")
        except Exception as e:
            logger.warning("Reranker unavailable (%s); reranking disabled.", e)
            self._failed = True
        return self._model

    @property
    def loaded(self) -> bool:
        """True only when a model object is already in memory.

        Distinct from :attr:`available`, which loads the model if it has to.
        Reading configuration must never download or initialise a model, so the
        inspector reads this instead of probing availability.
        """
        return self._model is not None

    @property
    def failed(self) -> bool:
        """True once a load attempt failed; it will not be retried."""
        return self._failed

    def state(self) -> str:
        """One of ``disabled``/``unloaded``/``loaded``/``failed`` - never loads.

        ``unloaded`` is the honest answer for "would reranking work?": the
        model is only brought up on the first search that needs it, so a
        configuration read cannot say more without paying for a load.
        """
        if not rerank_enabled():
            return "disabled"
        if self.loaded:
            return "loaded"
        return "failed" if self._failed else "unloaded"

    @property
    def available(self) -> bool:
        """Probe (and therefore load) the model; callers that gate on a search do."""
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
