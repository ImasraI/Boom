"""
LLM layer - pluggable OpenAI-compatible providers.

Available implementations:
1. MockLLMClient: Used for initial frontend/backend testing without an API key.
2. OllamaLLMClient: Direct HTTP client for Ollama's chat completion API.
3. GroqLLMClient: Client for Groq's OpenAI-compatible API.
4. GeminiLLMClient: Gemini's /v1beta/openai endpoint (vision capable,
   optional GEMINI_PROXY for geo-blocked regions).
5. CerebrasLLMClient: Cerebras Inference (fastest free tier, ~1M tokens/day).
6. OpenAICompatibleClient: Generic OpenAI-compatible client.

The chat/planning provider is selected through LLM_PROVIDER in .env; mock
(pool) generation can use a different provider/key via POOL_LLM_PROVIDER /
POOL_LLM_API_KEY so the token-heavy booklet builds never starve the
chatbot's quota. Vision keeps its own VISION_LLM_PROVIDER (usually Gemini).
"""

from abc import ABC, abstractmethod
from typing import Any, List, Dict, Generator, NamedTuple, Optional, Sequence
import json
import time
import httpx
import base64

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

LLMMessage = Dict[str, Any]
ImageInput = str | bytes


class TokenUsage(NamedTuple):
    """Token accounting for the most recent successful generate() call.

    Clients expose it as `self.last_usage`; generate()'s string return type
    and signature are unchanged (purely additive bookkeeping).
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


ZERO_USAGE = TokenUsage(0, 0, 0)


def _usage_from_openai(data: dict) -> TokenUsage:
    """Parse the OpenAI-compatible top-level 'usage' object
    ({prompt_tokens, completion_tokens, total_tokens}) returned by Groq,
    generic OpenAI-compatible providers, and Gemini's /openai endpoint."""
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    return TokenUsage(prompt, completion, total)


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_stream(
        self,
        messages: List[LLMMessage],
        images: Optional[Sequence[ImageInput]] = None,
    ) -> Generator[str, None, None]:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """Test client that does not require a real LLM or API key."""
    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        user_message = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            ""
        )
        image_note = f" ({len(images)} image(s) attached)" if images else ""
        return (
            "[Test response - real LLM is not connected]\n"
            "This is a mock response used to verify that the RAG pipeline "
            "(document retrieval) is working correctly. To use a real LLM, "
            "set LLM_PROVIDER to 'ollama' in the .env file.\n\n"
            f"Received question{image_note}: {user_message}"
        )

    def generate_stream(
        self,
        messages: List[LLMMessage],
        images: Optional[Sequence[ImageInput]] = None,
    ) -> Generator[str, None, None]:
        full_text = self.generate(messages, images=images)
        for word in full_text.split(" "):
            yield word + " "
            time.sleep(0.03)


class OllamaLLMClient(BaseLLMClient):
    """Direct HTTP client for Ollama's /api/chat endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 300.0,
    ):
        clean_url = (base_url or "").strip().rstrip("/")
        if "localhost" in clean_url:
            clean_url = clean_url.replace("localhost", "127.0.0.1")
        if clean_url.endswith("/v1"):
            clean_url = clean_url[:-3]
        self.base_url = clean_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False)

    @staticmethod
    def _encode_images(image_paths: Sequence[ImageInput]) -> List[str]:
        """Read image files from disk and base64-encode them for Ollama's
        /api/chat 'images' field (which takes raw base64, no data: URI prefix)."""
        encoded = []
        for path in image_paths:
            try:
                if isinstance(path, bytes):
                    image_data = path
                else:
                    with open(path, "rb") as f:
                        image_data = f.read()
                encoded.append(base64.b64encode(image_data).decode("utf-8"))
            except OSError as e:
                logger.warning(f"Could not read image for vision request: {path} ({e})")
        return encoded

    def _prepare_payload(
        self,
        messages: List[LLMMessage],
        stream: bool = False,
        max_tokens: Optional[int] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ):
        """Prepare the request payload for Ollama's /api/chat endpoint."""
        messages = [dict(m) for m in messages]
        if images:
            encoded_images = self._encode_images(images)
            for message in reversed(messages):
                if message.get("role") == "user":
                    message["images"] = encoded_images
                    break

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.max_tokens,
            },
        }
        return payload

    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload = self._prepare_payload(messages, stream=False, max_tokens=max_tokens, images=images)
        req_timeout = timeout if timeout is not None else self.timeout
        
        try:
            resp = self.client.post(url, json=payload, timeout=req_timeout)
            resp.raise_for_status()
            data = resp.json()
            if "message" in data and "content" in data["message"]:
                return data["message"]["content"]
            else:
                logger.warning("Unexpected response format from Ollama: %s", data)
                return ""
        except httpx.TimeoutException:
            logger.warning("Ollama request timed out after %ss.", req_timeout)
            return ""
        except Exception as e:
            logger.warning(f"Ollama request failed: {e}")
            return ""

    def generate_stream(
        self,
        messages: List[LLMMessage],
        images: Optional[Sequence[ImageInput]] = None,
    ) -> Generator[str, None, None]:
        url = f"{self.base_url}/api/chat"
        payload = self._prepare_payload(messages, stream=True, images=images)
        
        try:
            with self.client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            yield chunk["message"]["content"]
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse Ollama stream line: {line} - {e}")
        except httpx.TimeoutException:
            logger.warning("Ollama streaming request timed out.")
            yield "خطا: زمان پاسخدهی به پایان رسید."
        except Exception as e:
            logger.warning(f"Ollama streaming request failed: {e}")
            yield f"خطا: {e}"


