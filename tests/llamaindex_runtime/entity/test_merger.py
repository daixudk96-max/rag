"""RED merger tests for the E2b raw-corpus entity layer (Phase 16-03).

Pins the deterministic, versioned in-memory mention merger:
- ``merge_mentions(raw_candidates, *, merger_version) -> MergedMentions``,
- immutable ``MergedMentions`` with a ``selected`` tuple and per-occurrence
  outcome attribution for EVERY candidate occurrence (including identical
  duplicate occurrences),
- the frozen D3 source-kind priority
  (frontmatter_declared > dictionary_exact > rule_weight > model_probability
  > unavailable) with confidence numerics never compared across kinds,
- shuffle-equivalent byte determinism,
- per-scope isolation on ``(input_kind, input_id, input_revision,
  segment_id)`` so nothing ever merges across inputs or segments,
- query-origin request-scoped results with zero durable-write surface,
- the zero heavy-import boundary (no modelscope/torch/jieba).
"""

from __future__ import annotations

import hashlib
import inspect
import random
import sys
from dataclasses import FrozenInstanceError, fields
from typing import get_args
from uuid import UUID

import pytest

from llamaindex_runtime.entity import (
    CandidateOutcome,
    MergedMentions,
    MentionCandidate,
    OutcomeStatus,
    merge_mentions,
)
from llamaindex_runtime.entity.contracts import canonical_json
from llamaindex_runtime.entity.merger import OUTCOME_STATUSES, _PRIORITY

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_SPAN_ID_B = str(UUID(int=4))
_DOCUMENT_ID_B = str(UUID(int=5))
_VERSION_ID_B = str(UUID(int=6))
_QUERY_ID = str(UUID(int=10))
_NORMALIZED = "猫猫今天开会议程很紧张"


