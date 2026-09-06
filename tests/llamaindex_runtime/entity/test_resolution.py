"""RED resolution tests (Phase 16-08, Task 1).

Frozen D3/D1 resolution contract for ``resolve_candidates(candidates, *,
entities, aliases, priority_version)``: public exact ``PRIORITY_ORDER``;
frozen ResolutionDecision(candidate, entity_id) / ResolutionResult(
priority_version, resolved, pending, chosen_priority) DTOs (keyword-only, no
mention_id/alias helpers); occurrence identity excludes segment_id; D3 kind
priority frontmatter_declared > dictionary_exact > rule_weight >
model_probability > unavailable; chosen_priority is an immutable Mapping keyed
by the frozen occurrence identity whose value is the winner's confidence_kind
STRING directly (Mapping[OccurrenceKey, ConfidenceKind], never a nested
record); same-kind ties reuse the merger structural fingerprint (merge_mentions
is the oracle, never confidence magnitude); D1 attach via exact case-sensitive
canonical_name + entity_type OR exact case-sensitive alias to a matching-type
entity (matched against mention_text, never canonical_label); competition/type-
mismatch/case-only/unknown-target stay pending; shuffled input is byte-
identical; pure (no DB/network/model/LLM, never creates entities); malformed
records fail closed with ResolutionInputError; entities/aliases are sequences
of mappings. RED: imports the missing resolution module directly so collection
genuinely fails (ModuleNotFoundError) until resolution.py exists.
"""

from __future__ import annotations

import ast
import inspect
import random
import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from typing import Any
from uuid import UUID

import pytest

from llamaindex_runtime.entity.contracts import MentionCandidate, canonical_json
from llamaindex_runtime.entity.merger import _PRIORITY, merge_mentions
from llamaindex_runtime.entity.resolution import (
    PRIORITY_ORDER,
    ResolutionDecision,
    ResolutionInputError,
    ResolutionResult,
    resolve_candidates,
)
import llamaindex_runtime.entity.resolution as resolution_module

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_SPAN_ID_B = str(UUID(int=4))
_ENTITY_ID_1 = str(UUID(int=5))
_ENTITY_ID_2 = str(UUID(int=6))
_ENTITY_ID_3 = str(UUID(int=7))
_NORMALIZED = "猫猫今天开会议程很紧张"

_FORBIDDEN_IMPORT_MARKERS = (
    "modelscope",
    "torch",
    "jieba",
    "psycopg",
    "sqlite",
    "postgres",
    "urllib",
    "requests",
    "http",
    "socket",
    "openai",
    "anthropic",
    "raner_adapter",
    "offline_mirror",
    "registry",
    "llm",
)


def _mention(**overrides: object) -> MentionCandidate:
    """Model-provenance base; byte-identical to the merger test base so the
    pinned same-kind structural fingerprint directions are reproducible."""
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


def _model(**overrides: object) -> MentionCandidate:
    return _mention(**overrides)


def _dictionary(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "confidence_kind": "dictionary_exact",
        "confidence": 1.0,
        "source": "dictionary",
        "extractor_id": "supplementary",
        "model_id": None,
        "model_revision": None,
        "artifact_digest": None,
        "runtime_compatibility_id": None,
        "schema_version": "e2b-dict-schema-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "c" * 64,
        "segment_id": None,
    }
    base.update(overrides)
    return _mention(**base)


def _frontmatter(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "confidence_kind": "frontmatter_declared",
        "confidence": 1.0,
        "source": "frontmatter",
        "extractor_id": "supplementary",
        "model_id": None,
        "model_revision": None,
        "artifact_digest": None,
        "runtime_compatibility_id": None,
        "schema_version": "e2b-fm-schema-1",
        "segmentation_version": "seg-1",
        "label_map_digest": "c" * 64,
        "segment_id": None,
    }
    base.update(overrides)
    return _mention(**base)


def _rule() -> MentionCandidate:
    return _mention(
        confidence_kind="rule_weight",
        confidence=0.5,
        source="rule",
        extractor_id="rule-supplement",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        runtime_compatibility_id=None,
    )


