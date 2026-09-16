"""
Auto-ingest the "raw" study PDFs picture-by-picture.

PDFs dropped into ``data/raw`` (e.g. big scanned Konkoor books) are
rasterized page-by-page and embedded into the page-image vector store so
the vision pipeline can retrieve them.  Only documents that are not yet
ingested are processed, so re-running is cheap and idempotent.

PDFs are organized in subfolders that also act as their *category*::

    data/raw/
      plans/               -> category "plan"     (mock-exam schedules, yearly plans)
      test-books/          -> category "test_book" (Konkoor question banks)
      ministerial-books/   -> category "ministerial" (وزارت / school textbooks)
      custom-sources/      -> category "custom"   (personal/extra sources)

Files dropped directly in ``data/raw`` (legacy layout) get category "".

Run directly before the site starts::

    cd backend
    .venv\\Scripts\\python.exe -m app.rag.ingest_raw

It also runs automatically as a background task when the FastAPI app
starts (see app.main lifespan).
"""

from pathlib import Path
from typing import Dict, List

from app.config import get_settings
from app.rag.pipeline import ingest_pdf_as_images
from app.rag.vector_store import get_image_vector_store
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Subfolder name -> category tag stored with each page embedding.
RAW_CATEGORY_DIRS: Dict[str, str] = {
    "plans": "plan",
    "test-books": "test_book",
    "ministerial-books": "ministerial",
    "custom-sources": "custom",
}


def list_raw_pdfs() -> List[Path]:
    """All PDFs under ``settings.RAW_DIR`` (recursively), leaf subfolder
    order first so category folders are stable and legacy flat files still
    work unchanged."""
    settings = get_settings()
    raw_dir = Path(settings.RAW_DIR)
    if not raw_dir.exists():
        return []

    def _key(p: Path) -> tuple[int, str]:
        rel = p.relative_to(raw_dir)
        return (len(rel.parts), str(rel))

    return sorted(raw_dir.rglob("*.pdf"), key=_key)


def category_for_pdf(pdf: Path) -> str:
    """Category of a raw PDF based on its parent folder name, "" if unknown."""
    parent = pdf.parent.name
    return RAW_CATEGORY_DIRS.get(parent, "")


def document_category_map() -> Dict[str, str]:
    """filename -> category resolver from the current raw folder tree.

    Used at retrieval time so *already-ingested* documents (embedded before
    categories existed, or with a stale metadata field) can still be bucketed
    by their containing folder.
    """
    return {p.name: category_for_pdf(p) for p in list_raw_pdfs()}


def ingest_raw_pdfs(user_id: int | None = None) -> dict:
    """Embed every not-yet-ingested PDF in ``settings.RAW_DIR`` as page images.

    Returns a summary of newly-ingested and already-ingested documents.
    """
    settings = get_settings()
    user_id = user_id if user_id is not None else settings.DEMO_USER_ID

    pdfs = list_raw_pdfs()
    if not pdfs:
        logger.info("No PDFs found in '%s'.", settings.RAW_DIR)
        return {"ingested": [], "skipped": []}

    # Already-ingested documents are skipped so startup stays fast.
    image_store = get_image_vector_store()
    known = set(image_store.list_documents(user_id=user_id))

    ingested: List[str] = []
    skipped: List[str] = []

    for pdf in pdfs:
        category = category_for_pdf(pdf)
        logger.info(
            "Processing raw PDF: %s (%.1f MB, category='%s')",
            pdf.name, pdf.stat().st_size / 1e6, category,
        )
        if pdf.name in known:
            logger.info("  already ingested, skipping.")
            skipped.append(pdf.name)
            continue

        logger.info("  rendering + embedding each page...")
        count = ingest_pdf_as_images(
            pdf.name,
            pdf,
            user_id=user_id,
            dpi=settings.RAW_INGEST_DPI,
            category=category,
        )
        logger.info("  done: %d page image(s) stored for '%s'.", count, pdf.name)
        ingested.append(pdf.name)

    summary = {"ingested": ingested, "skipped": skipped}
    logger.info(
        "Raw PDF ingestion finished: %d ingested, %d skipped.",
        len(ingested), len(skipped),
    )
    return summary


if __name__ == "__main__":
    summary = ingest_raw_pdfs()
    print("Ingested:", summary["ingested"] or "none")
    print("Skipped (already present):", summary["skipped"] or "none")