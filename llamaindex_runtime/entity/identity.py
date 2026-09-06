"""Cross-document exact-name entity identity (Phase 17 Wave 4a).

Identity key: (normalized mention text, canonical entity type).  Merge
planning applies hard vetoes (type mismatch, USCC conflict) before name
rules; deferred cases are the W4b fuzzy-recall entry point.  Pure
stdlib, no I/O, no wall-clock time (provenance timestamps belong to
the persistence layer).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from llamaindex_runtime.entity.contracts import MentionCandidate
from llamaindex_runtime.entity.label_map import RAINER_RAW_TO_CANONICAL
from llamaindex_runtime.entity.normalization import (
    extract_uscc,
    normalize_mention_text,
)

__all__ = [
    "CANONICAL_TYPES",
    "ENTITY_IDENTITY_NAMESPACE",
    "EntityIdentity",
    "EntityMergeEvent",
    "MergeDecision",
    "MergeOutcome",
    "VetoKind",
    "make_decision_id",
    "make_event_id",
    "make_identity_id",
    "plan_merge",
    "record_merge_event",
    "resolve_identities",
]

ENTITY_IDENTITY_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(
    uuid.NAMESPACE_URL, "llamaindex-runtime/entity-identity-v1"
)

CANONICAL_TYPES: Final[frozenset[str]] = frozenset(RAINER_RAW_TO_CANONICAL.values())

_IDENTITY_REQUIRED: Final[frozenset[str]] = frozenset(
    {"identity_id", "normalized_name", "entity_type", "member_span_ids"}
)
_IDENTITY_OPTIONAL: Final[frozenset[str]] = frozenset({"provenance"})
_DECISION_REQUIRED: Final[frozenset[str]] = frozenset(
    {
        "decision_id",
        "a_identity_id",
        "b_identity_id",
        "outcome",
        "veto_kind",
        "rule_id",
        "reasons",
    }
)
_EVENT_REQUIRED: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "decision_id",
        "merged_into_id",
        "absorbed_id",
        "rule_id",
        "recorded_by",
    }
)


def _require_nonempty_str(value: object, name: str) -> None:
    """Require a non-empty string (both type and emptiness are checked)."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_string_keys(raw: Mapping[object, object], label: str) -> None:
    """Reject non-string mapping keys before any set/sort operation."""
    for key in raw:
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be strings, got {type(key).__name__}")


def make_identity_id(normalized_name: str, entity_type: str) -> str:
    _require_nonempty_str(normalized_name, "normalized_name")
    _require_nonempty_str(entity_type, "entity_type")
    # The default json.dumps encoding of the payload IS the identity
    # contract (no ensure_ascii/sort_keys/separators overrides): changing
    # them would silently change every identity_id value.
    payload = json.dumps([normalized_name, entity_type])
    return str(uuid.uuid5(ENTITY_IDENTITY_NAMESPACE, payload))


def make_decision_id(a_identity_id: str, b_identity_id: str) -> str:
    _require_nonempty_str(a_identity_id, "a_identity_id")
    _require_nonempty_str(b_identity_id, "b_identity_id")
    payload = json.dumps(sorted([a_identity_id, b_identity_id]), separators=(",", ":"))
    return str(uuid.uuid5(ENTITY_IDENTITY_NAMESPACE, payload))


def make_event_id(decision_id: str) -> str:
    _require_nonempty_str(decision_id, "decision_id")
    payload = json.dumps(
        ["merge-event", decision_id], ensure_ascii=False, separators=(",", ":")
    )
    return str(uuid.uuid5(ENTITY_IDENTITY_NAMESPACE, payload))


