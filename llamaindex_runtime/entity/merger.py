"""Deterministic, versioned in-memory candidate merger for the E2b entity layer.

Phase 16-03. ``merge_mentions`` is a pure function of
``(raw_candidates, merger_version)`` that resolves overlapping raw
``MentionCandidate`` occurrences into an immutable ``MergedMentions`` result
with outcome attribution for EVERY occurrence.

Frozen design rules
-------------------
- Scope isolation: candidates are resolved independently per
  ``(input_kind, input_id, input_revision, segment_id)``; nothing is ever
  merged across inputs, revisions, or segments.
- Source-kind priority (never a numeric cross-kind confidence comparison):
  ``frontmatter_declared > dictionary_exact > rule_weight > model_probability
  > unavailable``. ``unavailable`` is retainable whenever it does not lose an
  actual interval conflict.
- Winner-rank selection with NO displacement: candidates are processed in
  deterministic winner-rank order ``(confidence-kind priority, structural
  fingerprint)`` and a candidate is accepted only when it overlaps no
  already-retained winner. Because the retained set is monotonic, every
  rejected occurrence provably overlaps at least one retained winner, so no
  outcome ever references a disjoint winner (no orphan attribution).
- Non-numeric same-kind tie-break: within an equal ``confidence_kind`` the
  winner rank is the SHA-256 digest of the OKF canonical JSON of the complete
  candidate representation. The raw numeric ``confidence`` is included only as
  opaque DATA inside that fingerprint; it is never compared as a magnitude or
  used ascending/descending as a score. The winner-rank key is a true total
  structural order ``(priority, sha256_digest, canonical_candidate_payload)``:
  the canonical payload is the collision fallback for DISTINCT values, so two
  distinct candidates always rank deterministically even on a SHA-256 digest
  collision. A stable global occurrence ordinal distinguishes only truly
  identical duplicate occurrences (equal canonical payloads); it is NOT the
  fallback for distinct digest collisions.
- Determinism: the stable total order normalizes nullable provenance and is
  rich enough that shuffled input produces byte-identical results. Identical
  candidate occurrences are distinguished by a deterministic occurrence key
  (winner-rank key + stable global ordinal), so duplicate occurrences are
  represented safely.
- Purity: imports only the stdlib plus ``.contracts``; the module and its
  results expose no save/write/insert/upsert/delete/commit/repository/
  connection/cursor/DML capability. ``query_text`` candidates flow through the
  same pure request-scoped result.

Outcomes (frozen): ``selected`` | ``duplicate`` | ``grouped`` | ``suppressed``
| ``nested`` | ``overlap``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, get_args

from .contracts import MentionCandidate, canonical_json

OutcomeStatus = Literal[
    "selected",
    "duplicate",
    "grouped",
    "suppressed",
    "nested",
    "overlap",
]
OUTCOME_STATUSES = frozenset(get_args(OutcomeStatus))

# Priority ladder frozen from the D3 source-kind contract. Lower integer ==
# higher priority. Only the KIND participates; confidence numeric values are
# never compared across kinds or within a kind.
_PRIORITY: Mapping[str, int] = {
    "frontmatter_declared": 0,
    "dictionary_exact": 1,
    "rule_weight": 2,
    "model_probability": 3,
    "unavailable": 4,
}

# Every MentionCandidate field except ``projection``, which is appended to the
# structural fingerprint separately (as canonical JSON) because it is an
# immutable Mapping and not directly orderable.
_SORT_FIELD_NAMES = (
    "input_kind",
    "input_id",
    "input_revision",
    "normalized_text",
    "segment_id",
    "char_start",
    "char_end",
    "mention_text",
    "raw_label",
    "canonical_label",
    "entity_type",
    "confidence_kind",
    "confidence",
    "source",
    "extractor_id",
    "extractor_version",
    "schema_version",
    "normalization_version",
    "segmentation_version",
    "label_map_digest",
    "model_id",
    "model_revision",
    "artifact_digest",
    "runtime_compatibility_id",
    "span_id",
    "document_id",
    "version_id",
    "document_revision",
)

OccurrenceKey = tuple[object, ...]
SelectedEntry = tuple[OccurrenceKey, MentionCandidate]


def _candidate_payload(candidate: MentionCandidate) -> str:
    """Canonical JSON serialization of the complete candidate representation.

    Serializes every scalar field in frozen canonical order plus the projection
    mapping with the OKF canonical JSON (sorted keys, compact separators).
    ``confidence`` is included as opaque DATA inside the serialization; it is
    never compared as a magnitude or used ascending/descending as a score.
    Payload equality is exactly full candidate equality.
    """
    data: dict[str, object] = {
        name: getattr(candidate, name) for name in _SORT_FIELD_NAMES
    }
    data["projection"] = candidate.projection if candidate.projection is not None else {}
    return canonical_json(data)


def _candidate_fingerprint(candidate: MentionCandidate) -> str:
    """Non-numeric structural SHA-256 fingerprint over the complete candidate."""
    return hashlib.sha256(_candidate_payload(candidate).encode("utf-8")).hexdigest()


def _rank_key(candidate: MentionCandidate) -> OccurrenceKey:
    """Deterministic winner-rank total structural order.

    ``(D3 confidence-kind priority, SHA-256 structural digest, canonical
    candidate payload)``. The digest is the non-numeric structural rank for
    equal kinds; the canonical payload is a pure collision fallback so distinct
    values still order even on a digest collision. Numeric confidence never
    ranks candidates as a magnitude. Two candidates share a rank key only when
    they are value-identical (equal canonical payloads); distinct values always
    differ in the payload element.
    """
    payload = _candidate_payload(candidate)
    return (
        _PRIORITY[candidate.confidence_kind],
        _candidate_fingerprint(candidate),
        payload,
    )


def _overlap(a: MentionCandidate, b: MentionCandidate) -> bool:
    return a.char_start < b.char_end and b.char_start < a.char_end


def _same_interval(a: MentionCandidate, b: MentionCandidate) -> bool:
    return a.char_start == b.char_start and a.char_end == b.char_end


def _strictly_contains(container: MentionCandidate, inner: MentionCandidate) -> bool:
    return container.char_start < inner.char_start and inner.char_end < container.char_end


def _classify(candidate: MentionCandidate, winner: MentionCandidate) -> str:
    """Classify a losing candidate against the retained winner."""
    if _same_interval(candidate, winner):
        same_label = (
            candidate.canonical_label == winner.canonical_label
            and candidate.entity_type == winner.entity_type
        )
        return "grouped" if same_label else "suppressed"
    if _strictly_contains(candidate, winner) or _strictly_contains(
        winner, candidate
    ):
        return "nested"
    return "overlap"


@dataclass(frozen=True)
class CandidateOutcome:
    """Immutable per-occurrence outcome attribution."""

    status: OutcomeStatus
    reason: str
    occurrence_key: OccurrenceKey
    winner_occurrence_key: OccurrenceKey | None


@dataclass(frozen=True)
class MergedMentions:
    """Immutable pure result of ``merge_mentions``.

    ``outcomes`` maps every occurrence key to its ``CandidateOutcome`` (one
    entry per occurrence, including identical duplicate occurrences). The
    result type offers no durable-write surface; it is a pure request-scoped
    value reconstructable from ``(raw_candidates, merger_version)``.
    """

    selected: tuple[MentionCandidate, ...]
    outcomes: Mapping[OccurrenceKey, CandidateOutcome]
    merger_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", MappingProxyType(dict(self.outcomes)))


def _scope_key(candidate: MentionCandidate) -> OccurrenceKey:
    """Per-scope resolution key: never merge across inputs or segments."""
    return (
        candidate.input_kind,
        candidate.input_id,
        candidate.input_revision,
        candidate.segment_id if candidate.segment_id is not None else "",
    )


def _ordered_occurrences(
    candidates: Sequence[MentionCandidate],
) -> list[tuple[OccurrenceKey, OccurrenceKey, MentionCandidate]]:
    """Deterministic (scope, occurrence_key, candidate) list.

    The stable total order is (winner-rank key, original position), so shuffled
    input reconstructs the same occurrence sequence. The position assigned by
    the stable sort distinguishes only truly identical candidate values (equal
    canonical payloads / equal rank keys); distinct values are ordered by the
    rank key itself even on a SHA-256 digest collision.
    """
    ordered = sorted(
        enumerate(candidates),
        key=lambda item: (_rank_key(item[1]), item[0]),
    )
    return [
        (
            _scope_key(candidate),
            (_rank_key(candidate), position),
            candidate,
        )
        for position, (_, candidate) in enumerate(ordered)
    ]


def _sweep_scope(
    members: Sequence[tuple[OccurrenceKey, MentionCandidate]],
) -> list[SelectedEntry]:
    """Select the deterministic winner set within one resolution scope.

    Candidates are processed in winner-rank order. A candidate is accepted only
    when it overlaps no already-retained winner; there is NO displacement, so
    the retained set is monotonic. Every rejected candidate therefore overlaps
    at least one retained winner (the winner-rank invariant), which guarantees
    truthful, non-orphan outcome attribution.
    """
    selected: list[SelectedEntry] = []
    for occurrence_key, candidate in members:
        if any(_overlap(candidate, entry[1]) for entry in selected):
            continue
        selected.append((occurrence_key, candidate))
    return selected


def _attribute_loser(
    candidate: MentionCandidate,
    selected_in_scope: Sequence[SelectedEntry],
) -> tuple[str, OccurrenceKey]:
    """Deterministically attribute a losing candidate to a retained winner."""
    candidate_payload = _candidate_payload(candidate)
    identical = [
        entry
        for entry in selected_in_scope
        if _candidate_payload(entry[1]) == candidate_payload
    ]
    if identical:
        winner_key, _ = identical[0]
        return "duplicate", winner_key
    # The winner-rank invariant guarantees ``overlapping`` is non-empty: the
    # sweep rejects a candidate only when it overlaps an already-retained
    # winner, and the retained set is monotonic (no displacement). Attribute to
    # the highest-ranked overlapping retained winner (preferable per plan).
    overlapping = [
        entry for entry in selected_in_scope if _overlap(candidate, entry[1])
    ]
    primary = min(overlapping, key=lambda entry: _rank_key(entry[1]))
    winner_key, winner_candidate = primary
    return _classify(candidate, winner_candidate), winner_key


def _make_outcome(
    occurrence_key: OccurrenceKey,
    candidate: MentionCandidate,
    selected_in_scope: Sequence[SelectedEntry],
) -> CandidateOutcome:
    selected_keys = {key for key, _ in selected_in_scope}
    if occurrence_key in selected_keys:
        return CandidateOutcome(
            status="selected",
            reason="",
            occurrence_key=occurrence_key,
            winner_occurrence_key=None,
        )
    status, winner_key = _attribute_loser(candidate, selected_in_scope)
    return CandidateOutcome(
        status=status,
        reason=f"{status}: see selected occurrence {winner_key!r}",
        occurrence_key=occurrence_key,
        winner_occurrence_key=winner_key,
    )


def merge_mentions(
    raw_candidates: Sequence[MentionCandidate], *, merger_version: str
) -> MergedMentions:
    """Resolve raw overlapping candidates into a deterministic merged result."""
    if type(merger_version) is not str or not merger_version:
        raise ValueError("merger_version must be a non-empty string")
    candidates = list(raw_candidates)
    for index, entry in enumerate(candidates):
        if type(entry) is not MentionCandidate:
            raise ValueError(f"raw_candidates[{index}] must be a MentionCandidate")

    occurrences = _ordered_occurrences(candidates)

    members_by_scope: dict[OccurrenceKey, list[SelectedEntry]] = {}
    for scope, occurrence_key, candidate in occurrences:
        members_by_scope.setdefault(scope, []).append((occurrence_key, candidate))
    selected_by_scope = {
        scope: _sweep_scope(members)
        for scope, members in members_by_scope.items()
    }

    all_selected: list[SelectedEntry] = []
    for scope in members_by_scope:
        all_selected.extend(selected_by_scope[scope])
    all_selected.sort(key=lambda entry: entry[0])
    selected_candidates = tuple(candidate for _, candidate in all_selected)

    outcomes: dict[OccurrenceKey, CandidateOutcome] = {}
    for scope, occurrence_key, candidate in occurrences:
        outcomes[occurrence_key] = _make_outcome(
            occurrence_key, candidate, selected_by_scope[scope]
        )

    return MergedMentions(
        selected=selected_candidates,
        outcomes=outcomes,
        merger_version=merger_version,
    )


__all__ = [
    "CandidateOutcome",
    "MergedMentions",
    "OUTCOME_STATUSES",
    "OutcomeStatus",
    "merge_mentions",
]
