"""Deterministic D3/D1 candidate resolution (Phase 16-08).

``resolve_candidates(candidates, *, entities, aliases, priority_version)`` is a
pure function that picks ONE winning ``MentionCandidate`` per frozen occurrence
and attaches an existing entity only on an exact D1 match.

D3 conflict priority (frozen)
-----------------------------
``PRIORITY_ORDER = ("frontmatter_declared", "dictionary_exact", "rule_weight",
"model_probability", "unavailable")``. Within an equal confidence kind the
winner is the merger structural total order (``merger._rank_key``): a SHA-256
digest plus the canonical candidate payload. Numeric confidence is opaque data
inside that fingerprint and is never compared as a magnitude. ``unavailable``
is the LOWEST priority but is never dropped merely for being unavailable; it
loses only on an actual occurrence conflict.

Occurrence identity (frozen)
----------------------------
``(input_kind, input_id, input_revision, char_start, char_end, mention_text)``;
``segment_id`` is provenance only and EXCLUDED. Groups are emitted sorted by
this exact occurrence key, so shuffled candidates/entities/aliases produce
byte-identical output.

D1 canonical attachment (frozen)
--------------------------------
Attach only when the selected candidate's exact case-sensitive ``mention_text``
matches an existing compatible entity ``canonical_name`` (with an exact
``entity_type``) OR an exact case-sensitive alias whose referenced existing
entity has exactly matching ``entity_type``. Canonical and alias targets are
unioned; attach only if exactly one unique compatible entity_id results.
Unknown alias targets, type mismatch, case-only mismatch, and competing
canonical/alias targets all remain pending with ``entity_id=None``.
``canonical_label`` is never used for alias matching. Nothing is ever created
or persisted.

Fail-closed contract
--------------------
``entities`` and ``aliases`` are required keyword-only sequences of mappings.
Entity records require non-empty string ``entity_id`` / ``canonical_name`` /
``entity_type``. Alias records require non-empty ``alias`` / ``entity_id`` and a
``source`` that is exactly ``okf`` or ``dictionary``. Malformed or ambiguous
authority input raises ``ResolutionInputError``. Direct ``ResolutionResult``
construction validates ``resolved``/``pending`` as ``ResolutionDecision``
sequences and every ``chosen_priority`` entry as a frozen six-field occurrence
key with a supported confidence-kind value, defensively freezing all outputs.
The result exposes no durable write surface; ``chosen_priority`` is a read-only
mapping.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import (
    CONFIDENCE_KINDS,
    INPUT_KINDS,
    ConfidenceKind,
    MentionCandidate,
)
from .merger import OccurrenceKey, _rank_key

PRIORITY_ORDER = (
    "frontmatter_declared",
    "dictionary_exact",
    "rule_weight",
    "model_probability",
    "unavailable",
)

_ALIAS_SOURCES = ("okf", "dictionary")


class ResolutionInputError(ValueError):
    """Fail-closed typed error for malformed resolution authority input."""


@dataclass(frozen=True)
class ResolutionDecision:
    """Immutable attach/pending decision for one winning candidate."""

    candidate: MentionCandidate
    entity_id: str | None


def _validate_decision_sequence(
    value: object, name: str
) -> tuple[ResolutionDecision, ...]:
    """Validate a decision sequence and defensively copy it to a tuple."""
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or isinstance(value, Mapping)
    ):
        raise ResolutionInputError(f"{name} must be a sequence of ResolutionDecision")
    decisions = tuple(value)
    for index, decision in enumerate(decisions):
        if type(decision) is not ResolutionDecision:
            raise ResolutionInputError(f"{name}[{index}] must be a ResolutionDecision")
    return decisions


def _validate_occurrence_key(key: object) -> None:
    """Validate a frozen six-field occurrence identity tuple."""
    if type(key) is not tuple or len(key) != 6:
        raise ResolutionInputError(
            "chosen_priority key must be a 6-field occurrence tuple"
        )
    input_kind, input_id, input_revision, char_start, char_end, mention_text = key
    if input_kind not in INPUT_KINDS:
        raise ResolutionInputError(
            "chosen_priority occurrence input_kind is unsupported"
        )
    _require_nonempty_str(input_id, "chosen_priority occurrence input_id")
    _require_nonempty_str(input_revision, "chosen_priority occurrence input_revision")
    _require_nonempty_str(mention_text, "chosen_priority occurrence mention_text")
    if type(char_start) is not int or type(char_end) is not int:
        raise ResolutionInputError(
            "chosen_priority occurrence coordinates must be integers"
        )
    if char_start < 0 or char_start >= char_end:
        raise ResolutionInputError(
            "chosen_priority occurrence coordinates must satisfy 0 <= start < end"
        )


@dataclass(frozen=True)
class ResolutionResult:
    """Immutable pure result of ``resolve_candidates``.

    ``resolved``/``pending`` are defensively copied to tuples and
    ``chosen_priority`` is frozen to a read-only proxy, so direct construction
    never leaves a mutable backing sequence behind. Every output tuple/mapping
    is genuinely immutable and the result exposes no durable-write surface.
    """

    priority_version: str
    resolved: tuple[ResolutionDecision, ...]
    pending: tuple[ResolutionDecision, ...]
    chosen_priority: Mapping[OccurrenceKey, ConfidenceKind]

    def __post_init__(self) -> None:
        if type(self.priority_version) is not str or not self.priority_version:
            raise ResolutionInputError("priority_version must be a non-empty string")
        if not isinstance(self.chosen_priority, Mapping):
            raise ResolutionInputError("chosen_priority must be a Mapping")
        object.__setattr__(
            self, "resolved", _validate_decision_sequence(self.resolved, "resolved")
        )
        object.__setattr__(
            self, "pending", _validate_decision_sequence(self.pending, "pending")
        )
        frozen_priority: dict[OccurrenceKey, ConfidenceKind] = {}
        for key, value in self.chosen_priority.items():
            _validate_occurrence_key(key)
            if value not in CONFIDENCE_KINDS:
                raise ResolutionInputError(
                    "chosen_priority value must be a supported confidence_kind"
                )
            frozen_priority[key] = value
        object.__setattr__(self, "chosen_priority", MappingProxyType(frozen_priority))


def _occurrence_key(candidate: MentionCandidate) -> OccurrenceKey:
    """Frozen occurrence identity; ``segment_id`` is deliberately excluded."""
    return (
        candidate.input_kind,
        candidate.input_id,
        candidate.input_revision,
        candidate.char_start,
        candidate.char_end,
        candidate.mention_text,
    )


def _require_nonempty_str(value: object, name: str) -> None:
    if type(value) is not str or not value:
        raise ResolutionInputError(f"{name} must be a non-empty string")


def _require_records_sequence(value: object, name: str) -> list[Mapping[str, object]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or isinstance(value, Mapping)
    ):
        raise ResolutionInputError(f"{name} must be a sequence of mappings")
    return list(value)


def _validate_entity_records(entities: Sequence[Mapping[str, object]]) -> None:
    seen: dict[str, tuple[str, str]] = {}
    for index, record in enumerate(entities):
        if not isinstance(record, Mapping):
            raise ResolutionInputError(f"entities[{index}] must be a mapping")
        _require_nonempty_str(record.get("entity_id"), f"entities[{index}].entity_id")
        _require_nonempty_str(
            record.get("canonical_name"), f"entities[{index}].canonical_name"
        )
        _require_nonempty_str(
            record.get("entity_type"), f"entities[{index}].entity_type"
        )
        entity_id = record["entity_id"]
        name_and_type = (record["canonical_name"], record["entity_type"])
        if entity_id in seen and seen[entity_id] != name_and_type:
            raise ResolutionInputError(
                f"conflicting authority records share entity_id {entity_id!r}"
            )
        seen[entity_id] = name_and_type


def _validate_alias_records(aliases: Sequence[Mapping[str, object]]) -> None:
    for index, record in enumerate(aliases):
        if not isinstance(record, Mapping):
            raise ResolutionInputError(f"aliases[{index}] must be a mapping")
        _require_nonempty_str(record.get("alias"), f"aliases[{index}].alias")
        _require_nonempty_str(record.get("entity_id"), f"aliases[{index}].entity_id")
        source = record.get("source")
        if source not in _ALIAS_SOURCES:
            raise ResolutionInputError(
                f"aliases[{index}].source must be exactly 'okf' or 'dictionary'"
            )


@dataclass(frozen=True)
class _AuthorityIndex:
    """Immutable prebuilt authority snapshot for D1 attachment."""

    entity_type_by_id: Mapping[str, str]
    canonical_by_key: Mapping[tuple[str, str], frozenset[str]]
    alias_ids_by_text: Mapping[str, frozenset[str]]


def _build_authority_index(
    entities: Sequence[Mapping[str, object]],
    aliases: Sequence[Mapping[str, object]],
) -> _AuthorityIndex:
    """Build deterministic immutable D1 lookup indexes once per call."""
    entity_type_by_id: dict[str, str] = {}
    canonical_by_key: dict[tuple[str, str], set[str]] = {}
    for record in entities:
        entity_id = record["entity_id"]
        entity_type_by_id[entity_id] = record["entity_type"]
        canonical_by_key.setdefault(
            (record["canonical_name"], record["entity_type"]), set()
        ).add(entity_id)
    alias_ids_by_text: dict[str, set[str]] = {}
    for record in aliases:
        entity_id = record["entity_id"]
        if entity_id not in entity_type_by_id:
            continue  # unknown alias target is ignored
        alias_ids_by_text.setdefault(record["alias"], set()).add(entity_id)
    return _AuthorityIndex(
        entity_type_by_id=MappingProxyType(entity_type_by_id),
        canonical_by_key=MappingProxyType(
            {key: frozenset(value) for key, value in canonical_by_key.items()}
        ),
        alias_ids_by_text=MappingProxyType(
            {key: frozenset(value) for key, value in alias_ids_by_text.items()}
        ),
    )


def _attach(winner: MentionCandidate, authority: _AuthorityIndex) -> str | None:
    """Exact D1 attach against the prebuilt authority snapshot."""
    targets: set[str] = set(
        authority.canonical_by_key.get((winner.mention_text, winner.entity_type), ())
    )
    for entity_id in authority.alias_ids_by_text.get(winner.mention_text, ()):
        if authority.entity_type_by_id[entity_id] == winner.entity_type:
            targets.add(entity_id)
    if len(targets) == 1:
        return next(iter(targets))
    return None


def resolve_candidates(
    candidates: Sequence[MentionCandidate],
    *,
    entities: Sequence[Mapping[str, object]],
    aliases: Sequence[Mapping[str, object]],
    priority_version: str,
) -> ResolutionResult:
    """Resolve candidates to attach/pending decisions by the D3/D1 rules."""
    if type(priority_version) is not str or not priority_version:
        raise ResolutionInputError("priority_version must be a non-empty string")
    entity_records = _require_records_sequence(entities, "entities")
    alias_records = _require_records_sequence(aliases, "aliases")
    _validate_entity_records(entity_records)
    _validate_alias_records(alias_records)
    authority = _build_authority_index(entity_records, alias_records)
    if not isinstance(candidates, Sequence) or isinstance(
        candidates, (str, bytes, bytearray)
    ):
        raise ResolutionInputError("candidates must be a sequence")
    candidate_list = list(candidates)
    for index, candidate in enumerate(candidate_list):
        if type(candidate) is not MentionCandidate:
            raise ResolutionInputError(
                f"candidates[{index}] must be a MentionCandidate"
            )

    groups: dict[OccurrenceKey, list[MentionCandidate]] = {}
    for candidate in candidate_list:
        groups.setdefault(_occurrence_key(candidate), []).append(candidate)

    chosen_priority: dict[OccurrenceKey, ConfidenceKind] = {}
    resolved: list[ResolutionDecision] = []
    pending: list[ResolutionDecision] = []
    for key in sorted(groups):
        winner = min(groups[key], key=_rank_key)
        chosen_priority[key] = winner.confidence_kind
        decision = ResolutionDecision(
            candidate=winner, entity_id=_attach(winner, authority)
        )
        if decision.entity_id is None:
            pending.append(decision)
        else:
            resolved.append(decision)

    return ResolutionResult(
        priority_version=priority_version,
        resolved=tuple(resolved),
        pending=tuple(pending),
        chosen_priority=chosen_priority,
    )


__all__ = [
    "PRIORITY_ORDER",
    "ResolutionDecision",
    "ResolutionInputError",
    "ResolutionResult",
    "resolve_candidates",
]
