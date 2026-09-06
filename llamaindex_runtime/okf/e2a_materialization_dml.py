"""Closed, cursor-only DML primitives for E2a materialization."""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from numbers import Real
from types import MappingProxyType
from typing import Protocol, cast

from ._e2a_materialization_values import COMMANDS, DmlTemplate, SQL_NULL
from ._e2a_postgres_semantics import _normalize_numeric
from .e2a_contracts import DmlRecorder


class Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...
    def fetchone(self) -> Mapping[str, object] | None: ...


@dataclass(frozen=True)
class _UpsertSpec:
    table: str
    key_fields: tuple[str, ...]
    mutable_fields: tuple[str, ...]
    casts: Mapping[str, str]
    statement: str

    @property
    def fields(self) -> tuple[str, ...]:
        return (*self.key_fields, *self.mutable_fields)


@dataclass(frozen=True)
class _PreparedValue:
    comparable: tuple[str, object]
    binding: object


@dataclass(frozen=True)
class _JsonArray:
    values: tuple[object, ...]


@dataclass(frozen=True)
class _JsonObject:
    items: tuple[tuple[str, object], ...]


_CAST_FRAGMENTS = MappingProxyType({"jsonb": "jsonb", "vector": "vector"})
_EMPTY_CASTS: Mapping[str, str] = MappingProxyType({})

# Global primary-key tables that require scope guard and RETURNING acknowledgement
_GLOBAL_PRIMARY_KEY_TABLES: frozenset[str] = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "tree_nodes",
        "evidence",
        "evidence_links",
    }
)

# Global tables require version_id for scope enforcement
_GLOBAL_SCOPE_REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "tree_nodes",
        "evidence",
        "evidence_links",
    }
)


