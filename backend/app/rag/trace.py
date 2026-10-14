"""Per-request RAG traces: a readable record of every stage behind an answer.

Why a contextvar: the retrieval helpers (``hybrid_search``, ``LexicalIndex``,
the reranker, the LLM clients) are shared singletons reached from many call
sites. Threading a ``trace`` parameter through all of them would touch every
signature for a debugging feature, so the active trace travels in a
``ContextVar`` instead. ``stage()`` is a no-op when nothing is recording, so
the production chat path pays one contextvar lookup per stage and nothing
else - it never builds rows it will not keep.

What a trace holds
    Each stage is a plain dict, so the API and the UI need no per-stage code:

        {"name": "rerank", "label": "بازرتبه‌بندی", "ms": 812.4,
         "command": "CrossEncoder.predict(20 pairs, max_length=512)",
         "meta": {"model": "BAAI/bge-reranker-base", "available": True},
         "columns": [{"key": "rank", "label": "رتبه"}],
         "rows": [{"rank": 1, "doc": "فیزیک ۱.pdf", "delta": 3}],
         "text": {"prompt": "..."}}

Traces live in memory only (the last ``TRACE_LIMIT`` per process) and are
never written to disk; they can contain chunk text and prompts, so the API
that serves them is admin-only.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
import math
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import unquote, urlsplit, urlunsplit
from itertools import islice

#: How many traces the process keeps. Enough to compare the last few answer
#: paths (and the playground runs between them) without unbounded growth.
TRACE_LIMIT = 50

#: Chunk text and prompts are clipped so 50 traces stay small enough to hold
#: in memory comfortably.
TEXT_LIMIT = 700

# --- payload bounds ---------------------------------------------------------
# A trace records whatever the pipeline handed it, and one chat prompt can be
# 100k characters. Counting records is not enough: 50 of those would sit in
# memory until the process restarts. These bounds are applied centrally in
# ``RagTrace.to_dict()``, so no caller has to remember them and no route can
# serve an unbounded field.
#:
#: One text block (prompt, model answer, raw provider reply).
FIELD_LIMIT = 4000
#: One title/label.
TITLE_LIMIT = 160
#: The question itself (the playground accepts 2000 characters).
QUESTION_LIMIT = 1000
#: A failure message kept for the viewer.
ERROR_LIMIT = 400
#: Rows kept per stage; the rest are dropped and the stage says so.
ROW_LIMIT = 200
#: Total serialised characters one trace may serve.
TRACE_PAYLOAD_LIMIT = 120_000
STAGE_LIMIT = 256
COLLECTION_LIMIT = 64
DEPTH_LIMIT = 8
KEY_LIMIT = 100

# --- credential redaction ---------------------------------------------------
#: Traces hold provider errors, base URLs and whole prompts, so a key can reach
#: the viewer through several doors. Everything served goes through ``redact``.
REDACTED = "«حذف‌شده»"

# Without a scheme boundary, a long ASCII prompt retries the entire suffix at
# every character before failing "://", making masking quadratic in its size.
_URL_PATTERN = re.compile(r"(?<![a-zA-Z0-9+.\-])[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'<>)\]}]+")
_USERINFO_PATTERN = re.compile(r"://[^/\s@:]+(?::[^/\s@]*)?@")
_SENSITIVE_PARAM_PATTERN = re.compile(
    r"(?i)([?&;](?:api[_-]?key|apikey|key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"token|secret|client[_-]?secret|password|passwd|pwd|signature|sig|auth|"
    r"authorization|credential|code)=)[^&#;\s]*")
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]+")
_KEY_PATTERN = re.compile(
    r"(?i)\b(?:(?:sk|rk|pk|gsk|xai|hf|glpat|ghp|gho|AIza)[-_]?[A-Za-z0-9_\-]{16,}|AQ\.[A-Za-z0-9_\-]{20,})\b")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_SECRET_NAMES = frozenset({"apikey", "xapikey", "accesstoken", "refreshtoken", "idtoken",
    "token", "secret", "clientsecret", "password", "passwd", "pwd", "authorization",
    "credential", "credentials", "jwt", "secretkey", "llmapikey", "geminiapikey", "groqapikey"})
_ASSIGNMENT_PATTERN = re.compile(
    r'''(?i)(["']?\b(?:x[-_]?api[-_]?key|api[-_]?key|access[-_]?token|refresh[-_]?token|id[-_]?token|token|secret|client[-_]?secret|password|passwd|pwd|authorization|credential|jwt)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''')


def _secret_name(name: Any) -> bool:
    return re.sub(r"[^a-z0-9]", "", unquote(str(name)).lower()) in _SECRET_NAMES


def _mask_assignment(match):
    suffix = match.group(0)[len(match.group(1)):]
    if suffix.lower() in {"bearer", "basic"}:
        return match.group(0)  # The following credential was masked separately.
    quote = suffix[0] if suffix[:1] in {"\"", "'"} else ""
    return f"{match.group(1)}{quote}{REDACTED}{quote}"


def redact(text: Any) -> str:
    """Strip credentials from one string before it is served.

    The four doors a key can come through: userinfo inside a URL, a sensitive
    query parameter, an ``Authorization`` header echoed back in a provider
    error, and a key pasted straight into a prompt.
    """
    value = "" if text is None else str(text)
    if not value:
        return value
    value = _URL_PATTERN.sub(_scrub_url, value)
    value = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {REDACTED}", value)
    value = _KEY_PATTERN.sub(REDACTED, value)
    value = _JWT_PATTERN.sub(REDACTED, value)
    value = _ASSIGNMENT_PATTERN.sub(_mask_assignment, value)
    return _SENSITIVE_PARAM_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", value)


def _scrub_url(match: "re.Match[str]") -> str:
    """Clean one URL: drop its userinfo, then its sensitive query values."""
    url = _USERINFO_PATTERN.sub(lambda _: f"://{REDACTED}@", match.group(0))
    try:
        parts = urlsplit(url)
        def scrub_params(params: str) -> str:
            def scrub(param):
                name, sep, value = param.partition("=")
                if sep and (_secret_name(name) or unquote(name).lower() in {"key", "code", "sig", "signature", "auth"}):
                    return name + sep + REDACTED
                decoded = unquote(value)
                masked = _JWT_PATTERN.sub(REDACTED, _KEY_PATTERN.sub(REDACTED, decoded))
                return name + sep + (masked if masked != decoded else value)
            return "&".join(scrub(p) for p in re.split(r"[&;]", params))
        url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                         scrub_params(parts.query), scrub_params(parts.fragment)))
    except ValueError:
        pass
    return _SENSITIVE_PARAM_PATTERN.sub(lambda m: f"{m.group(1)}{REDACTED}", url)


def _cap(value: Any, limit: int, depth: int = 0) -> Any:
    """JSON-safe, redacted, length-capped copy of a stored payload value."""
    if isinstance(value, str):
        return clip(redact(value), limit)
    if depth >= DEPTH_LIMIT:
        return "«عمق داده محدود شد»"
    if isinstance(value, dict):
        return {clip(redact(key), KEY_LIMIT): REDACTED if _secret_name(key) else _cap(item, limit, depth + 1)
                for key, item in islice(value.items(), COLLECTION_LIMIT)}
    if isinstance(value, (list, tuple, set)):
        return [_cap(item, limit, depth + 1) for item in islice(value, COLLECTION_LIMIT)]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    result = _jsonable(value)
    if isinstance(result, str): return clip(redact(result), limit)
    if isinstance(result, float) and not math.isfinite(result): return None
    return result


def _payload_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(value))


def _capped_stage(stage: Dict[str, Any]) -> Dict[str, Any]:
    """One stage, capped field by field and stripped of credentials."""
    return {
        "name": clip(redact(stage.get("name") or ""), TITLE_LIMIT),
        "label": clip(redact(stage.get("label") or ""), TITLE_LIMIT),
        "ms": round(float(stage.get("ms") or 0.0), 1),
        "command": clip(redact(stage.get("command") or ""), TEXT_LIMIT),
        "meta": _cap(stage.get("meta") or {}, TEXT_LIMIT),
        "columns": _cap(stage.get("columns") or [], TITLE_LIMIT),
        "rows": [_cap(row, TEXT_LIMIT) for row in (stage.get("rows") or [])[:ROW_LIMIT]],
        "text": _cap(stage.get("text") or {}, FIELD_LIMIT),
    }


def _cap_stage_in_place(stage: Dict[str, Any]) -> Dict[str, Any]:
    """Bound and redact one stage where it is stored, when it closes.

    ``to_dict`` already bounds what a route serialises, but a payload has to be
    bounded for what the *process keeps* as well: a 100k-character prompt was
    retained in the ring buffer until the trace was evicted. Capping on write
    means the stored record and the served record are the same size.
    """
    capped = _capped_stage(stage)
    stage.clear()
    stage.update(capped)
    return stage


def _fit_payload(stages: List[Dict[str, Any]],
                 limit: int = TRACE_PAYLOAD_LIMIT) -> tuple[List[Dict[str, Any]], bool]:
    """Keep one trace under ``limit`` characters, saying what was dropped.

    Per-field caps alone are not enough: forty stages each holding a few
    thousand characters still add up. Rather than drop a stage - which would
    hide that it ran at all - the heaviest payloads give up their text blocks
    and then their rows, and the stage records the truncation.
    """
    truncated = False
    sizes = [_payload_size(stage) for stage in stages]
    total = sum(sizes) + 2 + max(0, len(stages) - 1) * 2
    while total > limit:
        index = max(range(len(stages)), key=lambda i: sizes[i], default=None)
        if index is None:
            break
        heaviest = stages[index]
        meta = heaviest["meta"] if isinstance(heaviest.get("meta"), dict) else None
        if heaviest.get("text"):
            heaviest["text"] = {}
            if meta is not None:
                meta["truncated_text"] = True
            truncated = True
        elif len(heaviest.get("rows") or []) > 25:
            heaviest["rows"] = heaviest["rows"][:25]
            if meta is not None:
                meta["truncated_rows"] = True
            truncated = True
        elif heaviest.get("rows"):
            heaviest["rows"] = []
            if meta is not None:
                meta["truncated_rows"] = True
            truncated = True
        elif heaviest.get("columns"):
            heaviest["columns"] = []
            if meta is not None: meta["truncated_columns"] = True
            truncated = True
        elif _payload_size(heaviest.get("meta")) > 100:
            heaviest["meta"] = {"truncated_meta": True}
            truncated = True
        else:
            # A bounded stage header still records that this stage ran.
            heaviest["command"] = ""
            heaviest["name"] = clip(heaviest.get("name"), 60)
            heaviest["label"] = clip(heaviest.get("label"), 60)
            if _payload_size(heaviest) >= sizes[index]:
                stages.pop(index)
                sizes.pop(index)
                total = sum(sizes) + 2 + max(0, len(stages) - 1) * 2
                truncated = True
                continue
            truncated = True
        new_size = _payload_size(heaviest)
        total += new_size - sizes[index]
        sizes[index] = new_size
    return stages, truncated


def _bounded(value, limit, depth, notify, collection_limit=COLLECTION_LIMIT):
    """Convert values on assignment, before a running trace retains them."""
    if depth >= DEPTH_LIMIT:
        return "«عمق داده محدود شد»"
    if isinstance(value, dict):
        return _BoundedDict(value, limit, depth, notify)
    if isinstance(value, (list, tuple, set)):
        return _BoundedList(value, limit, depth, notify, collection_limit)
    return _cap(value, limit, depth)


class _BoundedDict(dict):
    def __init__(self, values, limit, depth, notify):
        self.limit, self.depth, self.notify = limit, depth, notify
        for key, value in islice(values.items(), COLLECTION_LIMIT):
            self._put(key, value)

    def _put(self, key, value):
        original = key
        key = clip(redact(key), KEY_LIMIT)
        if key not in self and len(self) >= COLLECTION_LIMIT:
            return
        field_limit = FIELD_LIMIT if self.depth == 0 and key == "text" else self.limit
        if self.depth == 0 and key == "columns": field_limit = TITLE_LIMIT
        count = ROW_LIMIT if self.depth == 0 and key == "rows" else COLLECTION_LIMIT
        dict.__setitem__(self, key, REDACTED if _secret_name(original) else
                         _bounded(value, field_limit, self.depth + 1, self.notify, count))

    def __setitem__(self, key, value):
        self._put(key, value)
        self.notify()

    def update(self, values=(), **kwargs):
        items = values.items() if hasattr(values, "items") else values
        for key, value in islice(items, COLLECTION_LIMIT): self._put(key, value)
        for key, value in islice(kwargs.items(), COLLECTION_LIMIT): self._put(key, value)
        self.notify()

    def setdefault(self, key, default=None):
        if key not in self: self[key] = default
        return self.get(key)

    def __ior__(self, other):
        self.update(other)
        return self


class _BoundedList(list):
    def __init__(self, values, limit, depth, notify, count):
        self.limit, self.depth, self.notify, self.count = limit, depth, notify, count
        list.__init__(self, (_bounded(item, limit, depth + 1, notify)
                            for item in islice(values, count)))

    def append(self, value):
        if len(self) < self.count:
            list.append(self, _bounded(value, self.limit, self.depth + 1, self.notify))
        self.notify()

    def extend(self, values):
        for value in islice(values, max(0, self.count - len(self))):
            list.append(self, _bounded(value, self.limit, self.depth + 1, self.notify))
        self.notify()

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            value = [_bounded(item, self.limit, self.depth + 1, self.notify)
                     for item in islice(value, self.count)]
        else: value = _bounded(value, self.limit, self.depth + 1, self.notify)
        list.__setitem__(self, key, value)
        list.__delitem__(self, slice(self.count, None))
        self.notify()

    def insert(self, index, value):
        if len(self) < self.count:
            list.insert(self, index, _bounded(value, self.limit, self.depth + 1, self.notify))
        self.notify()

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __imul__(self, count):
        if count <= 0: self.clear()
        elif count > 1: self.extend(list(self) * min(count - 1, self.count))
        self.notify()
        return self

_current: ContextVar[Optional["RagTrace"]] = ContextVar("rag_trace", default=None)

KIND_LABELS = {
    "chat": "گفتگوی کاربر",
    "playground": "بررسی دستی",
    "mock": "ساخت دفترچه",
    "ingest": "بارگذاری سند",
    "evaluation": "ارزیابی سوأل",
}


def clip(text: Any, limit: int = TEXT_LIMIT) -> str:
    """One-line, length-capped rendering for table cells and text blocks."""
    value = "" if text is None else str(text)
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _jsonable(value: Any) -> Any:
    """Keep stage payloads JSON-serialisable (numpy floats, paths, sets…)."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return str(value)


