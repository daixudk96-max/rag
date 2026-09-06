"""Closure validation for E2a's JSON materialization projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .e2a_contract_primitives import _digest, _uuid


_SYNC_FIELDS = frozenset(
    {
        "okf_file_path",
        "doc_id",
        "version_id",
        "source_checksum",
        "canonical_hash",
        "status",
        "materialization_owner",
    }
)
_CHUNK_FIELDS = frozenset(
    {
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
    }
)
_CHUNK_LINK_FIELDS = frozenset({"chunk_id", "span_id", "ordinal_no"})
_NODE_FIELDS = frozenset(
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
_NODE_LINK_FIELDS = frozenset({"node_id", "span_id", "ordinal_no"})


def validate_projection_graph(
    parents: Sequence[object],
    spans: Sequence[object],
    chunks: Sequence[object],
    chunk_links: Sequence[object],
    nodes: Sequence[object],
    node_links: Sequence[object],
    sync_rows: Sequence[object],
) -> None:
    """Require every persisted JSON projection to close over admitted parents."""
    parent_by_version = _parents_by_version(parents)
    span_versions = _span_versions(spans, parent_by_version)
    node_versions = _node_versions(nodes, parent_by_version)
    chunk_versions = _chunk_versions(chunks, parent_by_version, node_versions)
    linked_chunk_spans = _validate_links(
        chunk_links,
        fields=_CHUNK_LINK_FIELDS,
        left_name="chunk",
        left_versions=chunk_versions,
        span_versions=span_versions,
    )
    linked_node_spans = _validate_links(
        node_links,
        fields=_NODE_LINK_FIELDS,
        left_name="node",
        left_versions=node_versions,
        span_versions=span_versions,
    )
    if chunks or chunk_links:
        _require_exact_span_coverage(linked_chunk_spans, span_versions, "chunk")
    if nodes or node_links:
        _require_exact_span_coverage(linked_node_spans, span_versions, "node")
    _validate_sync_rows(sync_rows, parent_by_version)


def _parents_by_version(parents: Sequence[object]) -> Mapping[str, object]:
    result: dict[str, object] = {}
    for parent in parents:
        version_id = _attribute(parent, "version_id", "parent")
        if version_id in result:
            raise ValueError("duplicate parent version projection")
        result[version_id] = parent
    return result


def _span_versions(
    spans: Sequence[object], parent_by_version: Mapping[str, object]
) -> Mapping[str, str]:
    result: dict[str, str] = {}
    for span in spans:
        span_id = _attribute(span, "span_id", "span")
        version_id = _attribute(span, "version_id", "span")
        document_id = _attribute(span, "document_id", "span")
        parent = parent_by_version.get(version_id)
        if parent is None or document_id != _attribute(parent, "document_id", "parent"):
            raise ValueError("canonical span is outside the admitted parent graph")
        if span_id in result:
            raise ValueError("duplicate span projection")
        result[span_id] = version_id
    return result


def _node_versions(
    values: Sequence[object], parent_by_version: Mapping[str, object]
) -> Mapping[str, str]:
    rows = tuple(_row(value, _NODE_FIELDS, "tree node") for value in values)
    versions: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for row in rows:
        node_id = _uuid_value(row, "node_id", "tree node")
        version_id = _uuid_value(row, "version_id", "tree node")
        if version_id not in parent_by_version:
            raise ValueError("tree node version is outside the admitted parent graph")
        if node_id in versions:
            raise ValueError("duplicate tree node projection")
        versions[node_id] = version_id
        parents[node_id] = _optional_uuid(row, "parent_node_id", "tree node")
    for node_id, parent_id in parents.items():
        if parent_id is not None and versions.get(parent_id) != versions[node_id]:
            raise ValueError("tree parent is missing or crosses an admitted version")
    _assert_acyclic_forest(parents)
    return versions


def _chunk_versions(
    values: Sequence[object],
    parent_by_version: Mapping[str, object],
    node_versions: Mapping[str, str],
) -> Mapping[str, str]:
    result: dict[str, str] = {}
    orders: set[tuple[str, int]] = set()
    for value in values:
        row = _row(value, _CHUNK_FIELDS, "vector chunk")
        chunk_id = _uuid_value(row, "chunk_id", "vector chunk")
        version_id = _uuid_value(row, "version_id", "vector chunk")
        if version_id not in parent_by_version:
            raise ValueError(
                "vector chunk version is outside the admitted parent graph"
            )
        node_id = _optional_uuid(row, "node_id", "vector chunk")
        if node_id is not None and node_versions.get(node_id) != version_id:
            raise ValueError("vector chunk node is outside its admitted version")
        chunk_order = row["chunk_order"]
        if type(chunk_order) is not int or chunk_order < 0:
            raise ValueError("vector chunk ordinal is invalid")
        key = (version_id, chunk_order)
        if key in orders:
            raise ValueError("duplicate vector chunk ordinal")
        if chunk_id in result:
            raise ValueError("duplicate vector chunk projection")
        orders.add(key)
        result[chunk_id] = version_id
    return result


def _validate_links(
    values: Sequence[object],
    *,
    fields: frozenset[str],
    left_name: str,
    left_versions: Mapping[str, str],
    span_versions: Mapping[str, str],
) -> set[str]:
    key_field = f"{left_name}_id"
    pairs: set[tuple[str, str]] = set()
    ordinals: set[tuple[str, int]] = set()
    owners_by_span: dict[str, str] = {}
    for value in values:
        row = _row(value, fields, f"{left_name} span link")
        left_id = _uuid_value(row, key_field, f"{left_name} span link")
        span_id = _uuid_value(row, "span_id", f"{left_name} span link")
        ordinal = row["ordinal_no"]
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError(f"{left_name} span link ordinal is invalid")
        if left_versions.get(left_id) is None or span_versions.get(span_id) is None:
            raise ValueError(f"{left_name} span link is outside the admitted graph")
        if left_versions[left_id] != span_versions[span_id]:
            raise ValueError(f"{left_name} span link crosses admitted versions")
        if span_id in owners_by_span and owners_by_span[span_id] != left_id:
            raise ValueError(f"canonical span has multiple {left_name} projections")
        pair = (left_id, span_id)
        ordinal_key = (left_id, ordinal)
        if pair in pairs or ordinal_key in ordinals:
            raise ValueError(f"duplicate {left_name} span link projection")
        owners_by_span[span_id] = left_id
        pairs.add(pair)
        ordinals.add(ordinal_key)
    return set(owners_by_span)


def _require_exact_span_coverage(
    linked_spans: set[str], span_versions: Mapping[str, str], left_name: str
) -> None:
    if linked_spans != set(span_versions):
        raise ValueError(f"{left_name} span links do not cover canonical spans exactly")


def _validate_sync_rows(
    values: Sequence[object], parent_by_version: Mapping[str, object]
) -> None:
    rows_by_path: dict[str, Mapping[str, object]] = {}
    for value in values:
        row = _row(value, _SYNC_FIELDS, "sync projection")
        path = row["okf_file_path"]
        if type(path) is not str or not path:
            raise ValueError("sync projection path is invalid")
        document_id = _uuid_value(row, "doc_id", "sync projection")
        version_id = _uuid_value(row, "version_id", "sync projection")
        _digest(row["source_checksum"], "sync source checksum")
        _digest(row["canonical_hash"], "sync canonical hash")
        if row["status"] != "materialized":
            raise ValueError("sync projection status must be materialized")
        if row["materialization_owner"] != "e2a":
            raise ValueError("sync projection owner must be e2a")
        parent = parent_by_version.get(version_id)
        if (
            parent is None
            or path != _parent_text(parent, "relative_path")
            or document_id != _attribute(parent, "document_id", "parent")
            or row["canonical_hash"] != _parent_text(parent, "canonical_hash")
        ):
            raise ValueError("sync projection does not match its admitted parent")
        if path in rows_by_path:
            raise ValueError("duplicate sync projection path")
        rows_by_path[path] = row
    if len(rows_by_path) != len(values):
        raise ValueError("sync projection path uniqueness is invalid")


def _row(value: object, fields: frozenset[str], name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        raise ValueError(f"{name} projection fields are invalid")
    return value


def _attribute(value: object, name: str, context: str) -> str:
    try:
        identifier = getattr(value, name)
    except AttributeError:
        raise ValueError(f"{context} projection is invalid") from None
    _uuid(identifier, name)
    return identifier


def _parent_text(value: object, name: str) -> str:
    try:
        text = getattr(value, name)
    except AttributeError:
        raise ValueError("parent projection is invalid") from None
    if type(text) is not str or not text:
        raise ValueError("parent projection is invalid")
    return text


def _uuid_value(row: Mapping[str, object], field: str, context: str) -> str:
    value = row[field]
    if type(value) is not str:
        raise ValueError(f"{context} projection identifier is invalid")
    _uuid(value, field)
    return value


def _optional_uuid(row: Mapping[str, object], field: str, context: str) -> str | None:
    value = row[field]
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"{context} projection identifier is invalid")
    _uuid(value, field)
    return value


def _assert_acyclic_forest(parents: Mapping[str, str | None]) -> None:
    completed: set[str] = set()
    for start in parents:
        path: set[str] = set()
        node_id: str | None = start
        while node_id is not None and node_id not in completed:
            if node_id in path:
                raise ValueError("tree node projection contains a cycle")
            path.add(node_id)
            node_id = parents[node_id]
        completed.update(path)