@dataclass(frozen=True)
class EntityIdentity:
    identity_id: str
    normalized_name: str
    entity_type: str
    member_span_ids: tuple[str, ...]
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.identity_id, "identity_id")
        _require_nonempty_str(self.normalized_name, "normalized_name")
        _require_nonempty_str(self.entity_type, "entity_type")
        if self.identity_id != make_identity_id(self.normalized_name, self.entity_type):
            raise ValueError(
                "identity_id must be make_identity_id(normalized_name, entity_type)"
            )
        if self.normalized_name != normalize_mention_text(self.normalized_name):
            raise ValueError(
                "normalized_name must equal normalize_mention_text(normalized_name)"
            )
        if self.entity_type not in CANONICAL_TYPES:
            raise ValueError(
                f"entity_type {self.entity_type!r} is not in the canonical set"
            )
        if not isinstance(self.member_span_ids, tuple):
            raise ValueError("member_span_ids must be a tuple")
        if not self.member_span_ids:
            raise ValueError("member_span_ids must not be empty")
        if any(
            not isinstance(span_id, str) or not span_id
            for span_id in self.member_span_ids
        ):
            raise ValueError("member_span_ids entries must be non-empty strings")
        if list(self.member_span_ids) != sorted(set(self.member_span_ids)):
            raise ValueError("member_span_ids must be sorted and unique")
        if not isinstance(self.provenance, tuple):
            raise ValueError("provenance must be a tuple")
        for pair in self.provenance:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or not pair[0]
                or not isinstance(pair[1], str)
                or not pair[1]
            ):
                raise ValueError(
                    "provenance entries must be (non-empty str, non-empty str) tuples"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity_id": self.identity_id,
            "normalized_name": self.normalized_name,
            "entity_type": self.entity_type,
            "member_span_ids": list(self.member_span_ids),
            "provenance": [list(pair) for pair in self.provenance],
        }

    @classmethod
    def from_dict(cls, raw: object) -> "EntityIdentity":
        if not isinstance(raw, Mapping):
            raise ValueError(
                "EntityIdentity.from_dict expects a Mapping, got " + type(raw).__name__
            )
        _require_string_keys(raw, "EntityIdentity.from_dict")
        missing = sorted(_IDENTITY_REQUIRED - set(raw))
        unknown = sorted(set(raw) - _IDENTITY_REQUIRED - _IDENTITY_OPTIONAL)
        if missing or unknown:
            raise ValueError(
                f"EntityIdentity.from_dict missing={missing} unknown={unknown}"
            )
        members_raw = raw["member_span_ids"]
        if not isinstance(members_raw, list):
            raise ValueError("member_span_ids must be a list")
        provenance_raw = raw["provenance"] if "provenance" in raw else []
        if not isinstance(provenance_raw, list):
            raise ValueError("provenance must be a list of [key, value] pairs")
        provenance: list[tuple[str, str]] = []
        for pair in provenance_raw:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or not pair[0]
                or not isinstance(pair[1], str)
                or not pair[1]
            ):
                raise ValueError(
                    "provenance must be a list of [non-empty str, non-empty str] pairs"
                )
            provenance.append((pair[0], pair[1]))
        return cls(
            identity_id=raw["identity_id"],
            normalized_name=raw["normalized_name"],
            entity_type=raw["entity_type"],
            member_span_ids=tuple(members_raw),
            provenance=tuple(provenance),
        )


class MergeOutcome(StrEnum):
    MERGED = "merged"
    DEFERRED_REVIEW = "deferred_review"
    BLOCKED_VETO = "blocked_veto"


class VetoKind(StrEnum):
    NONE = "none"
    TYPE_MISMATCH = "type_mismatch"
    USCC_CONFLICT = "uscc_conflict"


# rule_id must be consistent with (outcome, veto_kind): every other
# combination or a rule_id outside its allowed set is rejected.
_RULE_MATRIX: Final[dict[tuple[MergeOutcome, VetoKind], frozenset[str]]] = {
    (MergeOutcome.BLOCKED_VETO, VetoKind.TYPE_MISMATCH): frozenset(
        {"type_mismatch_veto"}
    ),
    (MergeOutcome.BLOCKED_VETO, VetoKind.USCC_CONFLICT): frozenset(
        {"uscc_conflict_veto"}
    ),
    (MergeOutcome.MERGED, VetoKind.NONE): frozenset(
        {"uscc_exact_match", "exact_normalized_name"}
    ),
    (MergeOutcome.DEFERRED_REVIEW, VetoKind.NONE): frozenset({"deferred_fuzzy_recall"}),
}


