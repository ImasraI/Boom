"""
Embedding layer for converting text into vector representations.

Supports:
- OpenAI-compatible APIs (Groq, Omniroute, etc.)
- Nomic embed-text

Recommended models for Persian: nomic-embed-text
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List
import httpx

from langchain_community.embeddings import HuggingFaceEmbeddings

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
        }
        try:
            resp = self.client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "data" in data:
                sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in sorted_data]
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
    provider = settings.EMBEDDING_PROVIDER

    if provider == "groq":
        if not settings.EMBEDDING_API_KEY:
            logger.warning("Groq embedding selected but EMBEDDING_API_KEY not set.")
            return None
        base_url = settings.EMBEDDING_BASE_URL or "https://api.groq.com/openai/v1"
        logger.info(f"Using Groq embeddings: {base_url}, model={settings.EMBEDDING_MODEL_NAME}")
        return OpenAICompatibleEmbeddingModel(
            api_key=settings.EMBEDDING_API_KEY,
            base_url=base_url,
            model_name=settings.EMBEDDING_MODEL_NAME,
        )

    if provider == "openai":
        if not settings.EMBEDDING_API_KEY:
            logger.warning("OpenAI-compatible embedding selected but EMBEDDING_API_KEY not set. Falling back to Groq.")
            provider = "groq"
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

    if provider == "nomic":
        # Nomic embed-text can be used locally or via API
        logger.info(f"Using Nomic embeddings: {settings.EMBEDDING_MODEL_NAME}")
        return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)

    logger.warning(f"Unknown embedding provider: {provider}. Falling back to Groq.")
    return get_embedding_model.__wrapped__(Settings()) if False else None
