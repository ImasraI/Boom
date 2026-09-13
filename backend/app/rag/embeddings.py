"""
Embedding layer for converting text into vector representations.

Supports:
- Ollama (local)
- OpenAI-compatible APIs (Groq, Omniroute, etc.)

Recommended models for Persian: nomic-embed-text, batai/qwen3-embedding:0.6b
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List
import httpx

from langchain_community.embeddings import OllamaEmbeddings

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


class OllamaEmbeddingModel(BaseEmbeddingModel):
    """Wrapper around Ollama's embedding models."""

    def __init__(self, model_name: str, base_url: str):
        logger.info(f"Loading Ollama embedding model: {model_name}")
        raw_url = base_url.strip().rstrip("/")
        if "localhost" in raw_url:
            raw_url = raw_url.replace("localhost", "127.0.0.1")
        if raw_url.endswith("/v1"):
            raw_url = raw_url[:-3]
        
        self.model = OllamaEmbeddings(
            model=model_name,
            base_url=raw_url
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.model.embed_query(text)


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

    if provider == "openai":
        if not settings.EMBEDDING_API_KEY:
            logger.warning("OpenAI-compatible embedding selected but EMBEDDING_API_KEY not set. Falling back to Ollama.")
            provider = "ollama"
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

    if provider == "ollama":
        base_url = settings.EMBEDDING_BASE_URL or "http://127.0.0.1:11434"
        logger.info(f"Using Ollama embeddings: {base_url}, model={settings.EMBEDDING_MODEL_NAME}")
        return OllamaEmbeddingModel(
            model_name=settings.EMBEDDING_MODEL_NAME,
            base_url=base_url,
        )

    logger.warning(f"Unknown embedding provider: {provider}. Falling back to Ollama.")
    return OllamaEmbeddingModel(
        model_name=settings.EMBEDDING_MODEL_NAME,
        base_url="http://127.0.0.1:11434",
    )
