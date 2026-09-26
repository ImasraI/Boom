from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, documents
from app.routers import insights
from app.routers import mocks
from app.routers import challenges
from app.routers import arena
from app.routers import admin
from app.routers.tasks import router as tasks_router
from .auth.database import ensure_schema
from .auth.router import router as auth_router
from app.routers.boom_ai import router as boom_ai_router
from app.utils.logger import get_logger


# Load application settings
settings = get_settings()
logger = get_logger(__name__)


def _start_raw_ingestion() -> None:
    """Background task that embeds any new PDFs from data/raw page-by-page.

    Runs right after the server starts so the endpoint is always reachable
    quickly; ``python -m app.rag.ingest_raw`` (invoked by run_boom.bat) does
    the same work *before* the site starts for the first run.
    """
    from app.rag.ingest_raw import ingest_raw_pdfs

    def _run() -> None:
        try:
            ingest_raw_pdfs()
        except Exception as exc:  # noqa: BLE001 - never crash the server
            logger.exception(f"Background raw-PDF ingestion failed: {exc}")

    thread = threading.Thread(target=_run, name="raw-ingest", daemon=True)
    thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_raw_ingestion()
    yield


ensure_schema()
# Create the FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="RAG-based AI assistant prototype for K. N. Toosi University",
    version="0.1.0",
    lifespan=lifespan,
)


# Configure allowed origins for CORS
if settings.CORS_ORIGINS == "*":
    origins = ["*"]

else:
    origins = []

    # Convert comma-separated origins into a list
    origin_list = settings.CORS_ORIGINS.split(",")

    for origin in origin_list:
        origin = origin.strip()
        origins.append(origin)


# Add CORS middleware to the application
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register application routers
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth_router)
app.include_router(boom_ai_router)
app.include_router(tasks_router)
app.include_router(insights.router)
app.include_router(mocks.router)
app.include_router(challenges.router)
app.include_router(arena.router)
app.include_router(admin.router)

# Health check endpoint
@app.get("/api/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME
    }
