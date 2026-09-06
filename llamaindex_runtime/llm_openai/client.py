"""Pure LLM transport for the phase 17 sockets.

A small OpenAI-compatible chat-completions client plus response/JSON
parsing.  Knows nothing about extraction or review; the api key never
enters reprs or logs.
"""

from __future__ import annotations

import http.client
import json
import math
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from llamaindex_runtime.llm_openai._validation import (
    _require_finite_positive,
    _require_nonempty_str,
)

__all__ = ["ChatResponse", "ChatTransport", "OpenAICompatClient"]

_DEFAULT_TEMPERATURE = 0.0


def _try_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _fenced_block(candidate: str) -> str | None:
    start = candidate.find("```")
    if start == -1:
        return None
    rest = candidate[start + 3 :].lstrip()
    if rest.startswith("json"):
        rest = rest[4:]
    end = rest.find("```")
    if end == -1:
        return None
    return rest[:end].strip()


def _brace_scan(candidate: str) -> str | None:
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    return candidate[start : end + 1]


def _parse_json_payload(text: str) -> dict[str, Any]:
    """Parse an LLM reply into a JSON object, tolerating wrapper prose.

    Order: strict parse of the whole reply, then a fenced block (the trial
    prompt asks for no fences; the fence branch is tolerance for models
    that add them anyway), then a first-brace-to-last-brace scan as the
    final fallback.  Anything unparseable raises; callers fail closed.
    """
    candidate = text.strip()
    payload = _try_json(candidate)
    if payload is None:
        payload = _try_json(_fenced_block(candidate))
    if payload is None:
        payload = _try_json(_brace_scan(candidate))
    if payload is None:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("llm output did not contain a JSON object") from None
        raise ValueError("llm output did not contain a valid JSON object") from None
    if not isinstance(payload, dict):
        raise ValueError("llm output JSON must be an object")
    return payload


class ChatTransport(Protocol):
    """Transport seam so chat calls are testable without network."""

    def post_chat(self, body: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ChatResponse:
    """Normalized chat completion (content plus optional usage)."""

    content: str
    model: str
    total_tokens: int | None


@dataclass(frozen=True)
class OpenAICompatClient:
    """OpenAI-compatible chat-completions client (R3 commercial API).

    The request body is pinned to exactly the three keys model, messages and
    temperature.  transport allows injecting a fake for offline tests; the
    default transport posts to <base_url>/chat/completions with a Bearer
    header.  The api key never appears in the repr.
    """

    model: str
    base_url: str = field(kw_only=True)
    api_key: str = field(kw_only=True, repr=False, compare=False, hash=False)
    transport: ChatTransport | None = field(kw_only=True, default=None)
    timeout_s: float = field(kw_only=True, default=30.0)
    temperature: float = field(kw_only=True, default=_DEFAULT_TEMPERATURE)

    def __post_init__(self) -> None:
        _require_nonempty_str(self.model, "model")
        _require_nonempty_str(self.base_url, "base_url")
        if not (
            self.base_url.startswith("http://") or self.base_url.startswith("https://")
        ):
            raise ValueError("base_url must start with http:// or https://")
        _require_nonempty_str(self.api_key, "api_key")
        _require_finite_positive(self.timeout_s, "timeout_s")
        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature, (int, float)
        ):
            raise ValueError("temperature must be a finite number in [0, 2]")
        temperature = float(self.temperature)
        if not math.isfinite(temperature) or not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be a finite number in [0, 2]")

    def __repr__(self) -> str:
        return (
            f"OpenAICompatClient(model={self.model!r},"
            f" base_url={self.base_url!r}, api_key=<redacted>)"
        )

    def _default_transport(self) -> ChatTransport:
        client = self

        class _UrllibChatTransport:
            def post_chat(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
                url = client.base_url.rstrip("/") + "/chat/completions"
                payload = json.dumps(dict(body)).encode("utf-8")
                request = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {client.api_key}",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(
                        request, timeout=client.timeout_s
                    ) as raw:
                        text = raw.read().decode("utf-8")
                        return json.loads(text)
                except (
                    urllib.error.URLError,
                    http.client.HTTPException,
                    OSError,
                ) as exc:
                    raise ValueError(f"openai chat request failed: {exc}") from exc
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ValueError(
                        f"openai chat response was not JSON: {exc}"
                    ) from exc

        return _UrllibChatTransport()

    def complete(self, prompt: str, *, system: str | None = None) -> ChatResponse:
        """One chat completion; raises on any transport or shape failure."""
        _require_nonempty_str(prompt, "prompt")
        messages: list[dict[str, str]] = []
        if system is not None:
            _require_nonempty_str(system, "system")
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        transport: ChatTransport = (
            self.transport if self.transport is not None else self._default_transport()
        )
        response = transport.post_chat(body)
        return _parse_chat_response(response, fallback_model=self.model)


def _parse_chat_response(
    response: Mapping[str, Any], *, fallback_model: str
) -> ChatResponse:
    if not isinstance(response, Mapping):
        raise ValueError("chat response must be a mapping")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response must contain a non-empty choices list")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise ValueError("chat response choices entries must be mappings")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("chat response choice must contain a message mapping")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("chat response message content must be a string")
    raw_model = response.get("model")
    model = raw_model if isinstance(raw_model, str) and raw_model else fallback_model
    total_tokens: int | None = None
    usage = response.get("usage")
    if isinstance(usage, Mapping) and usage.get("total_tokens") is not None:
        raw_total = usage["total_tokens"]
        if isinstance(raw_total, bool) or not isinstance(raw_total, int):
            raise ValueError("chat usage total_tokens must be an integer")
        total_tokens = raw_total
    return ChatResponse(content=content, model=model, total_tokens=total_tokens)
