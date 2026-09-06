"""RED contract tests for the E2b raw-corpus entity layer (Phase 16-02).

Pins the frozen pure contract layer only:
- the discriminated ``CorpusSpanInput | QueryTextInput`` union,
- the immutable full-provenance ``MentionCandidate``,
- exact Unicode code-point half-open slice invariants,
- field-VALUE revision equality (never the literal strings
  "document_revision" / "query_revision"),
- E2b-namespace-scoped deterministic identity helpers,
- the zero heavy-import boundary (no modelscope/torch/jieba).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import get_args
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from llamaindex_runtime.entity.contracts import (
    CONFIDENCE_KINDS,
    E2B_NAMESPACE,
    MENTION_SOURCES,
    CorpusSpanInput,
    ExtractionInput,
    MentionCandidate,
    QueryTextInput,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)

_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ID = str(UUID(int=3))
_QUERY_ID = str(UUID(int=10))
_CORPUS_NORMALIZED = "猫猫今天开会"
_QUERY_NORMALIZED = "猫猫是什么"


def _corpus_input(**overrides: object) -> CorpusSpanInput:
    base: dict[str, object] = {
        "document_id": _DOCUMENT_ID,
        "version_id": _VERSION_ID,
        "span_id": _SPAN_ID,
        "document_revision": "abc-v2",
        "input_revision": "abc-v2",
        "normalized_text": _CORPUS_NORMALIZED,
        "normalization_version": "norm-1",
        "projection": {"document_char_start": 0, "document_char_end": 2},
    }
    base.update(overrides)
    return CorpusSpanInput(**base)  # type: ignore[arg-type]


def _query_input(**overrides: object) -> QueryTextInput:
    base: dict[str, object] = {
        "query_id": _QUERY_ID,
        "query_revision": "query-v7",
        "input_revision": "query-v7",
        "normalized_text": _QUERY_NORMALIZED,
        "normalization_version": "norm-1",
    }
    base.update(overrides)
    return QueryTextInput(**base)  # type: ignore[arg-type]


def _mention(**overrides: object) -> MentionCandidate:
    base: dict[str, object] = {
        "input_id": _SPAN_ID,
        "input_kind": "corpus_span",
        "input_revision": "abc-v2",
        "normalized_text": _CORPUS_NORMALIZED,
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
        "model_id": "iic/nlp_raner_named-entity-recognition_chinese-large-generic",
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


# ---------------------------------------------------------------------------
# E2b namespace and canonical helpers
# ---------------------------------------------------------------------------


def test_e2b_namespace_is_derived_and_distinct_from_e2a() -> None:
    expected = uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2b")
    assert E2B_NAMESPACE == expected
    assert isinstance(E2B_NAMESPACE, UUID)
    assert E2B_NAMESPACE != uuid5(NAMESPACE_URL, "https://gitnexus.local/okf/e2a")


def test_canonical_json_sha256_is_deterministic_for_equal_inputs() -> None:
    left = {"b": ["猫", 2], "a": {"z": True}}
    right = {"a": {"z": True}, "b": ["猫", 2]}

    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":{"z":true},"b":["猫",2]}'
    assert canonical_json_sha256(left) == canonical_json_sha256(right)


def test_canonical_helpers_are_reused_from_e2a_not_copied() -> None:
    from llamaindex_runtime.okf import e2a_contracts

    assert canonical_json is e2a_contracts.canonical_json
    assert canonical_json_sha256 is e2a_contracts.canonical_json_sha256


def test_deterministic_id_is_stable_and_namespace_scoped() -> None:
    natural_key = canonical_json({"document_revision": "abc-v2", "span_id": _SPAN_ID})
    first = deterministic_id("entity_mention", natural_key)
    second = deterministic_id("entity_mention", natural_key)

    assert first == second
    assert isinstance(UUID(first), UUID)
    assert deterministic_id("entity_mention", natural_key) != deterministic_id(
        "mention", natural_key
    )
    # E2b identity must differ from the E2a identity for the same kind/key.
    from llamaindex_runtime.okf.e2a_contracts import (
        deterministic_id as e2a_deterministic_id,
    )

    assert first != e2a_deterministic_id("entity_mention", natural_key)
    with pytest.raises(ValueError, match="deterministic identity"):
        deterministic_id("", natural_key)
    with pytest.raises(ValueError, match="deterministic identity"):
        deterministic_id("entity_mention", "")


# ---------------------------------------------------------------------------
# Discriminated CorpusSpanInput | QueryTextInput union
# ---------------------------------------------------------------------------


def test_extraction_input_union_contains_both_immutable_members() -> None:
    members = get_args(ExtractionInput)
    assert set(members) == {CorpusSpanInput, QueryTextInput}
    for member in members:
        assert member.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_union_members_share_discriminated_input_shape() -> None:
    corpus = _corpus_input()
    query = _query_input()

    for value in (corpus, query):
        assert value.input_id
        assert value.input_kind in ("corpus_span", "query_text")
        assert value.input_revision
        assert value.normalized_text
    assert corpus.input_kind != query.input_kind


def test_corpus_span_input_requires_projection_and_field_value_revision() -> None:
    value = _corpus_input()

    assert value.input_id == value.span_id
    assert value.input_kind == "corpus_span"
    assert value.input_revision == "abc-v2"
    assert value.input_revision == value.document_revision
    assert isinstance(value.projection, Mapping)
    assert value.projection["document_char_start"] == 0  # type: ignore[index]
    with pytest.raises(TypeError):
        value.projection["document_char_start"] = 99  # type: ignore[index]


def test_corpus_span_input_rejects_hard_coded_revision_literal() -> None:
    # document_revision is "abc-v2", so input_revision must be "abc-v2",
    # never the constant string "document_revision".
    assert _corpus_input(input_revision="abc-v2").input_revision == "abc-v2"
    with pytest.raises(ValueError, match="input_revision"):
        _corpus_input(input_revision="document_revision")
    with pytest.raises(ValueError, match="input_revision"):
        _corpus_input(document_revision="abc-v2", input_revision="other-v1")


def test_corpus_span_input_requires_document_and_sidecar_projection() -> None:
    with pytest.raises(ValueError, match="projection"):
        _corpus_input(projection=None)


def test_corpus_span_input_validates_corpus_identifiers() -> None:
    with pytest.raises(ValueError, match="document_id"):
        _corpus_input(document_id="not-a-uuid")
    with pytest.raises(ValueError, match="span_id"):
        _corpus_input(span_id="not-a-uuid")
    with pytest.raises(ValueError, match="normalized_text"):
        _corpus_input(normalized_text="")


def test_query_text_input_is_immutable_and_has_no_corpus_projection() -> None:
    value = _query_input()

    assert value.input_id == value.query_id
    assert value.input_kind == "query_text"
    assert value.input_revision == value.query_revision == "query-v7"
    # QueryTextInput never carries corpus document/sidecar projection.
    for forbidden in (
        "projection",
        "document_id",
        "version_id",
        "document_revision",
        "span_id",
    ):
        assert not hasattr(value, forbidden)
    with pytest.raises(FrozenInstanceError):
        value.normalized_text = "changed"  # type: ignore[misc]


def test_query_text_input_rejects_hard_coded_revision_literal() -> None:
    assert _query_input(input_revision="query-v7").input_revision == "query-v7"
    with pytest.raises(ValueError, match="input_revision"):
        _query_input(input_revision="query_revision")
    with pytest.raises(ValueError, match="input_revision"):
        _query_input(query_revision="query-v7", input_revision="other-v1")


def test_query_text_input_validates_query_identifier() -> None:
    with pytest.raises(ValueError, match="query_id"):
        _query_input(query_id="not-a-uuid")
    with pytest.raises(ValueError, match="normalized_text"):
        _query_input(normalized_text="")


# ---------------------------------------------------------------------------
# MentionCandidate provenance, immutability, and offset invariants
# ---------------------------------------------------------------------------


def test_mention_candidate_is_frozen_with_full_provenance() -> None:
    mention = _mention()

    assert mention.input_kind == "corpus_span"
    assert mention.input_id == _SPAN_ID
    assert mention.mention_text == "猫猫"
    assert mention.source == "model"
    assert mention.confidence_kind == "model_probability"
    assert mention.artifact_digest == "a" * 64
    assert mention.label_map_digest == "b" * 64
    assert mention.runtime_compatibility_id == "tuple-1"
    with pytest.raises(FrozenInstanceError):
        mention.mention_text = "other"  # type: ignore[misc]


def test_mention_always_mandatory_provenance_fields_are_required() -> None:
    mention = _mention()
    for name in (
        "extractor_id",
        "extractor_version",
        "schema_version",
        "normalization_version",
        "segmentation_version",
        "label_map_digest",
        "source",
        "confidence_kind",
        "raw_label",
        "canonical_label",
        "entity_type",
    ):
        assert getattr(mention, name), name
    with pytest.raises(ValueError, match="extractor_id"):
        _mention(extractor_id="")
    with pytest.raises(ValueError, match="label_map_digest"):
        _mention(label_map_digest="not-a-digest")


def test_mention_confidence_ladder_and_sources_are_pinned() -> None:
    assert CONFIDENCE_KINDS == frozenset(
        {
            "frontmatter_declared",
            "dictionary_exact",
            "rule_weight",
            "model_probability",
            "unavailable",
        }
    )
    assert MENTION_SOURCES == frozenset({"model", "dictionary", "rule", "frontmatter"})


def test_mention_valid_slice_back_succeeds() -> None:
    mention = _mention()
    assert 0 <= mention.char_start < mention.char_end <= len(mention.normalized_text)
    assert mention.normalized_text[mention.char_start : mention.char_end] == mention.mention_text


@pytest.mark.parametrize(
    "overrides",
    [
        {"char_start": 2, "char_end": 1},  # start > end
        {"char_start": 1, "char_end": 1},  # start == end (empty span)
        {"char_start": -1, "char_end": 2},  # negative start
        {"char_start": 0, "char_end": 7},  # end > len(normalized_text)
        {"char_start": 0, "char_end": 2, "mention_text": "狗狗"},  # no slice-back
    ],
)
def test_mention_candidate_rejects_invalid_offsets(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _mention(**overrides)


def test_mention_offsets_are_unicode_code_points_not_bytes() -> None:
    astral = "😀猫😀"  # astral-plane emoji is one code point
    assert len(astral) == 3
    mention = _mention(
        normalized_text=astral,
        char_start=0,
        char_end=2,
        mention_text="😀猫",
    )
    assert mention.normalized_text[mention.char_start : mention.char_end] == "😀猫"

    combining = "é猫"  # e + combining acute accent = two code points
    assert len(combining) == 3
    mention = _mention(
        normalized_text=combining,
        char_start=0,
        char_end=2,
        mention_text="é",
    )
    assert mention.normalized_text[mention.char_start : mention.char_end] == "é"


def test_mention_offsets_handle_full_width_and_repeated_entities() -> None:
    text = "，猫猫，猫"  # full-width punctuation plus repeated entity text
    mention = _mention(
        normalized_text=text,
        char_start=1,
        char_end=3,
        mention_text="猫猫",
    )
    assert mention.normalized_text[1:3] == "猫猫"
    repeated = _mention(
        normalized_text=text,
        char_start=4,
        char_end=5,
        mention_text="猫",
    )
    assert repeated.normalized_text[4:5] == "猫"


def test_mention_confidence_none_only_when_unavailable() -> None:
    mention = _mention(confidence=None, confidence_kind="unavailable")
    assert mention.confidence is None
    with pytest.raises(ValueError, match="unavailable"):
        _mention(confidence=None, confidence_kind="model_probability")
    with pytest.raises(ValueError, match="unavailable"):
        _mention(confidence=0.5, confidence_kind="unavailable")
    with pytest.raises(ValueError, match="confidence_kind"):
        _mention(confidence=0.5, confidence_kind="invented")
    with pytest.raises(ValueError, match="source"):
        _mention(source="invented")


@pytest.mark.parametrize("kind", sorted(CONFIDENCE_KINDS))
def test_mention_accepts_all_confidence_kinds(kind: str) -> None:
    confidence = None if kind == "unavailable" else 0.5
    mention = _mention(confidence=confidence, confidence_kind=kind)  # type: ignore[arg-type]
    assert mention.confidence_kind == kind


def test_corpus_mention_requires_span_and_projection() -> None:
    with pytest.raises(ValueError, match="span_id"):
        _mention(span_id=None)
    with pytest.raises(ValueError, match="input_id"):
        _mention(input_id=str(UUID(int=99)))
    with pytest.raises(ValueError, match="document/sidecar"):
        _mention(document_id=None)
    with pytest.raises(ValueError, match="projection"):
        _mention(projection=None)


def test_corpus_mention_input_revision_equals_document_revision_field_value() -> None:
    mention = _mention(input_revision="abc-v2", document_revision="abc-v2")
    assert mention.input_revision == mention.document_revision == "abc-v2"
    # Never the literal string "document_revision".
    with pytest.raises(ValueError, match="input_revision"):
        _mention(input_revision="document_revision", document_revision="abc-v2")
    with pytest.raises(ValueError, match="input_revision"):
        _mention(input_revision="abc-v2", document_revision="other-v9")


def test_query_mention_forbids_span_and_corpus_projection() -> None:
    mention = _mention(
        input_id=_QUERY_ID,
        input_kind="query_text",
        input_revision="query-v7",
        span_id=None,
        segment_id=None,
        document_id=None,
        version_id=None,
        document_revision=None,
        projection=None,
        normalized_text=_QUERY_NORMALIZED,
    )
    assert mention.input_kind == "query_text"
    assert mention.span_id is None
    assert mention.document_id is None
    assert mention.projection is None
    with pytest.raises(ValueError, match="query mention"):
        _mention(
            input_id=_QUERY_ID,
            input_kind="query_text",
            input_revision="query-v7",
            span_id=_SPAN_ID,
            document_id=None,
            version_id=None,
            document_revision=None,
            projection=None,
            normalized_text=_QUERY_NORMALIZED,
        )
    with pytest.raises(ValueError, match="query mention"):
        _mention(
            input_id=_QUERY_ID,
            input_kind="query_text",
            input_revision="query-v7",
            span_id=None,
            document_id=_DOCUMENT_ID,
            version_id=None,
            document_revision=None,
            projection=None,
            normalized_text=_QUERY_NORMALIZED,
        )
    with pytest.raises(ValueError, match="query mention"):
        _mention(
            input_id=_QUERY_ID,
            input_kind="query_text",
            input_revision="query-v7",
            span_id=None,
            document_id=None,
            version_id=None,
            document_revision=None,
            projection={"document_char_start": 0},
            normalized_text=_QUERY_NORMALIZED,
        )


def test_query_mention_rejects_frontmatter_source() -> None:
    # A valid supplementary candidate carries no model provenance, so the
    # frontmatter-source rejection is isolated from model-provenance checks.
    with pytest.raises(ValueError, match="frontmatter"):
        _mention(
            input_id=_QUERY_ID,
            input_kind="query_text",
            input_revision="query-v7",
            span_id=None,
            segment_id=None,
            document_id=None,
            version_id=None,
            document_revision=None,
            projection=None,
            normalized_text=_QUERY_NORMALIZED,
            source="frontmatter",
            confidence_kind="frontmatter_declared",
            confidence=1.0,
            extractor_id="supplementary",
            model_id=None,
            model_revision=None,
            artifact_digest=None,
            runtime_compatibility_id=None,
        )


def test_mention_rejects_invalid_coordinate_types() -> None:
    with pytest.raises(ValueError, match="integers"):
        _mention(char_start="0", char_end=2)
    with pytest.raises(ValueError, match="integers"):
        _mention(char_start=0, char_end=2.0)


def test_mention_rejects_non_finite_or_non_float_confidence() -> None:
    with pytest.raises(ValueError, match="finite float"):
        _mention(confidence=1)
    with pytest.raises(ValueError, match="finite float"):
        _mention(confidence=float("nan"))
    with pytest.raises(ValueError, match="finite float"):
        _mention(confidence=float("inf"))


def test_mention_rejects_unknown_input_kind() -> None:
    with pytest.raises(ValueError, match="input_kind"):
        _mention(input_kind="invented")


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("dictionary", "dictionary_exact"),
        ("rule", "rule_weight"),
        ("frontmatter", "frontmatter_declared"),
    ],
)
def test_supplementary_candidates_allow_nullable_model_provenance(
    source: str, kind: str
) -> None:
    # 16-08: dictionary/frontmatter/rule supplements emit candidates with
    # extractor_id="supplementary" and model_id=None.
    candidate = _mention(
        source=source,  # type: ignore[arg-type]
        confidence_kind=kind,  # type: ignore[arg-type]
        confidence=1.0,
        extractor_id="supplementary",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        runtime_compatibility_id=None,
    )
    assert candidate.model_id is None
    assert candidate.model_revision is None
    assert candidate.artifact_digest is None
    assert candidate.runtime_compatibility_id is None
    assert candidate.source == source
    assert candidate.extractor_id == "supplementary"


def test_model_candidate_allows_unresolved_runtime_compatibility_before_smoke() -> None:
    # 16-07/D8: runtime compatibility is unresolved (None) until a
    # separately-authorized mirror smoke freezes it.
    candidate = _mention(runtime_compatibility_id=None)
    assert candidate.runtime_compatibility_id is None
    assert candidate.model_id == "iic/nlp_raner_named-entity-recognition_chinese-large-generic"
    assert candidate.model_revision == "4d15e5b"
    assert candidate.artifact_digest == "a" * 64


def test_model_candidate_requires_complete_model_provenance() -> None:
    with pytest.raises(ValueError, match="model provenance"):
        _mention(model_id=None)
    with pytest.raises(ValueError, match="model provenance"):
        _mention(model_revision=None)
    with pytest.raises(ValueError, match="model provenance"):
        _mention(artifact_digest=None)


def test_model_candidate_rejects_malformed_model_provenance() -> None:
    with pytest.raises(ValueError, match="model_id"):
        _mention(model_id="")
    with pytest.raises(ValueError, match="model_revision"):
        _mention(model_revision="")
    with pytest.raises(ValueError, match="artifact_digest"):
        _mention(artifact_digest="not-a-digest")
    with pytest.raises(ValueError, match="runtime_compatibility_id"):
        _mention(runtime_compatibility_id="")


def test_non_model_candidate_rejects_model_provenance() -> None:
    # Partial/forged model provenance on a supplementary candidate is rejected:
    # model provenance is all-or-nothing and never attributed to non-model sources.
    with pytest.raises(ValueError, match="model provenance"):
        _mention(
            source="dictionary",  # type: ignore[arg-type]
            confidence_kind="dictionary_exact",  # type: ignore[arg-type]
            confidence=1.0,
            extractor_id="supplementary",
            model_id="some-model",
            model_revision=None,
            artifact_digest=None,
            runtime_compatibility_id=None,
        )
    with pytest.raises(ValueError, match="model provenance"):
        _mention(
            source="dictionary",  # type: ignore[arg-type]
            confidence_kind="dictionary_exact",  # type: ignore[arg-type]
            confidence=1.0,
            extractor_id="supplementary",
            model_id=None,
            model_revision="rev",
            artifact_digest=None,
            runtime_compatibility_id=None,
        )
    with pytest.raises(ValueError, match="model provenance"):
        _mention(
            source="dictionary",  # type: ignore[arg-type]
            confidence_kind="dictionary_exact",  # type: ignore[arg-type]
            confidence=1.0,
            extractor_id="supplementary",
            model_id=None,
            model_revision=None,
            artifact_digest="a" * 64,
            runtime_compatibility_id=None,
        )
    with pytest.raises(ValueError, match="model provenance"):
        _mention(
            source="rule",  # type: ignore[arg-type]
            confidence_kind="rule_weight",  # type: ignore[arg-type]
            confidence=0.5,
            extractor_id="supplementary",
            model_id=None,
            model_revision=None,
            artifact_digest=None,
            runtime_compatibility_id="tuple-1",
        )


def test_importing_entity_package_imports_no_heavy_dependencies() -> None:
    import llamaindex_runtime.entity as entity

    assert hasattr(entity, "MentionCandidate")
    assert hasattr(entity, "CorpusSpanInput")
    assert hasattr(entity, "deterministic_id")
    for name in ("modelscope", "torch", "jieba"):
        assert name not in sys.modules, (
            f"llamaindex_runtime.entity must not import {name}"
        )
