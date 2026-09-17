"""
Renders each page of a PDF to an image, storing the result via the R2
storage wrapper (or local disk fallback).  Returns the *key* (not a local
Path) so the caller can hand it to the vision pipeline regardless of
whether R2 or local disk is active.
"""

import sys
from pathlib import Path
from typing import Any, List, cast

import pymupdf

from app.utils.logger import get_logger
from app.utils.storage import put_object, get_object

logger = get_logger(__name__)


def pdf_to_page_images(
    pdf_path: Path,
    user_id: int,
    document_name: str,
    dpi: int = 200,
) -> List[str]:
    """
    Rasterize every page of `pdf_path` into PNG images stored via the
    R2-aware storage module.

    Returns a list of *storage keys* (not local Path objects) in page order.
    The key scheme is: ``{user_id}/{document_name}/page_{page_num:04d}.png``.

    If R2 credentials are not configured, images fall back to local disk
    under ``data/page_images/`` and the returned keys still follow the
    same scheme so the downstream pipeline (pipeline.py) can read them
    back via ``get_object()``.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)

    image_keys: List[str] = []

    doc = pymupdf.open(pdf_path)
    try:
        for page_num in range(1, doc.page_count + 1):
            page = cast(Any, doc[page_num - 1])
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Key scheme: {user_id}/{document_name}/page_{page_num:04d}.png
            key = f"{user_id}/{document_name}/page_{page_num:04d}.png"

            # Render to bytes in memory first, then upload
            buf = pix.tobytes(format="PNG")
            put_object(key, buf)

            image_keys.append(key)

        logger.info(
            f"Rendered {len(image_keys)} page image(s) from '{pdf_path.name}' "
            f"at {dpi} DPI (key scheme: {key})."
        )
    finally:
        doc.close()

    return image_keys