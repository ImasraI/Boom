from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "RAG-LLM"
    APP_ENV: str = "development"
    DEMO_USER_ID: int = 1

    # Allowed frontend origins for CORS
    CORS_ORIGINS: str = "*"

    # File storage paths
    UPLOAD_DIR: str = "data/uploads"
    CHROMA_DIR: str = "data/chroma_db"

    # Vector database collection name
    CHROMA_COLLECTION: str = "documents"

    # Embedding model configuration
    EMBEDDING_PROVIDER: str = "groq"  # Options: "groq", "openai", "jina", etc.
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "nomic-embed-text"
    EMBEDDING_BASE_URL: str = "https://api.groq.com/openai/v1"
    EMBEDDING_DEVICE: str = "cpu"

    # LLM provider configuration
    LLM_PROVIDER: str = "groq"  # Options: "groq", "openai", "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL_NAME: str = "llama-3.1-8b-instant"

    # LLM generation parameters
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 800

    # Text splitting settings for RAG chunks
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # Number of documents retrieved from vector database
    TOP_K: int = 4

    # ================= Image-based PDF RAG (page-as-image) =================
    # Default processing mode for uploaded PDFs when the client doesn't
    # explicitly choose one: "text" (old pipeline) or "image" (new pipeline).
    PDF_PROCESSING_MODE: str = "image"

    # Where rendered page images are stored on disk
    IMAGES_DIR: str = "data/page_images"

    # Resolution used when rasterizing PDF pages to images.
    # 200 is a good quality/speed tradeoff for reading dense Persian text.
    IMAGE_DPI: int = 200

    # Batch size for embedding a document's pages (one batch per DB add,
    # keeps memory bounded on big scanned PDFs).
    IMAGE_BATCH_SIZE: int = 30

    # Folder containing "raw" study PDFs that should be embedded
    # page-by-page automatically before the app is used (see
    # app/rag/ingest_raw.py).
    RAW_DIR: str = "data/raw"

    # Resolution used for the big bulk raw PDFs. Lower than IMAGE_DPI to
    # keep the rendered page count / disk usage reasonable (120 DPI is
    # still readable by the vision model).
    RAW_INGEST_DPI: int = 120

    # Number of page images retrieved per question
    IMAGE_TOP_K: int = 3

# Minimum cosine similarity required before a page image can trigger
    # the vision pipeline.  Without this cutoff Chroma returns nearest
    # neighbours even for unrelated questions whenever images are indexed.
    #
    # The multilingual-CLIP text tower scores Persian questions against
    # page images in a flat ~0.25-0.31 band, so 0.35 never fires. 0.24 keeps
    # the cutoff meaningful while letting genuinely-related pages through.
    IMAGE_RELEVANCE_THRESHOLD: float = 0.24

    # Separate Chroma collection for image embeddings (kept apart from the
    # text-chunk collection so the two pipelines never mix).
    CHROMA_IMAGE_COLLECTION: str = "document_images"

    # Which embedding backend to use for page images: "clip" or "colpali".
    # This is a single switch — swap it any time without touching code.
    IMAGE_EMBEDDING_BACKEND: str = "clip"

    # --- CLIP backend (default: light, CPU-friendly, multilingual) ---
    # Two separate towers are used on purpose: sentence-transformers' CLIP
    # image tower is English-only, and the multilingual text tower was
    # distilled to share the *same* vector space so Persian queries still
    # match against it correctly.
    CLIP_IMAGE_MODEL_NAME: str = "clip-ViT-B-32"
    CLIP_TEXT_MODEL_NAME: str = "clip-ViT-B-32-multilingual-v1"

    # --- ColPali backend (optional: much stronger, GPU strongly recommended) ---
    COLPALI_MODEL_NAME: str = "vidore/colqwen2.5-v0.2"
    # =========================================================================

    # ---------- ADD THIS LINE ----------
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"   # <-- allows extra env vars like SECRET_KEY
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
