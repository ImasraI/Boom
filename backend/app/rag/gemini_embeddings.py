"""Hosted Gemini text embeddings; no model download or local inference.

Gemini 2 uses asymmetric retrieval prompts rather than taskType. Each text
is a separate embed request, never multiple parts of one aggregated vector.
"""
import math
import threading
import time

import httpx

from app.rag.embeddings import BaseEmbeddingModel
from app.utils.logger import get_logger
from app.rag.provider_quota import (quota_identity, blocked_access, blocked_quota,
    block_access, block_daily_quota, block_rate_limit, rate_limited)

logger = get_logger(__name__)


class EmbeddingError(RuntimeError):
    """Safe operational error without credentials, response bodies or input text."""


def gemini_collection_name(base: str, model: str, dimensions: int) -> str:
    import hashlib
    import re
    suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", model.removeprefix("models/"))
    name = f"{base}_{suffix}_{dimensions}_retrieval_v1"
    if len(name) > 63:
        name = name[:50] + "_" + hashlib.sha256(name.encode()).hexdigest()[:12]
    return name


def text_collection_name(settings, base: str) -> str:
    if settings.EMBEDDING_PROVIDER.strip().lower() == "gemini":
        return gemini_collection_name(base, settings.EMBEDDING_MODEL_NAME,
                                      settings.EMBEDDING_DIMENSIONS)
    return base


class EmbeddingRateLimiter:
    """Shared request budget when multiple workers use the same credential."""
    def __init__(self, requests_per_minute, adaptive=False):
        self.interval = 60.0 / requests_per_minute
        self.ceiling = requests_per_minute
        self.adaptive = adaptive
        self.successes = 0
        self.next_request = 0.0
        self.lock = threading.Lock()

    def wait(self, activity):
        while True:
            with self.lock:
                delay = max(0, self.next_request - time.monotonic())
                if delay == 0:
                    self.next_request = time.monotonic() + self.interval
                    return
            activity("waiting_for_request_interval", delay)
            time.sleep(delay)

    def cooldown(self, seconds):
        with self.lock:
            self.next_request = max(self.next_request, time.monotonic() + seconds)

    def throttle(self, limits, request_units):
        """Reduce the shared budget only after an actual per-minute refusal."""
        if not self.adaptive:
            return
        with self.lock:
            for limit in limits:
                if limit["period"] == "minute" and "requests" in limit["metric"]:
                    self.ceiling = min(self.ceiling, max(1, limit["value"] * .9 / request_units))
            rate = min(self.ceiling, max(1, 60 / self.interval / 2))
            self.interval = 60 / rate
            self.successes = 0

    def succeeded(self):
        if not self.adaptive:
            return
        with self.lock:
            self.successes += 1
            if self.successes >= 5:
                self.interval = 60 / min(self.ceiling, 60 / self.interval * 1.1)
                self.successes = 0


def safe_quota_limits(error):
    """Expose provider constraints without response text, dimensions or secrets."""
    limits = []
    for detail in error.get("details", []):
        for violation in detail.get("violations", []):
            metric, quota_id = violation.get("quotaMetric", ""), violation.get("quotaId", "").lower()
            if not isinstance(metric, str) or not metric.startswith("generativelanguage.googleapis.com/"):
                continue
            try:
                value = float(violation.get("quotaValue"))
            except (ValueError, TypeError):
                continue
            if not math.isfinite(value) or value < 0:
                continue
            period = "day" if "perday" in quota_id else "minute" if "perminute" in quota_id else "other"
            limits.append({"metric": metric, "value": value, "period": period})
    return limits