def _beijing_mention(canonical_label: str = "北京", **overrides: object) -> MentionCandidate:
    """A Location mention with surface text 北京 at [0,2)."""
    base: dict[str, object] = {
        "normalized_text": "北京今天开会议程很紧张",
        "char_start": 0,
        "char_end": 2,
        "mention_text": "北京",
        "raw_label": "LOC",
        "canonical_label": canonical_label,
        "entity_type": "Location",
    }
    base.update(overrides)
    return _dictionary(**base)


def _loc(char_start: int, char_end: int, mention_text: str, **overrides: object) -> MentionCandidate:
    """A dictionary-provenance Location candidate at explicit coordinates."""
    base: dict[str, object] = {
        "char_start": char_start,
        "char_end": char_end,
        "mention_text": mention_text,
        "raw_label": "LOC",
        "canonical_label": "Location",
        "entity_type": "Location",
    }
    base.update(overrides)
    return _dictionary(**base)


def _phrase(confidence: float) -> MentionCandidate:
    """The exact PHR candidate the merger test pins to opposite numeric
    directions; only the confidence value varies between the two."""
    return _model(
        confidence=confidence,
        char_start=0,
        char_end=10,
        mention_text="猫猫今天开会议程很紧",
        raw_label="PHR",
        canonical_label="Phrase",
        entity_type="Phrase",
    )


def _entity(entity_id: object = _ENTITY_ID_1, canonical_name: object = "北京", entity_type: object = "Location", **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "entity_id": entity_id,
        "canonical_name": canonical_name,
        "entity_type": entity_type,
    }
    base.update(overrides)
    return base


def _alias(alias: object = "北京", entity_id: object = _ENTITY_ID_1, source: object = "okf", **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "alias": alias,
        "entity_id": entity_id,
        "source": source,
    }
    base.update(overrides)
    return base


def _occurrence_key(candidate: MentionCandidate) -> tuple[object, ...]:
    """Frozen occurrence identity; segment_id is deliberately excluded."""
    return (
        candidate.input_kind,
        candidate.input_id,
        candidate.input_revision,
        candidate.char_start,
        candidate.char_end,
        candidate.mention_text,
    )


def _decisions(result: ResolutionResult) -> tuple[ResolutionDecision, ...]:
    return result.resolved + result.pending


def _result_canonical(result: ResolutionResult) -> str:
    def _as_json(decision: ResolutionDecision) -> dict[str, object]:
        candidate = {f.name: getattr(decision.candidate, f.name) for f in fields(decision.candidate)}
        return {"entity_id": decision.entity_id, "candidate": candidate}

    return canonical_json(
        {
            "priority_version": result.priority_version,
            "resolved": [_as_json(d) for d in result.resolved],
            "pending": [_as_json(d) for d in result.pending],
            "chosen_priority": sorted(
                (list(key), value) for key, value in result.chosen_priority.items()
            ),
        }
    )


def _structural_winner(left: MentionCandidate, right: MentionCandidate) -> MentionCandidate:
    """Frozen merger oracle: D3 priority + SHA-256 structural fingerprint +
    canonical payload, never a numeric confidence magnitude."""
    merged = merge_mentions([left, right], merger_version="v1")
    assert len(merged.selected) == 1
    return merged.selected[0]


def _module_imported_names(module: Any) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_resolution_public_api_exported_from_entity_facade() -> None:
    import llamaindex_runtime.entity as entity

    assert entity.resolve_candidates is resolve_candidates
    assert entity.ResolutionDecision is ResolutionDecision
    assert entity.ResolutionResult is ResolutionResult
    assert entity.PRIORITY_ORDER is PRIORITY_ORDER


def test_public_priority_order_is_frozen_exact_tuple_matching_merger() -> None:
    assert PRIORITY_ORDER == (
        "frontmatter_declared", "dictionary_exact", "rule_weight",
        "model_probability", "unavailable",
    )
    ranks = [_PRIORITY[kind] for kind in PRIORITY_ORDER]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)


