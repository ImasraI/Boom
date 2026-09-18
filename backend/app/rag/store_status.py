"""
Inspect how much book content is actually embedded, and where.

Tells you whether the 34 raw books are carrying content in the two Chroma
stores:

    * TEXT store  (collection "documents")          - OCR'd pages / uploaded text
    * IMAGE store (collection "document_images_*")  - page images of every book

Usage::

    cd backend
    .venv\\Scripts\\python.exe -m app.rag.store_status [--user 1]

If Chroma is unavailable/corrupt it falls back to a read-only SQLite crawl of
the store file so you can still see what is there.
"""

import argparse
from collections import Counter
from pathlib import Path
from typing import Dict, List

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _via_chroma(user_id: int) -> Dict[str, Dict[str, int]]:
    """Per-collection {document_name: chunk_count} using the real clients."""
    from app.rag.vector_store import get_vector_store, get_image_vector_store

    out: Dict[str, Dict[str, int]] = {}

    for key, store in (("documents", get_vector_store()), ("document_images", get_image_vector_store())):
        col = store.collection
        counts: Counter = Counter()
        n = col.count()
        step = 1000
        for offset in range(0, n, step):
            data = col.get(limit=step, offset=offset, where={"user_id": user_id},
                           include=["metadatas"])
            for m in (data.get("metadatas") or []):
                if m and m.get("document_name"):
                    counts[m["document_name"]] += 1
        out[key] = dict(counts)
    return out


def _via_sqlite() -> Dict[str, Dict[str, int]]:
    """Read-only crawl of chroma.sqlite3 -> per collection {document_name: count}."""
    import sqlite3

    db = Path(get_settings().CHROMA_DIR) / "chroma.sqlite3"
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """
            select c.name, m.string_value, count(*)
            from embeddings e
            join segments s on s.id = e.segment_id
            join collections c on c.id = s.collection_id
            join embedding_metadata m on m.id = e.id and m.key = 'document_name'
            group by c.name, m.string_value
            order by c.name, m.string_value
            """
        ).fetchall()
    finally:
        con.close()
    out: Dict[str, Dict[str, int]] = {}
    for coll, doc, cnt in rows:
        out.setdefault(coll, {})[doc] = cnt
    return out


def main() -> None:
    from app.rag.ingest_raw import list_raw_pdfs

    parser = argparse.ArgumentParser(description="Show how much book content is embedded.")
    parser.add_argument("--user", type=int, default=None)
    args = parser.parse_args()

    uid = args.user or get_settings().DEMO_USER_ID
    raw_pdfs = list_raw_pdfs()
    raw_by_cat: Counter = Counter()
    for p in raw_pdfs:
        raw_by_cat[p.parent.name or "flat"] += 1

    source = "chroma"
    try:
        counts = _via_chroma(uid)
    except Exception as exc:
        logger.warning("Chroma read failed (%s); falling back to sqlite crawl.", exc)
        counts = _via_sqlite()
        source = "sqlite (fallback)"

    print(f"Raw PDFs available: {len(raw_pdfs)}")
    for cat, n in raw_by_cat.most_common():
        print(f"   {cat:<20} {n}")

    labels = [("TEXT store ('documents')", "documents", False),
              ("IMAGE store ('document_images_*')", "document_images", True)]
    for label, key, is_image in labels:
        per_doc = next((counts[k] for k in counts if k == key or (is_image and k.startswith("document_images"))), {})
        total = sum(per_doc.values())
        print(f"\n{label} — {total} chunks across {len(per_doc)} doc(s)  [{source}]")
        for doc in sorted(per_doc):
            print(f"   {per_doc[doc]:>6}  {doc}")
        if is_image:
            missing = sorted({p.name for p in raw_pdfs} - set(per_doc))
            if missing:
                print(f"   Books NOT embedded as pages ({len(missing)} of {len(raw_pdfs)}):")
                for m in missing:
                    print(f"      - {m}")
            else:
                print("   All raw books are embedded as page images.")

    print("\nAn empty TEXT store is normal until a book's OCR finishes and is embedded "
          "(python -m app.rag.ocr_corpus). Book *page images* live in the IMAGE store.")


if __name__ == "__main__":
    main()