"""
Embedding layer for converting text into vector representations.

Supports:
- Ollama local embeddings (nomic-embed-text, etc.)
- OpenAI-compatible APIs (Groq, Omniroute, etc.)
- HuggingFace embeddings (local or hub)

Recommended models for Persian: nomic-embed-text (via Ollama)
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List, Optional
import httpx

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseEmbeddingModel(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


_OLLAMA_EMBEDDING_ALIASES = {
    "nomic-embed-text-v1_5": "nomic-embed-text",
    "nomic-embed-text-v1.5": "nomic-embed-text",
}


def ollama_embedding_model_name(model_name: str) -> str:
    """Map Groq/OpenAI nomic ids onto the local Ollama model name."""
    key = (model_name or "").strip()
    return _OLLAMA_EMBEDDING_ALIASES.get(key, key or "nomic-embed-text")


def _ollama_native_base(base_url: str) -> str:
    url = (base_url or "http://localhost:11434").rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url or "http://localhost:11434"


class OllamaEmbeddingModel(BaseEmbeddingModel):
    """HTTP client for the local Ollama embedding API."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ):
        self.model = ollama_embedding_model_name(model_name)
        self.base_url = _ollama_native_base(base_url)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def _parse_embedding(self, data: dict) -> List[float]:
        if "embeddings" in data and data["embeddings"]:
            first = data["embeddings"][0]
            return first if isinstance(first, list) else []
        if "embedding" in data and data["embedding"]:
            return data["embedding"]
        return []

    def _encode_text(self, text: str) -> List[float]:
        """Send a single text to Ollama for embedding."""
        attempts = (
            (f"{self.base_url}/api/embed", {"model": self.model, "input": text}),
            (f"{self.base_url}/api/embeddings", {"model": self.model, "prompt": text}),
        )
        last_error = None
        for url, payload in attempts:
            try:
                resp = self.client.post(url, json=payload)
                if resp.status_code >= 400:
                    last_error = f"{resp.status_code} {resp.text[:300]}"
                    continue
                embedding = self._parse_embedding(resp.json())
                if embedding:
                    return embedding
                last_error = f"empty vector from {url}"
            except Exception as e:
                last_error = str(e)
        logger.warning(
            "Ollama embedding failed for model=%s at %s: %s. "
            "Is Ollama running, and have you pulled the model? "
            "(ollama serve && ollama pull %s)",
            self.model,
            self.base_url,
            last_error,
            self.model,
        )
        return []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts using Ollama embeddings."""
        return [self._encode_text(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        """Encode a single query text using Ollama embeddings."""
        return self._encode_text(text)


class HuggingFaceEmbeddingModel(BaseEmbeddingModel):
    """LangChain-backed HuggingFace embedding model."""

    def __init__(self, model_name: str):
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self.model = HuggingFaceEmbeddings(model_name=model_name)
        except Exception as e:
            logger.warning(f"Failed to initialize HuggingFace embeddings: {e}")
            self.model = None

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self.model is None:
            return []
        return self.model.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        if self.model is None:
            return []
        return self.model.embed_query(text)


_GROQ_EMBEDDING_ALIASES = {
    "nomic-embed-text": "nomic-embed-text-v1_5",
    "nomic-embed-text-v1.5": "nomic-embed-text-v1_5",
}


def groq_embedding_model_name(model_name: str) -> str:
    """Groq only serves nomic-embed-text-v1_5; Ollama uses nomic-embed-text."""
    key = (model_name or "").strip()
    return _GROQ_EMBEDDING_ALIASES.get(key, key)


class OpenAICompatibleEmbeddingModel(BaseEmbeddingModel):
    """HTTP client for OpenAI-compatible embedding APIs (Groq, Omniroute, etc.)."""

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.model = model_name
        self.client = httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        logger.info(f"Initialized OpenAI-compatible embedding client: {base_url}, model={model_name}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        try:
            resp = self.client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "Embedding request failed (%s) model=%s body=%s",
                    resp.status_code,
                    self.model,
                    resp.text[:500],
                )
                return []
            data = resp.json()
            if "data" in data:
                sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                vectors = []
                for item in sorted_data:
                    embedding = item.get("embedding") or []
                    if not embedding:
                        logger.warning("Embedding API returned an empty vector.")
                        return []
                    vectors.append(embedding)
                return vectors
            logger.warning("Unexpected embedding response format: %s", data)
            return []
        except Exception as e:
            logger.warning(f"Embedding request failed: {e}")
            return []

    def embed_query(self, text: str) -> List[float]:
        results = self.embed_documents([text])
        return results[0] if results else []


@lru_cache
def get_embedding_model() -> BaseEmbeddingModel:
    settings = get_settings()
    provider = (settings.EMBEDDING_PROVIDER or "").strip().lower()

    if provider == "groq":
        if not settings.EMBEDDING_API_KEY:
            logger.warning("Groq embedding selected but EMBEDDING_API_KEY not set.")
            raise RuntimeError("EMBEDDING_API_KEY is required for the Groq embedding provider.")
        base_url = settings.EMBEDDING_BASE_URL or "https://api.groq.com/openai/v1"
        model_name = groq_embedding_model_name(settings.EMBEDDING_MODEL_NAME)
        logger.info(f"Using Groq embeddings: {base_url}, model={model_name}")
        return OpenAICompatibleEmbeddingModel(
            api_key=settings.EMBEDDING_API_KEY,
            base_url=base_url,
            model_name=model_name,
        )

    if provider == "openai":
        if not settings.EMBEDDING_API_KEY:
            raise RuntimeError(
                "EMBEDDING_API_KEY is required for the OpenAI-compatible embedding provider."
            )
        else:
            base_url = settings.EMBEDDING_BASE_URL
            if not base_url or base_url == "http://localhost:11434":
                base_url = "https://api.omniroute.ai/v1"
            logger.info(f"Using OpenAI-compatible embeddings: {base_url}, model={settings.EMBEDDING_MODEL_NAME}")
            return OpenAICompatibleEmbeddingModel(
                api_key=settings.EMBEDDING_API_KEY,
                base_url=base_url,
                model_name=settings.EMBEDDING_MODEL_NAME,
            )

    if provider in ("ollama", "nomic"):
        model_name = ollama_embedding_model_name(settings.EMBEDDING_MODEL_NAME)
        base_url = settings.EMBEDDING_BASE_URL or "http://localhost:11434"
        logger.info(f"Using Ollama embeddings: {model_name} at {base_url}")
        return OllamaEmbeddingModel(model_name=model_name, base_url=base_url)

    if provider == "huggingface":
        logger.info(f"Using HuggingFace embeddings: {settings.EMBEDDING_MODEL_NAME}")
        return HuggingFaceEmbeddingModel(model_name=settings.EMBEDDING_MODEL_NAME)

    raise ValueError(f"Unknown embedding provider: {provider}")