def test_resolve_candidates_signature_requires_keyword_only_inputs() -> None:
    parameters = inspect.signature(resolve_candidates).parameters
    assert list(parameters)[0] == "candidates"
    for name in ("entities", "aliases", "priority_version"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["priority_version"].default is inspect.Parameter.empty


@pytest.mark.parametrize("bad", ["", None, 3, 3.5, True, ["v1"], b"v1"])
def test_resolve_candidates_rejects_invalid_priority_version(bad: object) -> None:
    with pytest.raises(ValueError, match="priority_version"):
        resolve_candidates([], entities=[], aliases=[], priority_version=bad)  # type: ignore[arg-type]


def test_resolution_dtos_are_frozen_with_exact_field_names() -> None:
    assert {name.name for name in fields(ResolutionDecision)} == {"candidate", "entity_id"}
    assert {name.name for name in fields(ResolutionResult)} == {
        "priority_version", "resolved", "pending", "chosen_priority",
    }
    decision = ResolutionDecision(candidate=_dictionary(), entity_id=None)
    with pytest.raises(FrozenInstanceError):
        decision.entity_id = _ENTITY_ID_1  # type: ignore[misc]
    # Direct DTO construction must accept a Mapping for chosen_priority.
    result = ResolutionResult(
        priority_version="v1", resolved=(decision,), pending=(), chosen_priority={}
    )
    with pytest.raises(FrozenInstanceError):
        result.priority_version = "v2"  # type: ignore[misc]
    # resolve emits only (candidate, entity_id) decisions; no entity/alias creation.
    resolved = resolve_candidates(
        [_dictionary()], entities=[_entity()], aliases=[_alias()], priority_version="v1"
    )
    assert isinstance(resolved.resolved, tuple)
    assert isinstance(resolved.pending, tuple)
    assert isinstance(resolved.chosen_priority, Mapping)
    for resolved_decision in resolved.resolved + resolved.pending:
        assert {name.name for name in fields(resolved_decision)} == {"candidate", "entity_id"}


def test_resolution_result_shapes_tuples_and_records_priority_version() -> None:
    result = resolve_candidates(
        [_dictionary()], entities=[], aliases=[], priority_version="e2b-resolve-v1"
    )
    assert isinstance(result.resolved, tuple)
    assert isinstance(result.pending, tuple)
    assert result.priority_version == "e2b-resolve-v1"
    assert isinstance(result.chosen_priority, Mapping)
    for decision in result.resolved + result.pending:
        assert isinstance(decision, ResolutionDecision)


def test_resolution_forbids_mention_id_and_alias_helpers_but_requires_chosen_priority() -> None:
    # mention_id belongs to 16-09 materialization; chosen_priority IS required.
    result = resolve_candidates([], entities=[], aliases=[], priority_version="v1")
    assert isinstance(result.chosen_priority, Mapping)
    for name in ("mention_id", "alias_map", "entities", "aliases"):
        assert not hasattr(result, name)
        assert not hasattr(ResolutionResult, name)
        assert not hasattr(ResolutionDecision, name)


def test_chosen_priority_records_winner_confidence_kind_per_selected_occurrence() -> None:
    candidates = [
        _frontmatter(),  # occurrence 1 winner
        _dictionary(),  # same occurrence 1
        _loc(9, 11, "紧张"),  # occurrence 2 winner
    ]
    result = resolve_candidates(candidates, entities=[], aliases=[], priority_version="v1")
    decisions = _decisions(result)
    assert len(decisions) == 2
    assert len(result.chosen_priority) == len(decisions)  # one entry per occurrence
    for decision in decisions:
        key = _occurrence_key(decision.candidate)
        assert key in result.chosen_priority
        # value is the winner confidence_kind STRING directly, not a Mapping.
        assert isinstance(result.chosen_priority[key], str)
        assert result.chosen_priority[key] == decision.candidate.confidence_kind
    assert set(result.chosen_priority.values()) == {
        "frontmatter_declared",
        "dictionary_exact",
    }


def test_chosen_priority_is_immutable_mapping_with_no_mutable_backing() -> None:
    result = resolve_candidates([_frontmatter(), _dictionary()], entities=[], aliases=[], priority_version="v1")
    assert isinstance(result.chosen_priority, Mapping)
    key = _occurrence_key(result.pending[0].candidate)
    assert key in result.chosen_priority
    with pytest.raises(TypeError):
        result.chosen_priority[key] = "model_probability"  # type: ignore[index]


def test_one_decision_per_occurrence_across_sources_and_segments() -> None:
    # segment_id is provenance only; the three sources form ONE occurrence and
    # the chosen_priority key is the segment-free occurrence identity.
    candidates = [_model(segment_id="seg-1"), _dictionary(segment_id=None), _frontmatter(segment_id=None)]
    result = resolve_candidates(candidates, entities=[], aliases=[], priority_version="v1")
    decisions = _decisions(result)
    assert len(decisions) == 1
    assert decisions[0].candidate.source == "frontmatter"
    assert _occurrence_key(decisions[0].candidate) in result.chosen_priority
    assert len(result.chosen_priority) == 1


def test_distinct_occurrences_get_separate_decisions() -> None:
    candidates = [
        _dictionary(),  # [0,2)
        _loc(2, 4, "今天"),
        _loc(9, 11, "紧张"),
    ]
    result = resolve_candidates(candidates, entities=[], aliases=[], priority_version="v1")
    assert len(_decisions(result)) == 3


def test_different_input_identity_is_a_different_occurrence() -> None:
    other_span = _dictionary(input_id=_SPAN_ID_B, span_id=_SPAN_ID_B)
    other_revision = _dictionary(input_revision="abc-v3", document_revision="abc-v3")
    result = resolve_candidates(
        [_dictionary(), other_span, other_revision], entities=[], aliases=[], priority_version="v1"
    )
    assert len(_decisions(result)) == 3


@pytest.mark.parametrize(
    "winner,loser",
    [
        (_frontmatter(), _dictionary()),
        (_dictionary(), _model()),
        (_rule(), _model()),
        (_model(), _model(confidence=None, confidence_kind="unavailable")),
    ],
)
def test_higher_d3_kind_wins(winner: MentionCandidate, loser: MentionCandidate) -> None:
    result = resolve_candidates([loser, winner], entities=[], aliases=[], priority_version="v1")
    decisions = _decisions(result)
    assert len(decisions) == 1
    assert decisions[0].candidate == winner
    assert result.chosen_priority[_occurrence_key(winner)] == winner.confidence_kind


def test_unavailable_never_dropped_merely_for_being_unavailable() -> None:
    low = _model(confidence=None, confidence_kind="unavailable")
    other = _loc(9, 11, "紧张")
    result = resolve_candidates([low, other], entities=[], aliases=[], priority_version="v1")
    decisions = _decisions(result)
    assert len(decisions) == 2
    assert {decision.candidate.confidence_kind for decision in decisions} == {
        "unavailable",
        "dictionary_exact",
    }


def test_unavailable_loses_only_on_actual_occurrence_conflict() -> None:
    result = resolve_candidates(
        [_model(confidence=None, confidence_kind="unavailable"), _dictionary()],
        entities=[],
        aliases=[],
        priority_version="v1",
    )
    decisions = _decisions(result)
    assert len(decisions) == 1
    assert decisions[0].candidate.source == "dictionary"


def test_same_kind_winner_is_not_confidence_magnitude() -> None:
    # Reuses the exact data the merger test pins to opposite numeric directions:
    # (0.1, 0.2) -> 0.2 wins and (0.1, 0.5) -> 0.1 wins. Any always-higher or
    # always-lower numeric comparator fails one pair; only the structural rank
    # passes both, so resolution must follow it.
    winners: list[float] = []
    for low_conf, high_conf in [(0.1, 0.2), (0.1, 0.5)]:
        lo, hi = _phrase(low_conf), _phrase(high_conf)
        expected = _structural_winner(lo, hi)
        assert expected.confidence in (low_conf, high_conf)
        result = resolve_candidates([lo, hi], entities=[], aliases=[], priority_version="v1")
        decisions = _decisions(result)
        assert len(decisions) == 1
        assert decisions[0].candidate == expected
        winners.append(expected.confidence)  # type: ignore[arg-type]
    assert winners[0] != winners[1]


def test_no_match_stays_pending_with_entity_id_none() -> None:
    result = resolve_candidates(
        [_dictionary()], entities=[_entity()], aliases=[], priority_version="v1"
    )
    assert result.resolved == ()
    assert len(result.pending) == 1
    assert result.pending[0].entity_id is None


def test_exact_canonical_name_and_type_attach() -> None:
    candidate = _beijing_mention()
    result = resolve_candidates(
        [candidate],
        entities=[_entity(entity_id=_ENTITY_ID_1, canonical_name="北京", entity_type="Location")],
        aliases=[],
        priority_version="v1",
    )
    assert len(result.resolved) == 1
    assert result.pending == ()
    assert result.resolved[0].entity_id == _ENTITY_ID_1
    assert result.resolved[0].candidate is candidate


@pytest.mark.parametrize(
    "entity",
    [
        _entity(entity_id=_ENTITY_ID_1, canonical_name="北京", entity_type="Organization"),  # type mismatch
        _entity(entity_id=_ENTITY_ID_1, canonical_name="beijing", entity_type="Location"),  # case-normalized only
    ],
)
def test_canonical_non_compatible_match_stays_pending(entity: dict[str, object]) -> None:
    result = resolve_candidates(
        [_beijing_mention()], entities=[entity], aliases=[], priority_version="v1"
    )
    assert result.resolved == ()
    assert result.pending[0].entity_id is None


def test_exact_alias_match_attaches_regardless_of_authority() -> None:
    candidate = _beijing_mention(canonical_label="首都")
    entities = [_entity(entity_id=_ENTITY_ID_1, canonical_name="Beijing", entity_type="Location")]
    for source in ("okf", "dictionary"):
        result = resolve_candidates(
            [candidate],
            entities=entities,
            aliases=[_alias(alias="北京", entity_id=_ENTITY_ID_1, source=source)],
            priority_version="v1",
        )
        assert len(result.resolved) == 1, f"source={source} must attach"
        assert result.resolved[0].entity_id == _ENTITY_ID_1


@pytest.mark.parametrize(
    "alias,entity",
    [
        (_alias(alias="beijing", entity_id=_ENTITY_ID_1, source="okf"),  # case-sensitive
         _entity(entity_id=_ENTITY_ID_1, canonical_name="Beijing", entity_type="Location")),
        (_alias(alias="北京", entity_id=_ENTITY_ID_1, source="okf"),  # referenced type mismatch
         _entity(entity_id=_ENTITY_ID_1, canonical_name="Beijing", entity_type="Organization")),
    ],
)
def test_alias_non_compatible_match_stays_pending(
    alias: dict[str, object], entity: dict[str, object]
) -> None:
    candidate = _beijing_mention(canonical_label="首都")
    result = resolve_candidates([candidate], entities=[entity], aliases=[alias], priority_version="v1")
    assert result.resolved == ()
    assert result.pending[0].entity_id is None


def test_alias_match_is_against_mention_text_not_canonical_label() -> None:
    # alias "首都" equals the candidate's canonical_label but not its surface
    # mention_text "北京"; alias matching is surface-to-surface, so no attach.
    candidate = _beijing_mention(canonical_label="首都")
    entities = [_entity(entity_id=_ENTITY_ID_1, canonical_name="Beijing", entity_type="Location")]
    result = resolve_candidates(
        [candidate],
        entities=entities,
        aliases=[_alias(alias="首都", entity_id=_ENTITY_ID_1, source="okf")],
        priority_version="v1",
    )
    assert result.resolved == ()
    assert result.pending[0].entity_id is None


def test_duplicate_alias_records_to_same_entity_remain_attachable() -> None:
    candidate = _beijing_mention(canonical_label="首都")
    entities = [_entity(entity_id=_ENTITY_ID_1, canonical_name="Beijing", entity_type="Location")]
    aliases = [
        _alias(alias="北京", entity_id=_ENTITY_ID_1, source="okf"),
        _alias(alias="北京", entity_id=_ENTITY_ID_1, source="dictionary"),
        _alias(alias="北京", entity_id=_ENTITY_ID_1, source="okf"),
    ]
    result = resolve_candidates([candidate], entities=entities, aliases=aliases, priority_version="v1")
    assert len(result.resolved) == 1
    assert result.resolved[0].entity_id == _ENTITY_ID_1


@pytest.mark.parametrize(
    "entities,aliases",
    [
        (  # competing alias targets (both compatible)
            [_entity(_ENTITY_ID_1, "Beijing", "Location"), _entity(_ENTITY_ID_2, "Peking", "Location")],
            [_alias("北京", _ENTITY_ID_1, "okf"), _alias("北京", _ENTITY_ID_2, "dictionary")],
        ),
        (  # competing canonical targets
            [_entity(_ENTITY_ID_1, "北京", "Location"), _entity(_ENTITY_ID_2, "北京", "Location")],
            [],
        ),
        (  # canonical-vs-alias target conflict
            [_entity(_ENTITY_ID_1, "北京", "Location"), _entity(_ENTITY_ID_2, "Beijing", "Location")],
            [_alias("北京", _ENTITY_ID_2, "okf")],
        ),
    ],
)
def test_competing_targets_fail_closed_to_pending(
    entities: list[dict[str, object]], aliases: list[dict[str, object]]
) -> None:
    candidate = _beijing_mention()
    result = resolve_candidates([candidate], entities=entities, aliases=aliases, priority_version="v1")
    assert result.resolved == ()
    assert len(result.pending) == 1
    assert result.pending[0].entity_id is None


def test_canonical_and_alias_matching_same_entity_attach() -> None:
    candidate = _beijing_mention()
    entities = [_entity(entity_id=_ENTITY_ID_1, canonical_name="北京", entity_type="Location")]
    aliases = [_alias(alias="北京", entity_id=_ENTITY_ID_1, source="okf")]
    result = resolve_candidates([candidate], entities=entities, aliases=aliases, priority_version="v1")
    assert len(result.resolved) == 1
    assert result.resolved[0].entity_id == _ENTITY_ID_1


def test_alias_referencing_unknown_entity_stays_pending() -> None:
    candidate = _beijing_mention(canonical_label="首都")
    result = resolve_candidates(
        [candidate],
        entities=[],
        aliases=[_alias(alias="北京", entity_id=_ENTITY_ID_3, source="okf")],
        priority_version="v1",
    )
    assert result.resolved == ()
    assert len(result.pending) == 1
    assert result.pending[0].entity_id is None


def test_resolve_candidates_does_not_mutate_inputs() -> None:
    candidate = _dictionary()
    entity = _entity()
    alias = _alias()
    candidates = [candidate]
    entities = [entity]
    aliases = [alias]
    resolve_candidates(candidates, entities=entities, aliases=aliases, priority_version="v1")
    assert candidates == [candidate]
    assert entities == [entity]
    assert aliases == [alias]


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
    "execute",
)


