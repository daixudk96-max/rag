"""RED specifications for pure E2a desired-state materialization.

The Wave 2 implementation is intentionally loaded only inside tests.  That
keeps this specification collectible while the production modules are absent
and makes the initial RED failure describe the missing capability.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType, ModuleType
from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
)

_MODULE = "llamaindex_runtime.okf.e2a_reconciler"
_DIGEST = "a" * 64


def _wave2_reconciler() -> ModuleType:
    """Load Wave 2 lazily so absence is a test failure, never collection error."""
    specification = importlib.util.find_spec(_MODULE)
    assert specification is not None, (
        "Wave 2 RED: llamaindex_runtime.okf.e2a_reconciler must provide "
        "immutable desired-state materialization"
    )
    return importlib.import_module(_MODULE)


def _span_id(number: int) -> str:
    return str(UUID(int=number))


def _admitted_state(*, shuffled: bool = False) -> E2aDesiredState:
    document_id = _span_id(1)
    version_id = _span_id(2)
    parent = E2aParent(document_id, version_id, "raw/guide.pair.json", _DIGEST)
    spans = (
        E2aSpan(document_id, version_id, _span_id(3), 0, "Cats are mammals."),
        E2aSpan(document_id, version_id, _span_id(4), 18, "Medicine helps cats."),
        E2aSpan(document_id, version_id, _span_id(5), 37, "猫 are companion animals."),
    )
    if shuffled:
        spans = (spans[2], spans[0], spans[1])
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{document_id}:{version_id}",
                "canonical_hash": _DIGEST,
            }
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=spans,
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({"raw_pair_protocol": "M-D-S-M"}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _span_records() -> tuple[dict[str, object], ...]:
    return (
        {
            "span_id": _span_id(3),
            "heading_path": "Guide > Biology",
            "page_no": 1,
            "semantic_domain": "Animals",
        },
        {
            "span_id": _span_id(4),
            "heading_path": "Guide > Care",
            "page_no": 2,
            "semantic_domain": "Medicine",
        },
        {
            "span_id": _span_id(5),
            "heading_path": "Guide > Biology",
            "page_no": 3,
            "semantic_domain": "animals",
        },
    )


def _materialization_input(module: ModuleType, *, shuffled: bool = False) -> object:
    records = _span_records()
    if shuffled:
        records = (records[2], records[0], records[1])
    admitted = _admitted_state(shuffled=shuffled)
    return module.E2aMaterializationInput(
        admitted=admitted,
        span_records=records,
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )


def _builder(module: ModuleType) -> object:
    return module.E2aDesiredStateBuilder(
        embed_text=lambda text: tuple(float(len(text) % 7) for _ in range(16))
    )


def _mapping_rows(values: tuple[object, ...]) -> tuple[dict[str, object], ...]:
    return tuple(dict(value) for value in values)


def test_materialization_input_is_recursively_immutable_and_builder_is_pure() -> None:
    module = _wave2_reconciler()
    records = _span_records()
    raw_record = records[0]
    admitted = _admitted_state()
    source = module.E2aMaterializationInput(
        admitted=admitted,
        span_records=records,
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )

    raw_record["heading_path"] = "mutated after construction"
    assert source.span_records[0]["heading_path"] == "Guide > Biology"
    with pytest.raises(FrozenInstanceError):
        source.admitted = _admitted_state()  # type: ignore[misc]
    with pytest.raises(TypeError):
        source.span_records[0]["page_no"] = 9  # type: ignore[index]
    with pytest.raises(TypeError):
        source.parent_source_checksums[admitted.parents[0].version_id] = "c" * 64  # type: ignore[index]

    desired = _builder(module).build(source)
    assert desired is not source.admitted
    assert type(desired) is E2aDesiredState
    assert all(type(parent) is E2aParent for parent in desired.parents)
    assert all(type(span) is E2aSpan for span in desired.canonical_spans)
    assert desired.corpus_manifest == source.admitted.corpus_manifest
    assert desired.provenance_metadata["parent_source_checksums"] == {
        admitted.parents[0].version_id: "b" * 64
    }
    assert desired.canonical_spans == tuple(
        sorted(
            source.admitted.canonical_spans,
            key=lambda span: (span.version_id, span.offset, span.span_id),
        )
    )


def test_builder_requires_one_immutable_source_checksum_for_every_parent() -> None:
    module = _wave2_reconciler()
    source = _materialization_input(module)
    missing = replace(source, parent_source_checksums={})
    malformed = replace(
        source,
        parent_source_checksums={source.admitted.parents[0].version_id: "not-a-digest"},
    )

    for invalid in (missing, malformed):
        with pytest.raises(ValueError, match="source checksum"):
            _builder(module).build(invalid)


@pytest.mark.parametrize(
    "invalid_input",
    (None, "not-a-materialization-input", 0, object()),
)
def test_builder_rejects_invalid_or_null_materialization_input(
    invalid_input: object,
) -> None:
    module = _wave2_reconciler()

    with pytest.raises((TypeError, ValueError), match="materialization input"):
        _builder(module).build(invalid_input)


def test_builder_rejects_unknown_duplicate_and_cross_parent_span_records() -> None:
    module = _wave2_reconciler()
    input_value = _materialization_input(module)
    duplicate = replace(
        input_value,
        span_records=(*input_value.span_records, input_value.span_records[0]),
    )
    unknown = replace(
        input_value,
        span_records=({**input_value.span_records[0], "span_id": _span_id(999)},),
    )

    for invalid in (duplicate, unknown):
        with pytest.raises(ValueError, match="span.*record"):
            _builder(module).build(invalid)


def test_shuffled_equivalent_spans_produce_identical_chunks_tree_and_manifest() -> None:
    module = _wave2_reconciler()
    builder = _builder(module)

    first = builder.build(_materialization_input(module))
    shuffled = builder.build(_materialization_input(module, shuffled=True))

    assert first.corpus_manifest_sha256 == shuffled.corpus_manifest_sha256
    assert first.canonical_spans == shuffled.canonical_spans
    assert canonical_json(first.vector_chunks) == canonical_json(shuffled.vector_chunks)
    assert canonical_json(first.vector_chunk_span_links) == canonical_json(
        shuffled.vector_chunk_span_links
    )
    assert canonical_json(first.tree_nodes) == canonical_json(shuffled.tree_nodes)
    assert canonical_json(first.tree_node_span_links) == canonical_json(
        shuffled.tree_node_span_links
    )


def test_vector_and_tree_outputs_have_stable_ids_complete_spans_and_parent_first_order() -> (
    None
):
    module = _wave2_reconciler()
    desired = _builder(module).build(_materialization_input(module))
    chunks = _mapping_rows(desired.vector_chunks)
    chunk_links = _mapping_rows(desired.vector_chunk_span_links)
    nodes = _mapping_rows(desired.tree_nodes)
    node_links = _mapping_rows(desired.tree_node_span_links)

    chunk_ids = [row["chunk_id"] for row in chunks]
    node_ids = [row["node_id"] for row in nodes]
    admitted_span_ids = {span.span_id for span in desired.canonical_spans}
    linked_chunk_spans = {row["span_id"] for row in chunk_links}
    linked_node_spans = {row["span_id"] for row in node_links}
    index_by_node = {node_id: index for index, node_id in enumerate(node_ids)}

    assert chunk_ids == sorted(chunk_ids, key=str)
    assert len(chunk_ids) == len(set(chunk_ids))
    assert len(node_ids) == len(set(node_ids))
    assert linked_chunk_spans == admitted_span_ids
    assert linked_node_spans == admitted_span_ids
    assert {row["chunk_id"] for row in chunk_links} <= set(chunk_ids)
    assert {row["node_id"] for row in node_links} <= set(node_ids)
    assert all(
        node["parent_node_id"] is None
        or index_by_node[node["parent_node_id"]] < index_by_node[node["node_id"]]
        for node in nodes
    )


def test_builder_normalizes_semantic_domains_before_tree_derivation() -> None:
    module = _wave2_reconciler()
    baseline = _materialization_input(module)
    variant = replace(
        baseline,
        span_records=tuple(
            {
                **record,
                "semantic_domain": (
                    str(record["semantic_domain"]).upper()
                    if index == 0
                    else f"  {record['semantic_domain']}  "
                ),
            }
            for index, record in enumerate(reversed(baseline.span_records))
        ),
    )

    first = _builder(module).build(baseline)
    second = _builder(module).build(variant)

    assert canonical_json(first.tree_nodes) == canonical_json(second.tree_nodes)
    assert canonical_json(first.tree_node_span_links) == canonical_json(
        second.tree_node_span_links
    )


def test_builder_rejects_nonfinite_embedding_and_malformed_span_metadata() -> None:
    module = _wave2_reconciler()
    input_value = _materialization_input(module)
    malformed = replace(
        input_value,
        span_records=({**input_value.span_records[0], "page_no": -1},),
    )
    nonfinite_builder = module.E2aDesiredStateBuilder(
        embed_text=lambda _: (float("nan"),) * 16
    )

    with pytest.raises(ValueError, match="span.*record"):
        _builder(module).build(malformed)
    with pytest.raises(ValueError, match="finite"):
        nonfinite_builder.build(input_value)


def test_materialized_state_does_not_expose_e2b_or_external_projection_fields() -> None:
    module = _wave2_reconciler()
    desired = _builder(module).build(_materialization_input(module))
    encoded = canonical_json(
        {
            "manifest": desired.corpus_manifest,
            "validation": desired.validation_metadata,
            "provenance": desired.provenance_metadata,
            "chunks": desired.vector_chunks,
        }
    )

    for forbidden in (
        "chunk_entity_links",
        "node_entity_links",
        "entity_mentions",
        "external_projection",
        "qdrant",
    ):
        assert forbidden not in encoded


class _StrSubclass(str):
    """A str subclass to test exact-type rejection."""


def _input_with_bad_top_level_key(module: ModuleType, key: object) -> object:
    """Construct E2aMaterializationInput with a non-str top-level span-record key."""
    admitted = _admitted_state()
    bad_record: dict[object, object] = {
        key: _span_id(3),
        "heading_path": "Guide > Biology",
        "page_no": 1,
        "semantic_domain": "Animals",
    }
    return module.E2aMaterializationInput(
        admitted=admitted,
        span_records=(bad_record,),
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )


def _input_with_bad_nested_key(module: ModuleType, key: object) -> object:
    """Construct E2aMaterializationInput with a non-str key in a nested mapping."""
    admitted = _admitted_state()
    bad_record = {
        "span_id": _span_id(3),
        "heading_path": "Guide > Biology",
        "page_no": 1,
        "semantic_domain": "Animals",
        "nested": {key: "value"},
    }
    return module.E2aMaterializationInput(
        admitted=admitted,
        span_records=(bad_record,),
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )


def _input_with_bad_key_in_sequence(module: ModuleType, key: object) -> object:
    """Construct E2aMaterializationInput with a non-str key in a mapping inside a sequence."""
    admitted = _admitted_state()
    bad_record = {
        "span_id": _span_id(3),
        "heading_path": "Guide > Biology",
        "page_no": 1,
        "semantic_domain": "Animals",
        "items": ({key: "value"},),
    }
    return module.E2aMaterializationInput(
        admitted=admitted,
        span_records=(bad_record,),
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )


def _input_with_bad_parent_checksum_key(module: ModuleType, key: object) -> object:
    """Construct E2aMaterializationInput with a non-str key in parent_source_checksums."""
    admitted = _admitted_state()
    bad_checksums: dict[object, str] = {key: "b" * 64}
    return module.E2aMaterializationInput(
        admitted=admitted,
        span_records=_span_records(),
        parent_source_checksums=bad_checksums,
    )


@pytest.mark.parametrize(
    "constructor",
    [
        _input_with_bad_top_level_key,
        _input_with_bad_nested_key,
        _input_with_bad_key_in_sequence,
        _input_with_bad_parent_checksum_key,
    ],
)
def test_materialization_input_rejects_integer_key_at_all_mapping_boundaries(
    constructor: Callable[[ModuleType, object], object],
) -> None:
    module = _wave2_reconciler()
    with pytest.raises(ValueError, match="mapping.*key"):
        constructor(module, 1)


@pytest.mark.parametrize(
    "constructor",
    [
        _input_with_bad_top_level_key,
        _input_with_bad_nested_key,
        _input_with_bad_key_in_sequence,
        _input_with_bad_parent_checksum_key,
    ],
)
def test_materialization_input_rejects_float_key_at_all_mapping_boundaries(
    constructor: Callable[[ModuleType, object], object],
) -> None:
    module = _wave2_reconciler()
    with pytest.raises(ValueError, match="mapping.*key"):
        constructor(module, 3.14)


@pytest.mark.parametrize(
    "constructor",
    [
        _input_with_bad_top_level_key,
        _input_with_bad_nested_key,
        _input_with_bad_key_in_sequence,
        _input_with_bad_parent_checksum_key,
    ],
)
def test_materialization_input_rejects_str_subclass_key_at_all_mapping_boundaries(
    constructor: Callable[[ModuleType, object], object],
) -> None:
    module = _wave2_reconciler()
    with pytest.raises(ValueError, match="mapping.*key"):
        constructor(module, _StrSubclass("valid_string"))


@pytest.mark.parametrize(
    "constructor",
    [
        _input_with_bad_top_level_key,
        _input_with_bad_nested_key,
        _input_with_bad_key_in_sequence,
        _input_with_bad_parent_checksum_key,
    ],
)
def test_materialization_input_rejects_lone_surrogate_key_at_all_mapping_boundaries(
    constructor: Callable[[ModuleType, object], object],
) -> None:
    module = _wave2_reconciler()
    with pytest.raises(ValueError, match="surrogate|scalar|UTF-8|key"):
        constructor(module, "\ud800")


def test_materialization_input_prevents_key_collapse_at_top_level() -> None:
    module = _wave2_reconciler()
    admitted = _admitted_state()
    span_id_str = _span_id(3)
    collapsed_record: dict[object, object] = {
        1: "integer_key_value",
        "1": span_id_str,
        "heading_path": "Guide > Biology",
        "page_no": 1,
        "semantic_domain": "Animals",
    }
    with pytest.raises(ValueError, match="mapping.*key"):
        module.E2aMaterializationInput(
            admitted=admitted,
            span_records=(collapsed_record,),
            parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
        )


def test_materialization_input_accepts_unicode_noncharacter_u_fffe_in_nested_mapping() -> (
    None
):
    module = _wave2_reconciler()
    admitted = _admitted_state()
    fffe_key = "￾"
    good_record = {
        "span_id": _span_id(3),
        "heading_path": "Guide > Biology",
        "page_no": 1,
        "semantic_domain": "Animals",
        "metadata": {fffe_key: "preserved_value"},
    }
    source = module.E2aMaterializationInput(
        admitted=admitted,
        span_records=(good_record,),
        parent_source_checksums={admitted.parents[0].version_id: "b" * 64},
    )
    assert source.span_records[0]["metadata"][fffe_key] == "preserved_value"


def test_materialization_input_accepts_unicode_noncharacter_u_fffe_in_parent_checksums() -> (
    None
):
    module = _wave2_reconciler()
    admitted = _admitted_state()
    fffe_key = "￾"
    parent_checksums: dict[str, str] = {fffe_key: "b" * 64}
    source = module.E2aMaterializationInput(
        admitted=admitted,
        span_records=_span_records(),
        parent_source_checksums=parent_checksums,
    )
    assert source.parent_source_checksums[fffe_key] == "b" * 64


def test_frozen_extraction_contract_preserves_object_identity() -> None:
    """Phase 15 Wave 2 Task #66: verify behavior-preserving reconciler extraction.

    The reconciler module delegates to a frozen private implementation module
    and must re-export the exact same objects (same identity, not just equality).
    """
    reconciler = _wave2_reconciler()
    private_module = importlib.import_module(
        "llamaindex_runtime.okf._e2a_materialization_input"
    )
    assert (
        reconciler.E2aMaterializationInput is private_module.E2aMaterializationInput
    ), "E2aMaterializationInput must be same object after extraction"
    assert (
        reconciler.E2aDesiredStateBuilder is private_module.E2aDesiredStateBuilder
    ), "E2aDesiredStateBuilder must be same object after extraction"
