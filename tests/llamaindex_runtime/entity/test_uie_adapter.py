"""Phase 17-W2 contract tests for the pure UIE adapter (TDD, fake JSON only).

Pins llamaindex_runtime/entity/uie_adapter.py against fake UIE mappings --
no model is loaded and no network is touched anywhere in this module:

- normalize_source_text freezes the v1 policy: NFKC normalization plus
  end-of-string whitespace stripping, idempotent by construction.
- map_entity_mentions builds full-provenance corpus MentionCandidate values
  only from exact slices of normalized_text; offsets are never guessed or
  recovered (a declared offset that does not slice back fails closed even
  when the text occurs elsewhere); span_id is deterministic over
  (document_id, version_id, mention_text, offset, normalized-text digest)
  so reruns are idempotent and input_id == span_id.
- Rejections are recorded per entity/relation, never silently dropped;
  unknown or missing UIE labels fail closed against the explicitly frozen
  canonical type table (renming/diming/gongsiming/chanpinming ->
  Person/Location/Organization/Product -- the OKF canonical set of the
  frozen label_map v1).
- RelationSchema v2 is frozen, with a two-sided gate {relation:
  (allowed_subject_types, allowed_object_types)}, and round-trips through
  to_dict/from_dict, including through a JSON file-state round trip.
- map_relation_triples requires the subject and object text to exactly
  equal the mention_text of an accepted candidate of the same call, and
  rejects unknown relations, two-sided gate violations, unknown entity
  types, self loops, duplicate relations, too-short texts, and any
  subject/object/source text that is not an exact substring of the
  mandatory source sentence (which itself must be anchored in
  normalized_text).
- Integration: two same-name mentions of one document/version form exactly
  one build_coref_clusters cluster under resolver_mode="rules".
- Module purity: the adapter imports only the standard library plus
  .contracts; membership checks only verify declared spans and anchoring
  and never locate or recover text positions.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.entity import uie_adapter
from llamaindex_runtime.entity.contracts import MentionCandidate
from llamaindex_runtime.entity.coref_rules import build_coref_clusters
from llamaindex_runtime.entity.label_map import RAINER_RAW_TO_CANONICAL
from llamaindex_runtime.entity.resolution import resolve_candidates
from llamaindex_runtime.entity.uie_adapter import (
    CANONICAL_ENTITY_TYPES,
    DEFAULT_RELATION_SCHEMA,
    LABEL_MAP_DIGEST,
    UIE_TYPE_TO_CANONICAL,
    RelationSchema,
    RelationTriple,
    RejectionReason,
    UieMappingError,
    UieRejection,
    map_entity_mentions,
    map_relation_triples,
    normalize_source_text,
)

_DOCUMENT_ID = str(UUID(int=1701))
_VERSION_ID = str(UUID(int=1702))
_OTHER_VERSION_ID = str(UUID(int=1703))
_SENTENCE = "李雷在北京使用华为Mate60"
_PRIORITY_VERSION = "w2-test"
_COREF_RULES_VERSION = "w2-test"


def _offsets(text: str, needle: str, *, start: int = 0) -> tuple[int, int]:
    begin = text.index(needle, start)
    return begin, begin + len(needle)


def _entity(
    text: str,
    label: str,
    char_start: int,
    char_end: int,
    *,
    confidence: object = 0.9,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "text": text,
        "label": label,
        "char_start": char_start,
        "char_end": char_end,
    }
    if confidence is not None:
        entry["confidence"] = confidence
    return entry


def _relation(
    subject_text: str,
    subject_type: str,
    relation: str,
    object_text: str,
    object_type: str,
    source_text: str,
) -> dict[str, object]:
    return {
        "subject_text": subject_text,
        "subject_type": subject_type,
        "relation": relation,
        "object_text": object_text,
        "object_type": object_type,
        "source_text": source_text,
    }


def test_normalize_source_text_applies_nfkc_and_strips_ends() -> None:
    assert normalize_source_text("Ｈｅｌｌｏ  李雷　") == "Hello  李雷"
    assert normalize_source_text("ﬁx  ") == "fix"
    raw = "  李雷 在北京 "
    once = normalize_source_text(raw)
    assert once == "李雷 在北京"
    assert normalize_source_text(once) == once  # v1 policy is idempotent
    with pytest.raises(UieMappingError):
        normalize_source_text(123)  # type: ignore[arg-type]


def test_map_entity_mentions_happy_path_builds_full_provenance() -> None:
    entities = [
        _entity("李雷", "人名", 0, 2, confidence=0.93),
        _entity("北京", "地名", 3, 5),
        _entity("华为Mate60", "产品名", 7, 15, confidence=None),
    ]
    result = map_entity_mentions(
        entities,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.rejected == ()
    candidates = result.candidates
    assert [candidate.mention_text for candidate in candidates] == [
        "李雷",
        "北京",
        "华为Mate60",
    ]
    assert [(c.entity_type, c.raw_label) for c in candidates] == [
        ("Person", "人名"),
        ("Location", "地名"),
        ("Product", "产品名"),
    ]
    first = candidates[0]
    assert isinstance(first, MentionCandidate)
    assert first.input_kind == "corpus_span"
    assert first.input_id == first.span_id
    assert str(UUID(first.span_id)) == first.span_id  # canonical UUID form
    assert (first.char_start, first.char_end) == (0, 2)
    assert first.normalized_text == _SENTENCE
    assert first.source == "model"
    assert first.confidence == 0.93
    assert first.confidence_kind == "model_probability"
    assert first.extractor_id == "pp-uie-0.5b"
    assert first.model_id == "PP-UIE-0.5B"
    assert first.document_id == _DOCUMENT_ID
    assert first.version_id == _VERSION_ID
    assert first.document_revision == first.input_revision
    assert len(first.label_map_digest) == 64
    assert len(first.artifact_digest or "") == 64
    assert isinstance(first.projection, MappingProxyType)
    third = candidates[2]
    assert third.confidence is None
    assert third.confidence_kind == "unavailable"


def test_map_entity_mentions_span_ids_are_deterministic_and_scoped() -> None:
    entities = [_entity("李雷", "人名", 0, 2), _entity("北京", "地名", 3, 5)]
    first = map_entity_mentions(
        list(entities),
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    second = map_entity_mentions(
        list(entities),
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert [c.span_id for c in first.candidates] == [
        c.span_id for c in second.candidates
    ]
    other_version = map_entity_mentions(
        list(entities),
        document_id=_DOCUMENT_ID,
        version_id=_OTHER_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert [c.span_id for c in other_version.candidates] != [
        c.span_id for c in first.candidates
    ]


def test_map_entity_mentions_fails_closed_on_bad_slices_and_offsets() -> None:
    entities: list[object] = [
        # "华为" occurs at 7 in the sentence, but the declared offset slices
        # "李雷" -- the adapter must reject, never recover by searching.
        _entity("华为", "公司名", 0, 2),
        _entity("李雷", "人名", 0, 99),
        _entity("李雷", "人名", -1, 2),
        {"text": "李雷", "label": "人名", "char_end": 2},
        {"text": "", "label": "人名", "char_start": 0, "char_end": 0},
        "not-a-mapping",
    ]
    result = map_entity_mentions(
        entities,  # type: ignore[arg-type]
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.candidates == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.NOT_EXACT_SLICE,
        RejectionReason.OUT_OF_RANGE,
        RejectionReason.OUT_OF_RANGE,
        RejectionReason.MISSING_OFFSET,
        RejectionReason.MISSING_TEXT,
        RejectionReason.NOT_A_MAPPING,
    ]
    assert [rejection.index for rejection in result.rejected] == [0, 1, 2, 3, 4, 5]
    assert result.rejected[0].text == "华为"


def test_map_entity_mentions_rejects_unknown_or_missing_uie_types() -> None:
    entities: list[object] = [
        _entity("李雷", "组织名", 0, 2),
        {"text": "北京", "char_start": 3, "char_end": 5},
    ]
    result = map_entity_mentions(
        entities,  # type: ignore[arg-type]
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.candidates == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.UNKNOWN_ENTITY_TYPE,
        RejectionReason.UNKNOWN_ENTITY_TYPE,
    ]


def test_map_entity_mentions_rejects_duplicate_spans() -> None:
    entities = [_entity("李雷", "人名", 0, 2), _entity("李雷", "人名", 0, 2)]
    result = map_entity_mentions(
        entities,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert len(result.candidates) == 1
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.DUPLICATE_SPAN
    ]
    assert result.rejected[0].index == 1


def test_map_entity_mentions_call_level_guards_fail_closed() -> None:
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            [],
            document_id="doc-1",
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
        )
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            [],
            document_id=_DOCUMENT_ID,
            version_id=_OTHER_VERSION_ID.upper(),
            normalized_text=_SENTENCE,
        )
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            [],
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text="李雷 在北京 ",  # not end-stripped: not canonical
        )
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            [],
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text="ＬＩＬＥＩ",  # fullwidth: not NFKC-canonical
        )
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            [],
            document_id="00000000-0000-0000-0000-000000000000",  # nil UUID
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
        )


def test_mapping_results_are_frozen_sequences() -> None:
    result = map_entity_mentions(
        [_entity("李雷", "人名", 0, 2)],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert isinstance(result.candidates, tuple)
    assert isinstance(result.rejected, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.candidates = ()  # type: ignore[misc]
    record = UieRejection(
        index=0,
        reason=RejectionReason.MISSING_TEXT,
        text="",
        detail="x",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.index = 1  # type: ignore[misc]


def test_canonical_type_table_is_explicit_and_frozen() -> None:
    assert dict(UIE_TYPE_TO_CANONICAL) == {
        "人名": "Person",
        "地名": "Location",
        "公司名": "Organization",
        "产品名": "Product",
    }
    assert sorted(CANONICAL_ENTITY_TYPES) == [
        "Location",
        "Organization",
        "Person",
        "Product",
    ]
    with pytest.raises(TypeError):
        UIE_TYPE_TO_CANONICAL["组织名"] = "Organization"  # type: ignore[index]


def test_uie_canonical_types_align_with_label_map_okf_set() -> None:
    # Adjudication A1: the adapter canonical set must stay inside the frozen
    # label_map v1 OKF canonical set that resolution/coref match on.
    assert set(UIE_TYPE_TO_CANONICAL.values()) <= set(RAINER_RAW_TO_CANONICAL.values())


def test_default_relation_schema_pins_frozen_v2_schema() -> None:
    schema = DEFAULT_RELATION_SCHEMA
    assert schema.version == "uie-relation-schema-v2"
    assert schema.relations == (
        "所在地",
        "所属公司",
        "任职于",
        "发布",
        "总部位于",
        "使用",
        "通话",
        "前往",
    )
    # Two-sided v2 gate: relation -> (allowed subject types, allowed object
    # types) over the canonical OKF vocabulary.
    assert dict(schema.gate) == {
        "所在地": (("Person",), ("Location",)),
        "所属公司": (("Person", "Product"), ("Organization",)),
        "任职于": (("Person",), ("Organization",)),
        "发布": (("Organization",), ("Product",)),
        "总部位于": (("Organization",), ("Location",)),
        "使用": (("Person",), ("Product",)),
        "通话": (("Person",), ("Person",)),
        "前往": (("Person",), ("Location",)),
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        schema.relations = ()  # type: ignore[misc]


def test_relation_schema_round_trips_and_validates() -> None:
    restored = RelationSchema.from_dict(DEFAULT_RELATION_SCHEMA.to_dict())
    assert restored == DEFAULT_RELATION_SCHEMA
    with pytest.raises(UieMappingError):
        RelationSchema.from_dict(
            {"relations": ["发布"], "gate": {"发布": ("Organization",)}}
        )  # gate values must be (subjects, objects) pairs
    with pytest.raises(UieMappingError):
        RelationSchema.from_dict(
            {"relations": ["发布"], "gate": {"投资": (("Organization",), ("Product",))}}
        )  # gate keys must be schema relations
    with pytest.raises(UieMappingError):
        RelationSchema.from_dict(
            {"relations": ["发布"], "gate": {"发布": (("Organization",), ("Widget",))}}
        )  # gate types must be canonical
    with pytest.raises(UieMappingError):
        RelationSchema.from_dict({"gate": {}})


def test_relation_schema_json_file_round_trip() -> None:
    payload = json.dumps(DEFAULT_RELATION_SCHEMA.to_dict(), ensure_ascii=False)
    rebuilt = RelationSchema.from_dict(json.loads(payload))
    assert rebuilt == DEFAULT_RELATION_SCHEMA
    assert rebuilt.to_dict() == DEFAULT_RELATION_SCHEMA.to_dict()


def test_map_relation_triples_happy_path() -> None:
    normalized = normalize_source_text("李雷在北京使用华为Mate60。华为的总部在杭州。")
    sentence_a = "李雷在北京使用华为Mate60"
    sentence_b = "华为的总部在杭州"
    mentions = map_entity_mentions(
        [
            _entity("李雷", "人名", 0, 2),
            _entity("华为Mate60", "产品名", 7, 15),
            _entity("华为", "公司名", 16, 18),
            _entity("杭州", "地名", 22, 24),
        ],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=normalized,
    )
    assert mentions.rejected == ()
    relations = [
        _relation("李雷", "人名", "使用", "华为Mate60", "产品名", sentence_a),
        _relation("华为", "公司名", "总部位于", "杭州", "地名", sentence_b),
    ]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=normalized,
        candidates=mentions.candidates,
    )
    assert result.rejected == ()
    assert len(result.triples) == 2
    first = result.triples[0]
    assert isinstance(first, RelationTriple)
    assert first.subject_text == "李雷"
    assert first.subject_type == "Person"
    assert first.relation == "使用"
    assert first.object_text == "华为Mate60"
    assert first.object_type == "Product"
    assert first.source_text == sentence_a
    assert first.document_id == _DOCUMENT_ID
    assert first.version_id == _VERSION_ID
    second = result.triples[1]
    assert (second.subject_type, second.object_type) == ("Organization", "Location")


def test_map_relation_triples_rejects_schema_and_gate_violations() -> None:
    relations = [
        _relation("李雷", "人名", "投资", "华为", "公司名", _SENTENCE),
        _relation("华为", "公司名", "使用", "Mate60", "产品名", _SENTENCE),
        _relation("李雷", "人名", "总部位于", "杭州", "地名", _SENTENCE),
        _relation("李雷", "组织", "使用", "华为Mate60", "产品名", _SENTENCE),
        _relation("李雷", "人名", "使用", "华为Mate60", "设备", _SENTENCE),
        _relation("李雷", "人名", "使用", "华为Mate60", "产品名", ""),
        _relation("王小明", "人名", "通话", "韩梅梅", "人名", _SENTENCE),
        _relation("李雷", "人名", "使用", "小米", "产品名", _SENTENCE),
        _relation("韩梅梅", "人名", "前往", "上海", "地名", "韩梅梅明天去上海出差"),
    ]
    mentions = map_entity_mentions(
        [
            _entity("李雷", "人名", 0, 2),
            _entity("华为", "公司名", 7, 9),
            _entity("Mate60", "产品名", 9, 15),
            _entity("华为Mate60", "产品名", 7, 15),
        ],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert mentions.rejected == ()
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=mentions.candidates,
    )
    assert result.triples == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.RELATION_NOT_IN_SCHEMA,
        RejectionReason.SUBJECT_TYPE_NOT_ALLOWED,
        RejectionReason.SUBJECT_TYPE_NOT_ALLOWED,
        RejectionReason.UNKNOWN_ENTITY_TYPE,
        RejectionReason.UNKNOWN_ENTITY_TYPE,
        RejectionReason.MISSING_SOURCE_TEXT,
        RejectionReason.SUBJECT_NOT_IN_SOURCE,
        RejectionReason.OBJECT_NOT_IN_SOURCE,
        RejectionReason.SOURCE_NOT_IN_NORMALIZED_TEXT,
    ]
    assert [rejection.index for rejection in result.rejected] == list(range(9))
    assert result.rejected[0].text == "李雷"
    assert "投资" in result.rejected[0].detail


def test_relation_triple_is_frozen_with_exact_fields() -> None:
    assert [field.name for field in dataclasses.fields(RelationTriple)] == [
        "subject_text",
        "subject_type",
        "relation",
        "object_text",
        "object_type",
        "source_text",
        "document_id",
        "version_id",
    ]
    triple = RelationTriple(
        subject_text="李雷",
        subject_type="Person",
        relation="使用",
        object_text="华为Mate60",
        object_type="Product",
        source_text=_SENTENCE,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        triple.relation = "发布"  # type: ignore[misc]
    with pytest.raises(ValueError):
        RelationTriple(
            subject_text="李雷",
            subject_type="Person",
            relation="使用",
            object_text="小米",
            object_type="Product",
            source_text=_SENTENCE,
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
        )
    with pytest.raises(ValueError):
        RelationTriple(
            subject_text="李雷",
            subject_type="Widget",
            relation="使用",
            object_text="华为Mate60",
            object_type="Product",
            source_text=_SENTENCE,
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
        )
    with pytest.raises(ValueError):
        RelationTriple(
            subject_text="李雷",
            subject_type="Person",
            relation="使用",
            object_text="华为Mate60",
            object_type="Product",
            source_text=_SENTENCE,
            document_id="doc-1",
            version_id=_VERSION_ID,
        )


def test_map_relation_triples_call_level_guards_fail_closed() -> None:
    with pytest.raises(UieMappingError):
        map_relation_triples(
            [],
            DEFAULT_RELATION_SCHEMA,
            document_id="doc-1",
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
            candidates=[],
        )
    with pytest.raises(UieMappingError):
        map_relation_triples(
            [],
            DEFAULT_RELATION_SCHEMA,
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text="李雷 在北京 ",
            candidates=[],
        )
    with pytest.raises(UieMappingError):
        map_relation_triples(
            [],
            "not-a-schema",  # type: ignore[arg-type]
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
            candidates=[],
        )
    with pytest.raises(UieMappingError):
        map_relation_triples(
            42,  # type: ignore[arg-type]
            DEFAULT_RELATION_SCHEMA,
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
            candidates=[],
        )
    with pytest.raises(UieMappingError):
        map_relation_triples(
            [],
            DEFAULT_RELATION_SCHEMA,
            document_id=_DOCUMENT_ID,
            version_id="00000000-0000-0000-0000-000000000000",  # nil UUID
            normalized_text=_SENTENCE,
            candidates=[],
        )


def test_coref_rules_two_same_name_mentions_form_one_cluster() -> None:
    raw = "李雷在北京使用华为Mate60，韩梅梅告诉李雷明天出发。"
    text = normalize_source_text(raw)  # fullwidth comma NFKC-collapses
    li_start, li_end = _offsets(text, "李雷")
    li_second_start, li_second_end = _offsets(text, "李雷", start=li_end)
    bei_start, bei_end = _offsets(text, "北京")
    mate_start, mate_end = _offsets(text, "华为Mate60")
    han_start, han_end = _offsets(text, "韩梅梅")
    entities = [
        _entity("李雷", "人名", li_start, li_end, confidence=0.91),
        _entity("北京", "地名", bei_start, bei_end, confidence=0.88),
        _entity("华为Mate60", "产品名", mate_start, mate_end, confidence=0.72),
        _entity("李雷", "人名", li_second_start, li_second_end, confidence=0.86),
        _entity("韩梅梅", "人名", han_start, han_end, confidence=0.77),
    ]
    result = map_entity_mentions(
        entities,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=text,
    )
    assert result.rejected == ()
    assert len({candidate.span_id for candidate in result.candidates}) == 5
    authority = [
        {
            "entity_id": str(UUID(int=9001)),
            "canonical_name": "李雷",
            "entity_type": "Person",
        }
    ]
    resolved = resolve_candidates(
        list(result.candidates),
        entities=authority,
        aliases=[],
        priority_version=_PRIORITY_VERSION,
    )
    li_lei_members = {
        candidate.span_id
        for candidate in result.candidates
        if candidate.mention_text == "李雷"
    }
    assert {d.candidate.span_id for d in resolved.resolved} == li_lei_members
    clusters = build_coref_clusters(
        resolved,
        coref_rules_version=_COREF_RULES_VERSION,
        resolver_mode="rules",
    )
    assert len(clusters.clusters) == 1
    assert set(clusters.clusters[0].member_mention_ids) == li_lei_members


def _accepted_mentions() -> tuple[MentionCandidate, ...]:
    mentions = map_entity_mentions(
        [
            _entity("李雷", "人名", 0, 2),
            _entity("北京", "地名", 3, 5),
            _entity("华为", "公司名", 7, 9),
            _entity("Mate60", "产品名", 9, 15),
            _entity("华为Mate60", "产品名", 7, 15),
        ],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert mentions.rejected == ()
    return mentions.candidates


def test_map_entity_mentions_rejects_too_short_mentions() -> None:
    entities: list[object] = [
        _entity("李", "人名", 0, 1),  # length < 2
        {"text": "   ", "label": "人名", "char_start": 0, "char_end": 1},
    ]
    result = map_entity_mentions(
        entities,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.candidates == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.TOO_SHORT,
        RejectionReason.TOO_SHORT,
    ]


@pytest.mark.parametrize(
    "bad_confidence",
    ["0.9", float("nan"), float("inf"), True, 2.0, -5.0, 10**400],
)
def test_map_entity_mentions_rejects_invalid_confidence(
    bad_confidence: object,
) -> None:
    result = map_entity_mentions(
        [_entity("李雷", "人名", 0, 2, confidence=bad_confidence)],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.candidates == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.INVALID_CONFIDENCE
    ]


def test_map_entity_mentions_confidence_boundaries_and_missing() -> None:
    result = map_entity_mentions(
        [
            _entity("李雷", "人名", 0, 2, confidence=0.0),
            _entity("北京", "地名", 3, 5, confidence=1.0),
            _entity("华为Mate60", "产品名", 7, 15, confidence=None),
        ],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert result.rejected == ()
    assert [candidate.confidence for candidate in result.candidates] == [
        0.0,
        1.0,
        None,
    ]
    assert [c.confidence_kind for c in result.candidates] == [
        "model_probability",
        "model_probability",
        "unavailable",
    ]


def test_label_map_digest_hashes_sorted_key_value_pairs() -> None:
    expected = hashlib.sha256(
        json.dumps(sorted(UIE_TYPE_TO_CANONICAL.items()), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    assert LABEL_MAP_DIGEST == expected
    assert len(LABEL_MAP_DIGEST) == 64


def test_map_entity_mentions_rejects_non_iterable_input() -> None:
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            42,  # type: ignore[arg-type]
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
        )
    with pytest.raises(UieMappingError):
        map_entity_mentions(
            None,  # type: ignore[arg-type]
            document_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            normalized_text=_SENTENCE,
        )


def test_map_relation_triples_requires_accepted_mentions() -> None:
    mentions = map_entity_mentions(
        [
            _entity("李雷", "人名", 0, 2),
            _entity("华为Mate60", "产品名", 7, 15),
        ],
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
    )
    assert mentions.rejected == ()
    relations = [
        # 北京 occurs in the sentence but was never accepted as a mention:
        # the adapter must not trust arbitrary relation-side substrings.
        _relation("李雷", "人名", "通话", "北京", "人名", _SENTENCE),
        _relation("北京", "人名", "通话", "李雷", "人名", _SENTENCE),
    ]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=mentions.candidates,
    )
    assert result.triples == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.OBJECT_NOT_A_MENTION,
        RejectionReason.SUBJECT_NOT_A_MENTION,
    ]


def test_map_relation_triples_rejects_self_loop() -> None:
    relations = [_relation("李雷", "人名", "通话", "李雷", "人名", _SENTENCE)]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=_accepted_mentions(),
    )
    assert result.triples == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.SELF_LOOP
    ]


def test_map_relation_triples_rejects_duplicate_relations() -> None:
    relations = [
        _relation("李雷", "人名", "使用", "华为Mate60", "产品名", _SENTENCE),
        _relation("李雷", "人名", "使用", "华为Mate60", "产品名", _SENTENCE),
    ]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=_accepted_mentions(),
    )
    assert len(result.triples) == 1
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.DUPLICATE_RELATION
    ]
    assert result.rejected[0].index == 1


def test_map_relation_triples_rejects_too_short_texts() -> None:
    relations = [
        _relation("李", "人名", "通话", "李雷", "人名", _SENTENCE),
        _relation("李雷", "人名", "通话", " ", "人名", _SENTENCE),
    ]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=_accepted_mentions(),
    )
    assert result.triples == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.TOO_SHORT,
        RejectionReason.TOO_SHORT,
    ]


def test_map_relation_triples_enforces_object_type_gate() -> None:
    # v2 two-sided gate: 使用 is Person -> Product; a Location object is
    # rejected even though the subject side would be allowed.
    relations = [_relation("李雷", "人名", "使用", "北京", "地名", _SENTENCE)]
    result = map_relation_triples(
        relations,
        DEFAULT_RELATION_SCHEMA,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        normalized_text=_SENTENCE,
        candidates=_accepted_mentions(),
    )
    assert result.triples == ()
    assert [rejection.reason for rejection in result.rejected] == [
        RejectionReason.OBJECT_TYPE_NOT_ALLOWED
    ]


def test_relation_triple_rejects_non_canonical_document_uuid() -> None:
    # The RelationTriple constructor itself rejects non-canonical/nil UUIDs;
    # the INVALID_CANDIDATE catch is unreachable via the public API.
    with pytest.raises(ValueError):
        RelationTriple(
            subject_text="李雷",
            subject_type="Person",
            relation="使用",
            object_text="华为Mate60",
            object_type="Product",
            source_text=_SENTENCE,
            document_id="uie-adapter-v1",
            version_id=_VERSION_ID,
        )
    with pytest.raises(ValueError):
        RelationTriple(
            subject_text="李雷",
            subject_type="Person",
            relation="使用",
            object_text="华为Mate60",
            object_type="Product",
            source_text=_SENTENCE,
            document_id=_DOCUMENT_ID,
            version_id="00000000-0000-0000-0000-000000000000",
        )


_BANNED_IMPORT_ROOTS = (
    "paddle",
    "lightrag",
    "torch",
    "transformers",
    "modelscope",
    "jieba",
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "ssl",
    "subprocess",
    "pathlib",
    "os",
    "sys",
)
_SUBSTRING_SEARCH_APIS = (".find(", ".index(")


def test_uie_adapter_module_purity() -> None:
    source = Path(uie_adapter.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _BANNED_IMPORT_ROOTS, root
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                root = node.module.split(".")[0]
                assert root not in _BANNED_IMPORT_ROOTS, root
            else:
                assert node.module == "contracts"
    for token in _SUBSTRING_SEARCH_APIS:
        assert token not in source, token
    heavy_already_loaded = {
        root
        for root in ("paddle", "lightrag", "torch", "transformers", "modelscope")
        if root in sys.modules
    }
    if heavy_already_loaded:
        # Suite-order contamination: if a heavy module was imported by an
        # earlier test module, this adapter cannot be blamed for it.
        pytest.skip(
            "heavy modules already imported by earlier suite order: "
            + ",".join(sorted(heavy_already_loaded))
        )
    assert "paddle" not in sys.modules
    assert "lightrag" not in sys.modules
