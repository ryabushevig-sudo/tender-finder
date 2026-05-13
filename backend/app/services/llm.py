"""LLM provider adapters (Ollama and OpenRouter) with a unified chat interface."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger


class LLMError(RuntimeError):
    """Raised when the underlying LLM provider fails."""


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _parse_json_tolerant(content: str, *, source: str, finish_reason: str | None = None) -> dict[str, Any]:
    """Parse JSON from an LLM response, tolerating common issues:
    - markdown code fences (```json ... ```)
    - leading/trailing prose
    - truncation (finish_reason='length'): close open arrays/objects and salvage what parses
    """
    if not content:
        raise LLMError(f"Empty content from {source}")

    cleaned = _CODE_FENCE_RE.sub("", content).strip()
    start = cleaned.find("{")
    if start == -1:
        logger.warning("{}: no JSON object marker in response: {}", source, cleaned[:500])
        raise LLMError(f"No JSON object in {source} response")
    candidate = cleaned[start:]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as direct_exc:
        salvaged = _try_salvage_truncated_json(candidate)
        if salvaged is not None:
            logger.warning(
                "{} returned truncated JSON (finish_reason={}); salvaged {} top-level keys",
                source,
                finish_reason,
                len(salvaged) if isinstance(salvaged, dict) else "?",
            )
            return salvaged
        logger.warning(
            "Failed to parse {} JSON (finish_reason={}): head={!r} tail={!r}",
            source,
            finish_reason,
            candidate[:200],
            candidate[-200:],
        )
        raise LLMError(f"Invalid JSON from {source}: {direct_exc}") from direct_exc


def _try_salvage_truncated_json(text: str) -> dict[str, Any] | None:
    """Best-effort fix for JSON cut off mid-stream by a token limit.

    Strategy: scan character by character, tracking brace/bracket depth and
    string state. At the last position where we were inside a structure that
    could be cleanly closed (i.e. between items in an array), record a
    candidate end. Then try to parse text[:candidate] + matching closers.
    """
    depth_stack: list[str] = []  # stack of '{' or '['
    in_string = False
    escape = False
    last_safe_end = -1  # index *after* the last clean item separator
    last_safe_close: list[str] = []

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            depth_stack.append(ch)
        elif ch in "}]":
            if depth_stack:
                depth_stack.pop()
            if not depth_stack:
                last_safe_end = i + 1
                last_safe_close = []
        elif ch == "," and depth_stack:
            # Safe place to truncate the inner-most container
            last_safe_end = i  # don't include the comma
            last_safe_close = ["}" if c == "{" else "]" for c in reversed(depth_stack)]

    if last_safe_end > 0:
        candidate = text[:last_safe_end] + "".join(last_safe_close)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None


class LLMProvider(ABC):
    """Common interface for chat-completion-style providers."""

    @abstractmethod
    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        """Send a chat request, request JSON output, return parsed JSON or raise."""

    @abstractmethod
    async def health(self) -> bool:
        """Quick reachability check; returns True if the provider responds."""


class OllamaProvider(LLMProvider):
    def __init__(self, host: str, model: str) -> None:
        self.host = host.rstrip("/")
        self.model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise LLMError("Empty content from Ollama")
        return _parse_json_tolerant(content, source="Ollama", finish_reason=data.get("done_reason"))

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ryabushevig-sudo/tender-finder",
            "X-Title": "Tender Finder",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            if response.status_code >= 400:
                logger.error("OpenRouter error {}: {}", response.status_code, response.text[:500])
                response.raise_for_status()
            data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected OpenRouter response: {data}") from exc
        finish_reason = data["choices"][0].get("finish_reason")
        return _parse_json_tolerant(content, source="OpenRouter", finish_reason=finish_reason)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return response.status_code == 200
        except Exception:
            return False


def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaProvider(host=settings.ollama_host, model=settings.ollama_model)
    if provider == "openrouter":
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
        )
    raise LLMError(f"Unknown LLM provider: {provider}")