def test_resolution_result_exposes_no_durable_write_surface() -> None:
    result = resolve_candidates([_dictionary()], entities=[], aliases=[], priority_version="v1")
    for name in _NO_PERSISTENCE_NAMES:
        assert not hasattr(result, name)
    for cls in (ResolutionResult, ResolutionDecision):
        for name in _NO_PERSISTENCE_NAMES:
            assert not hasattr(cls, name)


def test_resolution_output_is_byte_identical_under_shuffle() -> None:
    candidates = [
        _frontmatter(),  # [0,2) Person
        _dictionary(),  # [0,2) Person, same occurrence
        _model(),  # [0,2) Person, same occurrence
        _loc(2, 4, "今天"),
        _loc(9, 11, "紧张"),
    ]
    entities = [
        _entity(entity_id=_ENTITY_ID_1, canonical_name="猫猫", entity_type="Person"),
        _entity(entity_id=_ENTITY_ID_2, canonical_name="Beijing", entity_type="Location"),
    ]
    aliases = [
        _alias(alias="猫猫", entity_id=_ENTITY_ID_1, source="okf"),
        _alias(alias="北京", entity_id=_ENTITY_ID_2, source="dictionary"),
    ]
    base = _result_canonical(
        resolve_candidates(candidates, entities=entities, aliases=aliases, priority_version="e2b-resolve-v1")
    )
    for seed in range(5):
        shuffled_candidates = list(candidates)
        shuffled_entities = list(entities)
        shuffled_aliases = list(aliases)
        random.Random(seed).shuffle(shuffled_candidates)
        random.Random(seed + 1000).shuffle(shuffled_entities)
        random.Random(seed + 2000).shuffle(shuffled_aliases)
        result = resolve_candidates(
            shuffled_candidates,
            entities=shuffled_entities,
            aliases=shuffled_aliases,
            priority_version="e2b-resolve-v1",
        )
        assert _result_canonical(result) == base


