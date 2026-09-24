from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "RAG-LLM"
    APP_ENV: str = "development"
    DEMO_USER_ID: int = 1

    # Allowed frontend origins for CORS
    # Default allows all ("*") for development; override via CORS_ORIGINS env var for production
    CORS_ORIGINS: str = "*"  # e.g., "https://your-app.vercel.app" or "https://your-app.vercel.app,https://admin.your-app.vercel.app"

    # File storage paths
    UPLOAD_DIR: str = "data/uploads"
    CHROMA_DIR: str = "data/chroma_db"

    # Vector database collection name
    CHROMA_COLLECTION: str = "documents"

    # Embedding model configuration
    EMBEDDING_PROVIDER: str = "ollama"  # Options: "ollama", "groq", "openai"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "nomic-embed-text"
    EMBEDDING_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_DEVICE: str = "cpu"
    CHROMA_TELEMETRY: bool = False

    # LLM provider configuration
    LLM_PROVIDER: str = "groq"  # Options: "groq", "openai", "omniroute", "ollama", "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL_NAME: str = "llama-3.1-8b-instant"
    VISION_LLM_PROVIDER: str = "gemini"  # Options: "gemini", "groq", "ollama", "mock"
    VISION_LLM_MODEL_NAME: str = "gemini-3.6-flash"

    # Google Gemini API (vision-capable provider, free tier).
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL_NAME: str = "gemini-3.6-flash"

    # SMS signup verification (SMS.ir / Melipayamak panel).
    # Create a verification template containing {CODE} in the panel, then put
    # its numeric template id in SMS_VERIFY_TEMPLATE_ID.
    SMS_API_KEY: str = ""
    SMS_VERIFY_TEMPLATE_ID: str = ""
    SECRET_KEY: str = ""  # JWT + code-hashing secret (set it in .env!)
    SMS_BASE_URL: str = "https://api.sms.ir"
    # SMS-template-approval stopgap: numbers on the admin-managed signup
    # allowlist can complete signup with this shared passcode instead of a
    # texted code. Change it in .env once SMS is live (or set it empty to
    # disable bypass entirely). 6 digits to match the SMS code UI.
    SIGNUP_BYPASS_CODE: str = "111111"
    # Dev convenience: when True (and APP_ENV != production) the request-code
    # endpoint returns the code in the response instead of sending an SMS.
    SMS_DEBUG_ECHO: bool = False
    # Dev convenience: when True (and APP_ENV != production) signup skips SMS
    # code verification entirely - the client goes straight from the phone
    # step to setting a password. Never enable this in production.
    DISABLE_AUTH: bool = False

    # ====== Per-user daily AI quotas (0 or negative = unlimited) =========
    # Counts successful AI requests per user per UTC day; adjust in .env.
    AI_DAILY_CHAT: int = 50
    AI_DAILY_STUDY_PLAN: int = 10
    AI_DAILY_WEEKLY_PLAN: int = 20
    AI_DAILY_TODAY_TESTS: int = 30
    AI_DAILY_MOCK_GENERATE: int = 10
    AI_DAILY_ARENA_JOIN: int = 3
    # Rough daily per-user token budget across ALL AI features (prompt +
    # completion). ~200k tokens ≈ a full mock booklet + a few dozen chats.
    # Set 0 (or negative) in .env for unlimited.
    AI_DAILY_TOKEN_BUDGET: int = 200000

    # Upload limits (per file): reject anything bigger without reading it all.
    MAX_UPLOAD_MB: int = 20
    # Optional local proxy (e.g. VPN client) used ONLY for Gemini requests,
    # which are geo-blocked in some regions. Groq/Ollama stay direct.
    # Example: http://127.0.0.1:10809 (v2rayN HTTP port)
    GEMINI_PROXY: str = ""

    # OpenRouter (geo-unblocked alternative to Gemini; free-tier vision models)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_VISION_MODEL: str = "qwen/qwen2.5-vl-72b-instruct:free"

    # Groq (fast LPU inference; free tier includes llama-4 vision models)
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Pre-generated mock pool: pending_use booklets kept per (major,
    # difficulty) shelf by the pool worker (and the admin restock button).
    MOCK_POOL_TARGET: int = 5

    # ================= Question-bank transcription (vision RAG) ==========
    # Structured per-page transcription of the scanned books (questions,
    # options, figure descriptions, lesson prose) stored as JSON under
    # data/ocr/<book>/pages/ and embedded into the question_bank collection.
    TRANSCRIBE_PROVIDER: str = "auto"  # auto | gemini | groq | ollama
    TRANSCRIBE_DPI: int = 150
    TRANSCRIBE_SLEEP_SECONDS: float = 2.0
    TRANSCRIBE_LOCAL_MODEL: str = "qwen2.5vl:7b"

    # Separate Chroma collection for structured question chunks.
    CHROMA_QA_COLLECTION: str = "question_bank"

    # Cross-encoder reranking applied on top of hybrid retrieval.
    RERANK_ENABLED: bool = True
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-base"
    RERANK_CANDIDATES: int = 20

    # ================= Bulk OCR corpus of scanned books =================
    # OCR gives the planner knowledge of what every book contains (chapters,
    # questions, page ranges).  The vision path *still* reads the real page
    # image when a user asks for a question/answer/explanation, so figures
    # and formulas that OCR cannot keep are preserved.
    #
    # Free-tier Gemini caps image-mode requests at ~250 RPD, so the bulk job
    # is resumable and stops at a daily cap (GEMINI_OCR_DAILY_CAP) - re-run
    # it each day until the whole library is transcribed.
    OCR_DIR: str = "data/ocr"
    OCR_DPI: int = 120
    # Pages transcribed per Gemini request (fewer requests = less quota burn).
    OCR_PAGES_PER_REQUEST: int = 4
    # Safety margin under Gemini's 15 RPM image limit.
    OCR_SLEEP_SECONDS: float = 5.0
    # Do not exceed this many Gemini image requests per calendar day.
    GEMINI_OCR_DAILY_CAP: int = 200

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
    IMAGE_DPI: int = 200

    # Batch size for embedding a document's pages (one batch per DB add,
    # keeps memory bounded on big scanned PDFs).
    IMAGE_BATCH_SIZE: int = 30

    # Folder containing "raw" study PDFs that should be embedded
    # page-by-page automatically before the app is used (see
    # app/rag/ingest_raw.py).
    RAW_DIR: str = "data/raw"

    # Resolution used for the big bulk raw PDFs.
    RAW_INGEST_DPI: int = 120

    # Number of page images retrieved per question
    IMAGE_TOP_K: int = 3

    # Minimum cosine similarity required before a page image can trigger
    # the vision pipeline.  Without this cutoff Chroma returns nearest
    # neighbours even for unrelated questions whenever images are indexed.
    IMAGE_RELEVANCE_THRESHOLD: float = 0.24

    # Separate Chroma collection for image embeddings (kept apart from the
    # text-chunk collection so the two pipelines never mix).
    CHROMA_IMAGE_COLLECTION: str = "document_images"

    # Which embedding backend to use for page images: "clip" or "colpali".
    IMAGE_EMBEDDING_BACKEND: str = "clip"

    CLIP_IMAGE_MODEL_NAME: str = "clip-ViT-B-32"
    CLIP_TEXT_MODEL_NAME: str = "clip-ViT-B-32-multilingual-v1"

    COLPALI_MODEL_NAME: str = "vidore/colqwen2.5-v0.2"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
