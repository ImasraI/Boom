"""
Bulk OCR of the raw scanned books via the Gemini vision client.

What it does
------------
For every raw PDF we do not already know about:

1. Render each page to a PNG (``pdf_to_page_images``) - the same images that
   will later be attached to vision reads, so figures/formulas are never lost.
2. Ask Gemini to transcribe each page faithfully (OCR).  Every page's text is
   cached as ``data/ocr/<book_stem>/page_0001.txt`` etc. so the job is
   resumable and idempotent.
3. Once a book is fully transcribed, embed its page texts into the *text*
   vector store with ``[صفحه N]`` markers so retrieval can (a) tell the
   planner what each book actually contains and (b) locate the exact page
   image to show the vision model when a user asks about a specific question.

The vision pipeline keeps reading page *images* for question/answer/explanation
requests: OCR only supplies knowledge of what is in each book, not the answer
itself.

Run it directly::

    cd backend
    python -m app.rag.ocr_corpus                     # all books, resume anything pending
    python -m app.rag.ocr_corpus --book "فیزیک ۱ خیلی سبز.pdf"
    python -m app.rag.ocr_corpus --limit 12          # only first 12 pages per book
    python -m app.rag.ocr_corpus --embed-only        # only embed fully-OCR'd books

Free-tier Gemini caps image-mode requests at ~250 RPD, so the job stops at
``GEMINI_OCR_DAILY_CAP`` (default 200) and must be re-run periodically until
every book is done - it resumes exactly where it stopped.
"""

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from app.config import get_settings
from app.rag.image_loader import pdf_to_page_images
from app.rag.ingest_raw import category_for_pdf, list_raw_pdfs
from app.rag.llm import MockLLMClient, get_vision_llm_client
from app.utils.logger import get_logger
from app.utils.storage import get_object

logger = get_logger(__name__)

OCR_PROMPT = """تو یک موتور OCR دقیق برای کتاب‌های درسی کنکور ایرانی هستی.
برای هر تصویری که می‌فرستم، فقط متن داخل همان صفحه را با وفاداری کامل بازنویسی کن.
- عکس‌ها و شکل‌ها را توصیف نکن؛ فقط متن، فرمول‌ها، سوال‌ها، گزینه‌ها و جدول‌ها را بنویس.
- شماره سوال‌ها و گزینه‌ها (۱، ۲، ۳، ۴ یا الف/ب/ج/د) را حفظ کن.
- جدول‌ها را به صورت متن ساده و منظم بنویس.
- نام کتاب و سرصفحه را هم اگر در تصویر هست بنویس.

خروجی را دقیقا با این قالب بده (متن هر تصویر زیر هدر همان تصویر):
=== صفحه 1 ===
<متن صفحه اول>
=== صفحه 2 ===
<متن صفحه دوم>
...
برای تصویری که محتوای متنی ندارد فقط همین را بنویس:
=== صفحه N ===
(این صفحه تصویر/شکل دارد و متن مستقلی ندارد)
توضیحات اضافه نده."""