@dataclass(frozen=True)
class MergeDecision:
    decision_id: str
    a_identity_id: str
    b_identity_id: str
    outcome: MergeOutcome
    veto_kind: VetoKind
    rule_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty_str(self.decision_id, "decision_id")
        _require_nonempty_str(self.a_identity_id, "a_identity_id")
        _require_nonempty_str(self.b_identity_id, "b_identity_id")
        if not isinstance(self.outcome, MergeOutcome):
            raise ValueError(
                "outcome must be a MergeOutcome member (bare str rejected)"
            )
        if not isinstance(self.veto_kind, VetoKind):
            raise ValueError("veto_kind must be a VetoKind member (bare str rejected)")
        if self.decision_id != make_decision_id(self.a_identity_id, self.b_identity_id):
            raise ValueError(
                "decision_id must be make_decision_id(a_identity_id, b_identity_id)"
            )
        _require_nonempty_str(self.rule_id, "rule_id")
        if not isinstance(self.reasons, tuple):
            raise ValueError("reasons must be a tuple")
        if not self.reasons or any(
            not isinstance(r, str) or not r for r in self.reasons
        ):
            raise ValueError("reasons must be a non-empty tuple of non-empty strings")
        allowed_rules = _RULE_MATRIX.get((self.outcome, self.veto_kind))
        if allowed_rules is None or self.rule_id not in allowed_rules:
            raise ValueError(
                f"rule_id {self.rule_id!r} is inconsistent with outcome "
                f"{self.outcome.value!r} and veto_kind {self.veto_kind.value!r}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "a_identity_id": self.a_identity_id,
            "b_identity_id": self.b_identity_id,
            "outcome": self.outcome.value,
            "veto_kind": self.veto_kind.value,
            "rule_id": self.rule_id,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, raw: object) -> "MergeDecision":
        if not isinstance(raw, Mapping):
            raise ValueError(
                "MergeDecision.from_dict expects a Mapping, got " + type(raw).__name__
            )
        _require_string_keys(raw, "MergeDecision.from_dict")
        missing = sorted(_DECISION_REQUIRED - set(raw))
        unknown = sorted(set(raw) - _DECISION_REQUIRED)
        if missing or unknown:
            raise ValueError(
                f"MergeDecision.from_dict missing={missing} unknown={unknown}"
            )
        outcome_raw = raw["outcome"]
        if not isinstance(outcome_raw, str):
            raise ValueError("outcome must be a string")
        try:
            outcome = MergeOutcome(outcome_raw)
        except ValueError:
            raise ValueError(f"unknown MergeOutcome value {outcome_raw!r}") from None
        veto_raw = raw["veto_kind"]
        if not isinstance(veto_raw, str):
            raise ValueError("veto_kind must be a string")
        try:
            veto_kind = VetoKind(veto_raw)
        except ValueError:
            raise ValueError(f"unknown VetoKind value {veto_raw!r}") from None
        reasons_raw = raw["reasons"]
        if not isinstance(reasons_raw, list) or not all(
            isinstance(r, str) for r in reasons_raw
        ):
            raise ValueError("reasons must be a list of strings")
        return cls(
            decision_id=raw["decision_id"],
            a_identity_id=raw["a_identity_id"],
            b_identity_id=raw["b_identity_id"],
            outcome=outcome,
            veto_kind=veto_kind,
            rule_id=raw["rule_id"],
            reasons=tuple(reasons_raw),
        )


def resolve_identities(
    mentions: Sequence[MentionCandidate],
) -> tuple[EntityIdentity, ...]:
    """Group mentions into exact-name identities across documents.

    Key: (normalize_mention_text(mention_text), entity_type).  In-scope
    co-reference is the job of coref_rules; this layer only merges exact
    normalized names.  Non-canonical entity_type fails closed; query
    candidates (span_id None) are rejected outright, and a span_id may
    never belong to two different identity groups.
    """
    if isinstance(mentions, (str, bytes)) or not isinstance(mentions, Sequence):
        raise ValueError("resolve_identities expects a Sequence of MentionCandidate")
    groups: dict[tuple[str, str], list[str]] = {}
    span_owner: dict[str, tuple[str, str]] = {}
    for mention in mentions:
        if not isinstance(mention, MentionCandidate):
            raise ValueError(
                "resolve_identities expects MentionCandidate instances, got "
                + type(mention).__name__
            )
        if mention.entity_type not in CANONICAL_TYPES:
            raise ValueError(
                f"entity_type {mention.entity_type!r} is not in the canonical set"
            )
        if mention.span_id is None:
            raise ValueError(
                "resolve_identities rejects query_text candidates (span_id is None); "
                "only corpus_span mentions may be resolved"
            )
        normalized = normalize_mention_text(mention.mention_text)
        key = (normalized, mention.entity_type)
        owner = span_owner.get(mention.span_id)
        if owner is not None and owner != key:
            raise ValueError(
                f"span_id {mention.span_id!r} appears in more than one identity group"
            )
        span_owner[mention.span_id] = key
        groups.setdefault(key, []).append(mention.span_id)
    identities: list[EntityIdentity] = []
    for normalized, entity_type in sorted(groups):
        member_span_ids = tuple(sorted(set(groups[(normalized, entity_type)])))
        identities.append(
            EntityIdentity(
                identity_id=make_identity_id(normalized, entity_type),
                normalized_name=normalized,
                entity_type=entity_type,
                member_span_ids=member_span_ids,
            )
        )
    return tuple(identities)


