"""
Structured per-page transcription of the scanned book corpus.

For every page of every raw PDF a vision model produces a strict JSON
description of the page:

{
  "page_kind": "lesson | test | mixed | other",
  "lesson_title": "...",
  "page_text": "main prose of the page (lesson text), or empty",
  "questions": [
    {"number": 1, "text": "...", "options": [...], "figure": "...",
     "has_figure": true}
  ],
  "figures_general": ["..."],
  "tables": ["..."],
  "formulas": ["..."]
}

Provider chain (TRANSCRIBE_PROVIDER="auto"): gemini -> groq -> ollama.
Every page result is cached at ``data/ocr/<book>/pages/page_NNNN.json``
so the job is fully resumable and re-runs only touch pending pages.

Gemini gives the best Persian/figure quality but is geo-blocked without
a VPN; Groq (qwen3.8-27b) is always reachable but output-token limited;
the local Ollama model is the offline last resort.

Run::

    cd backend
    python -m app.rag.page_transcribe                    # all books
    python -m app.rag.page_transcribe --book "ریاضی ۱"
    python -m app.rag.page_transcribe --limit 5          # 5 pages/book
"""

import argparse
import base64
import io
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.config import get_settings
from app.rag.ingest_raw import category_for_pdf, list_raw_pdfs
from app.utils.logger import get_logger

logger = get_logger(__name__)

TRANSCRIBE_PROMPT = """You are a precise OCR + document-understanding engine for Iranian konkur test books (Persian).

Transcribe this book page into structured JSON exactly in this shape:
{
  "page_kind": "lesson | test | mixed | other",
  "lesson_title": "the lesson/section title on the page in Persian, or empty",
  "page_text": "full prose of the page's lesson text in Persian (for lesson pages). Empty for pure test pages.",
  "questions": [
    {
      "number": 1,
      "text": "full question text in Persian",
      "options": ["گزینه 1", "گزینه 2", "گزینه 3", "گزینه 4"],
      "figure": "detailed Persian description of any figure/graph/shape attached to this question, or empty",
      "has_figure": true
    }
  ],
  "figures_general": ["descriptions of lesson figures/diagrams not attached to a question"],
  "tables": ["descriptions of tables"],
  "formulas": ["math/chemistry formulas found, in LaTeX-ish or plain text"]
}

Rules:
- Copy Persian text EXACTLY as written. Do not translate. Do not summarize.
- Include EVERY numbered question on the page (test pages usually have 10+). Numbers must match the printed question numbers exactly.
- Question numbers that reference another book/exam in parentheses (e.g. (خارج ریاضی ۸۷)) stay inside the question text.
- Describe figures in Persian with geometric details: shapes, labels (A, B, C...), marked angles, given lengths, parallel/perpendicular marks.
- Options must contain all printed choices, in order, including mathematical notation (sqrt, fractions) as plain text.
- Output ONLY the JSON object, no markdown fences, no commentary."""

_OLLAMA_CHAT = "http://127.0.0.1:11434/api/chat"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_MAX_IMAGE_BYTES = 3_000_000  # keep every provider comfortably under limits


# --------------------------------------------------------------------------
# image preparation
# --------------------------------------------------------------------------