def _mention(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "input_id": _SPAN_ID,
        "input_kind": "corpus_span",
        "input_revision": "abc-v2",
        "normalized_text": _NORMALIZED,
        "span_id": _SPAN_ID,
        "segment_id": "seg-1",
        "char_start": 0,
        "char_end": 2,
        "mention_text": "猫猫",
        "raw_label": "PER",
        "canonical_label": "Person",
        "entity_type": "Person",
        "confidence": 0.93,
        "confidence_kind": "model_probability",
        "source": "model",
        "extractor_id": "raner",
        "extractor_version": "1.0.0",
        "model_id": "iic/raner",
        "model_revision": "4d15e5b",
        "artifact_digest": "a" * 64,
        "schema_version": "e2b-schema-1",
        "normalization_version": "norm-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "b" * 64,
        "runtime_compatibility_id": "tuple-1",
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "document_revision": "abc-v2",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return MentionCandidate(**base)  # type: ignore[arg-type]


def _query_mention(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "input_id": _QUERY_ID,
        "input_kind": "query_text",
        "input_revision": "query-v7",
        "normalized_text": _NORMALIZED,
        "span_id": None,
        "segment_id": None,
        "char_start": 0,
        "char_end": 2,
        "mention_text": "猫猫",
        "raw_label": "PER",
        "canonical_label": "Person",
        "entity_type": "Person",
        "confidence": 0.93,
        "confidence_kind": "model_probability",
        "source": "model",
        "extractor_id": "raner",
        "extractor_version": "1.0.0",
        "model_id": "iic/raner",
        "model_revision": "4d15e5b",
        "artifact_digest": "a" * 64,
        "schema_version": "e2b-schema-1",
        "normalization_version": "norm-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "b" * 64,
        "runtime_compatibility_id": "tuple-1",
        "document_id": None,
        "version_id": None,
        "document_revision": None,
        "projection": None,
    }
    base.update(overrides)
    return MentionCandidate(**base)  # type: ignore[arg-type]


def _supplementary(**overrides: object) -> MentionCandidate:
    """A dictionary/rule supplementary candidate carrying no model provenance."""
    base: dict[str, object] = {
        "confidence_kind": "dictionary_exact",
        "confidence": 1.0,
        "source": "dictionary",
        "extractor_id": "supplementary",
        "model_id": None,
        "model_revision": None,
        "artifact_digest": None,
        "runtime_compatibility_id": None,
    }
    base.update(overrides)
    return _mention(**base)


def _candidate_as_json(candidate: MentionCandidate) -> dict[str, object]:
    return {f.name: getattr(candidate, f.name) for f in fields(candidate)}


def _outcome_as_json(outcome: CandidateOutcome) -> dict[str, object]:
    return {
        "status": outcome.status,
        "reason": outcome.reason,
        "occurrence_key": list(outcome.occurrence_key),
        "winner_occurrence_key": (
            None
            if outcome.winner_occurrence_key is None
            else list(outcome.winner_occurrence_key)
        ),
    }


def _result_canonical(result: MergedMentions) -> str:
    return canonical_json(
        {
            "merger_version": result.merger_version,
            "selected": [_candidate_as_json(candidate) for candidate in result.selected],
            "outcomes": [
                _outcome_as_json(result.outcomes[key])
                for key in sorted(result.outcomes)
            ],
        }
    )


# ---------------------------------------------------------------------------
# Phase 16-03 repair helpers: non-numeric same-kind rank + occurrence map
# ---------------------------------------------------------------------------

# Complete field serialization for the structural tie-break fingerprint. This
# mirrors the frozen merger rank key exactly: every scalar MentionCandidate
# field in canonical order plus the projection mapping, serialized with the
# OKF canonical JSON (sorted keys, compact separators) and SHA-256-digested.
# ``confidence`` is included as opaque DATA inside the fingerprint, never
# compared as a magnitude or used ascending/descending as a score.
_FINGERPRINT_FIELD_NAMES = (
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


def _overlap(a: MentionCandidate, b: MentionCandidate) -> bool:
    return a.char_start < b.char_end and b.char_start < a.char_end


def _candidate_payload(candidate: MentionCandidate) -> str:
    data: dict[str, object] = {
        name: getattr(candidate, name) for name in _FINGERPRINT_FIELD_NAMES
    }
    data["projection"] = candidate.projection if candidate.projection is not None else {}
    return canonical_json(data)


def _fingerprint(candidate: MentionCandidate) -> str:
    return hashlib.sha256(_candidate_payload(candidate).encode("utf-8")).hexdigest()


def _rank_key(candidate: MentionCandidate) -> tuple[object, ...]:
    """Frozen winner-rank total structural order: (D3 confidence-kind priority,
    SHA-256 structural digest, canonical candidate payload). Numeric confidence
    is opaque serialized data inside the payload; never a magnitude rank."""
    return (
        _PRIORITY[candidate.confidence_kind],
        _fingerprint(candidate),
        _candidate_payload(candidate),
    )


def _occurrence_to_candidate_map(
    candidates: list[MentionCandidate],
    result: MergedMentions,
) -> dict[tuple[object, ...], MentionCandidate]:
    """Reconstruct the deterministic occurrence_key -> candidate map.

    Mirrors the merger's occurrence ordering: stable sort by
    (rank_key, original position) and enumerate sorted positions to bind
    per-occurrence keys. The occurrence ordinal distinguishes only truly
    identical duplicate occurrences.
    """
    ordered = sorted(
        enumerate(candidates),
        key=lambda item: (_rank_key(item[1]), item[0]),
    )
    mapping: dict[tuple[object, ...], MentionCandidate] = {}
    for position, (_, candidate) in enumerate(ordered):
        mapping[(_rank_key(candidate), position)] = candidate
    return mapping


# ---------------------------------------------------------------------------
# Public API / validation surface
# ---------------------------------------------------------------------------


def test_merger_public_api_exported_from_entity_facade() -> None:
    import llamaindex_runtime.entity as entity

    assert entity.merge_mentions is merge_mentions
    assert entity.MergedMentions is MergedMentions
    assert entity.CandidateOutcome is CandidateOutcome
    assert entity.OutcomeStatus is OutcomeStatus
    assert entity.OUTCOME_STATUSES == OUTCOME_STATUSES


def test_merge_mentions_signature_requires_merger_version_keyword() -> None:
    parameters = inspect.signature(merge_mentions).parameters
    assert list(parameters)[0] == "raw_candidates"
    assert "merger_version" in parameters
    assert parameters["merger_version"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("bad", ["", None, 3, 3.5, True, ["x"], b"v1"])
def test_merge_mentions_rejects_invalid_merger_version(bad: object) -> None:
    with pytest.raises(ValueError, match="merger_version"):
        merge_mentions([], merger_version=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [
        ["not-a-candidate"],
        [123],
        [None],
        ["x", _mention()],
    ],
)
def test_merge_mentions_rejects_non_candidate_entries(bad: list[object]) -> None:
    with pytest.raises(ValueError, match="MentionCandidate"):
        merge_mentions(bad, merger_version="v1")  # type: ignore[list-item]


def test_merge_mentions_does_not_mutate_or_reorder_caller_sequence() -> None:
    first = _mention()
    second = _mention(char_start=9, char_end=11, mention_text="紧张")
    original = [first, second]
    snapshot = list(original)

    merge_mentions(original, merger_version="v1")

    assert original == snapshot
    assert original[0] is first
    assert original[1] is second


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------


def test_identical_duplicate_occurrences_first_selected_later_duplicate() -> None:
    first = _mention()
    second = _mention()  # identical full candidate value
    result = merge_mentions([second, first], merger_version="v1")

    assert result.selected == (first,)  # value equality; identical values
    statuses = [outcome.status for outcome in result.outcomes.values()]
    assert statuses.count("selected") == 1
    assert statuses.count("duplicate") == 1
    selected = next(o for o in result.outcomes.values() if o.status == "selected")
    duplicate = next(o for o in result.outcomes.values() if o.status == "duplicate")
    assert duplicate.reason
    assert duplicate.winner_occurrence_key is not None
    assert duplicate.winner_occurrence_key == selected.occurrence_key


def test_same_interval_same_label_grouped_equivalent_evidence() -> None:
    winner = _supplementary()
    loser = _mention()  # same interval, same Person/Person, different provenance
    result = merge_mentions([loser, winner], merger_version="v1")

    assert result.selected == (winner,)
    grouped = next(o for o in result.outcomes.values() if o.status == "grouped")
    assert grouped.reason
    assert grouped.winner_occurrence_key is not None
    assert grouped.winner_occurrence_key in {
        o.occurrence_key for o in result.outcomes.values() if o.status == "selected"
    }


def test_same_interval_incompatible_label_suppressed() -> None:
    winner = _supplementary()
    loser = _mention(canonical_label="Animal", entity_type="Animal", raw_label="ANM")
    result = merge_mentions([loser, winner], merger_version="v1")

    assert result.selected == (winner,)
    suppressed = next(o for o in result.outcomes.values() if o.status == "suppressed")
    assert suppressed.reason
    assert suppressed.winner_occurrence_key is not None


def test_strict_containment_loser_nested() -> None:
    winner = _supplementary(char_start=2, char_end=4, mention_text="今天")
    loser = _mention(
        char_start=0,
        char_end=6,
        mention_text="猫猫今天开会",
        canonical_label="Phrase",
        entity_type="Phrase",
        raw_label="Phrase",
    )
    result = merge_mentions([loser, winner], merger_version="v1")

    assert result.selected == (winner,)
    nested = next(o for o in result.outcomes.values() if o.status == "nested")
    assert nested.reason
    assert nested.winner_occurrence_key is not None


def test_strict_containment_container_wins_on_priority() -> None:
    winner = _supplementary(
        char_start=0,
        char_end=6,
        mention_text="猫猫今天开会",
        canonical_label="Phrase",
        entity_type="Phrase",
        raw_label="Phrase",
    )
    loser = _mention(char_start=2, char_end=4, mention_text="今天")
    result = merge_mentions([loser, winner], merger_version="v1")

    assert result.selected == (winner,)
    nested = next(o for o in result.outcomes.values() if o.status == "nested")
    assert nested.winner_occurrence_key is not None


def test_partial_overlap_loser_overlap() -> None:
    winner = _supplementary(char_start=2, char_end=4, mention_text="今天")
    loser = _mention(
        char_start=3,
        char_end=6,
        mention_text="天开会",
        canonical_label="Event",
        entity_type="Event",
    )
    result = merge_mentions([loser, winner], merger_version="v1")

    assert result.selected == (winner,)
    overlap = next(o for o in result.outcomes.values() if o.status == "overlap")
    assert overlap.reason
    assert overlap.winner_occurrence_key is not None


def test_disjoint_intervals_each_selected() -> None:
    first = _mention()
    second = _mention(
        char_start=9,
        char_end=11,
        mention_text="紧张",
        canonical_label="Date",
        entity_type="Date",
    )
    result = merge_mentions([first, second], merger_version="v1")

    assert len(result.selected) == 2
    assert {outcome.status for outcome in result.outcomes.values()} == {"selected"}


def test_unavailable_confidence_retainable_when_not_in_conflict() -> None:
    low = _mention(confidence=None, confidence_kind="unavailable")
    other = _mention(char_start=9, char_end=11, mention_text="紧张")
    result = merge_mentions([low, other], merger_version="v1")

    assert len(result.selected) == 2
    assert {outcome.status for outcome in result.outcomes.values()} == {"selected"}


def test_unavailable_confidence_loses_only_on_actual_conflict() -> None:
    low = _mention(
        confidence=None,
        confidence_kind="unavailable",
        char_start=2,
        char_end=4,
        mention_text="今天",
        canonical_label="Date",
        entity_type="Date",
        raw_label="Date",
    )
    winner = _supplementary(
        char_start=2,
        char_end=4,
        mention_text="今天",
        canonical_label="Date",
        entity_type="Date",
        raw_label="Date",
    )
    result = merge_mentions([low, winner], merger_version="v1")

    assert result.selected == (winner,)
    grouped = next(o for o in result.outcomes.values() if o.status == "grouped")
    assert grouped.reason


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------


def test_never_merges_across_inputs_or_segments() -> None:
    first = _mention()
    second = _mention(
        input_id=_SPAN_ID_B,
        span_id=_SPAN_ID_B,
        segment_id="seg-2",
        document_id=_DOCUMENT_ID_B,
        version_id=_VERSION_ID_B,
    )
    result = merge_mentions([first, second], merger_version="v1")

    assert len(result.selected) == 2
    assert len(result.outcomes) == 2
    assert all(outcome.status == "selected" for outcome in result.outcomes.values())


def test_never_merges_across_input_revisions_or_segments() -> None:
    seg_a = _mention(segment_id="seg-1")
    seg_b = _mention(segment_id="seg-2")
    result = merge_mentions([seg_a, seg_b], merger_version="v1")
    assert len(result.selected) == 2

    rev_a = _mention(input_revision="rev-A", document_revision="rev-A")
    rev_b = _mention(input_revision="rev-B", document_revision="rev-B")
    result = merge_mentions([rev_a, rev_b], merger_version="v1")
    assert len(result.selected) == 2


# ---------------------------------------------------------------------------
# Query-origin request-scoped non-persistence
# ---------------------------------------------------------------------------

_NO_PERSISTENCE_NAMES = (
    "save",
    "write",
    "insert",
    "upsert",
    "delete",
    "commit",
    "repository",
    "connection",
    "cursor",
)


def test_query_candidates_request_scoped_with_no_durable_write_surface() -> None:
    q1 = _query_mention()
    q2 = _query_mention(
        char_start=2,
        char_end=4,
        mention_text="今天",
        canonical_label="Date",
        entity_type="Date",
        raw_label="Date",
    )
    result = merge_mentions([q1, q2], merger_version="v1")

    assert len(result.selected) == 2
    for name in _NO_PERSISTENCE_NAMES:
        assert not hasattr(result, name)
    for cls in (MergedMentions, CandidateOutcome):
        for name in _NO_PERSISTENCE_NAMES:
            assert not hasattr(cls, name)


def test_query_result_attributes_every_occurrence_request_scoped() -> None:
    q1 = _query_mention()
    q2 = _query_mention(char_start=2, char_end=4, mention_text="今天")
    result = merge_mentions([q1, q2], merger_version="v1")

    assert len(result.outcomes) == 2
    assert len(result.selected) == 2
    assert result.merger_version == "v1"


# ---------------------------------------------------------------------------
# Immutability, determinism, and completeness
# ---------------------------------------------------------------------------


def test_merged_mentions_is_frozen() -> None:
    result = merge_mentions([_mention()], merger_version="v1")
    with pytest.raises(FrozenInstanceError):
        result.merger_version = "v2"  # type: ignore[misc]


def test_candidate_outcome_is_frozen() -> None:
    result = merge_mentions([_mention()], merger_version="v1")
    outcome = next(iter(result.outcomes.values()))
    with pytest.raises(FrozenInstanceError):
        outcome.status = "duplicate"  # type: ignore[misc]


def test_outcome_statuses_are_exactly_the_frozen_six() -> None:
    assert OUTCOME_STATUSES == frozenset(
        {"selected", "duplicate", "grouped", "suppressed", "nested", "overlap"}
    )
    assert set(get_args(OutcomeStatus)) == OUTCOME_STATUSES


def test_every_occurrence_has_an_outcome() -> None:
    candidates = [
        _mention(),
        _mention(),  # identical duplicate
        _mention(char_start=2, char_end=4, mention_text="今天"),
    ]
    result = merge_mentions(candidates, merger_version="v1")

    assert len(result.outcomes) == len(candidates)
    assert len(result.selected) == 2  # [0,2) + disjoint [2,4)


def test_non_selected_outcomes_have_reason_and_winner_reference() -> None:
    winner = _supplementary()
    loser = _mention()
    result = merge_mentions([loser, winner], merger_version="v1")

    selected_keys = {
        o.occurrence_key for o in result.outcomes.values() if o.status == "selected"
    }
    for outcome in result.outcomes.values():
        if outcome.status == "selected":
            assert outcome.reason == ""
            assert outcome.winner_occurrence_key is None
        else:
            assert outcome.reason
            assert outcome.winner_occurrence_key is not None
            assert outcome.winner_occurrence_key in selected_keys


def test_merger_version_is_recorded() -> None:
    result = merge_mentions([_mention()], merger_version="e2b-merger-v1")
    assert result.merger_version == "e2b-merger-v1"


def test_selected_values_are_stable_under_input_permutation() -> None:
    candidates = [
        _mention(char_start=2, char_end=4, mention_text="今天"),
        _mention(),
        _mention(char_start=9, char_end=11, mention_text="紧张"),
    ]
    forward = merge_mentions(candidates, merger_version="v1")
    reverse = merge_mentions(list(reversed(candidates)), merger_version="v1")

    assert forward.selected == reverse.selected
    assert _result_canonical(forward) == _result_canonical(reverse)


def test_shuffle_determinism_byte_equivalent() -> None:
    candidates = [
        _mention(),  # [0,2) Person model
        _mention(),  # identical duplicate
        _supplementary(char_start=2, char_end=4, mention_text="今天"),
        _mention(
            char_start=3,
            char_end=6,
            mention_text="天开会",
            canonical_label="Event",
            entity_type="Event",
        ),
        _mention(char_start=9, char_end=11, mention_text="紧张"),
    ]
    base = _result_canonical(merge_mentions(candidates, merger_version="v1"))
    for seed in range(5):
        shuffled = list(candidates)
        random.Random(seed).shuffle(shuffled)
        assert _result_canonical(merge_mentions(shuffled, merger_version="v1")) == base


def test_result_reconstructable_from_raw_candidates_and_version() -> None:
    candidates = [
        _mention(),
        _supplementary(char_start=2, char_end=4, mention_text="今天"),
        _mention(char_start=9, char_end=11, mention_text="紧张"),
    ]
    first = merge_mentions(candidates, merger_version="v1")
    second = merge_mentions(tuple(candidates), merger_version="v1")

    assert _result_canonical(first) == _result_canonical(second)


def test_importing_entity_package_imports_no_heavy_dependencies() -> None:
    import llamaindex_runtime.entity as entity

    assert hasattr(entity, "merge_mentions")
    assert hasattr(entity, "MergedMentions")
    for name in ("modelscope", "torch", "jieba"):
        assert name not in sys.modules, (
            f"llamaindex_runtime.entity must not import {name}"
        )


# ---------------------------------------------------------------------------
# Phase 16-03 repair: no orphan attribution + non-numeric same-kind tie-break
# ---------------------------------------------------------------------------


def _frontmatter_candidate() -> MentionCandidate:
    return _mention(
        char_start=8,
        char_end=11,
        mention_text="很紧张",
        raw_label="LOC",
        canonical_label="Location",
        entity_type="Location",
        confidence_kind="frontmatter_declared",
        confidence=1.0,
        source="frontmatter",
        extractor_id="supplementary",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        runtime_compatibility_id=None,
    )


def test_chained_displacement_loser_never_orphan_to_disjoint_winner() -> None:
    # dictionary [0,10), model [2,4), frontmatter [8,11). Under the old
    # displace-on-higher-priority sweep, dictionary was selected, then model
    # lost nested to it, then frontmatter displaced dictionary — leaving model
    # attributed "overlap" against the disjoint frontmatter. The corrected
    # merger accepts a candidate only when it overlaps no retained winner, so
    # model [2,4) is selected and never references the disjoint frontmatter.
    dictionary = _supplementary(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
    )
    model = _mention(char_start=2, char_end=4, mention_text="今天")
    frontmatter = _frontmatter_candidate()
    candidates = [dictionary, model, frontmatter]
    result = merge_mentions(candidates, merger_version="v1")

    assert len(result.selected) == 2
    assert frontmatter in result.selected
    assert model in result.selected
    assert dictionary not in result.selected

    occ_map = _occurrence_to_candidate_map(candidates, result)
    model_key = next(key for key, cand in occ_map.items() if cand is model)
    assert result.outcomes[model_key].status == "selected"

    dict_key = next(key for key, cand in occ_map.items() if cand is dictionary)
    dict_outcome = result.outcomes[dict_key]
    assert dict_outcome.status == "overlap"
    assert occ_map[dict_outcome.winner_occurrence_key] is frontmatter
    assert _overlap(dictionary, frontmatter)


def test_every_non_selected_outcome_references_real_overlapping_winner() -> None:
    frontmatter = _frontmatter_candidate()
    dictionary = _supplementary(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
    )
    model = _mention(char_start=2, char_end=4, mention_text="今天")
    duplicate_a = _mention()
    duplicate_b = _mention()
    suppressed = _mention(
        canonical_label="Animal",
        entity_type="Animal",
        raw_label="ANM",
    )
    nested = _mention(
        char_start=1,
        char_end=5,
        mention_text="猫今天开",
        canonical_label="Phrase",
        entity_type="Phrase",
        raw_label="PHR",
    )
    partial = _mention(
        char_start=3,
        char_end=6,
        mention_text="天开会",
        canonical_label="Event",
        entity_type="Event",
        raw_label="EVT",
    )
    candidates = [
        frontmatter,
        dictionary,
        model,
        duplicate_a,
        duplicate_b,
        suppressed,
        nested,
        partial,
    ]
    result = merge_mentions(candidates, merger_version="v1")
    occ_map = _occurrence_to_candidate_map(candidates, result)

    assert len(result.outcomes) == len(candidates)
    selected_keys = {
        outcome.occurrence_key
        for outcome in result.outcomes.values()
        if outcome.status == "selected"
    }
    for outcome in result.outcomes.values():
        if outcome.status == "selected":
            continue
        assert outcome.winner_occurrence_key in selected_keys
        winner = occ_map[outcome.winner_occurrence_key]
        loser = occ_map[outcome.occurrence_key]
        assert _overlap(loser, winner)


def test_same_kind_confidence_values_are_not_ordered_numerically() -> None:
    # Same confidence_kind, identical interval [0,10), identical label; the two
    # candidates differ only in raw numeric confidence (0.1 vs 0.2). The frozen
    # D3 ladder is non-numeric, so the winner is the structural fingerprint
    # order, never a numeric confidence magnitude. For THIS data the 0.2
    # candidate has the smaller SHA-256 fingerprint and therefore wins — the
    # tie-break is neither "higher wins" nor "lower wins".
    lo = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.1,
    )
    hi = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.2,
    )
    result = merge_mentions([lo, hi], merger_version="v1")

    assert hi in result.selected
    assert lo not in result.selected

    occ_map = _occurrence_to_candidate_map([lo, hi], result)
    hi_key = next(key for key, cand in occ_map.items() if cand is hi)
    assert result.outcomes[hi_key].status == "selected"
    lo_key = next(key for key, cand in occ_map.items() if cand is lo)
    lo_outcome = result.outcomes[lo_key]
    assert lo_outcome.status == "grouped"
    assert occ_map[lo_outcome.winner_occurrence_key] is hi


def test_same_kind_tie_break_is_byte_identical_under_shuffle() -> None:
    lo = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.1,
    )
    hi = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.2,
    )
    forward = _result_canonical(merge_mentions([lo, hi], merger_version="v1"))
    reverse = _result_canonical(merge_mentions([hi, lo], merger_version="v1"))
    assert forward == reverse