def plan_merge(
    a: EntityIdentity,
    b: EntityIdentity,
    *,
    extract_uscc_fn: Callable[[str], str | None] = extract_uscc,
) -> MergeDecision:
    """Plan a merge between two identities under hard vetoes.

    Order: type mismatch veto, USCC conflict veto, USCC agreement,
    exact normalized name, else deferred review (W4b fuzzy recall).
    """
    if not isinstance(a, EntityIdentity) or not isinstance(b, EntityIdentity):
        raise ValueError("plan_merge expects EntityIdentity instances")
    decision_id = make_decision_id(a.identity_id, b.identity_id)

    def _mk(
        outcome: MergeOutcome, veto_kind: VetoKind, rule_id: str, *reasons: str
    ) -> MergeDecision:
        return MergeDecision(
            decision_id=decision_id,
            a_identity_id=a.identity_id,
            b_identity_id=b.identity_id,
            outcome=outcome,
            veto_kind=veto_kind,
            rule_id=rule_id,
            reasons=reasons,
        )

    if a.entity_type != b.entity_type:
        return _mk(
            MergeOutcome.BLOCKED_VETO,
            VetoKind.TYPE_MISMATCH,
            "type_mismatch_veto",
            f"entity_type mismatch: {a.entity_type!r} != {b.entity_type!r}",
        )
    uscc_a = extract_uscc_fn(a.normalized_name)
    uscc_b = extract_uscc_fn(b.normalized_name)
    if uscc_a is not None and uscc_b is not None:
        if uscc_a != uscc_b:
            return _mk(
                MergeOutcome.BLOCKED_VETO,
                VetoKind.USCC_CONFLICT,
                "uscc_conflict_veto",
                f"USCC conflict: {uscc_a} vs {uscc_b}",
            )
        return _mk(
            MergeOutcome.MERGED,
            VetoKind.NONE,
            "uscc_exact_match",
            f"same USCC {uscc_a}",
        )
    if a.normalized_name == b.normalized_name:
        return _mk(
            MergeOutcome.MERGED,
            VetoKind.NONE,
            "exact_normalized_name",
            "exact normalized name match",
        )
    return _mk(
        MergeOutcome.DEFERRED_REVIEW,
        VetoKind.NONE,
        "deferred_fuzzy_recall",
        "no USCC on both sides and names differ; fuzzy recall deferred to W4b",
    )


@dataclass(frozen=True)
class EntityMergeEvent:
    event_id: str
    decision_id: str
    merged_into_id: str
    absorbed_id: str
    rule_id: str
    recorded_by: str

    def __post_init__(self) -> None:
        for name in (
            "event_id",
            "decision_id",
            "merged_into_id",
            "absorbed_id",
            "rule_id",
            "recorded_by",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.event_id != make_event_id(self.decision_id):
            raise ValueError("event_id must be make_event_id(decision_id)")
        if self.merged_into_id == self.absorbed_id:
            raise ValueError("merged_into_id must differ from absorbed_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "decision_id": self.decision_id,
            "merged_into_id": self.merged_into_id,
            "absorbed_id": self.absorbed_id,
            "rule_id": self.rule_id,
            "recorded_by": self.recorded_by,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "EntityMergeEvent":
        if not isinstance(raw, Mapping):
            raise ValueError(
                "EntityMergeEvent.from_dict expects a Mapping, got "
                + type(raw).__name__
            )
        _require_string_keys(raw, "EntityMergeEvent.from_dict")
        missing = sorted(_EVENT_REQUIRED - set(raw))
        unknown = sorted(set(raw) - _EVENT_REQUIRED)
        if missing or unknown:
            raise ValueError(
                f"EntityMergeEvent.from_dict missing={missing} unknown={unknown}"
            )
        return cls(
            event_id=raw["event_id"],
            decision_id=raw["decision_id"],
            merged_into_id=raw["merged_into_id"],
            absorbed_id=raw["absorbed_id"],
            rule_id=raw["rule_id"],
            recorded_by=raw["recorded_by"],
        )


def record_merge_event(
    a: EntityIdentity, b: EntityIdentity, *, recorded_by: str
) -> EntityMergeEvent:
    """Record a logical merge (merged_into_id ledger entry).

    Records a merge between two identities directly: the decision is
    re-derived from the facts via plan_merge.  Self-merges (identical
    identity ids) are rejected at this event layer so that the
    exact_normalized_name branch of plan_merge stays independently
    testable.  recorded_by is a caller-supplied token; this module never
    reads wall-clock time.
    """
    if not isinstance(a, EntityIdentity) or not isinstance(b, EntityIdentity):
        raise ValueError("record_merge_event expects EntityIdentity instances")
    if not isinstance(recorded_by, str) or not recorded_by.strip():
        raise ValueError("recorded_by must be a non-empty string")
    if a.identity_id == b.identity_id:
        raise ValueError("cannot record a self-merge event")
    decision = plan_merge(a, b)
    if decision.outcome is not MergeOutcome.MERGED:
        raise ValueError(
            f"cannot record a merge event for outcome {decision.outcome.value}"
        )
    merged_into_id, absorbed_id = sorted(
        [decision.a_identity_id, decision.b_identity_id]
    )
    return EntityMergeEvent(
        event_id=make_event_id(decision.decision_id),
        decision_id=decision.decision_id,
        merged_into_id=merged_into_id,
        absorbed_id=absorbed_id,
        rule_id=decision.rule_id,
        recorded_by=recorded_by,
    )
