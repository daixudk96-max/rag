"""Review basket for deferred identity merges (Phase 17 Wave 5a).

Turns plan_merge DEFERRED_REVIEW pairs into a redacted, adjudication-ready
work queue.  Every item is re-derived from real EntityIdentity objects via
plan_merge at build time (W4b Security M1): a FuzzySuggestion is an advisory
claim and is never trusted as a decision.  Recording a merge event is out of
scope here (record_merge_event only accepts MERGED outcomes; alias-evidence
merges belong to the Phase 18 materialization layer).  basket_evidence_summary
is redacted: it never contains free text such as quotes or names.
Pure stdlib; no I/O, no wall-clock, no network; deterministic ordering.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from llamaindex_runtime.entity.contracts import MentionCandidate, canonical_json
from llamaindex_runtime.entity.fuzzy_recall import (
    DEFAULT_SUGGESTION_THRESHOLD,
    FuzzySuggestion,
    SuggestionReason,
    suggest_merges,
)
from llamaindex_runtime.entity.identity import (
    CANONICAL_TYPES,
    ENTITY_IDENTITY_NAMESPACE,
    EntityIdentity,
    MergeOutcome,
    make_identity_id,
    plan_merge,
)
from llamaindex_runtime.entity.normalization import normalize_mention_text

__all__ = [
    "BasketItem",
    "BasketItemKind",
    "BasketItemStatus",
    "EvidenceRef",
    "ReviewBasket",
    "TriageExit",
    "TriageVerdict",
    "basket_evidence_summary",
    "build_review_basket",
    "make_item_id",
    "triage_mention",
]


def _redacted_text(value: str) -> str:
    """Render a string for repr with its content redacted."""
    return "<redacted:" + str(len(value)) + "-chars>"


def _require_nonempty_str(value: object, label: str) -> None:
    """Require a non-empty, non-blank string.

    Unlike the identically named helper in identity.py this one also
    rejects whitespace-only strings.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a non-empty, non-blank string")


def _optional_offset(value: object, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + " must be None or a non-negative int")
    if value < 0:
        raise ValueError(label + " must be None or a non-negative int")


def _require_string_keys(raw: Mapping[object, object], label: str) -> None:
    """Reject non-string mapping keys before any set/sort operation."""
    for key in raw:
        if not isinstance(key, str):
            raise ValueError(label + " keys must be strings, got " + type(key).__name__)


