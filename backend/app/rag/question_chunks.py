"""
Question-aware chunking of the structured page transcriptions.

Turns each page's transcription JSON (see app.rag.page_transcribe) into
retrieval chunks:

- one chunk per printed question: question text + options + figure
  description, with metadata (book, page, question number, has_figure);
- one chunk for the lesson prose (page_text) of lesson pages;
- one chunk per general lesson figure / table description.

Chunks are embedded with the configured embedding model and stored in the
dedicated ``question_bank`` Chroma collection, namespaced per page
(document_name = "<book>::p<page>") so re-embedding a page is idempotent.

Run::

    cd backend
    python -m app.rag.question_chunks                    # embed all books
    python -m app.rag.question_chunks --book "هندسه ۱"
    python -m app.rag.question_chunks --book "هندسه ۱" --pages 30
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.rag.ingest_raw import category_for_pdf, list_raw_pdfs
from app.rag.page_transcribe import saved_pages
from app.utils.logger import get_logger

logger = get_logger(__name__)

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _norm_num(v: Any) -> Optional[int]:
    """'۹۹' / '99' / 99 -> 99 (None if not numeric)."""
    if v is None:
        return None
    s = str(v).strip().translate(_FA_DIGITS)
    m = re.search(r"\d{1,4}", s)
    return int(m.group(0)) if m else None


def build_chunks_for_page(book_stem: str, page: int, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One page's transcription -> retrieval chunks with rich metadata."""
    chunks: List[Dict[str, Any]] = []
    page_kind = str(data.get("page_kind") or "other")
    lesson_title = str(data.get("lesson_title") or "").strip()

    for q in data.get("questions", []):
        text = str(q.get("text") or "").strip()
        if not text:
            continue
        num = _norm_num(q.get("number", q.get("question_number")))
        opts = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        fig = str(q.get("figure") or q.get("figure_description") or "").strip()
        has_figure = bool(q.get("has_figure") or fig)

        parts = [f"[کتاب {book_stem} | صفحه {page}" + (f" | سؤال {num}" if num else "") + "]"]
        parts.append(text)
        if opts:
            parts.append("گزینه‌ها: " + " | ".join(opts))
        if fig:
            parts.append(f"توصیف شکل: {fig}")
        label = "درس" if page_kind == "lesson" else "سؤال"
        chunks.append({
            "text": "\n".join(parts),
            "metadata": {
                "kind": "question",
                "book": book_stem,
                "page": page,
                "question_number": num,
                "has_figure": has_figure,
                "page_kind": page_kind,
                "lesson_title": lesson_title,
                "label": label,
            },
        })

    body = str(data.get("page_text") or "").strip()
    if body:
        head = f"[کتاب {book_stem} | صفحه {page}" + (f" | درس: {lesson_title}" if lesson_title else "") + "]"
        chunks.append({
            "text": f"{head}\n{body}",
            "metadata": {
                "kind": "lesson",
                "book": book_stem,
                "page": page,
                "question_number": None,
                "has_figure": bool(data.get("figures_general")),
                "page_kind": page_kind,
                "lesson_title": lesson_title,
                "label": "متن درس",
            },
        })

    for i, fig in enumerate(data.get("figures_general", [])):
        fig = str(fig).strip()
        if not fig:
            continue
        chunks.append({
            "text": f"[کتاب {book_stem} | صفحه {page} | شکل درس]\n{fig}",
            "metadata": {
                "kind": "figure",
                "book": book_stem,
                "page": page,
                "question_number": None,
                "has_figure": True,
                "page_kind": page_kind,
                "lesson_title": lesson_title,
                "label": f"شکل {i + 1}",
            },
        })

    for i, tbl in enumerate(data.get("tables", [])):
        tbl = str(tbl).strip()
        if not tbl:
            continue
        chunks.append({
            "text": f"[کتاب {book_stem} | صفحه {page} | جدول]\n{tbl}",
            "metadata": {
                "kind": "table",
                "book": book_stem,
                "page": page,
                "question_number": None,
                "has_figure": False,
                "page_kind": page_kind,
                "lesson_title": lesson_title,
                "label": f"جدول {i + 1}",
            },
        })
    return chunks


def _qa_document_name(book_stem: str, page: int) -> str:
    return f"{book_stem}::p{page}"


def embed_book(
    book_stem: str,
    user_id: Optional[int] = None,
    only_pages: Optional[set] = None,
    rebuild: bool = False,
) -> int:
    """Embed every transcribed page of a book into the question_bank store.

    Per-page idempotent: pages already embedded are skipped unless
    ``rebuild`` is set. Returns the number of pages embedded this run.
    """
    from app.rag.embeddings import get_embedding_model
    from app.rag.vector_store import get_question_vector_store

    settings = get_settings()
    user_id = user_id if user_id is not None else settings.DEMO_USER_ID

    pages = saved_pages(book_stem)
    if not pages:
        logger.warning("No transcriptions for '%s' yet.", book_stem)
        return 0

    store = get_question_vector_store()
    embedded_pages = set()
    if not rebuild:
        existing = store.collection.get(
            where={"$and": [{"user_id": user_id}, {"book": book_stem}]},
            include=["metadatas"],
        )
        for m in (existing.get("metadatas") or []):
            if m and m.get("page") is not None:
                try:
                    embedded_pages.add(int(m["page"]))
                except (TypeError, ValueError):
                    continue

    model = get_embedding_model()
    embedded = 0
    for page in sorted(pages):
        if page in embedded_pages and not (only_pages and page in only_pages):
            continue
        if only_pages is not None and page not in only_pages:
            continue
        chunks = build_chunks_for_page(book_stem, page, pages[page])
        if not chunks:
            continue
        doc_name = _qa_document_name(book_stem, page)
        store.delete_document(doc_name, user_id)
        texts = [c["text"] for c in chunks]
        vectors = model.embed_documents(texts)
        if not vectors or not vectors[0]:
            logger.warning("Embedding failed for %s page %d; skipping.", book_stem, page)
            continue
        store.add_chunks_qa(
            document_name=doc_name,
            chunks=texts,
            embeddings=vectors,
            user_id=user_id,
            extra=[c["metadata"] for c in chunks],
            category="question_bank",
        )
        embedded += 1
        logger.info("Embedded %s page %d (%d chunks).", book_stem, page, len(chunks))
    return embedded


def embed_all_books(
    user_id: Optional[int] = None,
    book_filter: Optional[str] = None,
) -> List[str]:
    pdfs = list_raw_pdfs()
    if book_filter:
        needle = book_filter.strip().lower()
        pdfs = [p for p in pdfs if needle in p.name.lower()]
    pdfs = [p for p in pdfs if category_for_pdf(p) != "plan"]
    done = []
    for pdf in pdfs:
        n = embed_book(pdf.stem, user_id=user_id)
        if n:
            done.append(pdf.stem)
    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed question-bank chunks from transcriptions.")
    parser.add_argument("--book", help="Substring filter on book filename.")
    parser.add_argument("--rebuild", action="store_true", help="Re-embed pages even if already embedded.")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    books = embed_all_books(book_filter=args.book)
    if args.book and not books:
        # filter matched nothing embedded; try direct stem run for feedback
        books = embed_all_books(book_filter=args.book)
    print("Embedded books:", books or "none")
