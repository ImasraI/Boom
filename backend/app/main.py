from contextlib import asynccontextmanager
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, documents
from app.routers import insights
from app.routers import mocks
from app.routers import challenges
from app.routers import arena
from app.routers import admin
from app.routers.profile import router as profile_router
from app.routers.tasks import router as tasks_router
from .auth.database import ensure_schema
from .auth.router import router as auth_router
from app.routers.boom_ai import router as boom_ai_router
from app.utils.logger import get_logger
from app.utils.metrics import record_error, record_request


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


def _run_pool_sweep_once() -> None:
    """One pool top-up pass through the SAME shared sweep the dedicated
    worker script uses (pool rules can never drift between the two).

    The in-process sweep is budget-capped (POOL_SWEEP_MAX_BOOKLETS): a
    fresh deployment starts with every shelf empty and one booklet costs
    many LLM calls, so uncapped first sweeps would burn the free quotas.
    The cap applies per sweep, so shelves still fill gradually. The
    dedicated worker script stays uncapped (explicit operator intent).
    """
    from app.auth.database import SessionLocal
    from app.rag import pool_core
    db = SessionLocal()
    budget = max(0, settings.POOL_SWEEP_MAX_BOOKLETS)
    produced = duel = 0
    try:
        if budget:
            produced = pool_core.sweep(
                db, target=settings.MOCK_POOL_TARGET, max_booklets=budget)
            remaining = budget - produced
            if remaining > 0:
                duel = pool_core.sweep_duels(
                    db, target=settings.MOCK_POOL_TARGET,
                    max_booklets=remaining)
        if produced or duel:
            logger.info("Pool top-up: +%d mock(s), +%d duel booklet(s) "
                        "(budget %d).", produced, duel, budget)
    except Exception:
        logger.exception("Pool top-up sweep failed")
    finally:
        db.close()


def _start_pool_worker() -> None:
    """Keep the mock/duel pool stocked from inside the API process.

    Gated by POOL_WORKER_INPROCESS so a deployment running the dedicated
    scripts/mock_pool_worker.py process can turn this off and avoid two
    workers generating the same shelves. Runs one sweep right away so a
    fresh VM has booklets without waiting an interval, then every
    POOL_SWEEP_INTERVAL_SECONDS. One booklet can take minutes on free LLM
    tiers, so a single worker thread per process is intentional.
    """
    if not settings.POOL_WORKER_INPROCESS:
        logger.info("In-process pool worker disabled (POOL_WORKER_INPROCESS=false).")
        return

    def _loop() -> None:
        while True:
            _run_pool_sweep_once()
            time.sleep(max(60, settings.POOL_SWEEP_INTERVAL_SECONDS))

    thread = threading.Thread(target=_loop, name="pool-worker", daemon=True)
    thread.start()
    logger.info("In-process pool worker started (target=%d/ shelf, sweep every %ds).",
                settings.MOCK_POOL_TARGET, max(60, settings.POOL_SWEEP_INTERVAL_SECONDS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_raw_ingestion()
    _start_pool_worker()
    yield


ensure_schema()

# Fail fast in production on a missing/weak SECRET_KEY (growth-readiness
# project 8): HS256 tokens are only as strong as this secret. Dev keeps
# booting (random per-process key) so local work is never blocked.
from app.utils.startup_checks import validate_startup_secrets
validate_startup_secrets(env=settings.APP_ENV)
# Create the FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Boom (بوم): RAG-based AI study coach for Konkoor students",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_metrics(request, call_next):
    """Record status-level metrics without logging request bodies or tokens."""
    try:
        response = await call_next(request)
    except Exception:
        record_error(f"unhandled:{request.method} {request.url.path}")
        raise
    record_request(request.method, request.url.path, response.status_code)
    return response


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
app.include_router(profile_router)
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
