"""
LLM layer - Direct Ollama API client.

Two implementations are available:
1. MockLLMClient: Used for initial frontend/backend testing without an API key.
2. OllamaLLMClient: Direct HTTP client for Ollama's chat completion API.
3. GroqLLMClient: Client for Groq's OpenAI-compatible API.
4. OpenAICompatibleClient: Generic OpenAI-compatible client.

The implementation is selected through the LLM_PROVIDER setting in .env.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Generator, Optional
import json
import time
import httpx
import base64

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """Test client that does not require a real LLM or API key."""
    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[List[str]] = None,
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
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
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
    def _encode_images(image_paths: List[str]) -> List[str]:
        """Read image files from disk and base64-encode them for Ollama's
        /api/chat 'images' field (which takes raw base64, no data: URI prefix)."""
        encoded = []
        for path in image_paths:
            try:
                with open(path, "rb") as f:
                    encoded.append(base64.b64encode(f.read()).decode("utf-8"))
            except OSError as e:
                logger.warning(f"Could not read image for vision request: {path} ({e})")
        return encoded

    def _prepare_payload(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
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
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[List[str]] = None,
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
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
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

    def _prepare_payload(
        self,
        messages: List[Dict[str, str]],
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
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        if images:
            logger.warning("Groq does not support image inputs. Ignoring images.")
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
                logger.warning("Unexpected response format from Groq: %s", data)
                return ""
        except httpx.TimeoutException:
            logger.warning("Groq request timed out after %ss.", req_timeout)
            return ""
        except Exception as e:
            logger.warning(f"Groq request failed: {e}")
            return ""

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        if images:
            logger.warning("Groq does not support image inputs. Ignoring images.")
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
        except httpx.TimeoutException:
            logger.warning("Groq streaming request timed out.")
            yield "خطا: زمان پاسخدهی به پایان رسید."
        except Exception as e:
            logger.warning(f"Groq streaming request failed: {e}")
            yield f"خطا: {e}"


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
        messages: List[Dict[str, str]],
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
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        images: Optional[List[str]] = None,
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


def get_llm_client() -> BaseLLMClient:
    settings = get_settings()
    provider = settings.LLM_PROVIDER

    if provider == "groq":
        if not settings.LLM_API_KEY:
            logger.warning("Groq selected but LLM_API_KEY is not set. Using mock.")
            return MockLLMClient()
        logger.info(f"Using GroqLLMClient with model={settings.LLM_MODEL_NAME}")
        return GroqLLMClient(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL_NAME,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "openai" or provider == "omniroute":
        if not settings.LLM_API_KEY:
            logger.warning(f"{provider} selected but LLM_API_KEY is not set. Using mock.")
            return MockLLMClient()
        base_url = settings.LLM_BASE_URL
        if not base_url or base_url == "http://localhost:11434/v1":
            base_url = "https://api.omniroute.ai/v1"
        logger.info(f"Using OpenAICompatibleClient ({provider}) with base_url={base_url}, model={settings.LLM_MODEL_NAME}")
        return OpenAICompatibleClient(
            api_key=settings.LLM_API_KEY,
            base_url=base_url,
            model=settings.LLM_MODEL_NAME,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "ollama":
        if "localhost:11434" in settings.LLM_BASE_URL or "127.0.0.1:11434" in settings.LLM_BASE_URL:
            logger.info(f"Using OllamaLLMClient with base_url={settings.LLM_BASE_URL}, model={settings.LLM_MODEL_NAME}")
            return OllamaLLMClient(
                base_url=settings.LLM_BASE_URL,
                model=settings.LLM_MODEL_NAME,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
        else:
            logger.warning("Ollama selected but base_url is not local. Using mock.")
            return MockLLMClient()

    logger.info("Using MockLLMClient (test mode without a real LLM).")
    return MockLLMClient()


def get_vision_llm_client() -> BaseLLMClient:
    """
    Separate client for the "page-as-image" pipeline, pointed at a
    vision-capable model. Note: Groq doesn't support vision, so it falls back to mock.
    """
    settings = get_settings()
    provider = settings.LLM_PROVIDER

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