def render_page_bytes(pdf: Path, page: int, dpi: int) -> bytes:
    """Render one PDF page to PNG bytes, down-sized to JPEG if too heavy."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        if page < 1 or page > doc.page_count:
            raise ValueError(f"page {page} out of range (1..{doc.page_count})")
        zoom = dpi / 72
        pix = doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
    if len(png) <= _MAX_IMAGE_BYTES:
        return png
    # Re-encode as JPEG (white background) to cut the payload size.
    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# --------------------------------------------------------------------------
# providers
# --------------------------------------------------------------------------

class ProviderResult:
    def __init__(self, ok: bool, raw: str = "", error: str = "",
                 unavailable: bool = False, wait_s: float = 0.0):
        self.ok = ok
        self.raw = raw
        self.error = error
        # unavailable=True means "do not use this provider again this run"
        self.unavailable = unavailable
        # wait_s: seconds to sleep before the *next* request (rate limit)
        self.wait_s = wait_s


def _gemini_call(model: str, image_b64: str, key: str, timeout: int = 180) -> ProviderResult:
    payload = {
        "contents": [{"parts": [
            {"text": TRANSCRIBE_PROMPT},
            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
        ]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8000,
            "responseMimeType": "application/json",
        },
    }
    try:
        proxies = None
        from app.config import get_settings as _gs

        gemini_proxy = getattr(_gs(), "GEMINI_PROXY", "")
        if gemini_proxy:
            proxies = {"http": gemini_proxy, "https": gemini_proxy}
        r = requests.post(
            _GEMINI_URL.format(model=model), json=payload,
            params={"key": key}, timeout=timeout, proxies=proxies,
        )
    except Exception as e:
        return ProviderResult(False, error=str(e)[:300], wait_s=5.0)
    if r.status_code == 400 and "location" in r.text.lower():
        return ProviderResult(False, error="geo-blocked", unavailable=True)
    if r.status_code in (403,):
        return ProviderResult(False, error=r.text[:200], unavailable=True)
    if r.status_code == 429:
        # Distinguish a per-minute limit (wait it out) from a per-DAY quota
        # (sleeping a minute is useless - the worker enters a slow
        # sleep-retry loop until the daily reset).
        wait, daily = 30.0, False
        try:
            for det in r.json().get("error", {}).get("details", []):
                if "QuotaFailure" in str(det.get("@type", "")):
                    for v in det.get("violations", []):
                        if "PerDay" in v.get("quotaId", ""):
                            daily = True
                if "RetryInfo" in str(det.get("@type", "")):
                    d = det.get("retryDelay", "30s")
                    try:
                        wait = max(wait, float(str(d).rstrip("s")))
                    except Exception:
                        pass
        except Exception:
            pass
        return ProviderResult(False, error="429 daily quota" if daily else "429", wait_s=wait)
    if r.status_code >= 400:
        return ProviderResult(False, error=f"{r.status_code} {r.text[:200]}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return ProviderResult(True, raw=text)
    except Exception as e:
        return ProviderResult(False, error=f"bad response: {e}")


def _groq_call(model: str, image_b64: str, key: str, timeout: int = 240) -> ProviderResult:
    def _payload(force_json: bool) -> dict:
        p = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": TRANSCRIBE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ]}],
            "temperature": 0.0,
            "max_tokens": 8000,
        }
        if force_json:
            p["response_format"] = {"type": "json_object"}
        return p

    def _post(payload: dict, proxies) -> "requests.Response":
        return requests.post(
            _GROQ_URL, json=payload,
            headers={"Authorization": f"Bearer {key}"}, timeout=timeout,
            proxies=proxies,
        )

    # Groq's json_object mode intermittently fails generation (400
    # "Failed to generate JSON"); retry once without the constraint —
    # _parse_json tolerates free-form output.
    # A 403 on a direct call means Groq sees a blocked IP (VPN running
    # in system-proxy mode instead of TUN); retry once through the
    # configured proxy before giving up.
    proxy = getattr(get_settings(), "GEMINI_PROXY", "") or ""
    for force_json in (True, False):
        r = None
        for mode in ("direct", "proxy"):
            try:
                r = _post(_payload(force_json),
                          {"http": None, "https": None} if mode == "direct"
                          else {"http": proxy, "https": proxy})
            except Exception as e:
                if mode == "proxy":
                    return ProviderResult(False, error=str(e)[:300], wait_s=5.0)
                continue  # direct route failed -> try the proxy
            if r.status_code != 403 or not proxy:
                break
        if r is None:
            return ProviderResult(False,
                                  error="groq unreachable (direct + proxy)",
                                  wait_s=10.0)
        if r.status_code == 400 and "failed_generation" in r.text.lower():
            if force_json:
                continue  # retry once without response_format
            return ProviderResult(False, error=f"400 {r.text[:200]}")
    if r.status_code == 429:
        # honor the tightest reset window reported by Groq
        wait = 25.0
        for h in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests", "retry-after"):
            v = r.headers.get(h)
            if v:
                try:
                    wait = max(wait, float(v.rstrip("s").split("h")[0].split("m")[0]) if "h" not in v and "m" not in v else 60.0)
                except Exception:
                    pass
        return ProviderResult(False, error="429", wait_s=wait)
    if r.status_code in (401, 403):
        return ProviderResult(False, error=r.text[:200], unavailable=True)
    if r.status_code >= 400:
        return ProviderResult(False, error=f"{r.status_code} {r.text[:200]}")
    try:
        text = r.json()["choices"][0]["message"].get("content") or ""
        if not text.strip():
            return ProviderResult(False, error="empty content")
        return ProviderResult(True, raw=text, wait_s=6.0)
    except Exception as e:
        return ProviderResult(False, error=f"bad response: {e}")


def _ollama_call(model: str, image_b64: str, timeout: int = 900) -> ProviderResult:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TRANSCRIBE_PROMPT, "images": [image_b64]}],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {"temperature": 0.0, "num_predict": 3000, "num_ctx": 8192},
    }
    try:
        # trust_env: never send localhost Ollama traffic through a system/VPN proxy.
        r = requests.post(_OLLAMA_CHAT, json=payload, timeout=timeout,
                          proxies={"http": None, "https": None})
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "")
        if not text.strip():
            return ProviderResult(False, error="empty content")
        return ProviderResult(True, raw=text)
    except Exception as e:
        return ProviderResult(False, error=str(e)[:300], wait_s=3.0)


def _parse_json(raw: str) -> Dict[str, Any]:
    """Tolerant JSON extraction from a model response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("no JSON object found in model output")


