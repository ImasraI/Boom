#!/usr/bin/env python3
"""
Converts PDF to text using PyMuPDF (text layer) + Ollama qwen2.5vl:7b (scanned pages).
Optimized for speed: 72 DPI, lower num_predict. Supports page range for incremental OCR.
"""

from pathlib import Path
from typing import Any, Protocol, Optional, cast
import base64
import io
import requests

import pymupdf
from PIL import Image

DPI = 72
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5vl:7b"


class _PdfPage(Protocol):
    def get_text(self, kind: str) -> str: ...

    def get_pixmap(self, *, matrix: Any, alpha: bool) -> Any: ...


OCR_PROMPT = """این صفحه از یک کتاب درسی کنکور ایرانی است. لطفاً:
۱. تمام متن فارسی/عربی/انگلیسی را استخراج کنید (شامل سوالات، گزینه‌ها، فرمول‌ها، جداول)
۲. اگر تصویر/شکل/نمودار/جدول بصری دارد، آن را به زبان فارسی توصیف کنید
۳. اگر سوالی در تصویر است، متن سوال و گزینه‌ها را بنویسید
۴. اگر درس/مبحثی توضیح داده شده، خلاصه‌ی آموزشی به فارسی بدهید

فرمت خروجی:
=== صفحه 1 ===
[متن استخراج شده + توصیفات فارسی تصاویر/شکل‌ها]"""


def _pixmap_to_base64(pix) -> str:
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _ollama_ocr_image(base64_image: str, page_num: int) -> str:
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": OCR_PROMPT.replace("صفحه 1", f"صفحه {page_num}"),
            "images": [base64_image]
        }],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 1500}
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"(خطای OCR: {e})"


def pdf_to_text(
    pdf_path: Path,
    use_ocr: bool = True,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None
) -> str:
    """
    Extract text from PDF pages.
    
    Args:
        pdf_path: Path to PDF file
        use_ocr: If True, use vision model for pages without text layer
        start_page: 1-indexed start page (inclusive), None = first page
        end_page: 1-indexed end page (inclusive), None = last page
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    total_pages = doc.page_count
    
    start = (start_page - 1) if start_page else 0
    end = end_page if end_page else total_pages
    start = max(0, min(start, total_pages - 1))
    end = max(start + 1, min(end, total_pages))

    all_text = []

    try:
        for page_num in range(start + 1, end + 1):
            page = doc[page_num - 1]

            # Try native text layer first
            raw_text = page.get_text("text")
            if raw_text and isinstance(raw_text, str) and raw_text.strip():
                all_text.append(f"=== صفحه {page_num} ===\n{raw_text.strip()}\n")
                continue

            # No text layer → OCR via qwen2.5vl:7b at 72 DPI
            zoom = DPI / 72
            matrix = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            b64 = _pixmap_to_base64(pix)
            ocr_text = _ollama_ocr_image(b64, page_num)
            all_text.append(f"=== صفحه {page_num} ===\n{ocr_text}\n")

    finally:
        doc.close()

    return "\n".join(all_text)