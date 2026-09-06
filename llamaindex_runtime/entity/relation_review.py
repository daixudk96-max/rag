"""Relation-triple review basket: source-bound claims, pluggable reviewer.

Every relation claim must carry evidence (an EvidenceRef quote); claims
without provenance are rejected. The review step only checks whether the
source quote supports the triple - open-ended generation is out of scope
by contract. Review engines are pluggable (ReviewerEngine Protocol); the
deterministic default is a keyword-evidence reviewer. Any engine failure
(exception, malformed result, reviewer-id mismatch) degrades to an
UNCERTAIN pending item under the synthetic reviewer id 'fail-closed',
never to a silent pass.

Adjudication semantics mirror review_basket: items start PENDING; a human
adjudicator flips them via RelationBasket.adjudicate. Machine verdicts are
terminal in their buckets (SUPPORTED -> accepted, UNSUPPORTED -> rejected)
with adjudicated_by left empty; the invariants are:
  PENDING  iff UNCERTAIN and no adjudicator;
  ACCEPTED iff (human adjudicator set) or (machine SUPPORTED);
  REJECTED iff (human adjudicator set) or (machine UNSUPPORTED).

Summary output is redacted: item ids, exits, reviewer ids and statuses
only - subject/object names, predicates and quotes never enter it. Repr
redacts claim names and engine-authored reason text; predicate and
structured fields remain visible. Pure stdlib, no I/O, no wall clock, no
network.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol

from llamaindex_runtime.entity.contracts import canonical_json
from llamaindex_runtime.entity.identity import ENTITY_IDENTITY_NAMESPACE
from llamaindex_runtime.entity.normalization import normalize_mention_text
from llamaindex_runtime.entity.review_basket import (
    BasketItemKind,
    BasketItemStatus,
    EvidenceRef,
)

__all__ = [
    "KeywordEvidenceReviewer",
    "RelationBasket",
    "RelationClaim",
    "RelationReviewExit",
    "RelationReviewItem",
    "RelationReviewOutcome",
    "RelationReviewResult",
    "ReviewerEngine",
    "make_relation_item_id",
    "relation_evidence_summary",
    "review_relation_claims",
]


def _redacted_text(value: str) -> str:
    return "<redacted:" + str(len(value)) + "-chars>"


def _require_nonempty_str(value: object, label: str) -> None:
    """Require a non-empty, non-blank string.

    Note: stricter than the same-named helper in identity.py, which accepts
    whitespace-only strings. Kept module-local (frozen-module precedent).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a non-empty, non-blank string")


def _require_string_keys(raw: Mapping[object, object], label: str) -> None:
    """Require Mapping keys to be str; unhashable keys raise ValueError."""
    for key in raw:
        if not isinstance(key, str):
            raise ValueError(label + " keys must be strings, got " + type(key).__name__)