def _ocr_dir() -> Path:
    settings = get_settings()
    d = Path(settings.OCR_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _book_ocr_dir(pdf_path: Path) -> Path:
    d = _ocr_dir() / pdf_path.stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(book_dir: Path) -> Path:
    return book_dir / "manifest.json"


def _load_manifest(book_dir: Path) -> dict:
    p = _manifest_path(book_dir)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not read OCR manifest %s: %s", p, e)
    return {"done": [], "pages_total": 0, "embedded": False}


def _save_manifest(book_dir: Path, manifest: dict) -> None:
    _manifest_path(book_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )


# ---------------- Daily request guard (free-tier RPD) ----------------

def _requests_today() -> int:
    """Number of Gemini image requests already made today this process can see."""
    p = _ocr_dir() / "requests.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    return int(data.get(str(date.today()), 0))


def _mark_request() -> int:
    p = _ocr_dir() / "requests.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data[str(date.today())] = int(data.get(str(date.today()), 0)) + 1
    p.write_text(json.dumps(data), encoding="utf-8")
    return data[str(date.today())]


def _page_text_path(book_dir: Path, page: int) -> Path:
    return book_dir / f"page_{page:04d}.txt"


def _saved_pages(book_dir: Path) -> Dict[int, str]:
    """page_num -> text for every page cached on disk so far."""
    out: Dict[int, str] = {}
    for f in sorted(book_dir.glob("page_*.txt")):
        try:
            text = f.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            try:
                out[int(f.stem.split("_")[1])] = text
            except (ValueError, IndexError):
                continue
    return out


def _normalize_digits(s: str) -> str:
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    return s.translate(trans)


_PAGE_SECTION = re.compile(
    r"=== صفحه\s*([0-9۰-۹]+)\s*===(.*?)(?=(=== صفحه\s*[0-9۰-۹]+\s*===|$))",
    re.DOTALL,
)


def _parse_sections(text: str) -> Dict[int, str]:
    """Extract ``=== صفحه N === ...`` sections -> {page: transcription}."""
    out: Dict[int, str] = {}
    for m in _PAGE_SECTION.finditer(text):
        try:
            page = int(_normalize_digits(m.group(1)))
        except ValueError:
            continue
        body = m.group(2).strip()
        if body:
            out[page] = body
    return out


def _page_key(pdf_path: Path, user_id: int, page: int) -> str:
    return f"{user_id}/{pdf_path.name}/page_{page:04d}.png"


def ocr_pages(
    pages: List[int],
    images: List[bytes],
    client,
) -> Dict[int, str]:
    """One Gemini request: transcribe `images` (aligned with `pages`)."""
    settings = get_settings()
    page_list = "، ".join(f"تصویر {i + 1} = صفحه {p}" for i, p in enumerate(pages))
    prompt = (
        OCR_PROMPT
        + "\n\nترتیب تصاویر ارسالی:\n"
        + page_list
    )
    messages = [{"role": "user", "content": prompt}]
    out = client.generate(messages, images=images, timeout=240)
    return _parse_sections(out or "")


def ocr_book(
    pdf: Path,
    user_id: int,
    pages_per_request: Optional[int] = None,
    limit: Optional[int] = None,
    include_plans: bool = False,
) -> str:
    """Transcribe a single book's not-yet-OCR'd pages. Returns a status string:
    ``"done"`` / ``"partial"`` / ``"capped"`` / ``"no_vision"`` / ``"empty"``."""
    settings = get_settings()
    try:
        import pymupdf

        with pymupdf.open(pdf) as doc:
            total = doc.page_count
    except Exception as e:
        logger.warning("Cannot open PDF %s: %s", pdf, e)
        return "empty"
    if total == 0:
        return "empty"

    ppq = pages_per_request or settings.OCR_PAGES_PER_REQUEST
    cap = settings.GEMINI_OCR_DAILY_CAP

    book_dir = _book_ocr_dir(pdf)
    manifest = _load_manifest(book_dir)
    manifest["pages_total"] = total
    if "done" not in manifest:
        manifest["done"] = []

    # Render the page PNGs (shared with the vision read attachments).
    # Rendering is cheap and idempotent; only missing pages get re-rendered.
    try:
        pdf_to_page_images(pdf, user_id, pdf.name, dpi=settings.OCR_DPI)
    except Exception as e:
        logger.warning("Rendering failed for %s: %s", pdf.name, e)
        return "empty"

    done = set(manifest["done"]) | set(_saved_pages(book_dir).keys())
    pending = [p for p in range(1, total + 1) if p not in done]
    if limit:
        pending = pending[:limit]
    if not pending:
        _save_manifest(book_dir, manifest)
        return "done"

    client = get_vision_llm_client()
    if isinstance(client, MockLLMClient):
        logger.warning("No real vision model configured (VISION_LLM_PROVIDER). Skipping OCR.")
        return "no_vision"

    status = "partial"
    cursor = 0
    while cursor < len(pending):
        if _requests_today() >= cap:
            logger.info("Daily OCR cap reached (%d); stopping for today.", cap)
            status = "capped"
            break

        batch = pending[cursor:cursor + ppq]
        cursor += len(batch)
        images = [get_object(_page_key(pdf, user_id, p)) for p in batch]
        images = [b for b in images if b]
        if len(images) != len(batch):
            logger.warning("Missing rendered images for some pages; skipping batch.")
            continue

        logger.info("OCR %s pages %d-%d (%d/%d so far) ...",
                    pdf.name, batch[0], batch[-1], cursor, len(pending))
        sections = ocr_pages(batch, images, client)
        _mark_request()
        time.sleep(settings.OCR_SLEEP_SECONDS)

        if not sections:
            logger.warning("No page sections parsed from OCR answer; pages %s will retry next run.",
                           batch)
            continue

        for p in batch:
            text = sections.get(p)
            if text:
                _page_text_path(book_dir, p).write_text(text, encoding="utf-8")
                manifest["done"] = sorted(set(manifest["done"]) | {p})
                done.add(p)

        # If the batch answer only covered some pages, retry the missed ones
        # individually (one page per request) so nothing is lost.
        missed = [p for p in batch if p not in sections]
        for p in missed:
            if _requests_today() >= cap:
                status = "capped"
                break
            img = get_object(_page_key(pdf, user_id, p))
            if not img:
                continue
            text = ocr_pages([p], [img], client)
            _mark_request()
            time.sleep(settings.OCR_SLEEP_SECONDS)
            if text.get(p):
                _page_text_path(book_dir, p).write_text(text[p], encoding="utf-8")
                manifest["done"] = sorted(set(manifest["done"]) | {p})
                done.add(p)

    _save_manifest(book_dir, manifest)
    if status == "capped":
        return "capped"
    remaining = [p for p in range(1, total + 1) if p not in done]
    return "done" if not remaining else "partial"


def embed_book(pdf: Path, user_id: int) -> int:
    """Embed one fully-OCR'd book's page texts into the text vector store as
    per-page chunks (``[صفحه N] ...``), giving the planner and retrieval real
    content with page provenance. Returns the number of chunks stored.
    Idempotent: already-embedded books are skipped (and their manifest flag
    corrected) instead of duplicating chunks."""
    from app.rag.embeddings import get_embedding_model
    from app.rag.vector_store import get_vector_store

    book_dir = _book_ocr_dir(pdf)
    manifest = _load_manifest(book_dir)
    pages = _saved_pages(book_dir)
    total = manifest.get("pages_total") or (max(pages) if pages else 0)

    if not pages:
        return 0
    store = get_vector_store()
    present = pdf.name in store.list_documents(user_id)
    if present:
        # Already in the store (stale manifest flag, interrupted previous run...).
        manifest["embedded"] = True
        manifest["pages_total"] = total
        _save_manifest(book_dir, manifest)
        logger.info("OCR of '%s' is already embedded; skipping.", pdf.name)
        return 0
    if manifest.get("embedded") and not present:
        logger.warning(
            "OCR of '%s' was marked embedded but is missing from the store; re-embedding.",
            pdf.name,
        )

    chunks = [
        f"[صفحه {p}] {pages[p]}"
        for p in sorted(pages)
    ]
    embeddings = get_embedding_model().embed_documents(chunks)
    store.delete_document(pdf.name, user_id)
    count = store.add_chunks(
        pdf.name, chunks, embeddings,
        user_id=user_id, category=category_for_pdf(pdf) or "ocr",
    )
    from app.rag.hybrid_search import get_hybrid_search
    get_hybrid_search().refresh(user_id)

    manifest["embedded"] = True
    manifest["pages_total"] = total
    _save_manifest(book_dir, manifest)
    logger.info("Embedded OCR of '%s' (%d pages) into the text store.", pdf.name, count)
    return count


def embed_done_books(user_id: Optional[int] = None) -> List[str]:
    """Embed any fully-OCR'd book that isn't embedded yet."""
    from app.rag.ingest_raw import list_raw_pdfs

    settings = get_settings()
    user_id = user_id if user_id is not None else settings.DEMO_USER_ID
    embedded = []
    for pdf in list_raw_pdfs():
        if category_for_pdf(pdf) == "plan":
            continue
        book_dir = _book_ocr_dir(pdf)
        manifest = _load_manifest(book_dir)
        pages = _saved_pages(book_dir)
        total = manifest.get("pages_total") or (max(pages) if pages else 0)
        if total and len(pages) >= total:
            if embed_book(pdf, user_id):
                embedded.append(pdf.name)
    return embedded


def run(
    user_id: Optional[int] = None,
    book_filter: Optional[str] = None,
    limit: Optional[int] = None,
    pages_per_request: Optional[int] = None,
    embed_only: bool = False,
    include_plans: bool = False,
) -> dict:
    settings = get_settings()
    user_id = user_id if user_id is not None else settings.DEMO_USER_ID

    pdfs = list_raw_pdfs()
    if book_filter:
        needle = book_filter.strip().lower()
        pdfs = [p for p in pdfs if needle in p.name.lower()]
        if not pdfs:
            logger.warning("No PDF matches '%s'.", book_filter)
    if not include_plans:
        pdfs = [p for p in pdfs if category_for_pdf(p) != "plan"]

    summary = {"ocred": [], "capped": [], "skipped": [], "embedded": [], "failed": []}
    for pdf in pdfs:
        if not embed_only:
            status = ocr_book(pdf, user_id, pages_per_request=pages_per_request,
                              limit=limit, include_plans=include_plans)
            if status == "done":
                summary["ocred"].append(pdf.name)
                # Fully transcribed -> embed right away so the content is live.
                try:
                    n = embed_book(pdf, user_id)
                    if n:
                        summary["embedded"].append(pdf.name)
                except Exception as e:
                    logger.warning("Embedding OCR of %s failed: %s", pdf.name, e)
            elif status == "capped":
                summary["capped"].append(pdf.name)
                break  # stop early; tomorrow resumes here
            elif status == "no_vision":
                summary["failed"].append(f"{pdf.name} (no vision model)")
                break
            else:
                summary["skipped"].append(pdf.name)
        else:
            try:
                if embed_book(pdf, user_id):
                    summary["embedded"].append(pdf.name)
            except Exception as e:
                logger.warning("Embedding OCR of %s failed: %s", pdf.name, e)

    # Catch any book that finished in earlier runs but was never embedded.
    if not embed_only:
        summary["embedded"] = sorted(dict.fromkeys(summary["embedded"]))
    remaining = embed_done_books(user_id)
    summary["embedded"] = sorted(dict.fromkeys(summary["embedded"] + remaining))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk OCR of raw scanned books via Gemini.")
    parser.add_argument("--book", help="Substring filter on PDF filename.")
    parser.add_argument("--limit", type=int, help="Max pages to OCR per book in this run.")
    parser.add_argument("--pages-per-request", type=int, help="Pages per Gemini request (default from .env).")
    parser.add_argument("--embed-only", action="store_true",
                        help="Only embed already-OCR'd books into the text store.")
    parser.add_argument("--include-plans", action="store_true",
                        help="Also OCR the plan/mock PDFs (skipped by default).")
    args = parser.parse_args()

    summary = run(
        book_filter=args.book,
        limit=args.limit,
        pages_per_request=args.pages_per_request,
        embed_only=args.embed_only,
        include_plans=args.include_plans,
    )
    print("OCR'd this run:", summary["ocred"] or "none")
    print("Capped (resume another day):", summary["capped"] or "none")
    print("Still pending:", summary["skipped"] or "none")
    print("Embedded:", summary["embedded"] or "none")
    print("Failed:", summary["failed"] or "none")