@pytest.mark.parametrize("bad", [["not-a-candidate"], [123], [None]])
def test_resolve_candidates_rejects_non_candidate_entries(bad: list[object]) -> None:
    with pytest.raises(ValueError, match="MentionCandidate"):
        resolve_candidates(
            bad, entities=[], aliases=[], priority_version="v1"  # type: ignore[list-item]
        )


@pytest.mark.parametrize(
    "entity",
    [
        {},  # missing all keys
        {"entity_id": _ENTITY_ID_1, "canonical_name": "北京"},  # missing entity_type
        {"canonical_name": "北京", "entity_type": "Location"},  # missing entity_id
        {"entity_id": "", "canonical_name": "北京", "entity_type": "Location"},
        {"entity_id": _ENTITY_ID_1, "canonical_name": "", "entity_type": "Location"},
        {"entity_id": _ENTITY_ID_1, "canonical_name": "北京", "entity_type": ""},
        {"entity_id": 123, "canonical_name": "北京", "entity_type": "Location"},
        "not-a-mapping",
    ],
)
def test_malformed_entity_records_fail_closed(entity: object) -> None:
    with pytest.raises(ResolutionInputError):
        resolve_candidates(
            [_dictionary()],
            entities=[entity],  # type: ignore[list-item]
            aliases=[],
            priority_version="v1",
        )