def _finite_unit_interval(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number in [0.0, 1.0]")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(label + " must be a finite number in [0.0, 1.0]") from exc
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(label + " must be a finite number in [0.0, 1.0]")
    if not 0.0 <= result <= 1.0:
        raise ValueError(label + " must be a finite number in [0.0, 1.0]")
    return result


class BasketItemKind(StrEnum):
    """Kind of queue item (merge suggestion or relation claim)."""

    MERGE_SUGGESTION = "merge_suggestion"
    RELATION_CLAIM = "relation_claim"


class BasketItemStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TriageExit(StrEnum):
    """Three open-world exits for one mention against the identity universe."""

    AUTO = "auto"
    REVIEW = "review"
    NEW = "new"


def make_item_id(
    span_id: str, target_identity_id: str, candidate_identity_id: str
) -> str:
    """Deterministic review-item id over (span, target, candidate) ids."""
    _require_nonempty_str(span_id, "span_id")
    _require_nonempty_str(target_identity_id, "target_identity_id")
    _require_nonempty_str(candidate_identity_id, "candidate_identity_id")
    payload = json.dumps(
        ["review-item", span_id, target_identity_id, candidate_identity_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(ENTITY_IDENTITY_NAMESPACE, payload))


@dataclass(frozen=True)
class EvidenceRef:
    """One redacted evidence reference: source label plus a quote slice.

    The quote is user-facing free text; repr redacts it. Offsets are
    optional and must be provided together, with char_start <= char_end.
    """

    source: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None

    def __repr__(self) -> str:
        return (
            "EvidenceRef(source="
            + repr(self.source)
            + ", quote="
            + _redacted_text(self.quote)
            + ", char_start="
            + repr(self.char_start)
            + ", char_end="
            + repr(self.char_end)
            + ")"
        )

    def __post_init__(self) -> None:
        _require_nonempty_str(self.source, "source")
        _require_nonempty_str(self.quote, "quote")
        _optional_offset(self.char_start, "char_start")
        _optional_offset(self.char_end, "char_end")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be provided together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_start > self.char_end:
                raise ValueError("char_start must not exceed char_end")

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "quote": self.quote,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "EvidenceRef":
        if not isinstance(raw, Mapping):
            raise ValueError(
                "EvidenceRef.from_dict expects a Mapping, got " + type(raw).__name__
            )
        _require_string_keys(raw, "EvidenceRef.from_dict")
        keys = set(raw)
        expected = {"source", "quote", "char_start", "char_end"}
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        if missing or unknown:
            raise ValueError(
                "EvidenceRef.from_dict keys mismatch: missing="
                + repr(missing)
                + " unknown="
                + repr(unknown)
            )
        source_raw = raw["source"]
        quote_raw = raw["quote"]
        start_raw = raw["char_start"]
        end_raw = raw["char_end"]
        if not isinstance(source_raw, str):
            raise ValueError("source must be a string")
        if not isinstance(quote_raw, str):
            raise ValueError("quote must be a string")
        if start_raw is not None:
            if isinstance(start_raw, bool) or not isinstance(start_raw, int):
                raise ValueError("char_start must be None or a non-negative int")
        if end_raw is not None:
            if isinstance(end_raw, bool) or not isinstance(end_raw, int):
                raise ValueError("char_end must be None or a non-negative int")
        return cls(
            source=source_raw,
            quote=quote_raw,
            char_start=start_raw,
            char_end=end_raw,
        )


@dataclass(frozen=True)
class TriageVerdict:
    """One mention's open-world triage outcome (auto / review / new).

    AUTO needs a matched identity and no suggestions; REVIEW needs at least
    one suggestion; NEW allows neither.
    """

    span_id: str
    normalized_name: str
    entity_type: str
    exit: TriageExit
    matched_identity_id: str | None = None
    suggestions: tuple[FuzzySuggestion, ...] = ()

    def __repr__(self) -> str:
        return (
            "TriageVerdict(span_id="
            + repr(self.span_id)
            + ", normalized_name="
            + _redacted_text(self.normalized_name)
            + ", entity_type="
            + repr(self.entity_type)
            + ", exit="
            + repr(self.exit)
            + ", matched_identity_id="
            + repr(self.matched_identity_id)
            + ", suggestions="
            + repr(self.suggestions)
            + ")"
        )

    def __post_init__(self) -> None:
        _require_nonempty_str(self.span_id, "span_id")
        _require_nonempty_str(self.normalized_name, "normalized_name")
        _require_nonempty_str(self.entity_type, "entity_type")
        if not isinstance(self.exit, TriageExit):
            raise ValueError("exit must be a TriageExit value")
        for suggestion in self.suggestions:
            if not isinstance(suggestion, FuzzySuggestion):
                raise ValueError("suggestions must be FuzzySuggestion instances")
        if self.exit is TriageExit.AUTO:
            if self.matched_identity_id is None or self.suggestions:
                raise ValueError("AUTO verdict needs a matched id and no suggestions")
        elif self.exit is TriageExit.REVIEW:
            if self.matched_identity_id is not None or not self.suggestions:
                raise ValueError("REVIEW verdict needs suggestions and no matched id")
        else:
            if self.matched_identity_id is not None or self.suggestions:
                raise ValueError("NEW verdict needs no matched id and no suggestions")


@dataclass(frozen=True)
class BasketItem:
    """One adjudication-ready deferred merge suggestion.

    Implements a tiny redaction contract for repr: ids/score/reason/status/kind
    stay visible while candidate_normalized_name and every evidence quote are
    redacted, and evidence shows only its count.
    """

    item_id: str
    span_id: str
    target_identity_id: str
    candidate_identity_id: str
    candidate_normalized_name: str
    score: float
    reason: SuggestionReason
    decision_id: str
    evidence: tuple[EvidenceRef, ...]
    kind: BasketItemKind = BasketItemKind.MERGE_SUGGESTION
    status: BasketItemStatus = BasketItemStatus.PENDING
    adjudicated_by: str | None = None

    def __repr__(self) -> str:
        return (
            "BasketItem(item_id="
            + repr(self.item_id)
            + ", span_id="
            + repr(self.span_id)
            + ", target_identity_id="
            + repr(self.target_identity_id)
            + ", candidate_identity_id="
            + repr(self.candidate_identity_id)
            + ", candidate_normalized_name="
            + _redacted_text(self.candidate_normalized_name)
            + ", score="
            + repr(self.score)
            + ", reason="
            + repr(self.reason)
            + ", decision_id="
            + repr(self.decision_id)
            + ", evidence=<"
            + str(len(self.evidence))
            + " refs>"
            + ", kind="
            + repr(self.kind)
            + ", status="
            + repr(self.status)
            + ", adjudicated_by="
            + repr(self.adjudicated_by)
            + ")"
        )

    def __post_init__(self) -> None:
        if self.item_id != make_item_id(
            self.span_id, self.target_identity_id, self.candidate_identity_id
        ):
            raise ValueError("item_id must be make_item_id(span_id, target, candidate)")
        _require_nonempty_str(
            self.candidate_normalized_name, "candidate_normalized_name"
        )
        _require_nonempty_str(self.decision_id, "decision_id")
        if self.target_identity_id == self.candidate_identity_id:
            raise ValueError("target and candidate must be different identities")
        object.__setattr__(self, "score", _finite_unit_interval(self.score, "score"))
        if not isinstance(self.reason, SuggestionReason):
            raise ValueError("reason must be a SuggestionReason value")
        if not isinstance(self.kind, BasketItemKind):
            raise ValueError("kind must be a BasketItemKind value")
        if self.kind is not BasketItemKind.MERGE_SUGGESTION:
            raise ValueError(
                "basket item kind must be MERGE_SUGGESTION; relation claims use"
                " RelationReviewItem"
            )
        if not isinstance(self.status, BasketItemStatus):
            raise ValueError("status must be a BasketItemStatus value")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must be a non-empty tuple of EvidenceRef")
        for ref in self.evidence:
            if not isinstance(ref, EvidenceRef):
                raise ValueError("evidence entries must be EvidenceRef instances")
        if self.status is BasketItemStatus.PENDING:
            if self.adjudicated_by is not None:
                raise ValueError("adjudicated_by must be None while PENDING")
        else:
            _require_nonempty_str(self.adjudicated_by, "adjudicated_by")

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "span_id": self.span_id,
            "target_identity_id": self.target_identity_id,
            "candidate_identity_id": self.candidate_identity_id,
            "candidate_normalized_name": self.candidate_normalized_name,
            "score": self.score,
            "reason": self.reason.value,
            "decision_id": self.decision_id,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "kind": self.kind.value,
            "status": self.status.value,
            "adjudicated_by": self.adjudicated_by,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "BasketItem":
        if not isinstance(raw, Mapping):
            raise ValueError(
                "BasketItem.from_dict expects a Mapping, got " + type(raw).__name__
            )
        _require_string_keys(raw, "BasketItem.from_dict")
        keys = set(raw)
        expected = {
            "item_id",
            "span_id",
            "target_identity_id",
            "candidate_identity_id",
            "candidate_normalized_name",
            "score",
            "reason",
            "decision_id",
            "evidence",
            "kind",
            "status",
            "adjudicated_by",
        }
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        if missing or unknown:
            raise ValueError(
                "BasketItem.from_dict keys mismatch: missing="
                + repr(missing)
                + " unknown="
                + repr(unknown)
            )
        reason_raw = raw["reason"]
        if not isinstance(reason_raw, str) or reason_raw not in tuple(
            item.value for item in SuggestionReason
        ):
            raise ValueError("reason must be a known suggestion reason")
        status_raw = raw["status"]
        if not isinstance(status_raw, str) or status_raw not in tuple(
            item.value for item in BasketItemStatus
        ):
            raise ValueError("status must be a known basket item status")
        kind_raw = raw["kind"]
        if not isinstance(kind_raw, str) or kind_raw not in tuple(
            item.value for item in BasketItemKind
        ):
            raise ValueError("kind must be a known basket item kind")
        adjudicated_raw = raw["adjudicated_by"]
        if adjudicated_raw is not None:
            _require_nonempty_str(adjudicated_raw, "adjudicated_by")
        evidence_raw = raw["evidence"]
        if not isinstance(evidence_raw, list):
            raise ValueError("evidence must be a list of EvidenceRef dicts")
        evidence = tuple(EvidenceRef.from_dict(entry) for entry in evidence_raw)
        item_id_raw = raw["item_id"]
        span_raw = raw["span_id"]
        target_raw = raw["target_identity_id"]
        candidate_raw = raw["candidate_identity_id"]
        name_raw = raw["candidate_normalized_name"]
        score_raw = raw["score"]
        decision_raw = raw["decision_id"]
        for value, label in (
            (item_id_raw, "item_id"),
            (span_raw, "span_id"),
            (target_raw, "target_identity_id"),
            (candidate_raw, "candidate_identity_id"),
            (name_raw, "candidate_normalized_name"),
            (decision_raw, "decision_id"),
        ):
            if not isinstance(value, str):
                raise ValueError(label + " must be a string")
        if isinstance(score_raw, bool) or not isinstance(score_raw, (int, float)):
            raise ValueError("score must be a number")
        if adjudicated_raw is not None and not isinstance(adjudicated_raw, str):
            raise ValueError("adjudicated_by must be None or a non-empty string")
        return cls(
            item_id=item_id_raw,
            span_id=span_raw,
            target_identity_id=target_raw,
            candidate_identity_id=candidate_raw,
            candidate_normalized_name=name_raw,
            score=score_raw,
            reason=SuggestionReason(reason_raw),
            decision_id=decision_raw,
            evidence=evidence,
            kind=BasketItemKind(kind_raw),
            status=BasketItemStatus(status_raw),
            adjudicated_by=adjudicated_raw,
        )


@dataclass(frozen=True)
class ReviewBasket:
    """Immutable work queue of redacted review items."""

    items: tuple[BasketItem, ...] = ()

    def __post_init__(self) -> None:
        for item in self.items:
            if not isinstance(item, BasketItem):
                raise ValueError("items entries must be BasketItem instances")

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status is BasketItemStatus.PENDING)

    @property
    def accepted_count(self) -> int:
        return sum(1 for item in self.items if item.status is BasketItemStatus.ACCEPTED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for item in self.items if item.status is BasketItemStatus.REJECTED)

    def adjudicate(
        self, item_id: str, verdict: BasketItemStatus, *, adjudicated_by: str
    ) -> "ReviewBasket":
        _require_nonempty_str(item_id, "item_id")
        _require_nonempty_str(adjudicated_by, "adjudicated_by")
        if not isinstance(verdict, BasketItemStatus):
            raise ValueError("verdict must be a BasketItemStatus value")
        if verdict not in (BasketItemStatus.ACCEPTED, BasketItemStatus.REJECTED):
            raise ValueError("verdict must be ACCEPTED or REJECTED")
        found: int | None = None
        for position, item in enumerate(self.items):
            if item.item_id == item_id:
                found = position
                break
        if found is None:
            raise ValueError("unknown basket item_id: " + repr(item_id))
        target = self.items[found]
        if target.status is not BasketItemStatus.PENDING:
            raise ValueError("basket item has already been adjudicated")
        updated = replace(target, status=verdict, adjudicated_by=adjudicated_by)
        return ReviewBasket(
            items=self.items[:found] + (updated,) + self.items[found + 1 :]
        )

    def to_dict(self) -> dict[str, object]:
        return {"items": [item.to_dict() for item in self.items]}


def _build_target(mention: MentionCandidate, normalized: str) -> EntityIdentity:
    return EntityIdentity(
        identity_id=make_identity_id(normalized, mention.entity_type),
        normalized_name=normalized,
        entity_type=mention.entity_type,
        member_span_ids=(mention.span_id,),
    )


def _validate_universe(
    identities: Sequence[EntityIdentity],
) -> dict[str, EntityIdentity]:
    seen: dict[str, EntityIdentity] = {}
    for identity in identities:
        if not isinstance(identity, EntityIdentity):
            raise ValueError(
                "identities must be EntityIdentity instances, got "
                + type(identity).__name__
            )
        if identity.identity_id in seen:
            raise ValueError(
                "duplicate identity_id in universe: " + repr(identity.identity_id)
            )
        seen[identity.identity_id] = identity
    return seen


def triage_mention(
    mention: MentionCandidate,
    identities: Sequence[EntityIdentity],
    *,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
    ratio_fn: Callable[[str, str], float] | None = None,
) -> TriageVerdict:
    """Triage one mention to AUTO / REVIEW / NEW against an identity universe.

    Every suggestion is re-derived from plan_merge (M1); mere fuzzy
    similarity is never trusted as a decision.
    """
    if not isinstance(mention, MentionCandidate):
        raise ValueError("triage_mention expects a MentionCandidate instance")
    if mention.span_id is None:
        raise ValueError(
            "triage_mention rejects query_text candidates (span_id is None)"
        )
    if mention.entity_type not in CANONICAL_TYPES:
        raise ValueError(
            "entity_type " + repr(mention.entity_type) + " is not in the canonical set"
        )
    seen = _validate_universe(identities)
    normalized = normalize_mention_text(mention.mention_text)
    for identity in identities:
        if (
            identity.normalized_name == normalized
            and identity.entity_type == mention.entity_type
        ):
            return TriageVerdict(
                span_id=mention.span_id,
                normalized_name=normalized,
                entity_type=mention.entity_type,
                exit=TriageExit.AUTO,
                matched_identity_id=identity.identity_id,
            )
    target = _build_target(mention, normalized)
    if ratio_fn is None:
        suggestions = suggest_merges(target, identities, threshold=threshold)
    else:
        suggestions = suggest_merges(
            target, identities, threshold=threshold, ratio_fn=ratio_fn
        )
    survivors: list[FuzzySuggestion] = []
    for suggestion in suggestions:
        candidate = seen.get(suggestion.candidate_identity_id)
        if candidate is None:
            continue
        decision = plan_merge(target, candidate)
        if decision.outcome is not MergeOutcome.DEFERRED_REVIEW:
            continue
        if (
            decision.a_identity_id != suggestion.target_identity_id
            or decision.b_identity_id != suggestion.candidate_identity_id
        ):
            continue
        survivors.append(suggestion)
    if survivors:
        return TriageVerdict(
            span_id=mention.span_id,
            normalized_name=normalized,
            entity_type=mention.entity_type,
            exit=TriageExit.REVIEW,
            suggestions=tuple(survivors),
        )
    return TriageVerdict(
        span_id=mention.span_id,
        normalized_name=normalized,
        entity_type=mention.entity_type,
        exit=TriageExit.NEW,
    )


def build_review_basket(
    mentions: Sequence[MentionCandidate],
    identities: Sequence[EntityIdentity],
    *,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
    ratio_fn: Callable[[str, str], float] | None = None,
) -> ReviewBasket:
    """Build a redacted review basket from corpus mentions and an identity universe.

    threshold must be a finite number in [0.0, 1.0] and every identity must be
    an EntityIdentity -- both are validated even when mentions is empty.  Item
    names always come from the real candidate EntityIdentity (Security M1).
    """
    _finite_unit_interval(threshold, "threshold")
    for identity in identities:
        if not isinstance(identity, EntityIdentity):
            raise ValueError(
                "identities must be EntityIdentity instances, got "
                + type(identity).__name__
            )
    if isinstance(mentions, (str, bytes)) or not isinstance(mentions, Sequence):
        raise ValueError("build_review_basket expects a Sequence of MentionCandidate")
    seen_spans: set[str] = set()
    for mention in mentions:
        if not isinstance(mention, MentionCandidate):
            raise ValueError(
                "build_review_basket expects MentionCandidate instances, got "
                + type(mention).__name__
            )
        if mention.span_id is None:
            raise ValueError(
                "build_review_basket rejects query_text candidates (span_id is None)"
            )
        if mention.span_id in seen_spans:
            raise ValueError("span_id appears more than once: " + repr(mention.span_id))
        seen_spans.add(mention.span_id)
    by_id = {identity.identity_id: identity for identity in identities}
    items: list[BasketItem] = []
    ordered = sorted(
        mentions,
        key=lambda mention: (
            str(mention.span_id),
            normalize_mention_text(mention.mention_text),
        ),
    )
    for mention in ordered:
        verdict = triage_mention(
            mention, identities, threshold=threshold, ratio_fn=ratio_fn
        )
        if verdict.exit is not TriageExit.REVIEW:
            continue
        target = _build_target(mention, verdict.normalized_name)
        ref = EvidenceRef(
            source=str(mention.source),
            quote=mention.mention_text,
            char_start=mention.char_start,
            char_end=mention.char_end,
        )
        for suggestion in verdict.suggestions:
            candidate = by_id.get(suggestion.candidate_identity_id)
            if candidate is None:
                continue
            # M1 last line of defence: suggestions are advisory claims, so the
            # decision is re-derived here (also yields the fresh decision_id).
            # This re-run is intentionally redundant with triage_mention's.
            decision = plan_merge(target, candidate)
            if decision.outcome is not MergeOutcome.DEFERRED_REVIEW:
                continue
            items.append(
                BasketItem(
                    item_id=make_item_id(
                        mention.span_id,
                        suggestion.target_identity_id,
                        suggestion.candidate_identity_id,
                    ),
                    span_id=mention.span_id,
                    target_identity_id=suggestion.target_identity_id,
                    candidate_identity_id=suggestion.candidate_identity_id,
                    # Never trust the advisory display name: the item always
                    # uses the real candidate identity (Security M1).
                    candidate_normalized_name=candidate.normalized_name,
                    score=suggestion.score,
                    reason=suggestion.reason,
                    decision_id=decision.decision_id,
                    evidence=(ref,),
                )
            )
    return ReviewBasket(items=tuple(items))


def basket_evidence_summary(basket: ReviewBasket) -> str:
    """Deterministic, redacted summary JSON for audit logs.

    Never contains free text: quote and candidate display names are omitted
    entirely (ids, scores and statuses only).
    """
    if not isinstance(basket, ReviewBasket):
        raise ValueError("basket_evidence_summary expects a ReviewBasket")
    summary = {
        "basket_size": len(basket.items),
        "counts": {
            "pending": basket.pending_count,
            "accepted": basket.accepted_count,
            "rejected": basket.rejected_count,
        },
        "items": [
            {
                "item_id": item.item_id,
                "span_id": item.span_id,
                "target_identity_id": item.target_identity_id,
                "candidate_identity_id": item.candidate_identity_id,
                "decision_id": item.decision_id,
                "score": item.score,
                "reason": item.reason.value,
                "status": item.status.value,
            }
            for item in basket.items
        ],
    }
    return canonical_json(summary)