def test_candidate_fingerprint_tie_break_rule_is_pinned() -> None:
    # Pin the exact canonical-JSON + SHA-256 rule (not an accidental high/low
    # confidence preference): a fixed default candidate must produce this exact
    # digest, and the same-kind rank key must order by that fingerprint. The
    # rank key is the total structural order
    # (priority, sha256_digest, canonical_candidate_payload): the payload is a
    # pure collision fallback for DISTINCT values, never a numeric-confidence
    # magnitude.
    fixed = _mention()
    assert _fingerprint(fixed) == (
        "b29f1d6de55565583a6ef3e1f540d51e50e93c81bc209fa6b4ce8fa1cd5e7574"
    )
    lo = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.1,
    )
    hi = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.2,
    )
    assert _rank_key(hi) < _rank_key(lo)
    assert _rank_key(lo)[0] == _rank_key(hi)[0] == _PRIORITY["model_probability"]
    assert _rank_key(lo)[1] != _rank_key(hi)[1]
    assert _rank_key(lo)[2] != _rank_key(hi)[2]
    assert _rank_key(lo)[2] == _candidate_payload(lo)
    assert _rank_key(hi)[2] == _candidate_payload(hi)


def test_same_kind_pairs_with_opposite_numeric_directions_follow_structural_rank() -> None:
    # Pair A: higher numeric confidence (0.2) has the smaller fingerprint and
    # wins. Pair B: lower numeric confidence (0.1) has the smaller fingerprint
    # and wins. The two pairs demand opposite numeric directions, so any
    # always-higher or always-lower numeric comparator fails at least one pair;
    # only the pinned structural rank can pass both. Shuffle byte identity is
    # preserved for each pair.
    pairs = [
        (0.1, 0.2, 0.2),  # (low_conf, high_conf, expected_winner_conf)
        (0.1, 0.5, 0.1),
    ]
    for low_conf, high_conf, expected_winner_conf in pairs:
        low = _mention(
            char_start=0,
            char_end=10,
            mention_text="猫猫今天开会议程很紧",
            raw_label="PHR",
            canonical_label="Phrase",
            entity_type="Phrase",
            confidence=low_conf,
        )
        high = _mention(
            char_start=0,
            char_end=10,
            mention_text="猫猫今天开会议程很紧",
            raw_label="PHR",
            canonical_label="Phrase",
            entity_type="Phrase",
            confidence=high_conf,
        )
        expected = low if _rank_key(low) < _rank_key(high) else high
        assert expected.confidence == expected_winner_conf

        result = merge_mentions([low, high], merger_version="v1")
        assert expected in result.selected
        loser = high if expected is low else low
        assert loser not in result.selected

        forward = _result_canonical(merge_mentions([low, high], merger_version="v1"))
        reverse = _result_canonical(merge_mentions([high, low], merger_version="v1"))
        assert forward == reverse


