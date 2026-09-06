"""Private desired-state upsert orchestration for E2a materialization."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from ._e2a_materialization_inventory import Cursor
from .e2a_contracts import DmlRecorder, E2aDesiredState, E2aManualFact


class _Upsert(Protocol):
    def __call__(
        self,
        cursor: Cursor,
        table: str,
        row: Mapping[str, object],
        key_fields: tuple[str, ...],
        mutable_fields: tuple[str, ...],
        existing: Mapping[str, object] | None,
        recorder: DmlRecorder,
        *,
        casts: Mapping[str, str] | None = None,
    ) -> None: ...


_Links = Callable[
    [
        Cursor,
        str,
        Sequence[object],
        Sequence[Mapping[str, object]],
        tuple[str, ...],
        tuple[str, ...],
        DmlRecorder,
    ],
    None,
]


def _canonical_spans(
    cursor: Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    *,
    span_metadata: Callable[[E2aDesiredState], Mapping[str, tuple[object, object]]],
    indexed: Callable[
        [Sequence[Mapping[str, object]], str], Mapping[str, Mapping[str, object]]
    ],
    upsert: _Upsert,
) -> None:
    metadata = span_metadata(desired)
    old = indexed(existing["canonical_spans"], "span_id")
    for span in desired.canonical_spans:
        page_no, heading_path = metadata.get(span.span_id, (None, None))
        row = {
            "span_id": span.span_id,
            "version_id": span.version_id,
            "span_kind": "paragraph",
            "start_offset": span.offset,
            "end_offset": span.offset + len(span.text),
            "page_no": page_no,
            "heading_path": heading_path,
            "raw_text": span.text,
        }
        upsert(
            cursor,
            "canonical_spans",
            row,
            ("span_id",),
            (
                "version_id",
                "span_kind",
                "start_offset",
                "end_offset",
                "page_no",
                "heading_path",
                "raw_text",
            ),
            old.get(span.span_id),
            recorder,
        )


def _tree(
    cursor: Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    *,
    parent_first: Callable[[Sequence[object]], tuple[object, ...]],
    mapping: Callable[[object], Mapping[str, object]],
    fields: Callable[..., Mapping[str, object]],
    string: Callable[[object], str],
    indexed: Callable[
        [Sequence[Mapping[str, object]], str], Mapping[str, Mapping[str, object]]
    ],
    upsert: _Upsert,
    upsert_links: _Links,
) -> None:
    old_nodes = indexed(existing["tree_nodes"], "node_id")
    for node in parent_first(desired.tree_nodes):
        row = mapping(node)
        projected = fields(
            row,
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
        )
        upsert(
            cursor,
            "tree_nodes",
            projected,
            ("node_id",),
            (
                "version_id",
                "parent_node_id",
                "node_type",
                "level_no",
                "title",
                "heading_path",
                "page_start",
                "page_end",
                "summary_text",
            ),
            old_nodes.get(string(row.get("node_id"))),
            recorder,
        )
    upsert_links(
        cursor,
        "tree_node_spans",
        desired.tree_node_span_links,
        existing["tree_node_spans"],
        ("node_id", "span_id"),
        ("ordinal_no",),
        recorder,
    )


def _chunks(
    cursor: Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    *,
    mapping: Callable[[object], Mapping[str, object]],
    fields: Callable[..., Mapping[str, object]],
    string: Callable[[object], str],
    indexed: Callable[
        [Sequence[Mapping[str, object]], str], Mapping[str, Mapping[str, object]]
    ],
    upsert: _Upsert,
    upsert_links: _Links,
) -> None:
    old = indexed(existing["vector_chunks"], "chunk_id")
    for value in desired.vector_chunks:
        row = fields(
            mapping(value),
            "chunk_id",
            "version_id",
            "chunk_type",
            "chunk_order",
            "token_count",
            "text_preview",
            "page_no",
            "heading_path",
            "node_id",
            "embedding",
        )
        upsert(
            cursor,
            "vector_chunks",
            row,
            ("chunk_id",),
            (
                "version_id",
                "chunk_type",
                "chunk_order",
                "token_count",
                "text_preview",
                "page_no",
                "heading_path",
                "node_id",
                "embedding",
            ),
            old.get(string(row.get("chunk_id"))),
            recorder,
            casts={"embedding": "vector"},
        )
    upsert_links(
        cursor,
        "vector_chunk_spans",
        desired.vector_chunk_span_links,
        existing["vector_chunk_spans"],
        ("chunk_id", "span_id"),
        ("ordinal_no",),
        recorder,
    )


def _manual_facts(
    cursor: Cursor,
    desired: E2aDesiredState,
    existing: Mapping[str, tuple[Mapping[str, object], ...]],
    recorder: DmlRecorder,
    *,
    natural_object: Callable[[E2aManualFact], Mapping[str, object]],
    relation_payload: Callable[[E2aManualFact], Mapping[str, object]],
    indexed: Callable[
        [Sequence[Mapping[str, object]], str], Mapping[str, Mapping[str, object]]
    ],
    upsert: _Upsert,
) -> None:
    old_entities = indexed(existing["entities"], "entity_id")
    for fact in desired.manual_entities:
        natural = natural_object(fact)
        row = {
            "entity_id": fact.fact_id,
            "entity_key": fact.natural_key,
            "entity_type": natural.get("entity_type"),
            "canonical_name": natural.get("title"),
        }
        upsert(
            cursor,
            "entities",
            row,
            ("entity_id",),
            ("entity_key", "entity_type", "canonical_name"),
            old_entities.get(fact.fact_id),
            recorder,
        )
    old_relations = indexed(existing["relations"], "relation_id")
    for fact in desired.manual_relations:
        relation_row: Mapping[str, object] = relation_payload(fact)
        upsert(
            cursor,
            "relations",
            relation_row,
            ("relation_id",),
            (
                "relation_key",
                "relation_type",
                "source_entity_id",
                "target_entity_id",
                "negation",
                "condition",
                "direction",
                "confidence",
                "qualifiers",
            ),
            old_relations.get(fact.fact_id),
            recorder,
            casts={"qualifiers": "jsonb"},
        )
    old_owners = indexed(existing["okf_manual_fact_ownership"], "ownership_id")
    for owner in desired.ownership_facts:
        row = {
            "ownership_id": owner.ownership_id,
            "okf_relative_path": owner.relative_path,
            "fact_kind": owner.fact_kind,
            "fact_id": owner.fact_id,
            "entity_id": owner.fact_id if owner.fact_kind == "entity" else None,
            "relation_id": owner.fact_id if owner.fact_kind == "relation" else None,
            "source_digest": owner.source_digest,
            "document_id": owner.document_id,
            "version_id": owner.version_id,
            "scope_version_id": owner.scope_version_id,
        }
        upsert(
            cursor,
            "okf_manual_fact_ownership",
            row,
            ("ownership_id",),
            tuple(key for key in row if key != "ownership_id"),
            old_owners.get(owner.ownership_id),
            recorder,
        )