@pytest.mark.parametrize(
    "alias",
    [
        {},  # missing all keys
        {"alias": "北京", "entity_id": _ENTITY_ID_1},  # missing source
        {"entity_id": _ENTITY_ID_1, "source": "okf"},  # missing alias
        {"alias": "", "entity_id": _ENTITY_ID_1, "source": "okf"},
        {"alias": "北京", "entity_id": "", "source": "okf"},
        {"alias": "北京", "entity_id": _ENTITY_ID_1, "source": "invented"},
        {"alias": 7, "entity_id": _ENTITY_ID_1, "source": "okf"},
        "not-a-mapping",
    ],
)
def test_malformed_alias_records_fail_closed(alias: object) -> None:
    with pytest.raises(ResolutionInputError):
        resolve_candidates(
            [_dictionary()],
            entities=[],
            aliases=[alias],  # type: ignore[list-item]
            priority_version="v1",
        )


@pytest.mark.parametrize(
    "entities,aliases",
    [
        ("not-a-sequence", []),
        ({"k": _entity()}, []),
        (7, []),
        (None, []),
        ([], "not-a-sequence"),
        ([], {"北京": _entity()}),  # Mapping[str, one record] is rejected
        ([], 7),
        ([], None),
    ],
)
def test_entities_and_aliases_accept_only_sequences_of_mappings(entities: object, aliases: object) -> None:
    with pytest.raises(ResolutionInputError):
        resolve_candidates(
            [_dictionary()],
            entities=entities,  # type: ignore[arg-type]
            aliases=aliases,  # type: ignore[arg-type]
            priority_version="v1",
        )


def test_resolution_module_import_boundary() -> None:
    for name in _module_imported_names(resolution_module):
        assert not any(marker in name for marker in _FORBIDDEN_IMPORT_MARKERS), (
            f"resolution.py must not import {name!r}"
        )
    for heavy in ("modelscope", "torch", "jieba"):
        assert heavy not in sys.modules, f"resolution must not import {heavy}"


def test_resolution_module_has_no_sql_dml_or_generative_llm_calls() -> None:
    tree = ast.parse(inspect.getsource(resolution_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in (
                "execute",
                "executemany",
                "commit",
                "rollback",
                "complete",
                "acomplete",
            ), f"resolution.py must not call {node.func.attr}"