def test_distinct_values_with_digest_collision_still_rank_by_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llamaindex_runtime.entity.merger as merger_mod

    # Force every candidate to the same SHA-256 digest so only the canonical
    # payload (the collision fallback) can order distinct values. A real SHA-256
    # collision is infeasible; this controlled patch proves the total-order
    # fallback and that duplicate detection uses payload equality, not rank-key
    # equality.
    monkeypatch.setattr(merger_mod, "_candidate_fingerprint", lambda candidate: "0" * 64)

    low = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.1,
    )
    high = _mention(
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
        confidence=0.2,
    )
    assert merger_mod._candidate_payload(low) != merger_mod._candidate_payload(high)
    assert merger_mod._rank_key(low) != merger_mod._rank_key(high)

    result = merge_mentions([low, high], merger_version="v1")
    assert len(result.selected) == 1
    loser_statuses = [
        outcome.status
        for outcome in result.outcomes.values()
        if outcome.status != "selected"
    ]
    assert len(loser_statuses) == 1
    assert loser_statuses[0] != "duplicate"

    forward = _result_canonical(merge_mentions([low, high], merger_version="v1"))
    reverse = _result_canonical(merge_mentions([high, low], merger_version="v1"))
    assert forward == reverse


def test_identical_duplicates_still_detected_under_digest_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llamaindex_runtime.entity.merger as merger_mod

    monkeypatch.setattr(merger_mod, "_candidate_fingerprint", lambda candidate: "0" * 64)
    first = _mention()
    second = _mention()  # value-identical
    assert merger_mod._candidate_payload(first) == merger_mod._candidate_payload(second)

    result = merge_mentions([first, second], merger_version="v1")
    statuses = [outcome.status for outcome in result.outcomes.values()]
    assert statuses.count("selected") == 1
    assert statuses.count("duplicate") == 1