_UPSERT_SPECS: tuple[_UpsertSpec, ...] = (
    _UpsertSpec(
        "canonical_spans",
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
        _EMPTY_CASTS,
        "INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, "
        "end_offset, page_no, heading_path, raw_text) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (span_id) DO UPDATE SET "
        "version_id = EXCLUDED.version_id, span_kind = EXCLUDED.span_kind, "
        "start_offset = EXCLUDED.start_offset, end_offset = EXCLUDED.end_offset, "
        "page_no = EXCLUDED.page_no, heading_path = EXCLUDED.heading_path, "
        "raw_text = EXCLUDED.raw_text WHERE "
        "canonical_spans.version_id = EXCLUDED.version_id "
        "RETURNING 1",
    ),
    _UpsertSpec(
        "vector_chunks",
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
        MappingProxyType({"embedding": "vector"}),
        "INSERT INTO vector_chunks (chunk_id, version_id, chunk_type, chunk_order, "
        "token_count, text_preview, page_no, heading_path, node_id, embedding) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT (chunk_id) "
        "DO UPDATE SET version_id = EXCLUDED.version_id, chunk_type = EXCLUDED.chunk_type, "
        "chunk_order = EXCLUDED.chunk_order, token_count = EXCLUDED.token_count, "
        "text_preview = EXCLUDED.text_preview, page_no = EXCLUDED.page_no, "
        "heading_path = EXCLUDED.heading_path, node_id = EXCLUDED.node_id, "
        "embedding = EXCLUDED.embedding WHERE "
        "vector_chunks.version_id = EXCLUDED.version_id "
        "RETURNING 1",
    ),
    _UpsertSpec(
        "vector_chunk_spans",
        ("chunk_id", "span_id"),
        ("ordinal_no",),
        _EMPTY_CASTS,
        "INSERT INTO vector_chunk_spans (chunk_id, span_id, ordinal_no) VALUES "
        "(%s, %s, %s) ON CONFLICT (chunk_id, span_id) DO UPDATE SET "
        "ordinal_no = EXCLUDED.ordinal_no WHERE "
        "vector_chunk_spans.ordinal_no IS DISTINCT FROM EXCLUDED.ordinal_no",
    ),
    _UpsertSpec(
        "tree_nodes",
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
        _EMPTY_CASTS,
        "INSERT INTO tree_nodes (node_id, version_id, parent_node_id, node_type, level_no, "
        "title, heading_path, page_start, page_end, summary_text) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (node_id) DO UPDATE SET "
        "version_id = EXCLUDED.version_id, parent_node_id = EXCLUDED.parent_node_id, "
        "node_type = EXCLUDED.node_type, level_no = EXCLUDED.level_no, title = EXCLUDED.title, "
        "heading_path = EXCLUDED.heading_path, page_start = EXCLUDED.page_start, "
        "page_end = EXCLUDED.page_end, summary_text = EXCLUDED.summary_text WHERE "
        "tree_nodes.version_id = EXCLUDED.version_id "
        "RETURNING 1",
    ),
    _UpsertSpec(
        "tree_node_spans",
        ("node_id", "span_id"),
        ("ordinal_no",),
        _EMPTY_CASTS,
        "INSERT INTO tree_node_spans (node_id, span_id, ordinal_no) VALUES "
        "(%s, %s, %s) ON CONFLICT (node_id, span_id) DO UPDATE SET "
        "ordinal_no = EXCLUDED.ordinal_no WHERE "
        "tree_node_spans.ordinal_no IS DISTINCT FROM EXCLUDED.ordinal_no",
    ),
    _UpsertSpec(
        "entities",
        ("entity_id",),
        ("entity_key", "entity_type", "canonical_name"),
        _EMPTY_CASTS,
        "INSERT INTO entities (entity_id, entity_key, entity_type, canonical_name) VALUES "
        "(%s, %s, %s, %s) ON CONFLICT (entity_id) DO UPDATE SET "
        "entity_key = EXCLUDED.entity_key, entity_type = EXCLUDED.entity_type, "
        "canonical_name = EXCLUDED.canonical_name WHERE "
        "entities.entity_key IS DISTINCT FROM EXCLUDED.entity_key OR "
        "entities.entity_type IS DISTINCT FROM EXCLUDED.entity_type OR "
        "entities.canonical_name IS DISTINCT FROM EXCLUDED.canonical_name",
    ),
    _UpsertSpec(
        "relations",
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
        MappingProxyType({"qualifiers": "jsonb"}),
        "INSERT INTO relations (relation_id, relation_key, relation_type, source_entity_id, "
        "target_entity_id, negation, condition, direction, confidence, qualifiers) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (relation_id) "
        "DO UPDATE SET relation_key = EXCLUDED.relation_key, "
        "relation_type = EXCLUDED.relation_type, source_entity_id = EXCLUDED.source_entity_id, "
        "target_entity_id = EXCLUDED.target_entity_id, negation = EXCLUDED.negation, "
        "condition = EXCLUDED.condition, direction = EXCLUDED.direction, "
        "confidence = EXCLUDED.confidence, qualifiers = EXCLUDED.qualifiers WHERE "
        "relations.relation_key IS DISTINCT FROM EXCLUDED.relation_key OR "
        "relations.relation_type IS DISTINCT FROM EXCLUDED.relation_type OR "
        "relations.source_entity_id IS DISTINCT FROM EXCLUDED.source_entity_id OR "
        "relations.target_entity_id IS DISTINCT FROM EXCLUDED.target_entity_id OR "
        "relations.negation IS DISTINCT FROM EXCLUDED.negation OR "
        "relations.condition IS DISTINCT FROM EXCLUDED.condition OR "
        "relations.direction IS DISTINCT FROM EXCLUDED.direction OR "
        "relations.confidence IS DISTINCT FROM EXCLUDED.confidence OR "
        "relations.qualifiers IS DISTINCT FROM EXCLUDED.qualifiers",
    ),
    _UpsertSpec(
        "relations",
        ("relation_id",),
        ("confidence",),
        _EMPTY_CASTS,
        "INSERT INTO relations (relation_id, confidence) VALUES (%s, %s) "
        "ON CONFLICT (relation_id) DO UPDATE SET confidence = EXCLUDED.confidence WHERE "
        "relations.confidence IS DISTINCT FROM EXCLUDED.confidence",
    ),
    _UpsertSpec(
        "relations",
        ("relation_id",),
        ("qualifiers",),
        MappingProxyType({"qualifiers": "jsonb"}),
        "INSERT INTO relations (relation_id, qualifiers) VALUES (%s, %s::jsonb) "
        "ON CONFLICT (relation_id) DO UPDATE SET qualifiers = EXCLUDED.qualifiers WHERE "
        "relations.qualifiers IS DISTINCT FROM EXCLUDED.qualifiers",
    ),
    _UpsertSpec(
        "okf_manual_fact_ownership",
        ("ownership_id",),
        (
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
        _EMPTY_CASTS,
        "INSERT INTO okf_manual_fact_ownership (ownership_id, okf_relative_path, fact_kind, "
        "fact_id, entity_id, relation_id, source_digest, document_id, version_id, "
        "scope_version_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (ownership_id) DO UPDATE SET "
        "okf_relative_path = EXCLUDED.okf_relative_path, fact_kind = EXCLUDED.fact_kind, "
        "fact_id = EXCLUDED.fact_id, entity_id = EXCLUDED.entity_id, "
        "relation_id = EXCLUDED.relation_id, source_digest = EXCLUDED.source_digest, "
        "document_id = EXCLUDED.document_id, version_id = EXCLUDED.version_id, "
        "scope_version_id = EXCLUDED.scope_version_id WHERE "
        "okf_manual_fact_ownership.okf_relative_path "
        "IS DISTINCT FROM EXCLUDED.okf_relative_path OR "
        "okf_manual_fact_ownership.fact_kind IS DISTINCT FROM EXCLUDED.fact_kind OR "
        "okf_manual_fact_ownership.fact_id IS DISTINCT FROM EXCLUDED.fact_id OR "
        "okf_manual_fact_ownership.entity_id IS DISTINCT FROM EXCLUDED.entity_id OR "
        "okf_manual_fact_ownership.relation_id IS DISTINCT FROM EXCLUDED.relation_id OR "
        "okf_manual_fact_ownership.source_digest IS DISTINCT FROM EXCLUDED.source_digest OR "
        "okf_manual_fact_ownership.document_id IS DISTINCT FROM EXCLUDED.document_id OR "
        "okf_manual_fact_ownership.version_id IS DISTINCT FROM EXCLUDED.version_id OR "
        "okf_manual_fact_ownership.scope_version_id "
        "IS DISTINCT FROM EXCLUDED.scope_version_id",
    ),
    _UpsertSpec(
        "evidence",
        ("evidence_id",),
        ("version_id",),
        _EMPTY_CASTS,
        "INSERT INTO evidence (evidence_id, version_id) VALUES (%s, %s) "
        "ON CONFLICT (evidence_id) DO UPDATE SET version_id = EXCLUDED.version_id WHERE "
        "evidence.version_id = EXCLUDED.version_id "
        "RETURNING 1",
    ),
    _UpsertSpec(
        "evidence_links",
        ("evidence_link_id",),
        (
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
        _EMPTY_CASTS,
        "INSERT INTO evidence_links (evidence_link_id, version_id, entity_id, relation_id, "
        "span_id, source_kind, confidence_score, evidence_id, ownership_id, "
        "ownership_scope_version_id, manual_entity_id, manual_relation_id) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (evidence_link_id) DO UPDATE SET version_id = EXCLUDED.version_id, "
        "entity_id = EXCLUDED.entity_id, relation_id = EXCLUDED.relation_id, "
        "span_id = EXCLUDED.span_id, source_kind = EXCLUDED.source_kind, "
        "confidence_score = EXCLUDED.confidence_score, evidence_id = EXCLUDED.evidence_id, "
        "ownership_id = EXCLUDED.ownership_id, "
        "ownership_scope_version_id = EXCLUDED.ownership_scope_version_id, "
        "manual_entity_id = EXCLUDED.manual_entity_id, "
        "manual_relation_id = EXCLUDED.manual_relation_id WHERE "
        "evidence_links.version_id = EXCLUDED.version_id "
        "AND evidence_links.source_kind = 'manual_okf' "
        "RETURNING 1",
    ),
    _UpsertSpec(
        "okf_manual_evidence_targets",
        ("version_id", "evidence_id"),
        ("entity_id", "relation_id"),
        _EMPTY_CASTS,
        "INSERT INTO okf_manual_evidence_targets (version_id, evidence_id, entity_id, "
        "relation_id) VALUES (%s, %s, %s, %s) ON CONFLICT (version_id, evidence_id) "
        "DO UPDATE SET entity_id = EXCLUDED.entity_id, relation_id = EXCLUDED.relation_id "
        "WHERE okf_manual_evidence_targets.entity_id IS DISTINCT FROM EXCLUDED.entity_id OR "
        "okf_manual_evidence_targets.relation_id IS DISTINCT FROM EXCLUDED.relation_id",
    ),
)


def upsert_if_changed(
    cursor: Cursor,
    table: str,
    row: Mapping[str, object],
    key_fields: tuple[str, ...],
    mutable_fields: tuple[str, ...],
    existing: Mapping[str, object] | None,
    recorder: DmlRecorder,
    *,
    casts: Mapping[str, str] | None = None,
) -> None:
    """Issue only a closed-spec upsert when its persisted projection differs."""
    row_snapshot = _snapshot_row(row)
    existing_snapshot = None if existing is None else _snapshot_row(existing)
    cast_snapshot = _snapshot_casts(casts)
    spec = _upsert_spec(table, key_fields, mutable_fields, cast_snapshot)
    _validate_projection_row(row_snapshot, spec.fields)
    if existing_snapshot is not None:
        _validate_projection_row(existing_snapshot, spec.fields)
    _validate_relation_qualifiers(spec, row_snapshot)
    prepared_row = _prepare_row(row_snapshot, spec, persisted=False)
    prepared_existing = (
        None
        if existing_snapshot is None
        else _prepare_row(existing_snapshot, spec, persisted=True)
    )
    if prepared_existing is not None and _same_fields(
        prepared_existing, prepared_row, spec.fields
    ):
        return
    _issue(
        cursor,
        table=spec.table,
        operation="INSERT",
        statement=spec.statement,
        parameters=tuple(prepared_row[field].binding for field in spec.fields),
        recorder=recorder,
    )


def execute_template(
    cursor: Cursor,
    template: DmlTemplate,
    parameters: object,
    recorder: DmlRecorder,
) -> None:
    """Execute one module-owned DML template with caller-supplied bind values."""
    if type(template) is not DmlTemplate:
        raise ValueError("forbidden DML boundary")
    command = COMMANDS[template]
    _issue(
        cursor,
        table=command.table,
        operation=command.operation,
        statement=command.statement,
        parameters=parameters,
        recorder=recorder,
    )


def _issue(
    cursor: Cursor,
    *,
    table: str,
    operation: str,
    statement: str,
    parameters: object,
    recorder: DmlRecorder,
) -> None:
    cursor.execute(statement, parameters)
    recorder.record_issued(table=table, operation=operation)
    # Validate RETURNING acknowledgement for global primary-key tables
    if operation == "INSERT" and "RETURNING" in statement.upper():
        if table in _GLOBAL_PRIMARY_KEY_TABLES:
            row = cursor.fetchone()
            if row is None:
                raise ValueError(
                    f"global {table} upsert conflict: another scope owns the row"
                )


def _upsert_spec(
    table: object,
    key_fields: object,
    mutable_fields: object,
    casts: Mapping[str, str],
) -> _UpsertSpec:
    if (
        type(table) is not str
        or type(key_fields) is not tuple
        or type(mutable_fields) is not tuple
    ):
        raise ValueError("upsert projection is invalid")
    for spec in _UPSERT_SPECS:
        if (
            spec.table == table
            and spec.key_fields == key_fields
            and spec.mutable_fields == mutable_fields
            and dict(spec.casts) == dict(casts)
        ):
            # Reject embedding-only vector_chunks projection without version scope
            if table == "vector_chunks" and "version_id" not in mutable_fields:
                raise ValueError(
                    "upsert projection is invalid: global vector_chunks requires version_id scope"
                )
            return spec
    raise ValueError("upsert projection is invalid")


def _snapshot_row(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("upsert projection is invalid")
    try:
        return MappingProxyType(dict(value.items()))
    except (TypeError, ValueError):
        raise ValueError("upsert projection is invalid") from None


def _snapshot_casts(value: Mapping[str, str] | None) -> Mapping[str, str]:
    if value is None:
        return _EMPTY_CASTS
    if not isinstance(value, Mapping):
        raise ValueError("upsert projection is invalid")
    try:
        snapshot = dict(value.items())
    except (TypeError, ValueError):
        raise ValueError("upsert projection is invalid") from None
    if any(
        type(column) is not str or type(cast) is not str or cast not in _CAST_FRAGMENTS
        for column, cast in snapshot.items()
    ):
        raise ValueError("upsert projection is invalid")
    return MappingProxyType(snapshot)


def _validate_projection_row(
    row: Mapping[str, object], fields: tuple[str, ...]
) -> None:
    if set(row) != set(fields):
        raise ValueError("upsert projection is invalid")


def _validate_relation_qualifiers(spec: _UpsertSpec, row: Mapping[str, object]) -> None:
    if (
        spec.table == "relations"
        and "qualifiers" in spec.fields
        and not isinstance(row["qualifiers"], Mapping)
    ):
        raise ValueError("relation qualifiers must be an object")


def _prepare_row(
    row: Mapping[str, object], spec: _UpsertSpec, *, persisted: bool
) -> Mapping[str, _PreparedValue]:
    return MappingProxyType(
        {
            field: _prepare_value(
                row[field], spec.casts.get(field), persisted=persisted
            )
            for field in spec.fields
        }
    )


def _prepare_value(
    value: object, cast: str | None, *, persisted: bool
) -> _PreparedValue:
    if value is SQL_NULL:
        if persisted:
            return _PreparedValue(("sql_null", ""), None)
        raise ValueError("desired materialization value is invalid")
    if cast == "jsonb":
        frozen = _freeze_jsonb(value)
        return _PreparedValue(("json", _jsonb_semantic(frozen)), _jsonb_text(frozen))
    if cast == "vector":
        if value is None:
            return _PreparedValue(("sql_null", ""), None)
        components = _canonical_vector(value, persisted=persisted)
        return _PreparedValue(
            ("vector", components),
            "[" + ",".join(str(item) for item in components) + "]",
        )
    return _prepare_scalar(value)


def _prepare_scalar(value: object) -> _PreparedValue:
    if value is None:
        return _PreparedValue(("sql_null", ""), None)
    is_numeric, numeric_value = _normalize_numeric(value)
    if is_numeric:
        if numeric_value is None:
            raise ValueError("finite scalar value is required")
        return _PreparedValue(("numeric", numeric_value), value)
    if type(value) is bool:
        return _PreparedValue(("boolean", value), value)
    if type(value) is str:
        return _PreparedValue(("string", value), value)
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return _PreparedValue(("invalid", object()), value)
    return _PreparedValue(("json", encoded), value)


def _same_fields(
    left: Mapping[str, _PreparedValue],
    right: Mapping[str, _PreparedValue],
    fields: Sequence[str],
) -> bool:
    return all(left[field].comparable == right[field].comparable for field in fields)


def _freeze_jsonb(value: object) -> object:
    if value is None or type(value) is bool:
        return value
    is_numeric, numeric_value = _normalize_numeric(value)
    if is_numeric:
        if numeric_value is None:
            raise ValueError("JSON values must be finite")
        return value
    if type(value) is str:
        _reject_nul(value)
        return value
    if isinstance(value, Mapping):
        try:
            items = tuple(value.items())
        except (TypeError, ValueError):
            raise ValueError("JSON value is invalid") from None
        frozen_items: list[tuple[str, object]] = []
        for key, child in items:
            if type(key) is not str:
                raise ValueError("JSON keys must be strings")
            _reject_nul(key)
            frozen_items.append((key, _freeze_jsonb(child)))
        return _JsonObject(tuple(sorted(frozen_items)))
    if type(value) is tuple:
        return _JsonArray(
            tuple(_freeze_jsonb(item) for item in cast(tuple[object, ...], value))
        )
    if type(value) is list:
        return _JsonArray(
            tuple(_freeze_jsonb(item) for item in cast(list[object], value))
        )
    raise ValueError("JSON value is invalid")


def _reject_nul(value: str) -> None:
    if "\x00" in value:
        raise ValueError("JSON values must not contain NUL characters")


def _jsonb_semantic(value: object) -> object:
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("boolean", value)
    is_numeric, numeric_value = _normalize_numeric(value)
    if is_numeric and numeric_value is not None:
        return ("numeric", numeric_value)
    if type(value) is str:
        return ("string", value)
    if isinstance(value, _JsonObject):
        return (
            "object",
            tuple((key, _jsonb_semantic(item)) for key, item in value.items),
        )
    if isinstance(value, _JsonArray):
        return ("array", tuple(_jsonb_semantic(item) for item in value.values))
    raise ValueError("JSON value is invalid")


def _jsonb_text(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    is_numeric, numeric_value = _normalize_numeric(value)
    if is_numeric and numeric_value is not None:
        if isinstance(value, Decimal):
            return str(value)
        return json.dumps(value, allow_nan=False)
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, _JsonObject):
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + _jsonb_text(item)
                for key, item in value.items
            )
            + "}"
        )
    if isinstance(value, _JsonArray):
        return "[" + ",".join(_jsonb_text(item) for item in value.values) + "]"
    raise ValueError("JSON value is invalid")


def _canonical_vector(value: object, *, persisted: bool) -> tuple[float, ...]:
    components: Sequence[object]
    if type(value) is str:
        if not persisted:
            raise ValueError("vector chunk embedding is invalid")
        components = _vector_text_components(value)
        from_text = True
    else:
        components = _vector_sequence(value)
        from_text = False
    if len(components) != 16:
        raise ValueError("vector chunk embedding is invalid")
    return tuple(
        _finite_vector_component(component, from_text=from_text)
        for component in components
    )


def _vector_sequence(value: object) -> Sequence[object]:
    if type(value) in {tuple, list}:
        return cast(Sequence[object], value)
    for method_name in ("to_list", "tolist"):
        try:
            adapter = getattr(value, method_name)
        except AttributeError:
            continue
        except Exception:
            raise ValueError("vector chunk embedding is invalid") from None
        if not callable(adapter):
            raise ValueError("vector chunk embedding is invalid")
        try:
            components = adapter()
        except Exception:
            raise ValueError("vector chunk embedding is invalid") from None
        if type(components) not in {tuple, list}:
            raise ValueError("vector chunk embedding is invalid")
        return components
    raise ValueError("vector chunk embedding is invalid")


def _vector_text_components(value: str) -> tuple[str, ...]:
    text = value.strip()
    if len(text) < 2 or text[0] != "[" or text[-1] != "]":
        raise ValueError("vector chunk embedding is invalid")
    body = text[1:-1].strip()
    components = (
        () if not body else tuple(component.strip() for component in body.split(","))
    )
    if any(not _vector_component_text(component) for component in components):
        raise ValueError("vector chunk embedding is invalid")
    return components


def _vector_component_text(value: str) -> bool:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and bool(value)


def _finite_vector_component(value: object, *, from_text: bool) -> float:
    if from_text:
        if type(value) is not str or not _vector_component_text(value):
            raise ValueError("vector chunk embedding is invalid")
    elif type(value) is bool or not isinstance(value, (Real, Decimal)):
        raise ValueError("vector chunk embedding is invalid")
    try:
        result = float(value)
        rounded = struct.unpack("!f", struct.pack("!f", result))[0]
    except (OverflowError, TypeError, ValueError, struct.error):
        raise ValueError("vector chunk embedding is invalid") from None
    if not math.isfinite(result) or not math.isfinite(rounded):
        raise ValueError("vector chunk embedding is invalid")
    return rounded


__all__ = ["DmlTemplate", "execute_template", "upsert_if_changed"]
