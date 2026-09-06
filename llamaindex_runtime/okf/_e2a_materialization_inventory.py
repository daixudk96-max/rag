"""Cursor-only scope discovery for E2a materialization reconciliation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from ._e2a_materialization_deletion_guards import (
    has_external_fact_dependency,
    validate_destructive_closure,
)
from ._e2a_materialization_values import SQL_NULL
from ._e2a_parentless_manual_scope import _load_parentless_manual_scope


class Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...

    def fetchone(self) -> Mapping[str, object] | None: ...


Scope = Mapping[str, tuple[Mapping[str, object], ...]]

_SCOPE_KEYS = (
    "canonical_spans",
    "vector_chunks",
    "vector_chunk_spans",
    "tree_nodes",
    "tree_node_spans",
    "entities",
    "relations",
    "evidence",
    "evidence_links",
    "okf_manual_fact_ownership",
    "okf_manual_evidence_targets",
    "okf_sync_state",
)
_SYNC_FIELDS = (
    "okf_file_path",
    "doc_id",
    "version_id",
    "source_checksum",
    "canonical_hash",
    "status",
    "materialization_owner",
)


def load_existing_scope(
    cursor: Cursor, desired: object
) -> dict[str, tuple[Mapping[str, object], ...]]:
    """Load E2a rows plus global manual facts without transaction ownership."""
    parent_version_ids = _parent_version_ids(desired)
    spans = _values(desired, "canonical_spans")
    chunks = _values(desired, "vector_chunks")
    nodes = _values(desired, "tree_nodes")
    evidence_objects = _values(desired, "evidence_objects")
    evidence_links = _values(desired, "evidence_links")
    ownership = _values(desired, "ownership_facts")
    entities = _values(desired, "manual_entities")
    relations = _values(desired, "manual_relations")

    span_ids = _identifiers(spans, "span_id")
    chunk_ids = _identifiers(chunks, "chunk_id")
    node_ids = _identifiers(nodes, "node_id")
    evidence_ids = _identifiers(evidence_objects, "evidence_id")
    evidence_link_ids = _identifiers(evidence_links, "evidence_link_id")
    ownership_ids = _identifiers(ownership, "ownership_id")
    entity_ids = _identifiers(entities, "fact_id")
    relation_ids = _identifiers(relations, "fact_id")
    version_ids = _scope_version_ids(cursor, parent_version_ids)

    scope: dict[str, tuple[Mapping[str, object], ...]] = {}
    scope["canonical_spans"] = _state_and_actual_rows(
        cursor,
        inventory_statement="SELECT span_id FROM canonical_spans WHERE version_id = ANY(%s)",
        inventory_parameters=(version_ids,),
        inventory_fields=("span_id",),
        actual_statement=(
            "SELECT span_id, version_id, span_kind, start_offset, end_offset, page_no, "
            "heading_path, raw_text FROM canonical_spans WHERE span_id = ANY(%s)"
        ),
        actual_ids=span_ids,
        actual_fields=(
            "span_id",
            "version_id",
            "span_kind",
            "start_offset",
            "end_offset",
            "page_no",
            "heading_path",
            "raw_text",
        ),
        key="span_id",
    )
    scope["vector_chunks"] = _state_and_actual_rows(
        cursor,
        inventory_statement=(
            "SELECT chunk_id, version_id, node_id FROM vector_chunks "
            "WHERE version_id = ANY(%s)"
        ),
        inventory_parameters=(version_ids,),
        inventory_fields=("chunk_id", "version_id"),
        actual_statement=(
            "SELECT chunk_id, version_id, chunk_type, chunk_order, token_count, text_preview, "
            "page_no, heading_path, node_id, embedding FROM vector_chunks "
            "WHERE chunk_id = ANY(%s)"
        ),
        actual_ids=chunk_ids,
        actual_fields=(
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
        ),
        key="chunk_id",
    )
    scope["tree_nodes"] = _state_and_actual_rows(
        cursor,
        inventory_statement=(
            "SELECT node_id, version_id, parent_node_id FROM tree_nodes "
            "WHERE version_id = ANY(%s)"
        ),
        inventory_parameters=(version_ids,),
        inventory_fields=("node_id", "version_id"),
        actual_statement=(
            "SELECT node_id, version_id, parent_node_id, node_type, level_no, title, "
            "heading_path, page_start, page_end, summary_text FROM tree_nodes "
            "WHERE node_id = ANY(%s)"
        ),
        actual_ids=node_ids,
        actual_fields=(
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
        ),
        key="node_id",
    )
    scope["vector_chunk_spans"] = _actual_rows(
        cursor,
        statement=(
            "SELECT link.chunk_id, link.span_id, link.ordinal_no "
            "FROM vector_chunk_spans AS link WHERE link.chunk_id = ANY(%s)"
        ),
        parameters=(chunk_ids,),
        required_fields=("chunk_id", "span_id", "ordinal_no"),
        needed=bool(chunk_ids),
    )
    scope["tree_node_spans"] = _actual_rows(
        cursor,
        statement=(
            "SELECT link.node_id, link.span_id, link.ordinal_no "
            "FROM tree_node_spans AS link WHERE link.node_id = ANY(%s)"
        ),
        parameters=(node_ids,),
        required_fields=("node_id", "span_id", "ordinal_no"),
        needed=bool(node_ids),
    )
    scope["evidence"] = _state_and_actual_rows(
        cursor,
        inventory_statement=(
            "SELECT evidence.evidence_id FROM evidence INNER JOIN okf_manual_evidence_targets "
            "AS target ON target.evidence_id = evidence.evidence_id "
            "AND target.version_id = evidence.version_id WHERE target.version_id = ANY(%s)"
        ),
        inventory_parameters=(version_ids,),
        inventory_fields=("evidence_id",),
        actual_statement="SELECT evidence_id, version_id FROM evidence WHERE evidence_id = ANY(%s)",
        actual_ids=evidence_ids,
        actual_fields=("evidence_id", "version_id"),
        key="evidence_id",
    )
    scope["evidence_links"] = (
        ()
        if not evidence_link_ids
        else _state_and_actual_rows(
            cursor,
            inventory_statement=(
                "SELECT evidence_link_id, source_kind, evidence_id FROM evidence_links "
                "WHERE version_id = ANY(%s) AND source_kind = %s"
            ),
            inventory_parameters=(version_ids, "manual_okf"),
            inventory_fields=("evidence_link_id", "source_kind", "evidence_id"),
            actual_statement=(
                "SELECT evidence_link_id, version_id, entity_id, relation_id, span_id, source_kind, "
                "confidence_score, evidence_id, ownership_id, ownership_scope_version_id, "
                "manual_entity_id, manual_relation_id FROM evidence_links "
                "WHERE evidence_link_id = ANY(%s)"
            ),
            actual_ids=evidence_link_ids,
            actual_fields=(
                "evidence_link_id",
                "version_id",
                "entity_id",
                "relation_id",
                "span_id",
                "source_kind",
                "confidence_score",
                "evidence_id",
                "ownership_id",
                "ownership_scope_version_id",
                "manual_entity_id",
                "manual_relation_id",
            ),
            key="evidence_link_id",
        )
    )
    scope["okf_manual_evidence_targets"] = _actual_rows(
        cursor,
        statement=(
            "SELECT version_id, evidence_id, entity_id, relation_id "
            "FROM okf_manual_evidence_targets WHERE evidence_id = ANY(%s)"
        ),
        parameters=(evidence_ids,),
        required_fields=("version_id", "evidence_id", "entity_id", "relation_id"),
        needed=bool(evidence_ids),
    )
    scope["okf_manual_fact_ownership"] = _state_and_actual_rows(
        cursor,
        inventory_statement=(
            "SELECT ownership_id, fact_kind, fact_id FROM okf_manual_fact_ownership "
            "WHERE version_id = ANY(%s)"
        ),
        inventory_parameters=(version_ids,),
        inventory_fields=("ownership_id", "fact_kind", "fact_id"),
        actual_statement=(
            "SELECT ownership_id, okf_relative_path, fact_kind, fact_id, entity_id, relation_id, "
            "source_digest, document_id, version_id, scope_version_id "
            "FROM okf_manual_fact_ownership WHERE ownership_id = ANY(%s)"
        ),
        actual_ids=ownership_ids,
        actual_fields=(
            "ownership_id",
            "okf_relative_path",
            "fact_kind",
            "fact_id",
            "entity_id",
            "relation_id",
            "source_digest",
            "document_id",
            "version_id",
            "scope_version_id",
        ),
        key="ownership_id",
        include_actual_outside_inventory=True,
    )
    scope["okf_sync_state"] = _actual_rows(
        cursor,
        statement=(
            "SELECT okf_file_path, doc_id, version_id, source_checksum, canonical_hash, status, "
            "materialization_owner FROM okf_sync_state WHERE version_id = ANY(%s) "
            "AND materialization_owner = %s"
        ),
        parameters=(version_ids, "e2a"),
        required_fields=_SYNC_FIELDS,
        needed=bool(version_ids),
    )
    scope["entities"] = _actual_rows(
        cursor,
        statement=(
            "SELECT entity_id, entity_key, entity_type, canonical_name FROM entities "
            "WHERE entity_id = ANY(%s)"
        ),
        parameters=(entity_ids,),
        required_fields=("entity_id", "entity_key", "entity_type", "canonical_name"),
        needed=bool(entity_ids),
    )
    scope["relations"] = _relation_rows(
        cursor,
        statement=(
            "SELECT relation_id, relation_key, relation_type, source_entity_id, target_entity_id, "
            "negation, condition, direction, confidence, qualifiers, "
            "qualifiers IS NULL AS qualifiers_is_sql_null FROM relations "
            "WHERE relation_id = ANY(%s)"
        ),
        parameters=(relation_ids,),
        needed=bool(relation_ids),
    )
    global_manual_scope = _load_parentless_manual_scope(
        cursor, desired, scope_keys=_SCOPE_KEYS
    )
    for key, identifier in (
        ("okf_manual_fact_ownership", "ownership_id"),
        ("entities", "entity_id"),
        ("relations", "relation_id"),
    ):
        scope[key] = _merge_by_key(
            (*scope[key], *global_manual_scope[key]), (identifier,)
        )
    return scope


def stale_ids(
    existing: Sequence[Mapping[str, object]], values: Sequence[object], field: str
) -> list[str]:
    if type(field) is not str or not field:
        raise ValueError("materialization identifier field is invalid")
    desired_ids = {_desired_identifier(value, field) for value in values}
    existing_ids = {_identifier_from_row(row, field) for row in existing}
    return sorted(existing_ids - desired_ids)


def mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("desired materialization row is invalid")
    return value


def fields(row: Mapping[str, object], *required: str) -> Mapping[str, object]:
    if any(field not in row for field in required):
        raise ValueError("desired materialization row is missing required fields")
    return {field: row[field] for field in required}


def string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("materialization identifier is invalid")
    return value


def string_or_none(value: object) -> str | None:
    return None if value is None else string(value)


def _state_and_actual_rows(
    cursor: Cursor,
    *,
    inventory_statement: str,
    inventory_parameters: object,
    inventory_fields: tuple[str, ...],
    actual_statement: str,
    actual_ids: tuple[str, ...],
    actual_fields: tuple[str, ...],
    key: str,
    include_actual_outside_inventory: bool = False,
) -> tuple[Mapping[str, object], ...]:
    inventory = _minimal_inventory_rows(
        cursor, inventory_statement, inventory_parameters, inventory_fields
    )
    present = {_identifier_from_row(row, key) for row in inventory}
    actual_ids_present = (
        actual_ids
        if include_actual_outside_inventory
        else tuple(value for value in actual_ids if value in present)
    )
    actual = _actual_rows(
        cursor,
        statement=actual_statement,
        parameters=(actual_ids_present,),
        required_fields=actual_fields,
        needed=bool(actual_ids_present),
    )
    return _merge_by_key((*inventory, *actual), (key,))


def _minimal_inventory_rows(
    cursor: Cursor,
    statement: str,
    parameters: object,
    required_fields: tuple[str, ...],
) -> tuple[Mapping[str, object], ...]:
    return _projected_rows(
        cursor,
        statement,
        parameters,
        required_fields,
        exact_shape=False,
        error="cursor returned a malformed inventory row",
    )


def _relation_rows(
    cursor: Cursor,
    *,
    statement: str,
    parameters: object,
    needed: bool,
) -> tuple[Mapping[str, object], ...]:
    fields = (
        "relation_id",
        "relation_key",
        "relation_type",
        "source_entity_id",
        "target_entity_id",
        "negation",
        "condition",
        "direction",
        "confidence",
        "qualifiers",
        "qualifiers_is_sql_null",
    )
    rows = _actual_rows(
        cursor,
        statement=statement,
        parameters=parameters,
        required_fields=fields,
        needed=needed,
    )
    normalized: list[Mapping[str, object]] = []
    for row in rows:
        sql_null = row["qualifiers_is_sql_null"]
        if type(sql_null) is not bool or (sql_null and row["qualifiers"] is not None):
            raise ValueError("cursor returned a malformed relation qualifier row")
        normalized.append(
            {
                field: SQL_NULL if field == "qualifiers" and sql_null else row[field]
                for field in fields
                if field != "qualifiers_is_sql_null"
            }
        )
    return tuple(normalized)


def _actual_rows(
    cursor: Cursor,
    *,
    statement: str,
    parameters: object,
    required_fields: tuple[str, ...],
    needed: bool,
) -> tuple[Mapping[str, object], ...]:
    if not needed:
        return ()
    return _projected_rows(
        cursor,
        statement,
        parameters,
        required_fields,
        exact_shape=True,
        error="cursor returned a malformed full materialization row",
    )


def _array_parameters(parameters: object) -> object:
    if type(parameters) is not tuple:
        return parameters
    return tuple(list(value) if type(value) is tuple else value for value in parameters)


def _projected_rows(
    cursor: Cursor,
    statement: str,
    parameters: object,
    required_fields: tuple[str, ...],
    *,
    exact_shape: bool,
    error: str,
) -> tuple[Mapping[str, object], ...]:
    cursor.execute(statement, _array_parameters(parameters))
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("cursor returned an invalid result set")
    expected = frozenset(required_fields)
    result: list[Mapping[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping) or any(
            field not in row for field in required_fields
        ):
            raise ValueError(error)
        if exact_shape and frozenset(row) != expected:
            raise ValueError(error)
        result.append(row)
    return tuple(result)


def _parent_version_ids(desired: object) -> tuple[str, ...]:
    parents = _values(desired, "parents")
    return tuple(
        sorted({_desired_identifier(parent, "version_id") for parent in parents})
    )


def _scope_version_ids(
    cursor: Cursor, parent_version_ids: tuple[str, ...]
) -> tuple[str, ...]:
    history_rows = _actual_rows(
        cursor,
        statement=(
            "SELECT version_id, materialization_owner FROM okf_sync_state "
            "WHERE materialization_owner = %s"
        ),
        parameters=("e2a",),
        required_fields=("version_id", "materialization_owner"),
        needed=True,
    )
    marker_version_ids = frozenset(
        _identifier_from_row(row, "version_id") for row in history_rows
    )
    if any(row["materialization_owner"] != "e2a" for row in history_rows):
        raise ValueError("sync history contains a non-E2a owner")
    return tuple(sorted(frozenset(parent_version_ids) | marker_version_ids))


def _values(desired: object, field: str) -> Sequence[object]:
    try:
        values = getattr(desired, field)
    except AttributeError:
        raise ValueError("desired materialization state is invalid") from None
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError("desired materialization state is invalid")
    return values


def _merge_by_key(
    rows: Sequence[Mapping[str, object]], key_fields: tuple[str, ...]
) -> tuple[Mapping[str, object], ...]:
    merged: dict[tuple[str, ...], Mapping[str, object]] = {}
    for row in rows:
        key = tuple(_identifier_from_row(row, field) for field in key_fields)
        merged[key] = row
    return tuple(merged[key] for key in sorted(merged))


def _identifiers(values: Sequence[object], field: str) -> tuple[str, ...]:
    return tuple(sorted({_desired_identifier(value, field) for value in values}))


def _desired_identifier(value: object, field: str) -> str:
    if isinstance(value, Mapping):
        return _identifier_from_row(value, field)
    if field not in {
        "document_id",
        "version_id",
        "span_id",
        "chunk_id",
        "node_id",
        "fact_id",
        "evidence_id",
        "evidence_link_id",
        "ownership_id",
    }:
        raise ValueError(f"desired materialization value does not expose {field}")
    try:
        identifier = getattr(value, field)
    except AttributeError:
        raise ValueError(
            f"desired materialization value does not expose {field}"
        ) from None
    return string(identifier)


def _identifier_from_row(row: Mapping[str, object], field: str) -> str:
    if field not in row:
        raise ValueError("materialization state row is missing an identifier")
    return string(row[field])


__all__ = [
    "Cursor",
    "Scope",
    "fields",
    "has_external_fact_dependency",
    "load_existing_scope",
    "mapping",
    "stale_ids",
    "string",
    "string_or_none",
    "validate_destructive_closure",
]