def client_label(client: Any) -> Dict[str, str]:
    """Provider/model/base_url for an LLM or embedding client, best effort."""
    name = type(client).__name__
    provider = {
        "GroqLLMClient": "groq",
        "GeminiLLMClient": "gemini",
        "CerebrasLLMClient": "cerebras",
        "OllamaLLMClient": "ollama",
        "OpenAICompatibleClient": "openai-compatible",
        "MockLLMClient": "mock",
        "FallbackLLMClient": "fallback chain",
        "FallbackEmbeddingModel": "fallback chain",
    }.get(name, name)
    label = {"provider": provider, "model": str(getattr(client, "model", "") or "")}
    base_url = str(getattr(client, "base_url", "") or "")
    if base_url:
        label["base_url"] = base_url
    usage = getattr(client, "last_usage", None)
    if usage is not None:
        label["tokens"] = {
            "prompt": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion": int(getattr(usage, "completion_tokens", 0) or 0),
            "total": int(getattr(usage, "total_tokens", 0) or 0),
        }
    keys = getattr(client, "_labels", None)
    if keys:
        label["chain"] = " → ".join(str(k) for k in keys)
    return label


class RagTrace:
    """One inspection record: metadata, summary chips and ordered stages."""

    def __init__(self, kind: str, *, title: str = "", user_id: Optional[int] = None,
                 question: str = "", meta: Optional[Dict[str, Any]] = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = clip(redact(kind), TITLE_LIMIT)
        # Stored already bounded and credential-free, so a long prompt or an
        # error carrying a key is never retained even while the run is live.
        self.title = clip(redact(title), TITLE_LIMIT)
        self.question = clip(redact(question), QUESTION_LIMIT)
        self.user_id = user_id
        self.created_at = time.time()
        self.stages: List[Dict[str, Any]] = []
        self._bounding = False
        self.summary: Dict[str, Any] = _BoundedDict(meta or {}, TEXT_LIMIT, 0, self._bound_storage)
        self.status = "running"
        self.error = ""
        self.duration_ms = 0.0
        self._started = time.perf_counter()
        self._bound_storage()

    # ---- collecting ----------------------------------------------------
    @contextmanager
    def stage(self, name: str, label: str) -> Iterator[Dict[str, Any]]:
        """Time one stage; the yielded dict is filled in by the caller."""
        entry: Dict[str, Any] = _BoundedDict({
            "name": name, "label": label, "ms": 0.0,
            "command": "", "meta": {}, "columns": [], "rows": [], "text": {},
        }, TEXT_LIMIT, 0, self._bound_storage)
        if len(self.stages) < STAGE_LIMIT:
            self.stages.append(entry)
        else:
            self.summary["omitted_stages"] = int(self.summary.get("omitted_stages", 0)) + 1
            self.summary["payload_truncated"] = True
        self._bound_storage()
        started = time.perf_counter()
        try:
            yield entry
        finally:
            entry["ms"] = round((time.perf_counter() - started) * 1000, 1)
            _cap_stage_in_place(entry)

    def _bound_storage(self):
        if self._bounding:
            return
        self._bounding = True
        try:
            summary = self.summary
            while _payload_size(summary) > 8000:
                key = max(summary, key=lambda k: _payload_size(summary[k]))
                dict.__delitem__(summary, key)
                dict.__setitem__(summary, "payload_truncated", True)
            _, truncated = _fit_payload(self.stages,
                max(0, TRACE_PAYLOAD_LIMIT - _payload_size(summary) - 4000))
            if truncated: dict.__setitem__(summary, "payload_truncated", True)
        finally:
            self._bounding = False

    def note(self, **values: Any) -> None:
        """Summary chips shown in the trace list and the header."""
        for key, value in values.items():
            if value is not None and value != "":
                self.summary[key] = _cap(value, TEXT_LIMIT)

    def fail(self, message: str) -> None:
        self.status = "error"
        self.error = clip(redact(message), ERROR_LIMIT)

    def finish(self) -> None:
        self.duration_ms = round((time.perf_counter() - self._started) * 1000, 1)
        if self.status == "running":
            self.status = "ok"
        # A finished trace is as large as it will ever get, so the per-trace
        # bound is applied once here and the record the process keeps is the
        # record a route serves.
        self._bound_storage()

    # ---- reading -------------------------------------------------------
    def to_dict(self, *, include_stages: bool = True) -> Dict[str, Any]:
        """The served shape, bounded and credential-free.

        Every field the viewer can read passes through the caps and the
        redaction above here, once, so a new stage that stores a prompt, a
        provider error or a base URL cannot leak a key or an unbounded string.
        """
        stages: List[Dict[str, Any]] = []
        truncated = False
        if include_stages:
            stages, truncated = _fit_payload([_capped_stage(s) for s in self.stages])
        summary = _cap(self.summary, TEXT_LIMIT)
        if truncated and isinstance(summary, dict):
            summary["payload_truncated"] = True
        data: Dict[str, Any] = {
            "id": self.id, "kind": self.kind,
            "kind_label": KIND_LABELS.get(self.kind, self.kind),
            "title": clip(redact(self.title), TITLE_LIMIT),
            "question": clip(redact(self.question), QUESTION_LIMIT),
            "user_id": self.user_id, "created_at": self.created_at,
            "duration_ms": self.duration_ms, "status": self.status,
            "error": clip(redact(self.error), ERROR_LIMIT), "summary": summary,
            "stages": stages,
            "total_stage_ms": self.total_stage_ms(),
        }
        if include_stages:
            data["payload_characters"] = _payload_size(stages)
        # Include summary and envelope in the hard limit, not only stage rows.
        if _payload_size(data) > TRACE_PAYLOAD_LIMIT:
            overhead = _payload_size({**data, "stages": []})
            stages, _ = _fit_payload(stages, max(0, TRACE_PAYLOAD_LIMIT - overhead - 64))
            data["stages"] = stages
            data["summary"]["payload_truncated"] = True
            if include_stages: data["payload_characters"] = _payload_size(stages)
        return data

    def total_stage_ms(self) -> float:
        return round(sum(float(s.get("ms") or 0.0) for s in self.stages), 1)

    def counts(self) -> Dict[str, int]:
        return {"stages": len(self.stages),
                "rows": sum(len(s.get("rows") or []) for s in self.stages)}


# ----------------------------------------------------------------------
# Module-level helpers used from the RAG code. All of them are safe with no
# trace active (the production path), in which case they do nothing.
# ----------------------------------------------------------------------
def active_trace() -> Optional[RagTrace]:
    return _current.get()


@contextmanager
def stage(name: str, label: str) -> Iterator[Dict[str, Any]]:
    """Record a stage on the active trace, or hand back a throwaway dict."""
    trace = _current.get()
    if trace is None:
        yield {"name": name, "label": label, "ms": 0.0, "meta": {}, "rows": [],
               "columns": [], "text": {}, "command": ""}
        return
    with trace.stage(name, label) as entry:
        yield entry


def note(**values: Any) -> None:
    trace = _current.get()
    if trace is not None:
        trace.note(**values)


class TraceStore:
    """Bounded, thread-safe, newest-first ring buffer of traces."""

    def __init__(self, limit: int = TRACE_LIMIT):
        self.limit = max(1, int(limit))
        self._traces: List[RagTrace] = []
        self._lock = threading.Lock()

    def add(self, trace: RagTrace) -> None:
        with self._lock:
            self._traces = [t for t in self._traces if t.id != trace.id]
            self._traces.append(trace)
            if len(self._traces) > self.limit:
                del self._traces[: len(self._traces) - self.limit]

    def list(self, *, kind: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            traces = list(self._traces)
        traces.reverse()  # newest first
        if kind and kind != "all":
            traces = [t for t in traces if t.kind == kind]
        return [t.to_dict(include_stages=False) for t in traces[: max(1, int(limit))]]

    def get(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for trace in self._traces:
                if trace.id == trace_id:
                    return trace.to_dict()
        return None

    def clear(self, kind: Optional[str] = None) -> int:
        with self._lock:
            if kind and kind != "all":
                removed = [t for t in self._traces if t.kind == kind]
                self._traces = [t for t in self._traces if t.kind != kind]
            else:
                removed = self._traces
                self._traces = []
        return len(removed)

    def counts(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            for trace in self._traces:
                counts[trace.kind] = counts.get(trace.kind, 0) + 1
        return counts


store = TraceStore()


def begin_trace(kind: str, *, title: str = "", user_id: Optional[int] = None,
                question: str = "", meta: Optional[Dict[str, Any]] = None) -> RagTrace:
    """Start recording and make the trace visible immediately (status=running)."""
    trace = RagTrace(kind, title=title or question, user_id=user_id,
                     question=question, meta=meta)
    store.add(trace)
    return trace


@contextmanager
def record_trace(kind: str, *, title: str = "", user_id: Optional[int] = None,
                 question: str = "", meta: Optional[Dict[str, Any]] = None,
                 collapse_nested: bool = True) -> Iterator[RagTrace]:
    """Run a block under a new trace.

    Nested calls (a mock sweep inside a chat request, or the question-bank
    search inside the text search) reuse the trace already in flight so the
    viewer sees one timeline instead of disjoint fragments.
    """
    existing = _current.get()
    if existing is not None and collapse_nested:
        yield existing
        return
    trace = begin_trace(kind, title=title, user_id=user_id, question=question, meta=meta)
    token = _current.set(trace)
    try:
        yield trace
    except Exception as exc:  # record the reason, then re-raise untouched
        # An exception may name the message to record for itself (a wrapper
        # that carries a trace id can keep the underlying reason readable).
        trace.fail(getattr(exc, "trace_message", "") or f"{type(exc).__name__}: {exc}")
        raise
    finally:
        _current.reset(token)
        trace.finish()
