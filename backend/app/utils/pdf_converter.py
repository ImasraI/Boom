#!/usr/bin/env python3
"""
Converts PDF to text using PyMuPDF (text layer) + EasyOCR GPU (scanned pages).
Returns the extracted text as a string.
"""

from pathlib import Path
from typing import Any, Protocol, cast

import pymupdf
import numpy as np
import easyocr

DPI = 150

_reader = None


class _PdfPage(Protocol):
    def get_text(self, kind: str) -> str: ...

    def get_pixmap(self, *, matrix: Any, alpha: bool) -> Any: ...


def get_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['fa', 'en'], gpu=True)  # GPU enabled
    return _reader


def pdf_to_text(pdf_path: Path, use_ocr: bool = True) -> str:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    import pymupdf
    doc = pymupdf.open(pdf_path)
    all_text = []

    try:
        for page_num in range(1, doc.page_count + 1):
            page = doc[page_num - 1]

            # Try native text layer first
            raw_text = page.get_text("text")
            if raw_text and isinstance(raw_text, str) and raw_text.strip():
                all_text.append(f"===== صفحه {page_num} =====\n{raw_text.strip()}\n")
                continue

            # No text layer → EasyOCR on GPU (fast, local)
            if True:
                zoom = 150 / 72
                matrix = pymupdf.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                # Convert pixmap to numpy array
                if pix.n == 1:
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
                elif pix.n == 3:
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                else:  # RGBA
                    img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    img_array = img_rgb[:, :, :3]

                result = get_reader().readtext(img_array, detail=0, paragraph=False)
                page_text = "\n".join(str(item) for item in result) if result else ""
                all_text.append(f"===== صفحه {page_num} =====\n{page_text}\n")
    finally:
        doc.close()

    return "\n".join(all_text)