def _retry_after_seconds(response: httpx.Response, fallback: float,
                         cap: float = 90.0) -> float:
    """Seconds to wait after a 429, honoring the Retry-After header (capped).

    Groq's per-minute rate-limit windows are ~60s; a fixed 2-6s backoff can
    never clear one, so every retry burns quota and fails again. When the
    server tells us how long to wait, actually wait (bounded by `cap` so a
    bogus header can't stall a request thread for minutes).
    """
    try:
        raw = response.headers.get("retry-after")
        return min(max(float(raw), 0.0), cap) if raw else fallback
    except (TypeError, ValueError):
        return fallback


class GroqLLMClient(BaseLLMClient):
    """HTTP client for Groq's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 300.0,
    ):
        self.base_url = "https://api.groq.com/openai/v1"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        # Token usage of the last SUCCESSFUL generate(); zeros until then.
        self.last_usage = ZERO_USAGE

    @property
    def _is_reasoning_model(self) -> bool:
        # gpt-oss emits hidden "analysis" tokens that consume the completion
        # budget before the visible answer is written.
        return self.model.startswith("openai/gpt-oss")

    def _prepare_payload(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
    ):
        budget = max_tokens or self.max_tokens
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self._is_reasoning_model:
            # A small budget (e.g. the 150-token query rewrite) can be eaten
            # entirely by reasoning -> empty content with finish_reason=length.
            # reasoning_effort=low keeps analysis short and a generous floor
            # guarantees room for the visible answer.
            payload["reasoning_effort"] = "low"
            payload["max_completion_tokens"] = max(budget, 1024)
        else:
            payload["max_tokens"] = budget
        return payload

    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        if images:
            logger.warning("Groq does not support image inputs. Ignoring images.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages, max_tokens=max_tokens)
        req_timeout = timeout if timeout is not None else self.timeout

        # Groq occasionally returns an empty completion (HTTP 200, no usable
        # content) or a rate-limit/5xx error.  Retry briefly so a single
        # flaky call doesn't degrade weekly-planning to the default fallback.
        self.last_usage = ZERO_USAGE  # stays zero unless a response succeeds
        last = ""
        for attempt in range(4):
            wait_s = 2 * (attempt + 1)  # default short backoff
            try:
                resp = self.client.post(url, json=payload, timeout=req_timeout)
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    content = choice["message"]["content"]
                    if content:
                        self.last_usage = _usage_from_openai(data)
                        return content
                    finish = choice.get("finish_reason")
                    last = ""
                    logger.warning(
                        "Groq returned an empty completion (attempt %d, finish_reason=%s).",
                        attempt + 1, finish,
                    )
                    if finish == "length":
                        # Hidden reasoning consumed the whole budget; retry with
                        # a doubled completion budget.
                        payload = self._prepare_payload(
                            messages,
                            max_tokens=(max_tokens or self.max_tokens) * (2 ** (attempt + 1)),
                        )
                else:
                    last = ""
                    logger.warning("Unexpected response format from Groq: %s", data)
            except httpx.HTTPStatusError as e:
                last = ""
                logger.warning(
                    "Groq request failed (attempt %d): %s", attempt + 1, e,
                )
                # Rate limited: Groq tells us how long to wait - honor it
                # (capped), otherwise the fixed short backoff can never clear
                # a 60s rate-limit window and every attempt fails again.
                if e.response is not None and e.response.status_code == 429:
                    wait_s = _retry_after_seconds(e.response, fallback=wait_s)
            except httpx.TimeoutException:
                last = ""
                logger.warning(
                    "Groq request timed out after %ss (attempt %d).",
                    req_timeout, attempt + 1,
                )
            except Exception as e:
                last = ""
                logger.warning(
                    "Groq request failed (attempt %d): %s", attempt + 1, e,
                )
            if attempt < 3:
                time.sleep(wait_s)
        return last

    def generate_stream(
        self,
        messages: List[LLMMessage],
        images: Optional[Sequence[ImageInput]] = None,
    ) -> Generator[str, None, None]:
        if images:
            logger.warning("Groq does not support image inputs. Ignoring images.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages)
        payload["stream"] = True

        # Retry only the connection phase: a 429/raise_for_status fires
        # before any content is yielded, so a retry never duplicates output.
        # Once streaming has started, errors surface as before.
        for attempt in range(1, 4):
            try:
                with self.client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            line = line[6:]
                        try:
                            chunk = json.loads(line)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                content = chunk["choices"][0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                return
            except httpx.HTTPStatusError as e:
                retryable = (
                    e.response is not None and e.response.status_code == 429
                )
                if not retryable or attempt >= 3:
                    logger.warning(f"Groq streaming request failed: {e}")
                    yield f"خطا: {e}"
                    return
                wait = _retry_after_seconds(e.response, fallback=2.0 * attempt)
                logger.warning(
                    "Groq stream rate-limited (429); waiting %.0fs (attempt %d).",
                    wait, attempt,
                )
                time.sleep(wait)
            except httpx.TimeoutException:
                logger.warning("Groq streaming request timed out.")
                yield "خطا: زمان پاسخدهی به پایان رسید."
                return
            except Exception as e:
                logger.warning(f"Groq streaming request failed: {e}")
                yield f"خطا: {e}"
                return


class GeminiLLMClient(BaseLLMClient):
    """OpenAI-compatible HTTP client for Google Gemini (vision capable).

    Uses Gemini's ``/v1beta/openai`` endpoint so it accepts the same JSON
    shape as the other clients.  Images are sent as inline base64 ``data:``
    URLs in the last user message, which Gemini's API understands natively.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 300.0,
        proxy: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.proxy = (proxy or "").strip()
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            proxy=self.proxy or None,  # Gemini is geo-blocked in some regions
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        # Token usage of the last SUCCESSFUL generate(); zeros until then.
        self.last_usage = ZERO_USAGE

    @property
    def _is_thinking_model(self) -> bool:
        # Gemini 3.x flash/pro "think" before answering: hidden thinking
        # tokens silently consume the max_tokens completion budget (observed:
        # 207 of a 220-token budget spent thinking, empty visible answer).
        # Pinning thinking off gives predictable output size and ~4x lower
        # latency on the free tier.
        return self.model.startswith("gemini-3")

    def _encode_images(
        self, images: Sequence[ImageInput]
    ) -> List[Dict[str, str]]:
        """Build OpenAI-style image_url parts (inline base64) from file paths."""
        parts: List[Dict[str, str]] = []
        for path in images:
            try:
                if isinstance(path, bytes):
                    image_data = path
                    mime = "image/png"
                else:
                    with open(path, "rb") as f:
                        image_data = f.read()
                    # Gemini accepts PNG/JPEG; guess the mime from the suffix.
                    name = str(path).lower()
                    mime = "image/jpeg" if name.endswith(
                        (".jpg", ".jpeg")
                    ) else "image/png"
                b64 = base64.b64encode(image_data).decode("utf-8")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            except OSError as e:
                logger.warning(f"Could not read image for vision request: {path} ({e})")
        return parts

    def _prepare_payload(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ):
        messages = [dict(m) for m in messages]
        if images:
            image_parts = self._encode_images(images)
            if image_parts:
                for message in reversed(messages):
                    if message.get("role") == "user":
                        content = message.get("content", "")
                        message["content"] = [
                            {"type": "text", "text": content or "تصویر را تحلیل کن."},
                            *image_parts,
                        ]
                        break
                else:
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "تصویر را تحلیل کن."},
                            *image_parts,
                        ],
                    })
        return {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            **({"reasoning_effort": "none"} if self._is_thinking_model else {}),
        }

    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages, max_tokens=max_tokens, images=images)
        req_timeout = timeout if timeout is not None else self.timeout

        self.last_usage = ZERO_USAGE  # stays zero unless a response succeeds
        last_error = ""
        for attempt in range(1, 5):
            wait_s = 2 * attempt  # default short backoff
            try:
                resp = self.client.post(url, json=payload, timeout=req_timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code == 429:
                        wait_s = _retry_after_seconds(resp, fallback=wait_s)
                    time.sleep(wait_s)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("message", {}).get("content")
                    if content:
                        self.last_usage = _usage_from_openai(data)
                        return content
                    # 200 with empty content -> treat as a retryable hiccup
                    last_error = "empty completion"
                else:
                    last_error = "unexpected response format"
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}" if e.response is not None else str(e)
                status = e.response.status_code if e.response is not None else 0
                if status not in (429, 500, 502, 503, 504):
                    break
            except Exception as e:
                last_error = str(e)
            logger.warning("Gemini request attempt %d failed (%s); retrying...",
                           attempt, last_error)
            time.sleep(wait_s)

        logger.warning("Gemini request failed after retries: %s", last_error)
        return ""

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages, images=images)
        payload["stream"] = True

        # Retry only the connection phase (same contract as Groq): a 429
        # fires before any content is yielded, so a retry never duplicates
        # output. Once streaming has started, errors surface as before.
        for attempt in range(1, 4):
            try:
                with self.client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            line = line[6:]
                        try:
                            chunk = json.loads(line)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                content = chunk["choices"][0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                return
            except httpx.HTTPStatusError as e:
                retryable = (
                    e.response is not None and e.response.status_code == 429
                )
                if not retryable or attempt >= 3:
                    logger.warning(f"Gemini streaming request failed: {e}")
                    yield f"خطا: {e}"
                    return
                wait = _retry_after_seconds(e.response, fallback=2.0 * attempt)
                logger.warning(
                    "Gemini stream rate-limited (429); waiting %.0fs (attempt %d).",
                    wait, attempt,
                )
                time.sleep(wait)
            except Exception as e:
                logger.warning(f"Gemini streaming request failed: {e}")
                yield f"خطا: {e}"
                return


class CerebrasLLMClient(BaseLLMClient):
    """HTTP client for Cerebras Inference's OpenAI-compatible API.

    The free tier is the most generous of the supported providers (~30 RPM,
    ~1M tokens/day) and the wafer-scale hardware streams >1000 tok/s, so it
    suits both the interactive chatbot and token-heavy booklet generation.
    gpt-oss models emit hidden analysis tokens like Groq's, so the same
    reasoning_effort=low + completion-floor handling applies.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        # Token usage of the last SUCCESSFUL generate(); zeros until then.
        self.last_usage = ZERO_USAGE

    @property
    def _is_reasoning_model(self) -> bool:
        # gpt-oss emits hidden "analysis" tokens that consume the completion
        # budget before the visible answer is written (same as Groq).
        return self.model.startswith("gpt-oss") or self.model.startswith("openai/gpt-oss")

    def _prepare_payload(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
    ):
        budget = max_tokens or self.max_tokens
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self._is_reasoning_model:
            # Small budgets can be eaten entirely by reasoning -> empty
            # content with finish_reason=length (see GroqLLMClient).
            payload["reasoning_effort"] = "low"
            payload["max_completion_tokens"] = max(budget, 1024)
        else:
            payload["max_tokens"] = budget
        return payload

    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        if images:
            logger.warning("Cerebras does not support image inputs. Ignoring images.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages, max_tokens=max_tokens)
        req_timeout = timeout if timeout is not None else self.timeout

        self.last_usage = ZERO_USAGE  # stays zero unless a response succeeds
        last_error = ""
        for attempt in range(1, 5):
            wait_s = 2 * attempt  # default short backoff
            try:
                resp = self.client.post(url, json=payload, timeout=req_timeout)
                # 429/5xx handled inline so Retry-After is honored before any
                # raise_for_status() turn it into a generic failure.
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code == 429:
                        wait_s = _retry_after_seconds(resp, fallback=wait_s)
                    time.sleep(wait_s)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    content = choice.get("message", {}).get("content")
                    if content:
                        self.last_usage = _usage_from_openai(data)
                        return content
                    # 200 with empty content -> retryable hiccup; when hidden
                    # reasoning ate the budget, retry with a bigger one.
                    last_error = "empty completion"
                    if choice.get("finish_reason") == "length":
                        payload = self._prepare_payload(
                            messages,
                            max_tokens=(max_tokens or self.max_tokens) * (2 ** attempt),
                        )
                else:
                    last_error = "unexpected response format"
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                # 429/5xx never reach raise_for_status() (handled inline), so
                # anything here is a permanent client error: stop retrying.
                last_error = f"HTTP {e.response.status_code}" if e.response is not None else str(e)
                break
            except Exception as e:
                last_error = str(e)
            logger.warning("Cerebras request attempt %d failed (%s); retrying...",
                           attempt, last_error)
            time.sleep(wait_s)

        logger.warning("Cerebras request failed after retries: %s", last_error)
        return ""

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        if images:
            logger.warning("Cerebras does not support image inputs. Ignoring images.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages)
        payload["stream"] = True

        # Retry only the connection phase (same contract as Groq/Gemini): a
        # 429 fires before any content is yielded, so a retry never
        # duplicates output. Once streaming has started, errors surface.
        for attempt in range(1, 4):
            try:
                with self.client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            line = line[6:]
                        try:
                            chunk = json.loads(line)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                content = chunk["choices"][0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                return
            except httpx.HTTPStatusError as e:
                retryable = (
                    e.response is not None and e.response.status_code == 429
                )
                if not retryable or attempt >= 3:
                    logger.warning(f"Cerebras streaming request failed: {e}")
                    yield f"خطا: {e}"
                    return
                wait = _retry_after_seconds(e.response, fallback=2.0 * attempt)
                logger.warning(
                    "Cerebras stream rate-limited (429); waiting %.0fs (attempt %d).",
                    wait, attempt,
                )
                time.sleep(wait)
            except httpx.TimeoutException:
                logger.warning("Cerebras streaming request timed out.")
                yield "خطا: زمان پاسخدهی به پایان رسید."
                return
            except Exception as e:
                logger.warning(f"Cerebras streaming request failed: {e}")
                yield f"خطا: {e}"
                return


class OpenAICompatibleClient(BaseLLMClient):
    """Generic OpenAI-compatible client for providers like Omniroute, Cloudflare, etc."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def _prepare_payload(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
    ):
        return {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

    def generate(
        self,
        messages: List[LLMMessage],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[Sequence[ImageInput]] = None,
    ) -> str:
        if images:
            logger.warning("This provider does not support image inputs. Ignoring images.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages, max_tokens=max_tokens)
        req_timeout = timeout if timeout is not None else self.timeout

        try:
            resp = self.client.post(url, json=payload, timeout=req_timeout)
            resp.raise_for_status()
            data = resp.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                logger.warning("Unexpected response format: %s", data)
                return ""
        except httpx.TimeoutException:
            logger.warning("Request timed out after %ss.", req_timeout)
            return ""
        except Exception as e:
            logger.warning(f"Request failed: {e}")
            return ""

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        if images:
            logger.warning("This provider does not support image inputs.")
        url = f"{self.base_url}/chat/completions"
        payload = self._prepare_payload(messages)
        payload["stream"] = True

        try:
            with self.client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        chunk = json.loads(line)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            content = chunk["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Streaming request failed: {e}")
            yield f"خطا: {e}"


def get_llm_client(
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMClient:
    """Build the chat/planning LLM client from settings.

    ``provider`` overrides settings.LLM_PROVIDER - used by
    get_pool_llm_client() so mock generation can run on a different
    provider than the chatbot. ``api_key`` / ``model`` override the
    provider's default key/model - used so pool generation can run on its
    own key instead of competing with the chatbot for the same rate limits.
    """
    settings = get_settings()
    provider = (provider or settings.LLM_PROVIDER or "").strip().lower()

    if provider == "groq":
        key = api_key if api_key is not None else settings.LLM_API_KEY
        model_name = model if model is not None else settings.LLM_MODEL_NAME
        if not key:
            logger.warning("Groq selected but no API key is set. Using mock.")
            return MockLLMClient()
        logger.info(f"Using GroqLLMClient with model={model_name}")
        return GroqLLMClient(
            api_key=key,
            model=model_name,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "openai" or provider == "omniroute":
        key = api_key if api_key is not None else settings.LLM_API_KEY
        model_name = model if model is not None else settings.LLM_MODEL_NAME
        if not key:
            logger.warning(f"{provider} selected but no API key is set. Using mock.")
            return MockLLMClient()
        base_url = settings.LLM_BASE_URL
        if not base_url or base_url == "http://localhost:11434/v1":
            base_url = "https://api.omniroute.ai/v1"
        logger.info(f"Using OpenAICompatibleClient ({provider}) with base_url={base_url}, model={model_name}")
        return OpenAICompatibleClient(
            api_key=key,
            base_url=base_url,
            model=model_name,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "ollama":
        if "localhost:11434" in settings.LLM_BASE_URL or "127.0.0.1:11434" in settings.LLM_BASE_URL:
            model_name = model if model is not None else settings.LLM_MODEL_NAME
            logger.info(f"Using OllamaLLMClient with base_url={settings.LLM_BASE_URL}, model={model_name}")
            return OllamaLLMClient(
                base_url=settings.LLM_BASE_URL,
                model=model_name,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
        else:
            logger.warning("Ollama selected but base_url is not local. Using mock.")
            return MockLLMClient()

    if provider == "cerebras":
        key = api_key if api_key is not None else settings.CEREBRAS_API_KEY
        model_name = model if model is not None else settings.CEREBRAS_MODEL_NAME
        if not key:
            logger.warning("Cerebras selected but no API key is set. Using mock.")
            return MockLLMClient()
        logger.info(f"Using CerebrasLLMClient with model={model_name}")
        return CerebrasLLMClient(
            api_key=key,
            base_url=settings.CEREBRAS_BASE_URL,
            model=model_name,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "gemini":
        key = api_key if api_key is not None else settings.GEMINI_API_KEY
        model_name = model if model is not None else settings.GEMINI_MODEL_NAME
        if not key:
            logger.warning("Gemini selected but no API key is set. Using mock.")
            return MockLLMClient()
        logger.info(f"Using GeminiLLMClient with model={model_name}")
        return GeminiLLMClient(
            api_key=key,
            base_url=settings.GEMINI_BASE_URL,
            model=model_name,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            proxy=settings.GEMINI_PROXY,
        )

    logger.info("Using MockLLMClient (test mode without a real LLM).")
    return MockLLMClient()


def get_pool_llm_client() -> BaseLLMClient:
    """LLM client for MOCK GENERATION (pool worker, admin restock, live
    booklet builds).

    Uses POOL_LLM_API_KEY / POOL_LLM_MODEL_NAME when set, so pool generation
    gets its own provider quota instead of competing with the chatbot and
    planning on the main key. Empty key = fall back to the shared key
    (previous behavior).
    """
    settings = get_settings()
    pool_key = (settings.POOL_LLM_API_KEY or "").strip()
    pool_provider = (settings.POOL_LLM_PROVIDER or "").strip().lower()
    if not pool_key and not pool_provider:
        return get_llm_client()
    pool_model = (settings.POOL_LLM_MODEL_NAME or "").strip() or None
    logger.info("Using the dedicated pool LLM provider/key/model for mock generation.")
    return get_llm_client(
        provider=pool_provider or None,
        api_key=pool_key or None,
        model=pool_model,
    )


def get_vision_llm_client() -> BaseLLMClient:
    """
    Separate client for the "page-as-image" pipeline, pointed at a
    vision-capable model. Provider is chosen via VISION_LLM_PROVIDER so text
    (Groq) and vision (Google Gemini) can be different providers. Falls back
    to the mock client when the requested provider is unavailable.
    """
    settings = get_settings()
    provider = settings.VISION_LLM_PROVIDER

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            logger.warning("Gemini selected for vision but GEMINI_API_KEY is not set. Using mock.")
            return MockLLMClient()
        logger.info(f"Using GeminiLLMClient (vision) with model={settings.GEMINI_MODEL_NAME}")
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_BASE_URL,
            model=settings.GEMINI_MODEL_NAME,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            proxy=settings.GEMINI_PROXY,
        )

    if provider == "groq":
        logger.warning("Groq does not support vision models. Using mock for vision.")
        return MockLLMClient()

    if provider == "ollama":
        if "localhost:11434" in settings.LLM_BASE_URL or "127.0.0.1:11434" in settings.LLM_BASE_URL:
            logger.info(
                f"Using OllamaLLMClient (vision) with base_url={settings.LLM_BASE_URL}, "
                f"model={settings.VISION_LLM_MODEL_NAME}"
            )
            return OllamaLLMClient(
                base_url=settings.LLM_BASE_URL,
                model=settings.VISION_LLM_MODEL_NAME,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=300.0,
            )

    logger.info("Using MockLLMClient for vision (test mode).")
    return MockLLMClient()