class RelationReviewExit(StrEnum):
    """Reviewer verdicts: support / no support / needs human review."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class RelationClaim:
    """One source-bound relation triple awaiting evidence review.

    subject/object are raw mention texts; the span ids link them back to
    the mention layer. Evidence is mandatory: no provenance, no entry.
    """

    subject: str
    predicate: str
    object: str
    subject_span_id: str
    object_span_id: str
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        _require_nonempty_str(self.subject, "subject")
        _require_nonempty_str(self.predicate, "predicate")
        _require_nonempty_str(self.object, "object")
        _require_nonempty_str(self.subject_span_id, "subject_span_id")
        _require_nonempty_str(self.object_span_id, "object_span_id")
        if self.subject_span_id == self.object_span_id:
            raise ValueError("subject_span_id and object_span_id must differ")
        if not normalize_mention_text(self.subject):
            raise ValueError("subject normalizes to empty text")
        if not normalize_mention_text(self.object):
            raise ValueError("object normalizes to empty text")
        if not isinstance(self.evidence, tuple):
            raise ValueError("evidence must be a tuple of EvidenceRef")
        if len(self.evidence) == 0:
            raise ValueError("evidence must contain at least one EvidenceRef")
        for ref in self.evidence:
            if not isinstance(ref, EvidenceRef):
                raise ValueError("evidence entries must be EvidenceRef instances")

    def __repr__(self) -> str:
        return (
            "RelationClaim(subject="
            + _redacted_text(self.subject)
            + ", predicate="
            + repr(self.predicate)
            + ", object="
            + _redacted_text(self.object)
            + ", subject_span_id="
            + repr(self.subject_span_id)
            + ", object_span_id="
            + repr(self.object_span_id)
            + ", evidence="
            + str(len(self.evidence))
            + " refs)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "subject_span_id": self.subject_span_id,
            "object_span_id": self.object_span_id,
            "evidence": [ref.to_dict() for ref in self.evidence],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> RelationClaim:
        if not isinstance(raw, Mapping):
            raise ValueError("relation claim must be a mapping")
        _require_string_keys(raw, "relation claim")
        required = (
            "subject",
            "predicate",
            "object",
            "subject_span_id",
            "object_span_id",
            "evidence",
        )
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError("relation claim missing keys: " + ", ".join(missing))
        unknown = [key for key in raw if key not in required]
        if unknown:
            raise ValueError("relation claim unknown keys: " + ", ".join(unknown))
        fields: dict[str, str] = {}
        for label in (
            "subject",
            "predicate",
            "object",
            "subject_span_id",
            "object_span_id",
        ):
            value = raw[label]
            if not isinstance(value, str):
                raise ValueError(label + " must be a string")
            _require_nonempty_str(value, label)
            fields[label] = value
        evidence_raw = raw["evidence"]
        if not isinstance(evidence_raw, list):
            raise ValueError("evidence must be a list")
        refs: list[EvidenceRef] = []
        for entry in evidence_raw:
            if not isinstance(entry, Mapping):
                raise ValueError("evidence entries must be mappings")
            refs.append(EvidenceRef.from_dict(entry))
        return cls(
            subject=fields["subject"],
            predicate=fields["predicate"],
            object=fields["object"],
            subject_span_id=fields["subject_span_id"],
            object_span_id=fields["object_span_id"],
            evidence=tuple(refs),
        )


def make_relation_item_id(claim: RelationClaim) -> str:
    """Deterministic relation-review item id over the claim coordinates.

    Only (subject_span_id, predicate, object_span_id, evidence[0].source,
    evidence[0].quote) are hashed; subject/object surface text and
    evidence[1:] are intentionally excluded (idempotency equivalence class).
    """
    payload = json.dumps(
        [
            "relation-review",
            claim.subject_span_id,
            claim.predicate,
            claim.object_span_id,
            claim.evidence[0].source,
            claim.evidence[0].quote,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(ENTITY_IDENTITY_NAMESPACE, payload))


@dataclass(frozen=True)
class RelationReviewResult:
    """One reviewer verdict over one claim (advisory; validated by the loop)."""

    exit: RelationReviewExit
    reviewer_id: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.exit, RelationReviewExit):
            raise ValueError("exit must be a RelationReviewExit")
        _require_nonempty_str(self.reviewer_id, "reviewer_id")
        _require_nonempty_str(self.reason, "reason")

    def __repr__(self) -> str:
        return (
            "RelationReviewResult(exit="
            + repr(self.exit)
            + ", reviewer_id="
            + repr(self.reviewer_id)
            + ", reason="
            + _redacted_text(self.reason)
            + ")"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "exit": self.exit.value,
            "reviewer_id": self.reviewer_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> RelationReviewResult:
        if not isinstance(raw, Mapping):
            raise ValueError("relation review result must be a mapping")
        _require_string_keys(raw, "relation review result")
        required = ("exit", "reviewer_id", "reason")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(
                "relation review result missing keys: " + ", ".join(missing)
            )
        unknown = [key for key in raw if key not in required]
        if unknown:
            raise ValueError(
                "relation review result unknown keys: " + ", ".join(unknown)
            )
        exit_value = raw["exit"]
        if not isinstance(exit_value, str):
            raise ValueError("exit must be a string")
        try:
            exit_enum = RelationReviewExit(exit_value)
        except ValueError as exc:
            raise ValueError("exit must be a RelationReviewExit value") from exc
        reviewer_id = raw["reviewer_id"]
        if not isinstance(reviewer_id, str):
            raise ValueError("reviewer_id must be a string")
        _require_nonempty_str(reviewer_id, "reviewer_id")
        reason = raw["reason"]
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        _require_nonempty_str(reason, "reason")
        return cls(exit=exit_enum, reviewer_id=reviewer_id, reason=reason)


class ReviewerEngine(Protocol):
    """Pluggable relation reviewer; LLM engines arrive via the R3/W7 decision."""

    @property
    def reviewer_id(self) -> str:
        """Stable reviewer identity recorded on every verdict."""
        ...

    def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
        """Return one verdict for one claim; must not raise (fail-closed upstream)."""
        ...


@dataclass(frozen=True)
class KeywordEvidenceReviewer:
    """Deterministic lexical reviewer: no LLM, no I/O, no wall clock.

    SUPPORTED when the normalized subject and object both appear in the
    normalized primary quote; UNSUPPORTED when neither does; UNCERTAIN on
    partial support. Predicate wording is not required to appear verbatim.
    """

    @property
    def reviewer_id(self) -> str:
        return "keyword-evidence-v1"

    def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
        normalized_subject = normalize_mention_text(claim.subject)
        normalized_object = normalize_mention_text(claim.object)
        if not normalized_subject or not normalized_object:
            return RelationReviewResult(
                RelationReviewExit.UNCERTAIN,
                self.reviewer_id,
                "subject or object normalizes to empty text",
            )
        quote = normalize_mention_text(claim.evidence[0].quote)
        if not quote:
            return RelationReviewResult(
                RelationReviewExit.UNSUPPORTED,
                self.reviewer_id,
                "primary evidence quote normalizes to empty text",
            )
        subject_in = normalized_subject in quote
        object_in = normalized_object in quote
        if subject_in and object_in:
            return RelationReviewResult(
                RelationReviewExit.SUPPORTED,
                self.reviewer_id,
                "subject and object both present in the source quote",
            )
        if not subject_in and not object_in:
            return RelationReviewResult(
                RelationReviewExit.UNSUPPORTED,
                self.reviewer_id,
                "neither subject nor object appears in the source quote",
            )
        return RelationReviewResult(
            RelationReviewExit.UNCERTAIN,
            self.reviewer_id,
            "partial lexical support; manual review required",
        )


@dataclass(frozen=True)
class RelationReviewItem:
    """One reviewed relation claim with adjudication status."""

    item_id: str
    claim: RelationClaim
    exit: RelationReviewExit
    reviewer_id: str
    reason: str
    kind: BasketItemKind = BasketItemKind.RELATION_CLAIM
    status: BasketItemStatus = BasketItemStatus.PENDING
    adjudicated_by: str | None = None

    def __post_init__(self) -> None:
        if self.item_id != make_relation_item_id(self.claim):
            raise ValueError("item_id must equal make_relation_item_id(claim)")
        if self.kind is not BasketItemKind.RELATION_CLAIM:
            raise ValueError("kind must be BasketItemKind.RELATION_CLAIM")
        if not isinstance(self.exit, RelationReviewExit):
            raise ValueError("exit must be a RelationReviewExit")
        _require_nonempty_str(self.reviewer_id, "reviewer_id")
        _require_nonempty_str(self.reason, "reason")
        if not isinstance(self.status, BasketItemStatus):
            raise ValueError("status must be a BasketItemStatus")
        if self.adjudicated_by is not None:
            _require_nonempty_str(self.adjudicated_by, "adjudicated_by")
        if self.status is BasketItemStatus.PENDING:
            if self.adjudicated_by is not None:
                raise ValueError("pending items must not carry an adjudicator")
            if self.exit is not RelationReviewExit.UNCERTAIN:
                raise ValueError("only uncertain items stay pending")
            return
        if self.adjudicated_by is None:
            if self.exit is RelationReviewExit.UNCERTAIN:
                raise ValueError("adjudicated items must name the adjudicator")
            if (
                self.exit is RelationReviewExit.SUPPORTED
                and self.status is not BasketItemStatus.ACCEPTED
            ):
                raise ValueError("machine supported items must be accepted")
            if (
                self.exit is RelationReviewExit.UNSUPPORTED
                and self.status is not BasketItemStatus.REJECTED
            ):
                raise ValueError("machine unsupported items must be rejected")

    def __repr__(self) -> str:
        return (
            "RelationReviewItem(item_id="
            + repr(self.item_id)
            + ", claim="
            + repr(self.claim)
            + ", exit="
            + repr(self.exit)
            + ", reviewer_id="
            + repr(self.reviewer_id)
            + ", reason="
            + _redacted_text(self.reason)
            + ", kind="
            + repr(self.kind)
            + ", status="
            + repr(self.status)
            + ", adjudicated_by="
            + repr(self.adjudicated_by)
            + ")"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "claim": self.claim.to_dict(),
            "exit": self.exit.value,
            "reviewer_id": self.reviewer_id,
            "reason": self.reason,
            "kind": self.kind.value,
            "status": self.status.value,
            "adjudicated_by": self.adjudicated_by,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> RelationReviewItem:
        if not isinstance(raw, Mapping):
            raise ValueError("relation review item must be a mapping")
        _require_string_keys(raw, "relation review item")
        required = (
            "item_id",
            "claim",
            "exit",
            "reviewer_id",
            "reason",
            "kind",
            "status",
            "adjudicated_by",
        )
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError("relation review item missing keys: " + ", ".join(missing))
        unknown = [key for key in raw if key not in required]
        if unknown:
            raise ValueError("relation review item unknown keys: " + ", ".join(unknown))
        item_id = raw["item_id"]
        if not isinstance(item_id, str):
            raise ValueError("item_id must be a string")
        _require_nonempty_str(item_id, "item_id")
        claim_raw = raw["claim"]
        if not isinstance(claim_raw, Mapping):
            raise ValueError("claim must be a mapping")
        claim = RelationClaim.from_dict(claim_raw)
        exit_value = raw["exit"]
        if not isinstance(exit_value, str):
            raise ValueError("exit must be a string")
        try:
            exit_enum = RelationReviewExit(exit_value)
        except ValueError as exc:
            raise ValueError("exit must be a RelationReviewExit value") from exc
        reviewer_id = raw["reviewer_id"]
        if not isinstance(reviewer_id, str):
            raise ValueError("reviewer_id must be a string")
        _require_nonempty_str(reviewer_id, "reviewer_id")
        reason = raw["reason"]
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        _require_nonempty_str(reason, "reason")
        kind_value = raw["kind"]
        if (
            not isinstance(kind_value, str)
            or kind_value != BasketItemKind.RELATION_CLAIM.value
        ):
            raise ValueError("kind must be relation_claim")
        status_value = raw["status"]
        if not isinstance(status_value, str) or status_value not in (
            BasketItemStatus.PENDING.value,
            BasketItemStatus.ACCEPTED.value,
            BasketItemStatus.REJECTED.value,
        ):
            raise ValueError("status must be a BasketItemStatus value")
        status_enum = BasketItemStatus(status_value)
        adjudicated_by = raw["adjudicated_by"]
        if adjudicated_by is not None:
            if not isinstance(adjudicated_by, str):
                raise ValueError("adjudicated_by must be a string or null")
            _require_nonempty_str(adjudicated_by, "adjudicated_by")
        return cls(
            item_id=item_id,
            claim=claim,
            exit=exit_enum,
            reviewer_id=reviewer_id,
            reason=reason,
            kind=BasketItemKind.RELATION_CLAIM,
            status=status_enum,
            adjudicated_by=adjudicated_by,
        )


@dataclass(frozen=True)
class RelationBasket:
    """Pending relation claims awaiting human adjudication."""

    items: tuple[RelationReviewItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise ValueError("items must be a tuple")
        seen_item_ids: set[str] = set()
        for item in self.items:
            if not isinstance(item, RelationReviewItem):
                raise ValueError("items entries must be RelationReviewItem instances")
            if item.item_id in seen_item_ids:
                raise ValueError("duplicate relation item_id: " + repr(item.item_id))
            seen_item_ids.add(item.item_id)

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
        self,
        item_id: str,
        verdict: BasketItemStatus,
        *,
        adjudicated_by: str,
    ) -> RelationBasket:
        """Return a new basket with the item flipped; original untouched."""
        _require_nonempty_str(item_id, "item_id")
        _require_nonempty_str(adjudicated_by, "adjudicated_by")
        if not isinstance(verdict, BasketItemStatus):
            raise ValueError("verdict must be ACCEPTED or REJECTED")
        if verdict is BasketItemStatus.PENDING:
            raise ValueError("verdict must be ACCEPTED or REJECTED")
        target: RelationReviewItem | None = None
        for item in self.items:
            if item.item_id == item_id:
                if item.status is not BasketItemStatus.PENDING:
                    raise ValueError("item has already been adjudicated")
                target = item
                break
        if target is None:
            raise ValueError("unknown basket item_id: " + repr(item_id))
        flipped = replace(target, status=verdict, adjudicated_by=adjudicated_by)
        return RelationBasket(
            items=tuple(flipped if item is target else item for item in self.items)
        )

    def to_dict(self) -> dict[str, object]:
        return {"items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, raw: Any) -> RelationBasket:
        if not isinstance(raw, Mapping):
            raise ValueError("relation basket must be a mapping")
        _require_string_keys(raw, "relation basket")
        required = ("items",)
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError("relation basket missing keys: " + ", ".join(missing))
        unknown = [key for key in raw if key not in required]
        if unknown:
            raise ValueError("relation basket unknown keys: " + ", ".join(unknown))
        items_raw = raw["items"]
        if not isinstance(items_raw, list):
            raise ValueError("items must be a list")
        items: list[RelationReviewItem] = []
        for entry in items_raw:
            if not isinstance(entry, Mapping):
                raise ValueError("items entries must be mappings")
            items.append(RelationReviewItem.from_dict(entry))
        return cls(items=tuple(items))


@dataclass(frozen=True)
class RelationReviewOutcome:
    """Batch review result: machine-confirmed, machine-rejected, pending basket."""

    supported: tuple[RelationReviewItem, ...]
    rejected: tuple[RelationReviewItem, ...]
    basket: RelationBasket

    def __post_init__(self) -> None:
        pairs = (("supported", self.supported), ("rejected", self.rejected))
        for label, value in pairs:
            if not isinstance(value, tuple):
                raise ValueError(label + " must be a tuple of RelationReviewItem")
            for entry in value:
                if not isinstance(entry, RelationReviewItem):
                    raise ValueError(label + " must be a tuple of RelationReviewItem")
        if not isinstance(self.basket, RelationBasket):
            raise ValueError("basket must be a RelationBasket")

    @property
    def pending(self) -> tuple[RelationReviewItem, ...]:
        """Pending items, in basket order (only PENDING entries of basket.items)."""
        return tuple(
            item
            for item in self.basket.items
            if item.status is BasketItemStatus.PENDING
        )

    @property
    def supported_count(self) -> int:
        return len(self.supported)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def pending_count(self) -> int:
        return self.basket.pending_count

    def to_dict(self) -> dict[str, object]:
        """One-way serialization; no from_dict by design (mirrors W5a basket)."""
        return {
            "supported": [item.to_dict() for item in self.supported],
            "rejected": [item.to_dict() for item in self.rejected],
            "basket": self.basket.to_dict(),
        }


def _fail_closed(reason: str) -> RelationReviewResult:
    return RelationReviewResult(RelationReviewExit.UNCERTAIN, "fail-closed", reason)


def _all_fail_closed(claims: Sequence[object], reason: str) -> RelationReviewOutcome:
    """Degrade a whole batch to fail-closed pending items (engine probe blew up)."""
    items: list[RelationReviewItem] = []
    seen_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, RelationClaim):
            raise ValueError("claims entries must be RelationClaim instances")
        item_id = make_relation_item_id(claim)
        if item_id in seen_ids:
            raise ValueError("duplicate relation claim: " + item_id)
        seen_ids.add(item_id)
        items.append(
            RelationReviewItem(
                item_id=item_id,
                claim=claim,
                exit=RelationReviewExit.UNCERTAIN,
                reviewer_id="fail-closed",
                reason=reason,
                status=BasketItemStatus.PENDING,
            )
        )
    return RelationReviewOutcome(
        supported=(),
        rejected=(),
        basket=RelationBasket(items=tuple(items)),
    )


def _review_one(claim: RelationClaim, engine: ReviewerEngine) -> RelationReviewResult:
    """Call the engine and normalize any misbehavior to a pending verdict."""
    try:
        result = engine.review_claim(claim)
        expected = getattr(engine, "reviewer_id", "")
    except Exception as exc:  # deliberate fail-closed boundary
        return _fail_closed("reviewer engine raised " + type(exc).__name__)
    if not isinstance(result, RelationReviewResult) or result.reviewer_id != expected:
        return _fail_closed("reviewer result rejected")
    return result


def review_relation_claims(
    claims: Sequence[object],
    engine: ReviewerEngine,
) -> RelationReviewOutcome:
    """Review a batch of claims; fail-closed on any engine misbehavior.

    Engine exceptions, malformed results and reviewer-id mismatches all
    degrade to UNCERTAIN pending items; they never silently pass. Input
    order is preserved inside every bucket. Machine verdicts are terminal:
    SUPPORTED items are accepted and UNSUPPORTED items are rejected with no
    adjudicator; only UNCERTAIN claims land in the pending basket.
    """
    if isinstance(claims, (str, bytes)) or not isinstance(claims, Sequence):
        raise ValueError("claims must be a sequence of RelationClaim")
    try:
        reviewer_id = getattr(engine, "reviewer_id")
        review_call = getattr(engine, "review_claim")
    except AttributeError as exc:
        raise ValueError("engine must provide reviewer_id and review_claim") from exc
    except Exception as exc:
        return _all_fail_closed(claims, "reviewer engine raised " + type(exc).__name__)
    if (
        not isinstance(reviewer_id, str)
        or not reviewer_id.strip()
        or not callable(review_call)
    ):
        raise ValueError("engine must provide reviewer_id and review_claim")
    supported: list[RelationReviewItem] = []
    rejected: list[RelationReviewItem] = []
    pending: list[RelationReviewItem] = []
    seen_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, RelationClaim):
            raise ValueError("claims entries must be RelationClaim instances")
        item_id = make_relation_item_id(claim)
        if item_id in seen_ids:
            raise ValueError("duplicate relation claim: " + item_id)
        seen_ids.add(item_id)
        result = _review_one(claim, engine)
        if result.exit is RelationReviewExit.SUPPORTED:
            status = BasketItemStatus.ACCEPTED
        elif result.exit is RelationReviewExit.UNSUPPORTED:
            status = BasketItemStatus.REJECTED
        else:
            status = BasketItemStatus.PENDING
        item = RelationReviewItem(
            item_id=item_id,
            claim=claim,
            exit=result.exit,
            reviewer_id=result.reviewer_id,
            reason=result.reason,
            status=status,
        )
        if result.exit is RelationReviewExit.SUPPORTED:
            supported.append(item)
        elif result.exit is RelationReviewExit.UNSUPPORTED:
            rejected.append(item)
        else:
            pending.append(item)
    return RelationReviewOutcome(
        supported=tuple(supported),
        rejected=tuple(rejected),
        basket=RelationBasket(items=tuple(pending)),
    )


def relation_evidence_summary(outcome: RelationReviewOutcome) -> str:
    """Deterministic redacted audit summary; ids/exits/reviewer ids only."""
    ordered = sorted(
        outcome.supported + outcome.rejected + outcome.basket.items,
        key=lambda entry: entry.item_id,
    )
    items = [
        {
            "item_id": entry.item_id,
            "exit": entry.exit.value,
            "reviewer_id": entry.reviewer_id,
            "status": entry.status.value,
        }
        for entry in ordered
    ]
    summary = {
        "items": items,
        "pending_count": outcome.pending_count,
        "rejected_count": outcome.rejected_count,
        "supported_count": outcome.supported_count,
    }
    return canonical_json(summary)
