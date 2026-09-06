"""Parentless and global-manual E2a reconciliation scope loading."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from ._e2a_materialization_values import SQL_NULL


class _Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...


_OWNERSHIP_FIELDS = (
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
)


def _load_parentless_manual_scope(
    cursor: _Cursor,
    desired: object,
    *,
    scope_keys: Sequence[str],
) -> dict[str, tuple[Mapping[str, object], ...]]:
    """Load all global manual ownership before selecting stale facts for deletion."""
    ownership = _projected_rows(
        cursor,
        statement=(
            "SELECT ownership_id, okf_relative_path, fact_kind, fact_id, entity_id, relation_id, "
            "source_digest, document_id, version_id, scope_version_id "
            "FROM okf_manual_fact_ownership WHERE version_id IS NULL"
        ),
        parameters=(),
        required_fields=_OWNERSHIP_FIELDS,
        exact_shape=True,
        error="cursor returned a malformed full materialization row",
    )
    desired_entities = _identifiers(_values(desired, "manual_entities"), "fact_id")
    desired_relations = _identifiers(_values(desired, "manual_relations"), "fact_id")
    owned_entities = tuple(
        sorted(
            {
                _identifier_from_row(row, "fact_id")
                for row in ownership
                if row["fact_kind"] == "entity"
            }
        )
    )
    owned_relations = tuple(
        sorted(
            {
                _identifier_from_row(row, "fact_id")
                for row in ownership
                if row["fact_kind"] == "relation"
            }
        )
    )
    entity_ids = tuple(sorted(set(desired_entities) | set(owned_entities)))
    relation_ids = tuple(sorted(set(desired_relations) | set(owned_relations)))
    scope: dict[str, tuple[Mapping[str, object], ...]] = {key: () for key in scope_keys}
    scope["okf_manual_fact_ownership"] = ownership
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
    return scope


def _relation_rows(
    cursor: _Cursor,
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
    cursor: _Cursor,
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


def _projected_rows(
    cursor: _Cursor,
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


def _array_parameters(parameters: object) -> object:
    if type(parameters) is not tuple:
        return parameters
    return tuple(list(value) if type(value) is tuple else value for value in parameters)


def _values(desired: object, field: str) -> Sequence[object]:
    try:
        values = getattr(desired, field)
    except AttributeError:
        raise ValueError("desired materialization state is invalid") from None
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError("desired materialization state is invalid")
    return values


def _identifiers(values: Sequence[object], field: str) -> tuple[str, ...]:
    return tuple(sorted({_desired_identifier(value, field) for value in values}))


def _desired_identifier(value: object, field: str) -> str:
    if isinstance(value, Mapping):
        return _identifier_from_row(value, field)
    if field not in {"fact_id", "ownership_id"}:
        raise ValueError(f"desired materialization value does not expose {field}")
    try:
        identifier = getattr(value, field)
    except AttributeError:
        raise ValueError(
            f"desired materialization value does not expose {field}"
        ) from None
    return _string(identifier)


def _identifier_from_row(row: Mapping[str, object], field: str) -> str:
    if field not in row:
        raise ValueError("materialization state row is missing an identifier")
    return _string(row[field])


def _string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("materialization identifier is invalid")
    return value