# --------------------------------------------------------------------------
# storage layout
# --------------------------------------------------------------------------

def _ocr_root() -> Path:
    d = Path(get_settings().OCR_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _book_dir(book_stem: str) -> Path:
    # Windows forbids trailing spaces in directory names; some PDF stems
    # have them (e.g. "ریاضی جامع خیلی سبز جلد دوم ").
    d = _ocr_root() / book_stem.strip().rstrip(" .") / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _page_json_path(book_stem: str, page: int) -> Path:
    return _book_dir(book_stem) / f"page_{page:04d}.json"


# --------------------------------------------------------------------------
# STAGING store (model-scanned output awaiting promotion)
#
# Layout mirrors the live store but lives in data/ocr_pending/:
#   - cloud workers + the local Ollama transcriber WRITE here,
#   - retrieval (question_chunks) reads only the LIVE store (data/ocr),
#   - merge_and_embed.py --promote moves staged pages into the live store
#     and embeds them. This keeps "rough" model output out of the live
#     retrieval index until you decide to promote it (e.g. while the
#     EasyOCR baseline is the live text source).
# --------------------------------------------------------------------------

def _staging_root() -> Path:
    # <repo root>/scanned-pending - visible at the project root, next to
    # ocr-workers/. Derived from this file's location so it is CWD-proof.
    d = Path(__file__).resolve().parents[3] / "scanned-pending"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _staging_book_dir(book_stem: str) -> Path:
    d = _staging_root() / book_stem.strip().rstrip(" .") / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _staging_page_json_path(book_stem: str, page: int) -> Path:
    return _staging_book_dir(book_stem) / f"page_{page:04d}.json"


def load_staged_json(book_stem: str, page: int) -> Optional[Dict[str, Any]]:
    """Valid staged record for a page, or None (mirrors load_page_json)."""
    p = _staging_page_json_path(book_stem, page)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if "error" in data or "data" not in data:
        return None
    return data["data"]


def load_page_json(book_stem: str, page: int) -> Optional[Dict[str, Any]]:
    p = _page_json_path(book_stem, page)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if "error" in data or "data" not in data:
        return None
    return data["data"]


def saved_pages(book_stem: str) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for f in sorted(_book_dir(book_stem).glob("page_*.json")):
        try:
            page = int(f.stem.split("_")[1])
        except (ValueError, IndexError):
            continue
        data = load_page_json(book_stem, page)
        if data is not None:
            out[page] = data
    return out


# --------------------------------------------------------------------------
# main engine
# --------------------------------------------------------------------------

def _chain(providers: str, settings) -> List[str]:
    if providers != "auto":
        return [providers]
    chain = []
    if settings.GEMINI_API_KEY:
        chain.append("gemini")
    if getattr(settings, "GROQ_API_KEY", ""):
        chain.append("groq")
    chain.append("ollama")
    return chain


def transcribe_page(pdf: Path, page: int, chain: List[str], settings) -> Dict[str, Any]:
    """Transcribe one page trying providers in order. Returns the stored record."""
    dpi = getattr(settings, "TRANSCRIBE_DPI", 150)
    image = render_page_bytes(pdf, page, dpi)
    t0 = time.time()
    b64 = _b64(image)
    errors: List[str] = []
    for provider in chain:
        if provider == "gemini":
            res = _gemini_call(settings.GEMINI_MODEL_NAME, b64, settings.GEMINI_API_KEY)
        elif provider == "groq":
            res = _groq_call(settings.GROQ_VISION_MODEL, b64, settings.GROQ_API_KEY)
        elif provider == "ollama":
            res = _ollama_call(getattr(settings, "TRANSCRIBE_LOCAL_MODEL", "qwen2.5vl:7b"), b64)
        else:
            continue
        if res.ok:
            try:
                data = _parse_json(res.raw)
            except Exception as e:
                errors.append(f"{provider}: JSON parse failed: {e}")
                continue
            return {
                "page": page,
                "provider": provider,
                "latency_hint": round(time.time() - t0, 1),
                "data": data,
            }
        errors.append(f"{provider}: {res.error}")
        if res.unavailable:
            chain = [p for p in chain if p != provider]
            if not chain:
                break
        if res.wait_s:
            time.sleep(res.wait_s)
    return {"page": page, "provider": "none", "error": " | ".join(errors)[:500]}


def transcribe_book(
    pdf: Path,
    limit: Optional[int] = None,
    providers: str = "auto",
    max_errors: int = 8,
) -> Dict[str, Any]:
    """Transcribe all pending pages of one book. Returns a status summary."""
    settings = get_settings()
    import pymupdf

    try:
        with pymupdf.open(pdf) as doc:
            total = doc.page_count
    except Exception as e:
        return {"book": pdf.name, "status": "error", "detail": str(e)[:200]}

    stem = pdf.stem
    done = saved_pages(stem)
    pending = [p for p in range(1, total + 1) if p not in done]
    if limit:
        pending = pending[:limit]

    stats = {"book": pdf.name, "total": total, "already_done": len(done),
             "transcribed": 0, "failed": 0, "providers": {}}
    if not pending:
        stats["status"] = "done"
        return stats

    chain = _chain(providers, settings)
    consecutive_errors = 0
    for page in pending:
        record = transcribe_page(pdf, page, list(chain), settings)
        if "data" in record:
            out = _page_json_path(stem, page)
            out.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            stats["transcribed"] += 1
            stats["providers"][record["provider"]] = stats["providers"].get(record["provider"], 0) + 1
            consecutive_errors = 0
            # gentle pacing between successful cloud calls
            time.sleep(1.0 if record.get("provider") == "ollama" else getattr(settings, "TRANSCRIBE_SLEEP_SECONDS", 2.0))
        else:
            out = _page_json_path(stem, page)
            out.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            stats["failed"] += 1
            consecutive_errors += 1
            if consecutive_errors >= max_errors:
                stats["status"] = "stalled"
                stats["detail"] = f"{consecutive_errors} consecutive failures; stopping this run"
                break
    else:
        stats["status"] = "done" if stats["failed"] == 0 else "partial"

    logger.info("transcribe_book %s -> %s", pdf.name, stats["status"])
    return stats


def run(
    book_filter: Optional[str] = None,
    limit: Optional[int] = None,
    providers: str = "auto",
    include_plans: bool = False,
) -> Dict[str, Any]:
    pdfs = list_raw_pdfs()
    if book_filter:
        needle = book_filter.strip().lower()
        pdfs = [p for p in pdfs if needle in p.name.lower()]
        if not pdfs:
            return {"error": f"no book matches '{book_filter}'"}
    if not include_plans:
        pdfs = [p for p in pdfs if category_for_pdf(p) != "plan"]

    results = []
    for pdf in pdfs:
        results.append(transcribe_book(pdf, limit=limit, providers=providers))
    return {"books": results}


if __name__ == "__main__":
    sys_stdout_is_utf8 = True
    parser = argparse.ArgumentParser(description="Bulk structured transcription of scanned books.")
    parser.add_argument("--book", help="Substring filter on PDF filename.")
    parser.add_argument("--limit", type=int, help="Max pages to transcribe per book this run.")
    parser.add_argument("--providers", default="auto", help="auto | gemini | groq | ollama")
    parser.add_argument("--include-plans", action="store_true")
    args = parser.parse_args()

    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    summary = run(book_filter=args.book, limit=args.limit,
                  providers=args.providers, include_plans=args.include_plans)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
