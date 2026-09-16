"""
Image embedding layer for the "page-as-image" RAG pipeline.

Two interchangeable backends are provided behind one interface, selected
via `IMAGE_EMBEDDING_BACKEND` in .env / config.py:

  - "clip"    (default) Multilingual CLIP via sentence-transformers.
              Runs fine on CPU. Good baseline; Persian text-in-image and
              Persian questions both map into the same vector space.

  - "colpali" ColPali / ColQwen-style late-interaction retriever.
              State of the art for page-image retrieval (tops the ViDoRe
              benchmark), but the model is much larger and really wants a
              GPU. Its native output is *multiple* vectors per page
              (one per image patch); since our vector store (Chroma) only
              supports single-vector similarity, we mean-pool the patch
              vectors into one vector per page. This keeps the same
              storage/retrieval code path working for both backends, at
              the cost of some of ColPali's fine-grained matching power.
              If/when you outgrow this, swapping in a multi-vector store
              (e.g. Qdrant) will let you use the full late-interaction score.

Switching backends only requires re-ingesting existing PDFs (embeddings
from different backends are not compatible with each other).
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, List, cast

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseImageEmbeddingModel(ABC):
    @abstractmethod
    def embed_images(self, image_paths: List[Path]) -> List[List[float]]:
        """Embed a batch of page images."""
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a text question into the same vector space as the images."""
        raise NotImplementedError


class ClipImageEmbedding(BaseImageEmbeddingModel):
    """Multilingual CLIP: separate image and text towers sharing one space."""

    def __init__(self, image_model_name: str, text_model_name: str):
        from sentence_transformers import SentenceTransformer

        logger.info(
            f"Loading CLIP image tower '{image_model_name}' and "
            f"multilingual text tower '{text_model_name}'."
        )
        try:
            self.image_model = SentenceTransformer(image_model_name, local_files_only=True)
        except Exception:
            self.image_model = SentenceTransformer(image_model_name)

        try:
            self.text_model = SentenceTransformer(text_model_name, local_files_only=True)
        except Exception:
            self.text_model = SentenceTransformer(text_model_name)

    def embed_images(self, image_paths: List[Path]) -> List[List[float]]:
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in image_paths]
        embeddings = cast(Any, self.image_model).encode(
            cast(Any, images), convert_to_numpy=True, show_progress_bar=False
        )
        return cast(Any, embeddings).tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self.text_model.encode(text, convert_to_numpy=True)
        return cast(Any, embedding).tolist()


class ColPaliImageEmbedding(BaseImageEmbeddingModel):
    """ColPali/ColQwen late-interaction retriever, pooled to single vectors."""

    def __init__(self, model_name: str):
        import torch
        from importlib import import_module

        colpali_models = import_module("colpali_engine.models")
        colqwen_model = getattr(colpali_models, "ColQwen2_5")
        colqwen_processor = getattr(colpali_models, "ColQwen2_5_Processor")

        logger.info(f"Loading ColPali-family model '{model_name}'. This is a large "
                     f"model download and is much faster with a GPU available.")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning(
                "No GPU detected — ColPali will run on CPU and will be slow. "
                "Consider switching IMAGE_EMBEDDING_BACKEND back to 'clip' "
                "for CPU-only setups."
            )

        self.model = colqwen_model.from_pretrained(
            model_name,
            torch_dtype=torch.float32,
            device_map=self.device,
        ).eval()
        self.processor = colqwen_processor.from_pretrained(model_name)

    def _pool(self, multi_vector: Any) -> List[float]:
        # Mean-pool the per-patch vectors into a single vector so it fits
        # the single-vector Chroma store. See module docstring for context.
        return cast(Any, multi_vector.mean(dim=0)).tolist()

    def embed_images(self, image_paths: List[Path]) -> List[List[float]]:
        import torch
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in image_paths]
        batch = self.processor.process_images(images).to(self.device)

        with torch.no_grad():
            outputs = self.model(**batch)

        return [self._pool(vec) for vec in outputs]

    def embed_query(self, text: str) -> List[float]:
        import torch

        batch = self.processor.process_queries([text]).to(self.device)
        with torch.no_grad():
            outputs = self.model(**batch)

        return self._pool(outputs[0])


@lru_cache
def get_image_embedding_model() -> BaseImageEmbeddingModel:
    settings = get_settings()
    backend = settings.IMAGE_EMBEDDING_BACKEND.lower()

    if backend == "colpali":
        return ColPaliImageEmbedding(model_name=settings.COLPALI_MODEL_NAME)

    if backend != "clip":
        logger.warning(
            f"Unknown IMAGE_EMBEDDING_BACKEND='{backend}', falling back to 'clip'."
        )

    return ClipImageEmbedding(
        image_model_name=settings.CLIP_IMAGE_MODEL_NAME,
        text_model_name=settings.CLIP_TEXT_MODEL_NAME,
    )
