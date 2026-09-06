"""RED contracts for Phase 15 task #65 projection authority and determinism.

These specifications use only pure builders and in-memory admission fixtures.  They
intentionally name the missing public admission bridge and projection invariants;
no cursor, database, Docker, or network capability is required.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf import e2a_admission, e2a_reconciler
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aSpan,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.raw_pair import RawPairSnapshot
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar
from llamaindex_runtime.registry.tree_generator import TreeGenerator

_CANONICAL_HASH = "a" * 64
_SOURCE_CHECKSUM = "b" * 64
_DOCUMENT_ID = str(UUID(int=1))
_VERSION_ID = str(UUID(int=2))
_SPAN_ONE_ID = str(UUID(int=3))
_SPAN_TWO_ID = str(UUID(int=4))
_NODE_ONE_ID = str(UUID(int=10))
_NODE_TWO_ID = str(UUID(int=11))
_CHUNK_ONE_ID = str(UUID(int=20))
_CHUNK_TWO_ID = str(UUID(int=21))

_PERSISTED_TREE_NODE_FIELDS = frozenset(
    {
        "node_id",
        "version_id",
        "parent_node_id",
        "node_type",
        "level_no",
        "title",
        "heading_path",
        "page_start",
        "page_end",
        "summary_text",
    }
)


def _span_one() -> E2aSpan:
    return E2aSpan(
        _DOCUMENT_ID,
        _VERSION_ID,
        _SPAN_ONE_ID,
        0,
        "Machine learning algorithms train neural networks.",
    )


def _span_two() -> E2aSpan:
    return E2aSpan(
        _DOCUMENT_ID,
        _VERSION_ID,
        _SPAN_TWO_ID,
        50,
        "Cooking recipes use pasta, ingredients, and a kitchen.",
    )


def _parent() -> E2aParent:
    return E2aParent(
        _DOCUMENT_ID,
        _VERSION_ID,
        "raw/guide.pair.json",
        _CANONICAL_HASH,
    )


def _admitted_state(spans: tuple[E2aSpan, ...]) -> E2aDesiredState:
    parent = _parent()
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
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


def _source(spans: tuple[E2aSpan, ...]) -> e2a_reconciler.E2aMaterializationInput:
    metadata = {
        _SPAN_ONE_ID: {
            "page_no": 1,
            "heading_path": "Guide > Shared Topic",
            "semantic_domain": "machine learning",
        },
        _SPAN_TWO_ID: {
            "page_no": 2,
            "heading_path": "Guide > Shared Topic",
            "semantic_domain": "cooking",
        },
    }
    return e2a_reconciler.E2aMaterializationInput(
        admitted=_admitted_state(spans),
        span_records=tuple(
            {"span_id": span.span_id, **metadata[span.span_id]} for span in spans
        ),
        parent_source_checksums={_VERSION_ID: _SOURCE_CHECKSUM},
    )


def _builder(
    *, embed_text: object | None = None
) -> e2a_reconciler.E2aDesiredStateBuilder:
    embedding = embed_text or (lambda text: (float(len(text) % 7),) * 16)
    return e2a_reconciler.E2aDesiredStateBuilder(embed_text=embedding)  # type: ignore[arg-type]


def _tree_generator_input(spans: tuple[E2aSpan, ...]) -> list[dict[str, object]]:
    source = _source(spans)
    records = {record["span_id"]: record for record in source.span_records}
    return [
        {
            "span_id": UUID(span.span_id),
            "version_id": UUID(span.version_id),
            "start_offset": span.offset,
            "page_no": records[span.span_id]["page_no"],
            "heading_path": records[span.span_id]["heading_path"],
            "semantic_domain": records[span.span_id]["semantic_domain"],
            "raw_text": span.text,
        }
        for span in spans
    ]


def _projection_state(
    *,
    vector_links: tuple[dict[str, object], ...] | None = None,
    tree_links: tuple[dict[str, object], ...] | None = None,
) -> E2aDesiredState:
    spans = (_span_one(), _span_two())
    nodes = (
        {
            "node_id": _NODE_ONE_ID,
            "version_id": _VERSION_ID,
            "parent_node_id": None,
            "node_type": "chapter",
            "level_no": 0,
            "title": "First",
            "heading_path": "Guide > First",
            "page_start": 1,
            "page_end": 1,
            "summary_text": "first",
        },
        {
            "node_id": _NODE_TWO_ID,
            "version_id": _VERSION_ID,
            "parent_node_id": None,
            "node_type": "chapter",
            "level_no": 0,
            "title": "Second",
            "heading_path": "Guide > Second",
            "page_start": 2,
            "page_end": 2,
            "summary_text": "second",
        },
    )
    chunks = (
        {
            "chunk_id": _CHUNK_ONE_ID,
            "version_id": _VERSION_ID,
            "chunk_type": "canonical_span",
            "chunk_order": 0,
            "token_count": 2,
            "text_preview": "first",
            "page_no": 1,
            "heading_path": "Guide > First",
            "node_id": _NODE_ONE_ID,
            "embedding": [0.0] * 16,
        },
        {
            "chunk_id": _CHUNK_TWO_ID,
            "version_id": _VERSION_ID,
            "chunk_type": "canonical_span",
            "chunk_order": 1,
            "token_count": 2,
            "text_preview": "second",
            "page_no": 2,
            "heading_path": "Guide > Second",
            "node_id": _NODE_TWO_ID,
            "embedding": [1.0] * 16,
        },
    )
    default_vector_links = (
        {"chunk_id": _CHUNK_ONE_ID, "span_id": _SPAN_ONE_ID, "ordinal_no": 0},
        {"chunk_id": _CHUNK_TWO_ID, "span_id": _SPAN_TWO_ID, "ordinal_no": 0},
    )
    default_tree_links = (
        {"node_id": _NODE_ONE_ID, "span_id": _SPAN_ONE_ID, "ordinal_no": 0},
        {"node_id": _NODE_TWO_ID, "span_id": _SPAN_TWO_ID, "ordinal_no": 0},
    )
    state = _admitted_state(spans)
    return E2aDesiredState(
        **{
            **state.__dict__,
            "vector_chunks": chunks,
            "vector_chunk_span_links": (
                default_vector_links if vector_links is None else vector_links
            ),
            "tree_nodes": nodes,
            "tree_node_span_links": (
                default_tree_links if tree_links is None else tree_links
            ),
        }
    )


def test_semantic_split_projects_generator_local_cluster_id_out_of_persisted_nodes() -> (
    None
):
    spans = (_span_one(), _span_two())
    generator_tree = TreeGenerator().generate_tree(
        _tree_generator_input(spans), version_id=UUID(_VERSION_ID)
    )

    assert any("cluster_id" in node for node in generator_tree["nodes"])
    desired = _builder().build(_source(spans))

    assert desired.tree_nodes
    assert all(set(node) == _PERSISTED_TREE_NODE_FIELDS for node in desired.tree_nodes)
    assert all("cluster_id" not in node for node in desired.tree_nodes)


def _write_raw_triplet(root: Path) -> None:
    raw = root / "raw"
    raw.mkdir()
    (raw / "guide.pair.json").write_text("{}", encoding="utf-8")
    (raw / "guide.md").write_text("---\ntype: raw\n---\nbody\n", encoding="utf-8")
    (raw / "guide.spans.json").write_text("{}", encoding="utf-8")


def _raw_snapshot() -> RawPairSnapshot:
    markdown = (
        "---\n" "type: raw\n" f"source_checksum: {_SOURCE_CHECKSUM}\n" "---\n" "body\n"
    ).encode("utf-8")
    return RawPairSnapshot(
        markdown_bytes=markdown,
        sidecar_bytes=b"{}",
        manifest=None,  # type: ignore[arg-type]
        frontmatter=MappingProxyType(
            {"type": "raw", "source_checksum": _SOURCE_CHECKSUM}
        ),
        body="body",
        sidecar=SpanSidecar(
            schema_version=1,
            doc_id=_DOCUMENT_ID,
            version_id=_VERSION_ID,
            spans=(
                SpanRecord(
                    _SPAN_ONE_ID,
                    7,
                    ("Guide", "Authority"),
                    0,
                    "Immutable raw pair text.",
                ),
            ),
        ),
    )


def test_public_admission_bridge_retains_immutable_raw_pair_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_triplet(tmp_path)
    snapshot = _raw_snapshot()
    monkeypatch.setattr(e2a_admission, "read_raw_pair", lambda *_: snapshot)

    with BundleAuthority(tmp_path) as authority:
        admitted = e2a_admission.admit_e2a_corpus(authority)
    assert admitted.canonical_spans == (
        E2aSpan(
            _DOCUMENT_ID,
            _VERSION_ID,
            _SPAN_ONE_ID,
            0,
            "Immutable raw pair text.",
        ),
    )

    bridge = getattr(e2a_admission, "admit_e2a_materialization_input", None)
    assert callable(bridge), (
        "Task #65 RED: admission must expose "
        "admit_e2a_materialization_input(authority), preserving admitted raw-pair "
        "page_no, heading_path, and source_checksum without caller reconstruction"
    )
    with BundleAuthority(tmp_path) as authority:
        source = bridge(authority)

    assert type(source) is e2a_reconciler.E2aMaterializationInput
    assert source.span_records[0]["page_no"] == 7
    assert source.span_records[0]["heading_path"] == "Guide > Authority"
    assert source.parent_source_checksums == {_VERSION_ID: _SOURCE_CHECKSUM}
    with pytest.raises(TypeError):
        source.span_records[0]["page_no"] = 8  # type: ignore[index]
    with pytest.raises(TypeError):
        source.parent_source_checksums[_VERSION_ID] = _CANONICAL_HASH  # type: ignore[index]

    desired = _builder().build(source)
    assert desired.vector_chunks[0]["page_no"] == 7
    assert desired.vector_chunks[0]["heading_path"] == "Guide > Authority"
    assert desired.sync_state_rows[0]["source_checksum"] == _SOURCE_CHECKSUM


def test_projection_validator_rejects_conflicting_vector_span_mappings_in_any_order() -> (
    None
):
    complete = _projection_state()
    assert {link["span_id"] for link in complete.vector_chunk_span_links} == {
        _SPAN_ONE_ID,
        _SPAN_TWO_ID,
    }
    conflicting = (
        {"chunk_id": _CHUNK_ONE_ID, "span_id": _SPAN_ONE_ID, "ordinal_no": 0},
        {"chunk_id": _CHUNK_TWO_ID, "span_id": _SPAN_ONE_ID, "ordinal_no": 0},
    )

    for links in (conflicting, tuple(reversed(conflicting))):
        with pytest.raises(ValueError):
            _projection_state(vector_links=links)


class _AmbiguousTreeGenerator:
    """A valid generator result whose only defect is a duplicate span owner."""

    def generate_tree(
        self, spans: list[dict[str, object]], *, version_id: UUID
    ) -> dict[str, list[dict[str, object]]]:
        span = spans[0]
        nodes = [
            {
                "node_id": UUID(_NODE_ONE_ID),
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "First",
                "heading_path": "Guide > First",
                "page_start": span["page_no"],
                "page_end": span["page_no"],
                "summary_text": "first",
            },
            {
                "node_id": UUID(_NODE_TWO_ID),
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Second",
                "heading_path": "Guide > Second",
                "page_start": span["page_no"],
                "page_end": span["page_no"],
                "summary_text": "second",
            },
        ]
        return {
            "nodes": nodes,
            "node_spans": [
                {
                    "node_id": UUID(_NODE_ONE_ID),
                    "span_id": span["span_id"],
                    "ordinal_no": 0,
                },
                {
                    "node_id": UUID(_NODE_TWO_ID),
                    "span_id": span["span_id"],
                    "ordinal_no": 0,
                },
            ],
        }


def test_builder_rejects_multiple_tree_nodes_for_one_span_before_chunk_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(e2a_reconciler, "TreeGenerator", _AmbiguousTreeGenerator)

    def should_not_embed(_: str) -> tuple[float, ...]:
        raise AssertionError(
            "chunk node_id derivation ran before rejecting ambiguous tree span ownership"
        )

    with pytest.raises(ValueError):
        _builder(embed_text=should_not_embed).build(_source((_span_one(),)))


@pytest.mark.parametrize("missing", ("vector", "tree"))
def test_projection_validator_requires_exact_vector_and_tree_link_coverage(
    missing: str,
) -> None:
    complete = _projection_state()
    assert {link["span_id"] for link in complete.vector_chunk_span_links} == {
        _SPAN_ONE_ID,
        _SPAN_TWO_ID,
    }
    assert {link["span_id"] for link in complete.tree_node_span_links} == {
        _SPAN_ONE_ID,
        _SPAN_TWO_ID,
    }

    if missing == "vector":
        incomplete = {
            "vector_links": (
                {
                    "chunk_id": _CHUNK_ONE_ID,
                    "span_id": _SPAN_ONE_ID,
                    "ordinal_no": 0,
                },
            )
        }
    else:
        incomplete = {
            "tree_links": (
                {"node_id": _NODE_ONE_ID, "span_id": _SPAN_ONE_ID, "ordinal_no": 0},
            )
        }

    with pytest.raises(ValueError):
        _projection_state(**incomplete)


def test_shuffled_equivalent_semantic_split_has_identical_persisted_projections() -> (
    None
):
    spans = (_span_one(), _span_two())
    first = _builder().build(_source(spans))
    shuffled = _builder().build(_source(tuple(reversed(spans))))

    assert tuple(node["node_id"] for node in first.tree_nodes) == tuple(
        node["node_id"] for node in shuffled.tree_nodes
    )
    assert first.tree_nodes == shuffled.tree_nodes
    assert first.tree_node_span_links == shuffled.tree_node_span_links
    assert first.vector_chunks == shuffled.vector_chunks
    assert first.vector_chunk_span_links == shuffled.vector_chunk_span_links
    assert {chunk["chunk_id"]: chunk["node_id"] for chunk in first.vector_chunks} == {
        chunk["chunk_id"]: chunk["node_id"] for chunk in shuffled.vector_chunks
    }
