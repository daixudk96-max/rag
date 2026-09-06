"""Shared test fixtures and constants for the llm_openai suite."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from llamaindex_runtime.entity.relation_review import RelationClaim
from llamaindex_runtime.entity.review_basket import EvidenceRef
from llamaindex_runtime.llm_openai.client import OpenAICompatClient
from llamaindex_runtime.llm_openai.trial_engine import LlmTrialEngine

RELATION_TYPES = frozenset(
    {"所在地", "所属公司", "任职于", "发布", "总部位于", "使用", "通话", "前往"}
)
_S1 = "11111111-1111-4111-8111-111111111111"
_S2 = "22222222-2222-4222-8222-222222222222"


class _FakeTransport:
    def __init__(self, content: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._content = content

    def post_chat(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(dict(body))
        return {
            "choices": [{"message": {"content": self._content}}],
            "model": "test-model",
            "usage": {"total_tokens": 7},
        }


class _QueueTransport:
    def __init__(self, contents: list[str]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._contents = list(contents)

    def post_chat(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(dict(body))
        content = self._contents.pop(0)
        return {
            "choices": [{"message": {"content": content}}],
            "model": "m",
        }


class _ExplodingTransport:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def post_chat(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        raise self._exc


def _client(content: str) -> tuple[OpenAICompatClient, _FakeTransport]:
    transport = _FakeTransport(content)
    client = OpenAICompatClient(
        model="test-model",
        base_url="http://relay.test",
        api_key="secret-key",
        transport=transport,
    )
    return client, transport


def _trial_payload(
    entities: list[dict[str, str]] | None = None,
    relations: list[dict[str, str]] | None = None,
) -> str:
    payload: dict[str, Any] = {}
    if entities is not None:
        payload["entities"] = entities
    if relations is not None:
        payload["relations"] = relations
    return json.dumps(payload, ensure_ascii=False)


def _claim(quote: str = "华为的总部在杭州。") -> RelationClaim:
    return RelationClaim(
        subject="华为",
        predicate="总部位于",
        object="杭州",
        subject_span_id=_S1,
        object_span_id=_S2,
        evidence=(
            EvidenceRef(source="doc-1", quote=quote, char_start=None, char_end=None),
        ),
    )


def _trial_engine(
    content: str,
    *,
    engine_id: str | None = None,
    coverage_threshold: float | None = None,
) -> tuple[LlmTrialEngine, _FakeTransport]:
    client, transport = _client(content)
    kwargs: dict[str, Any] = {"relation_types": RELATION_TYPES}
    if engine_id is not None:
        kwargs["engine_id"] = engine_id
    if coverage_threshold is not None:
        kwargs["coverage_threshold"] = coverage_threshold
    engine = LlmTrialEngine(client=client, **kwargs)
    return engine, transport


SAMPLES = ["文本一", "文本二", "文本三"]
GOOD_ENTITIES = [{"name": "华为", "type": "Organization"}]
GOOD_RELATIONS = [{"subject": "华为", "predicate": "总部位于", "object": "杭州"}]
