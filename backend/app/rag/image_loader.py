"""
Renders each page of a PDF to an image file on disk.

This is the entry point for the "page-as-image" RAG pipeline: instead of
extracting text (and losing tables/figures/layout, or fighting OCR errors),
every page becomes one image chunk that gets embedded and, later, handed
directly to a vision-capable LLM.
"""

from pathlib import Path
from typing import Any, List, cast

import pymupdf

from app.utils.logger import get_logger

logger = get_logger(__name__)


def pdf_to_page_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 200,
) -> List[Path]:
    """
    Rasterize every page of `pdf_path` into a PNG file under `output_dir`.

    Returns the list of image paths, in page order (page 1 first).
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)

    image_paths: List[Path] = []

    doc = pymupdf.open(pdf_path)
    try:
        for page_num in range(1, doc.page_count + 1):
            page = cast(Any, doc[page_num - 1])
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            image_path = output_dir / f"page_{page_num:04d}.png"
            pix.save(str(image_path))
            image_paths.append(image_path)

        logger.info(
            f"Rendered {len(image_paths)} page image(s) from '{pdf_path.name}' "
            f"at {dpi} DPI."
        )
    finally:
        doc.close()

    return image_paths