class GeminiEmbeddingModel(BaseEmbeddingModel):
    def __init__(self, api_key: str, model_name: str = "gemini-embedding-2",
                 dimensions: int = 768, batch_size: int = 24,
                 requests_per_minute: int = 10,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 proxy: str = "", on_activity=None, rate_limiter=None):
        if not api_key.strip():
            raise EmbeddingError("Configure GEMINI_API_KEY or EMBEDDING_API_KEY.")
        self.model = model_name.removeprefix("models/")
        if self.model not in {"gemini-embedding-2", "gemini-embedding-001"}:
            raise EmbeddingError("Select gemini-embedding-2 or gemini-embedding-001 explicitly.")
        if not 128 <= dimensions <= 3072 or not 1 <= batch_size <= 100 or requests_per_minute < 1:
            raise ValueError("Invalid embedding dimensions, batch size or request rate.")
        if not base_url.startswith("https://"):
            raise ValueError("Gemini embedding endpoint must use HTTPS.")
        self.dimensions, self.batch_size = dimensions, batch_size
        # The validated worker configuration is promoted only after migration.
        self.api_key, self.proxy = api_key.strip(), proxy
        self._quota_identity = quota_identity(base_url, self.model, self.api_key)
        self.last_error_code = ""
        self.switch_on_rate_limit = False
        self.fingerprint = f"gemini:{self.model}:{dimensions}:retrieval_v1"
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60, trust_env=False, proxy=proxy or None,
                                  headers={"x-goog-api-key": api_key})
        self.rate_limiter = rate_limiter or EmbeddingRateLimiter(requests_per_minute)
        self.on_activity = on_activity

    def _activity(self, phase, wait_seconds=0, quota_limits=None):
        if self.on_activity:
            event = {"phase": phase, "wait_seconds": round(wait_seconds, 1)}
            if quota_limits:
                event["quota_limits"] = quota_limits
                event["effective_requests_per_minute"] = round(60 / self.rate_limiter.interval, 2)
            self.on_activity(event)

    def close(self):
        self.client.close()

    def _request_item(self, text: str, query: bool):
        item = {"model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.dimensions}
        if self.model == "gemini-embedding-2":
            item["content"]["parts"][0]["text"] = (
                f"task: search result | query: {text}" if query else f"title: none | text: {text}")
        else:
            item["taskType"] = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
        return item

    def _post(self, operation: str, payload: dict):
        self.last_error_code = ""
        if blocked_access(self._quota_identity):
            self.last_error_code = "provider_access_denied"
        elif blocked_quota(self._quota_identity):
            self.last_error_code = "provider_daily_quota"
        elif self.switch_on_rate_limit and rate_limited(self._quota_identity):
            self.last_error_code = "provider_rate_limit"
        if self.last_error_code:
            raise EmbeddingError("Gemini embedding credential is unavailable; respecting its retry period.")
        for attempt in range(3):
            self.rate_limiter.wait(self._activity)
            try:
                self._activity("contacting_gemini")
                response = self.client.post(f"{self.base_url}/models/{self.model}:{operation}", json=payload)
            except httpx.RequestError:
                if attempt < 2:
                    self._activity("retrying_network_connection", 2 ** attempt)
                    time.sleep(2 ** attempt)
                    continue
                raise EmbeddingError("Gemini embedding connection failed; migration can be resumed.") from None
            if response.is_success:
                try:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise ValueError
                    self.rate_limiter.succeeded()
                    self._activity("embedding_received")
                    return result
                except ValueError:
                    raise EmbeddingError("Gemini returned invalid embedding JSON.") from None
            # Daily/project quota cannot clear during an interactive request.
            if response.status_code in (401, 403):
                block_access(self._quota_identity, response.status_code)
                self.last_error_code = "provider_access_denied"
                raise EmbeddingError("Gemini embedding credential was rejected.")
            daily_limit = False
            provider_delay = None
            quota_limits = []
            if response.status_code == 429:
                try:
                    error = response.json().get("error", {})
                    quota_limits = safe_quota_limits(error)
                    quota = str(error).lower()
                    daily_limit = any(marker in quota for marker in
                                      ("perday", "per_day", "per day", "daily", "limit: 0"))
                    for detail in error.get("details", []):
                        if "retryDelay" in detail:
                            provider_delay = float(str(detail["retryDelay"]).removesuffix("s"))
                except (ValueError, AttributeError, TypeError):
                    pass
                if daily_limit:
                    block_daily_quota(self._quota_identity, "embedding daily quota")
                    self.last_error_code = "provider_daily_quota"
                elif self.switch_on_rate_limit:
                    try:
                        delay = max(1, float(response.headers.get('retry-after', provider_delay or 60)))
                    except (TypeError, ValueError):
                        delay = 60
                    block_rate_limit(self._quota_identity, min(delay, 3600))
                    self.last_error_code = "provider_rate_limit"
                    raise EmbeddingError("Gemini embedding credential reached its minute limit.")
            if (response.status_code == 429 and not daily_limit or response.status_code >= 500) and attempt < 2:
                try:
                    fallback = provider_delay if provider_delay is not None else (60 if response.status_code == 429 else 5)
                    delay = min(60, max(2 ** (attempt + 1), float(response.headers.get("retry-after", fallback))))
                except ValueError:
                    delay = 60 if response.status_code == 429 else 5
                self._activity("waiting_for_gemini_quota" if response.status_code == 429 else "waiting_for_provider_retry", delay)
                if response.status_code == 429:
                    # Every worker sharing this key must pause, otherwise
                    # peers keep exhausting the same quota during the retry.
                    self.rate_limiter.cooldown(delay)
                    self.rate_limiter.throttle(quota_limits, max(1, len(payload.get("requests", []))))
                    self._activity("waiting_for_gemini_quota", delay, quota_limits)
                time.sleep(delay)
                continue
            reason = "daily quota exhausted" if daily_limit else f"HTTP {response.status_code}"
            if daily_limit:
                self._activity("daily_quota_exhausted", provider_delay or 0, quota_limits)
            raise EmbeddingError(f"Gemini embeddings refused ({reason}); check access/key/quota in AI Studio.")

    def _validate(self, data, count: int):
        try:
            vectors = [row["values"] for row in data]
            if len(vectors) != count:
                raise ValueError
            for vector in vectors:
                if len(vector) != self.dimensions or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                                        or not math.isfinite(v) for v in vector):
                    raise ValueError
                norm = math.sqrt(sum(v * v for v in vector))
                if not math.isfinite(norm) or norm == 0:
                    raise ValueError
                vector[:] = [v / norm for v in vector]
            return vectors
        except (TypeError, KeyError, ValueError):
            raise EmbeddingError("Gemini returned missing, invalid or incompatible embedding vectors.") from None

    def embed_documents(self, texts):
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            result = self._post("batchEmbedContents", {"requests": [self._request_item(text, False) for text in batch]})
            vectors.extend(self._validate(result.get("embeddings"), len(batch)))
        return vectors

    def probe_query(self, text):
        result = self._post("embedContent", self._request_item(text, True))
        return self._validate([result.get("embedding")], 1)[0]

    def embed_query(self, text):
        try:
            return self.probe_query(text)
        except EmbeddingError as error:
            # Existing hybrid retrieval can still use the lexical index.
            # Indexing remains strict, so failed vectors are never stored.
            logger.warning("%s Falling back to lexical retrieval.", error)
            return []
