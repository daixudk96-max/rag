"""Client (pure transport) tests for the OpenAI-compatible adapter."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from llamaindex_runtime.llm_openai.client import ChatResponse, OpenAICompatClient

from ._helpers import _FakeTransport, _client


class TestOpenAICompatClient:
    def test_rejects_non_scheme_base_url(self) -> None:
        with pytest.raises(ValueError, match="base_url must start with"):
            OpenAICompatClient(model="m", base_url="ftp://x", api_key="k")

    def test_rejects_blank_fields(self) -> None:
        with pytest.raises(ValueError, match="model must be a non-blank"):
            OpenAICompatClient(model="  ", base_url="http://x", api_key="k")
        with pytest.raises(ValueError, match="base_url must be a non-blank"):
            OpenAICompatClient(model="m", base_url=" ", api_key="k")
        with pytest.raises(ValueError, match="api_key must be a non-blank"):
            OpenAICompatClient(model="m", base_url="http://x", api_key="")

    @pytest.mark.parametrize("bad", [0, -1, True, float("nan"), float("inf")])
    def test_rejects_bad_timeout(self, bad: object) -> None:
        with pytest.raises(ValueError, match="timeout_s must be a positive"):
            OpenAICompatClient(
                model="m",
                base_url="http://x",
                api_key="k",
                timeout_s=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("bad", [True, 2.5, -0.1, float("nan"), float("inf")])
    def test_rejects_bad_temperature(self, bad: object) -> None:
        with pytest.raises(ValueError, match="temperature must be a finite"):
            OpenAICompatClient(
                model="m",
                base_url="http://x",
                api_key="k",
                temperature=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("temp", [0.0, 2.0])
    def test_accepts_temperature_boundaries(self, temp: float) -> None:
        client = OpenAICompatClient(
            model="m", base_url="http://x", api_key="k", temperature=temp
        )
        assert client.temperature == temp

    def test_api_key_absent_from_repr(self) -> None:
        client = OpenAICompatClient(
            model="m", base_url="http://x", api_key="secret-key"
        )
        assert "api_key=<redacted>" in repr(client)
        assert "secret-key" not in repr(client)
        twin = OpenAICompatClient(model="m", base_url="http://x", api_key="other-key")
        assert client == twin
        assert hash(client) == hash(twin)

    def test_complete_builds_exact_body(self) -> None:
        client, transport = _client("hello")
        client.complete("hi there")
        assert set(transport.calls[0]) == {"model", "messages", "temperature"}
        assert transport.calls[0]["model"] == "test-model"
        assert transport.calls[0]["temperature"] == 0.0
        assert transport.calls[0]["messages"] == [
            {"role": "user", "content": "hi there"}
        ]

    def test_complete_with_system_prepends_system_message(self) -> None:
        client, transport = _client("hello")
        client.complete("hi", system="sys prompt")
        assert transport.calls[0]["messages"] == [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "hi"},
        ]

    def test_complete_parses_choices_and_usage(self) -> None:
        client, _ = _client("hello")
        response = client.complete("hi")
        assert isinstance(response, ChatResponse)
        assert response.content == "hello"
        assert response.model == "test-model"
        assert response.total_tokens == 7

    def test_complete_missing_usage_yields_none_tokens(self) -> None:
        transport = _FakeTransport("x")
        client = OpenAICompatClient(
            model="m", base_url="http://x", api_key="k", transport=transport
        )
        original = transport.post_chat

        def _no_usage(body: Mapping[str, Any]) -> Mapping[str, Any]:
            result = dict(original(body))
            result.pop("usage")
            return result

        transport.post_chat = _no_usage  # type: ignore[method-assign]
        assert client.complete("hi").total_tokens is None

    def test_complete_rejects_empty_choices(self) -> None:
        client, _ = _client("x")
        transport = client.transport
        assert transport is not None
        original = transport.post_chat

        def _empty(body: Mapping[str, Any]) -> Mapping[str, Any]:
            result = dict(original(body))
            result["choices"] = []
            return result

        transport.post_chat = _empty  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="non-empty choices list"):
            client.complete("hi")

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda r: r.update({"choices": [{"message": {"content": 42}}]}),
            lambda r: r.update({"choices": [{"message": {}}]}),
            lambda r: r.update({"choices": [42]}),
            lambda r: r.update({"usage": {"total_tokens": True}}),
        ],
    )
    def test_complete_rejects_malformed_responses(
        self, mutate: Callable[[dict[str, Any]], None]
    ) -> None:
        client, transport = _client("x")
        assert transport is not None
        original = transport.post_chat

        def _mutated(body: Mapping[str, Any]) -> Mapping[str, Any]:
            result = dict(original(body))
            mutate(result)
            return result

        transport.post_chat = _mutated  # type: ignore[method-assign]
        with pytest.raises(ValueError):
            client.complete("hi")

    def test_complete_rejects_blank_prompt_and_system(self) -> None:
        client, transport = _client("x")
        with pytest.raises(ValueError, match="prompt must be a non-blank"):
            client.complete("  ")
        with pytest.raises(ValueError, match="system must be a non-blank"):
            client.complete("hi", system=" ")
        assert transport.calls == []

    def test_default_transport_normalizes_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> object:
            raise urllib.error.URLError("connection refused (simulated)")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        client = OpenAICompatClient(
            model="m", base_url="http://127.0.0.1:9", api_key="k"
        )
        with pytest.raises(ValueError, match="openai chat request failed"):
            client.complete("hi")


def test_chat_response_is_exportable_contract() -> None:
    response = ChatResponse(content="c", model="m", total_tokens=None)
    assert response.total_tokens is None
