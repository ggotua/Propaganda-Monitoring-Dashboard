"""HTTP transports for the LLM providers (SPEC-005 §2).

Each transport speaks one provider's wire format and returns a uniform ``Completion``. They raise
only three domain errors, so the gateway's fallback logic stays provider-agnostic:

- ``ModelUnavailableError`` — retired (404), overloaded (503), timed out: try the next model;
- ``QuotaExceededError`` — 429: stop this provider, never rotate models to dodge a quota;
- ``LLMError`` — anything else (auth, malformed response).

No key is ever logged or included in an exception message (FR-8).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from gtaf.domain.llm import (
    LLMError,
    ModelSpec,
    ModelUnavailableError,
    QuotaExceededError,
    Usage,
)

TIMEOUT_SECONDS = 60
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


@dataclass(frozen=True, slots=True)
class Completion:
    """Raw provider result.

    Attributes:
        text: The reply text.
        usage: Token counts, with ``total_tokens`` including reasoning tokens.
        service_tier: Provider-reported tier, when present.
    """

    text: str
    usage: Usage
    service_tier: str | None = None


class Transport(Protocol):
    """A provider's wire protocol."""

    def complete(self, spec: ModelSpec, prompt: str) -> Completion:
        """Send one prompt to one model.

        Args:
            spec: Model to call.
            prompt: Fully rendered prompt.

        Returns:
            The completion.

        Raises:
            ModelUnavailableError: The model is retired, overloaded or timed out.
            QuotaExceededError: The provider refuses for quota reasons.
            LLMError: Any other failure.
        """
        ...


def load_env_file(path: Path) -> dict[str, str]:
    """Read a ``KEY=VALUE`` env file without logging values.

    Args:
        path: File to read.

    Returns:
        Mapping of names to values; empty when the file is absent.

    Notes:
        Deliberately tiny instead of adding `python-dotenv`: the format used here is two keys and
        comments, and a dependency for that would be a liability (SPEC-005 §6).
    """
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip()] = value.strip()
    return values


def api_key(name: str, env_file: Path) -> str:
    """Resolve a key from the environment, falling back to the env file.

    Args:
        name: Variable name.
        env_file: Path to `.env`.

    Returns:
        The key, or an empty string when unset.
    """
    return os.environ.get(name) or load_env_file(env_file).get(name, "")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """POST JSON and return the decoded body, mapping HTTP status to domain errors.

    Args:
        url: Endpoint.
        payload: Request body.
        headers: Request headers.

    Returns:
        Decoded response body.

    Raises:
        ModelUnavailableError: 404, 503, timeout.
        QuotaExceededError: 429.
        LLMError: Other failures, with the body excerpt but never the request headers.
    """
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return cast(
                dict[str, Any], json.loads(response.read().decode("utf-8", errors="replace"))
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code == 429:
            raise QuotaExceededError(f"HTTP 429 quota exhausted: {body}") from exc
        if exc.code in (404, 503):
            raise ModelUnavailableError(f"HTTP {exc.code}: {body}") from exc
        raise LLMError(f"HTTP {exc.code}: {body}") from exc
    except TimeoutError as exc:
        raise ModelUnavailableError(f"timeout after {TIMEOUT_SECONDS}s") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"transport error: {exc.reason}") from exc


class GeminiTransport:
    """Google Generative Language transport."""

    def __init__(self, key: str) -> None:
        """Store the key (never logged)."""
        self._key = key

    def complete(self, spec: ModelSpec, prompt: str) -> Completion:
        """Call one Gemini model."""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 512},
        }
        body = _post_json(
            f"{GEMINI_BASE}/{spec.model}:generateContent",
            payload,
            {"x-goog-api-key": self._key},
        )
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected Gemini response shape: {str(body)[:200]}") from exc
        meta = body.get("usageMetadata", {})
        usage = Usage(
            input_tokens=int(meta.get("promptTokenCount", 0)),
            output_tokens=int(meta.get("candidatesTokenCount", 0)),
            total_tokens=int(meta.get("totalTokenCount", 0)),
        )
        return Completion(text=str(text), usage=usage, service_tier=meta.get("serviceTier"))


class DeepSeekTransport:
    """DeepSeek chat-completions transport (OpenAI-compatible)."""

    def __init__(self, key: str) -> None:
        """Store the key (never logged)."""
        self._key = key

    def complete(self, spec: ModelSpec, prompt: str) -> Completion:
        """Call one DeepSeek model."""
        body = _post_json(
            DEEPSEEK_URL,
            {
                "model": spec.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 512,
            },
            {"Authorization": f"Bearer {self._key}"},
        )
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected DeepSeek response shape: {str(body)[:200]}") from exc
        meta = body.get("usage", {})
        usage = Usage(
            input_tokens=int(meta.get("prompt_tokens", 0)),
            output_tokens=int(meta.get("completion_tokens", 0)),
            total_tokens=int(meta.get("total_tokens", 0)),
        )
        return Completion(text=str(text), usage=usage)


def build_transport(provider: str, env_file: Path) -> Transport:
    """Construct the transport for a provider.

    Args:
        provider: ``gemini`` or ``deepseek``.
        env_file: Path to `.env`.

    Returns:
        The transport.

    Raises:
        LLMError: If the provider is unknown or its key is missing.
    """
    if provider == "gemini":
        key = api_key("GEMINI_API_KEY", env_file)
        if not key:
            raise LLMError("GEMINI_API_KEY is not set (checked environment and .env)")
        return GeminiTransport(key)
    if provider == "deepseek":
        key = api_key("DEEPSEEK_API_KEY", env_file)
        if not key:
            raise LLMError("DEEPSEEK_API_KEY is not set (checked environment and .env)")
        return DeepSeekTransport(key)
    raise LLMError(f"unknown provider {provider!r}")
