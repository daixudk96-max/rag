"""Relation reviewer adapter tests (never-raises UNCERTAIN fallback)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from llamaindex_runtime.entity.relation_review import RelationReviewExit
from llamaindex_runtime.llm_openai.client import OpenAICompatClient
from llamaindex_runtime.llm_openai.relation_reviewer import LlmRelationReviewer

from ._helpers import _ExplodingTransport, _FakeTransport, _client, _claim


class TestLlmRelationReviewer:
    def _reviewer(
        self, content: str, *, reviewer_id: str | None = None
    ) -> tuple[LlmRelationReviewer, _FakeTransport]:
        client, transport = _client(content)
        kwargs: dict[str, Any] = {"client": client}
        if reviewer_id is not None:
            kwargs["reviewer_id"] = reviewer_id
        reviewer = LlmRelationReviewer(**kwargs)
        return reviewer, transport

    @pytest.mark.parametrize(
        "verdict,expected",
        [
            ("supported", "supported"),
            ("unsupported", "unsupported"),
            ("uncertain", "uncertain"),
            ("SUPPORTED", "supported"),
        ],
    )
    def test_verdicts_map_to_exits(self, verdict: str, expected: str) -> None:
        reviewer, _ = self._reviewer(
            json.dumps(
                {"verdict": verdict, "reason": "quote matches"}, ensure_ascii=False
            )
        )
        result = reviewer.review_claim(_claim())
        assert result.exit.value == expected
        assert result.reviewer_id == "llm-relation-judge-v1"
        assert result.reason == "quote matches"

    def test_custom_reviewer_id(self) -> None:
        reviewer, _ = self._reviewer(
            json.dumps({"verdict": "supported", "reason": "r"}),
            reviewer_id="custom-v1",
        )
        assert reviewer.review_claim(_claim()).reviewer_id == "custom-v1"

    def test_prompt_contains_claim_and_quote(self) -> None:
        reviewer, transport = self._reviewer(
            json.dumps({"verdict": "supported", "reason": "r"})
        )
        reviewer.review_claim(_claim())
        prompt = transport.calls[0]["messages"][0]["content"]
        assert "华为" in prompt
        assert "总部位于" in prompt
        assert "杭州" in prompt
        assert "华为的总部在杭州。" in prompt

    def test_unparseable_json_is_uncertain(self) -> None:
        reviewer, _ = self._reviewer("garbage reply")
        result = reviewer.review_claim(_claim())
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reason == "llm verdict unparseable"

    @pytest.mark.parametrize("verdict", ["maybe", "", 42, None])
    def test_bad_verdict_is_uncertain(self, verdict: object) -> None:
        reviewer, _ = self._reviewer(
            json.dumps({"verdict": verdict, "reason": "r"}, ensure_ascii=False)
        )
        result = reviewer.review_claim(_claim())
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reason == "llm verdict unparseable"

    @pytest.mark.parametrize("reason", [None, 42, "", "   "])
    def test_bad_reason_is_uncertain(self, reason: object) -> None:
        reviewer, _ = self._reviewer(
            json.dumps({"verdict": "supported", "reason": reason}, ensure_ascii=False)
        )
        result = reviewer.review_claim(_claim())
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reason == "llm verdict unparseable"

    def test_transport_failure_is_uncertain(self) -> None:
        client = OpenAICompatClient(
            model="m",
            base_url="http://x",
            api_key="k",
            transport=_ExplodingTransport(RuntimeError("relay down")),
        )
        reviewer = LlmRelationReviewer(client=client)
        result = reviewer.review_claim(_claim())
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reason == "llm transport failed"

    def test_garbage_claim_never_raises(self) -> None:
        reviewer, _ = self._reviewer(
            json.dumps({"verdict": "supported", "reason": "r"})
        )
        result = reviewer.review_claim(None)  # type: ignore[arg-type]
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reason == "llm claim introspection failed"

    def test_markdown_fenced_json_is_tolerated(self) -> None:
        fenced = (
            "```json"
            + chr(10)
            + json.dumps({"verdict": "supported", "reason": "ok"})
            + chr(10)
            + "```"
        )
        reviewer, _ = self._reviewer(fenced)
        result = reviewer.review_claim(_claim())
        assert result.exit is RelationReviewExit.SUPPORTED

    def test_reviewer_rejects_non_client(self) -> None:
        with pytest.raises(ValueError, match="OpenAICompatClient"):
            LlmRelationReviewer(client=42)  # type: ignore[arg-type]

    def test_reviewer_rejects_blank_id(self) -> None:
        client, _ = _client("x")
        with pytest.raises(ValueError, match="reviewer_id must be a non-blank"):
            LlmRelationReviewer(client=client, reviewer_id=" ")
