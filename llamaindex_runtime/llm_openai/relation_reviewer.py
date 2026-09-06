"""ReviewerEngine adapter over the phase 17 LLM socket.

Never raises: every failure degrades to an UNCERTAIN pending item, never
to SUPPORTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llamaindex_runtime.entity.relation_review import (
    RelationClaim,
    RelationReviewExit,
    RelationReviewResult,
)
from llamaindex_runtime.llm_openai._validation import _require_nonempty_str
from llamaindex_runtime.llm_openai.client import (
    OpenAICompatClient,
    _parse_json_payload,
)

__all__ = ["LlmRelationReviewer"]

_RELATION_REVIEWER_ID = "llm-relation-judge-v1"
_VERDICT_MAP = {
    "supported": RelationReviewExit.SUPPORTED,
    "unsupported": RelationReviewExit.UNSUPPORTED,
    "uncertain": RelationReviewExit.UNCERTAIN,
}
_REVIEW_PROMPT_TEMPLATE = (
    "You are a strict evidence reviewer. Decide whether the evidence quote"
    " supports the relation claim. Respond with ONLY a JSON object of the"
    ' shape {{"verdict": "supported" | "unsupported" | "uncertain",'
    ' "reason": "..."}} with no markdown fences and no commentary.'
    " Claim: ({subject}) -[{predicate}]-> ({object}). Evidence quote: {quote}"
)


@dataclass(frozen=True)
class LlmRelationReviewer:
    """ReviewerEngine adapter: grey-zone relation judge over evidence.

    Never raises: transport failures, unparseable replies, and malformed
    claims all degrade to UNCERTAIN pending items.  The verdict is never
    upgraded past what the reply supports.
    """

    client: OpenAICompatClient
    reviewer_id: str = field(kw_only=True, default=_RELATION_REVIEWER_ID)

    def __post_init__(self) -> None:
        if not isinstance(self.client, OpenAICompatClient):
            raise ValueError("client must be an OpenAICompatClient")
        _require_nonempty_str(self.reviewer_id, "reviewer_id")

    def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
        try:
            quote = claim.evidence[0].quote
            subject = claim.subject
            predicate = claim.predicate
            obj = claim.object
            prompt = _REVIEW_PROMPT_TEMPLATE.format(
                subject=subject, predicate=predicate, object=obj, quote=quote
            )
        except Exception:
            return RelationReviewResult(
                RelationReviewExit.UNCERTAIN,
                self.reviewer_id,
                "llm claim introspection failed",
            )
        try:
            content = self.client.complete(prompt).content
        except Exception:
            return RelationReviewResult(
                RelationReviewExit.UNCERTAIN,
                self.reviewer_id,
                "llm transport failed",
            )
        try:
            payload = _parse_json_payload(content)
            verdict = payload["verdict"]
            reason = payload["reason"]
            if (
                not isinstance(verdict, str)
                or verdict.strip().casefold() not in _VERDICT_MAP
            ):
                raise ValueError("verdict must be supported, unsupported, or uncertain")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("reason must be a non-blank string")
        except Exception:
            return RelationReviewResult(
                RelationReviewExit.UNCERTAIN,
                self.reviewer_id,
                "llm verdict unparseable",
            )
        exit_value = _VERDICT_MAP[verdict.strip().casefold()]
        return RelationReviewResult(
            exit=exit_value, reviewer_id=self.reviewer_id, reason=reason
        )
