"""Local, hash-identified exam evidence. Never imports application DB or vectors."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "exam_examples"


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, separators=(",", ":"))
            f.flush(); os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def payload_digest(value) -> str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


@contextmanager
def job_lock(root: Path):
    """OS releases the lock on disconnect/crash; stale PID files cannot block resume."""
    root.mkdir(parents=True,exist_ok=True)
    with (root/'worker.lock').open('a+b') as handle:
        handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error: raise RuntimeError('Another corpus worker is running') from error
        try:yield
        finally:
            handle.seek(0)
            if os.name == 'nt': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle,fcntl.LOCK_UN)


def worker_alive(pid):
    if type(pid) is not int or pid<=0:return False
    if os.name == 'nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False
        try:
            code=ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(ctypes.c_void_p(handle))
    try:os.kill(pid,0);return True
    except OSError:return False


def normalized_text(text: str) -> str:
    # Search copy only. Never overwrite literal strings or equation signs.
    return unicodedata.normalize("NFKC", text).replace("ي", "ی").replace("ك", "ک")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def safe_path(parent: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or ":" in name or name.startswith(("/", "\\")):
        raise ValueError("Unsafe source path")
    clean = name.replace("\\", "/")
    if ".." in clean.split("/"): raise ValueError("Unsafe source path")
    target = (parent / clean).resolve()
    if not target.is_relative_to(parent.resolve()): raise ValueError("Unsafe source path")
    return target


def native_path(root: Path, document_id: str, page: int) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", document_id) or type(page) is not int or page < 1:
        raise ValueError("Invalid document/page identity")
    return root / "documents" / document_id / "native" / f"page_{page:05d}.json"


def confirmed_major(text: str) -> str | None:
    s = normalized_text(text)
    if re.search(r"(?:رشته|گروه|علوم)\s*(?:آزمایشی\s*)?ریاضی(?:\s*و\s*فنی|[\s‌-]*فیزیک)?", s): return "riazi"
    if re.search(r"(?:رشته|گروه|علوم)\s*(?:آزمایشی\s*)?تجربی", s): return "tajrobi"
    if re.search(r"(?:رشته|گروه|علوم)\s*(?:آزمایشی\s*)?انسانی", s): return "ensani"
    return None


def extraction_quality(text: str) -> dict:
    count = len(text.strip())
    bad = sum(c == "\ufffd" or (unicodedata.category(c) == "Cc" and c not in "\n\r\t") for c in text)
    letters = sum("\u0600" <= c <= "\u06ff" or "\ufb50" <= c <= "\ufeff" for c in text)
    return {"characters": count, "bad_character_ratio": bad / max(1, count),
            "persian_characters": letters,
            "needs_ocr": count < 120 or bad / max(1, count) > .01,
            "scientific_state": "not_checked"}


def extract_native(project: Path, root=DEFAULT_ROOT, *, progress=lambda event: None):
    import pymupdf
    inventory = read_json(root / "inventory.json")
    if not inventory: raise ValueError("Run source inventory before extraction")
    state = {"schema_version": SCHEMA_VERSION, "phase": "native_extraction", "pid": os.getpid(),
             "started_at": time.time(), "heartbeat": time.time(), "completed": 0, "failed": 0,
             "total_pages": sum(d.get("pages", 0) for d in inventory["documents"])}
    for document in inventory["documents"]:
        if "error" in document: continue
        source = safe_path(project, document["path"])
        document_id = document["document_id"]
        if digest(source)!=document_id:raise ValueError('Source content changed; re-inventory before resume')
        with pymupdf.open(source) as pdf:
            if pdf.page_count != document["pages"]: raise ValueError("Source page count changed")
            source_major = None
            for page_index in range(pdf.page_count):
                page = page_index + 1
                target = native_path(root, document_id, page)
                saved = read_json(target)
                if (saved and saved.get("schema_version") == SCHEMA_VERSION and saved.get("document_id") == document_id
                    and saved.get('pdf_page')==page and isinstance(saved.get('literal_text'),str)
                    and saved.get('layout_version')==2 and isinstance(saved.get('images'),list)
                    and isinstance(saved.get('blocks'),list) and isinstance(saved.get('quality'),dict)):
                    source_major = source_major or saved.get("source_major")
                    state["completed"] += 1
                    continue
                try:
                    p = pdf[page_index]
                    text = p.get_text("text", sort=False)
                    source_major = source_major or confirmed_major(text)
                    layout = p.get_text("dict",flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
                    blocks = []
                    for block in layout.get("blocks", []):
                        if block.get("type") != 0: continue
                        lines = []
                        for line in block.get("lines", []):
                            lines.append({"bbox": list(line["bbox"]), "direction": list(line.get("dir", [1, 0])),
                                "spans": [{"text": span["text"], "bbox": list(span["bbox"]),
                                           "font": span.get("font"), "size": span.get("size")}
                                          for span in line.get("spans", [])]})
                        blocks.append({"bbox": list(block["bbox"]), "lines": lines})
                    atomic_json(target, {"schema_version": SCHEMA_VERSION, 'layout_version':2,"document_id": document_id,
                        "document_name": document["name"], "pdf_page": page, "source_major": source_major,
                        "dimensions": [p.rect.width, p.rect.height], "literal_text": text,
                        "search_text": normalized_text(text), "blocks": blocks,
                        "quality": extraction_quality(text), "images":[{'bbox':list(i['bbox']),'width':i['width'],'height':i['height']}
                            for i in p.get_image_info()], "engine": "pymupdf", "engine_version": pymupdf.VersionBind})
                    state["completed"] += 1
                except Exception:
                    state["failed"] += 1
                    atomic_json(target.with_suffix(".error.json"), {"document_id": document_id, "page": page, "error": "native_extraction_error"})
                if page % 20 == 0:
                    state["heartbeat"] = time.time(); atomic_json(root / "native-status.json", state)
            state.update(heartbeat=time.time(), document=document["name"])
            atomic_json(root / "native-status.json", state); progress(state.copy())
    state.update(phase="native_extraction_complete", heartbeat=time.time())
    atomic_json(root / "native-status.json", state)
    return state


def render_page(source: Path, page: int, target: Path, dpi=220) -> Path:
    import pymupdf
    target.parent.mkdir(parents=True, exist_ok=True)
    signature={'source_sha256':digest(source),'pdf_page':page,'dpi':dpi,'engine_version':pymupdf.VersionBind}
    metadata=target.with_suffix('.render.json')
    if target.is_file() and read_json(metadata)==signature: return target
    with pymupdf.open(source) as pdf:
        if page < 1 or page > pdf.page_count: raise ValueError("Invalid PDF page")
        image = pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        # Byte write uses the same atomic-rename discipline as the records.
        fd, temp = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(image.tobytes("png")); f.flush(); os.fsync(f.fileno())
            os.replace(temp, target)
            atomic_json(metadata,signature)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return target


def status(root=DEFAULT_ROOT):
    inventory = read_json(root / "inventory.json", {"documents": []})
    native = read_json(root / "native-status.json", {})
    scan = read_json(root / "scan-status.json", {})
    stored = sum(1 for p in (root / "documents").glob("*/native/page_*.json") if not p.name.endswith(".error.json"))
    records = read_json(root / "style-index.json", {"records": []})
    coordinator=read_json(root/'coordinator-status.json',{})
    coordinator['worker_alive']=worker_alive(coordinator.get('pid'))
    native['worker_alive']=worker_alive(native.get('pid'))
    scan['worker_alive']=worker_alive(scan.get('pid'))
    scan['heartbeat_age_seconds']=round(max(0,time.time()-scan.get('heartbeat',time.time())))
    return {"unique_documents": len(inventory["documents"]),
            "total_pages": sum(d.get("pages", 0) for d in inventory["documents"]),
            "stored_native_pages": stored, "native": native, "scan": scan,'coordinator':coordinator,
            "style_references": len(records.get("records", [])),
            "human_reviewed_references": sum(bool(r.get("human_reviewed")) for r in records.get("records", []))}
