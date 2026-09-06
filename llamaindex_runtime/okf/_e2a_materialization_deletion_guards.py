"""Fail-closed stale-materialization deletion guards for E2a."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol


class Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...


Scope = Mapping[str, tuple[Mapping[str, object], ...]]


def validate_destructive_closure(
    cursor: Cursor, desired: object, existing: Scope
) -> Mapping[tuple[str, str], bool]:
    """Lock every stale candidate before rejecting external dependencies."""
    retiring_owners = _retiring_ownership_candidates(desired, existing)
    stale_spans = _stale_ids(
        _scope_rows(existing, "canonical_spans"),
        _values(desired, "canonical_spans"),
        "span_id",
    )
    stale_chunks = _stale_ids(
        _scope_rows(existing, "vector_chunks"),
        _values(desired, "vector_chunks"),
        "chunk_id",
    )
    stale_nodes = _stale_ids(
        _scope_rows(existing, "tree_nodes"),
        _values(desired, "tree_nodes"),
        "node_id",
    )
    stale_evidence = _stale_ids(
        _scope_rows(existing, "evidence"),
        _values(desired, "evidence_objects"),
        "evidence_id",
    )
    _lock_retiring_fact_candidates(cursor, retiring_owners)
    _lock_direct_stale_candidates(
        cursor, stale_spans, stale_chunks, stale_nodes, stale_evidence
    )
    _reject_out_of_scope_reverse_references(cursor, stale_spans, stale_nodes, existing)
    if stale_spans and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM entity_mentions WHERE span_id = ANY(%s)) AS present",
        (stale_spans,),
    ):
        raise ValueError("stale span has entity_mentions dependencies")
    if stale_spans and _selected_dependency_present(
        cursor,
        "SELECT evidence_link_id FROM evidence_links WHERE span_id = ANY(%s) "
        "AND source_kind IS DISTINCT FROM %s",
        (stale_spans, "manual_okf"),
        "evidence_link_id",
    ):
        raise ValueError("stale span has legacy evidence dependencies")
    if stale_chunks and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM chunk_entity_links WHERE chunk_id = ANY(%s)) "
        "AS present",
        (stale_chunks,),
    ):
        raise ValueError("stale chunk has chunk_entity_links dependencies")
    if stale_nodes and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM node_entity_links WHERE node_id = ANY(%s)) "
        "AS present",
        (stale_nodes,),
    ):
        raise ValueError("stale tree has node_entity_links dependencies")

    if stale_evidence and _selected_dependency_present(
        cursor,
        "SELECT evidence_link_id FROM evidence_links WHERE evidence_id = ANY(%s) "
        "AND source_kind IS DISTINCT FROM %s",
        (stale_evidence, "manual_okf"),
        "evidence_link_id",
    ):
        raise ValueError("stale evidence has non-E2a evidence-link dependencies")
    return _ownership_preservation(cursor, desired, retiring_owners)


def has_external_fact_dependency(
    cursor: Cursor,
    fact_id: str,
    kind: str,
    retiring_owner_ids: Sequence[str],
    *,
    safely_retiring_relation_ids: Sequence[str] = (),
) -> bool:
    """Return whether an E2a-owned fact still has an external dependency."""
    if kind not in {"entity", "relation"}:
        raise ValueError("ownership fact kind is invalid")
    validated_owners = _validate_identifier_sequence(
        retiring_owner_ids, "retiring ownership identifiers are invalid"
    )
    validated_relations = _validate_identifier_sequence(
        safely_retiring_relation_ids, "safely retiring relation identifiers are invalid"
    )
    if not validated_owners:
        raise ValueError("retiring ownership identifiers are required")
    identifier = "entity_id" if kind == "entity" else "relation_id"
    probes: list[tuple[str, tuple[object, ...]]] = [
        (
            "SELECT EXISTS (SELECT 1 FROM okf_manual_fact_ownership "
            "WHERE fact_kind = %s AND fact_id = %s "
            "AND NOT (ownership_id = ANY(%s))) AS present",
            (kind, fact_id, validated_owners),
        )
    ]
    if kind == "entity":
        probes.extend(
            (
                (
                    "SELECT EXISTS (SELECT 1 FROM entity_aliases WHERE entity_id = %s) "
                    "AS present",
                    (fact_id,),
                ),
                (
                    "SELECT EXISTS (SELECT 1 FROM entity_mentions WHERE entity_id = %s) "
                    "AS present",
                    (fact_id,),
                ),
            )
        )
        relation_parameters: tuple[object, ...] = (fact_id, fact_id)
        relation_statement = (
            "SELECT EXISTS (SELECT 1 FROM relations WHERE source_entity_id = %s "
            "OR target_entity_id = %s) AS present"
        )
        if validated_relations:
            retiring_relations = tuple(sorted(set(validated_relations)))
            relation_parameters = (*relation_parameters, retiring_relations)
            relation_statement = (
                "SELECT EXISTS (SELECT 1 FROM relations WHERE "
                "(source_entity_id = %s OR target_entity_id = %s) "
                "AND relation_id <> ALL(%s)) AS present"
            )
        probes.append((relation_statement, relation_parameters))
    probes.append(
        (
            f"SELECT EXISTS (SELECT 1 FROM evidence_links WHERE {identifier} = %s "
            "AND (source_kind IS DISTINCT FROM %s OR ownership_id IS NULL "
            "OR NOT (ownership_id = ANY(%s)))) AS present",
            (fact_id, "manual_okf", validated_owners),
        )
    )
    if kind == "entity":
        probes.extend(
            (
                (
                    "SELECT EXISTS (SELECT 1 FROM node_entity_links WHERE entity_id = %s) "
                    "AS present",
                    (fact_id,),
                ),
                (
                    "SELECT EXISTS (SELECT 1 FROM chunk_entity_links WHERE entity_id = %s) "
                    "AS present",
                    (fact_id,),
                ),
            )
        )
    return any(
        _dependency_present(cursor, statement, parameters)
        for statement, parameters in probes
    )


def _lock_direct_stale_candidates(
    cursor: Cursor,
    stale_spans: Sequence[str],
    stale_chunks: Sequence[str],
    stale_nodes: Sequence[str],
    stale_evidence: Sequence[str],
) -> None:
    for table, field, identifiers in (
        ("canonical_spans", "span_id", stale_spans),
        ("vector_chunks", "chunk_id", stale_chunks),
        ("tree_nodes", "node_id", stale_nodes),
        ("evidence", "evidence_id", stale_evidence),
    ):
        if not identifiers:
            continue
        requested_identifiers = tuple(sorted(identifiers))
        cursor.execute(
            f"SELECT {field} FROM {table} WHERE {field} = ANY(%s) "
            f"ORDER BY {field} FOR UPDATE",
            (list(requested_identifiers),),
        )
        _validate_lock_rows(cursor.fetchall(), field, requested_identifiers)


def _reject_out_of_scope_reverse_references(
    cursor: Cursor,
    stale_spans: Sequence[str],
    stale_nodes: Sequence[str],
    existing: Scope,
) -> None:
    permitted_chunk_ids = _scope_identifiers(existing, "vector_chunks", "chunk_id")
    permitted_node_ids = _scope_identifiers(existing, "tree_nodes", "node_id")
    if stale_spans and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM vector_chunk_spans WHERE span_id = ANY(%s) "
        "AND chunk_id <> ALL(%s)) AS present",
        (stale_spans, permitted_chunk_ids),
    ):
        raise ValueError("stale span has out-of-scope vector chunk span dependencies")
    if stale_spans and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM tree_node_spans WHERE span_id = ANY(%s) "
        "AND node_id <> ALL(%s)) AS present",
        (stale_spans, permitted_node_ids),
    ):
        raise ValueError("stale span has out-of-scope tree node span dependencies")
    if stale_nodes and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM vector_chunks WHERE node_id = ANY(%s) "
        "AND chunk_id <> ALL(%s)) AS present",
        (stale_nodes, permitted_chunk_ids),
    ):
        raise ValueError("stale tree has out-of-scope vector chunk dependencies")
    if stale_nodes and _dependency_present(
        cursor,
        "SELECT EXISTS (SELECT 1 FROM tree_nodes WHERE parent_node_id = ANY(%s) "
        "AND node_id <> ALL(%s)) AS present",
        (stale_nodes, permitted_node_ids),
    ):
        raise ValueError("stale tree has out-of-scope child tree node dependencies")


def _scope_identifiers(existing: Scope, key: str, field: str) -> tuple[str, ...]:
    return tuple(
        sorted(_identifier_from_row(row, field) for row in _scope_rows(existing, key))
    )


def _retiring_ownership_candidates(
    desired: object, existing: Scope
) -> Mapping[tuple[str, str], tuple[str, ...]]:
    desired_owner_ids = {
        _desired_identifier(owner, "ownership_id")
        for owner in _values(desired, "ownership_facts")
    }
    candidates: dict[tuple[str, str], list[str]] = {}
    for owner in _scope_rows(existing, "okf_manual_fact_ownership"):
        owner_id = _identifier_from_row(owner, "ownership_id")
        if owner_id in desired_owner_ids:
            continue
        fact_id = _identifier_from_row(owner, "fact_id")
        kind = _identifier_from_row(owner, "fact_kind")
        if kind not in {"entity", "relation"}:
            raise ValueError("ownership fact kind is invalid")
        candidates.setdefault((kind, fact_id), []).append(owner_id)
    return {
        key: tuple(sorted(owner_ids)) for key, owner_ids in sorted(candidates.items())
    }


def _lock_retiring_fact_candidates(
    cursor: Cursor, candidates: Mapping[tuple[str, str], Sequence[str]]
) -> None:
    for kind, table, field in (
        ("entity", "entities", "entity_id"),
        ("relation", "relations", "relation_id"),
    ):
        requested_identifiers = tuple(
            sorted(fact_id for fact_kind, fact_id in candidates if fact_kind == kind)
        )
        if not requested_identifiers:
            continue
        cursor.execute(
            f"SELECT {field} FROM {table} WHERE {field} = ANY(%s) "
            f"ORDER BY {field} FOR UPDATE",
            (list(requested_identifiers),),
        )
        _validate_lock_rows(cursor.fetchall(), field, requested_identifiers)


def _validate_lock_rows(value: object, field: str, identifiers: Sequence[str]) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("candidate lock returned an invalid result set")
    locked_identifiers: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or frozenset(row) != {field}:
            raise ValueError("candidate lock returned an invalid row")
        locked_identifiers.append(_string(row[field]))
    if tuple(locked_identifiers) != tuple(identifiers):
        raise ValueError("candidate lock did not return the requested identifiers")


def _ownership_preservation(
    cursor: Cursor,
    desired: object,
    retiring_owners: Mapping[tuple[str, str], Sequence[str]],
) -> Mapping[tuple[str, str], bool]:
    desired_fact_keys = {
        _desired_fact_key(owner) for owner in _values(desired, "ownership_facts")
    }
    desired_relation_entity_ids = _desired_relation_entity_ids(desired)
    preserve: dict[tuple[str, str], bool] = {}
    retiring_relations: list[str] = []
    for kind, fact_id in sorted(retiring_owners):
        if kind != "relation":
            continue
        retained = (kind, fact_id) in desired_fact_keys or has_external_fact_dependency(
            cursor, fact_id, kind, retiring_owners[(kind, fact_id)]
        )
        preserve[(kind, fact_id)] = retained
        if not retained:
            retiring_relations.append(fact_id)
    safe_relations = tuple(sorted(retiring_relations))
    for kind, fact_id in sorted(retiring_owners):
        if kind != "entity":
            continue
        preserve[(kind, fact_id)] = (
            (kind, fact_id) in desired_fact_keys
            or fact_id in desired_relation_entity_ids
            or has_external_fact_dependency(
                cursor,
                fact_id,
                kind,
                retiring_owners[(kind, fact_id)],
                safely_retiring_relation_ids=safe_relations,
            )
        )
    return preserve


def _dependency_present(cursor: Cursor, statement: str, parameters: object) -> bool:
    cursor.execute(statement, _array_parameters(parameters))
    rows = _result_rows(cursor.fetchall(), "dependency probe")
    if len(rows) != 1:
        raise ValueError("dependency probe must return exactly one row")
    row = rows[0]
    if frozenset(row) != {"present"} or type(row["present"]) is not bool:
        raise ValueError(
            "dependency probe must return exactly one boolean present field"
        )
    return row["present"]


def _selected_dependency_present(
    cursor: Cursor, statement: str, parameters: object, field: str
) -> bool:
    cursor.execute(statement, _array_parameters(parameters))
    rows = _result_rows(cursor.fetchall(), "dependency probe")
    for row in rows:
        if frozenset(row) != {field}:
            raise ValueError("dependency probe selected an invalid row")
        _identifier_from_row(row, field)
    return bool(rows)


def _stale_ids(
    existing: Sequence[Mapping[str, object]], values: Sequence[object], field: str
) -> list[str]:
    desired_ids = {_desired_identifier(value, field) for value in values}
    existing_ids = {_identifier_from_row(row, field) for row in existing}
    return sorted(existing_ids - desired_ids)


def _result_rows(value: object, context: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"cursor returned an invalid {context}")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"cursor returned an invalid {context}")
    return tuple(value)


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


def _scope_rows(existing: Scope, key: str) -> tuple[Mapping[str, object], ...]:
    try:
        rows = existing[key]
    except KeyError:
        raise ValueError("materialization scope is incomplete") from None
    if not isinstance(rows, tuple):
        raise ValueError("materialization scope is invalid")
    return rows


def _desired_identifier(value: object, field: str) -> str:
    if isinstance(value, Mapping):
        return _identifier_from_row(value, field)
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


def _desired_fact_key(value: object) -> tuple[str, str]:
    kind = _desired_identifier(value, "fact_kind")
    if kind not in {"entity", "relation"}:
        raise ValueError("ownership fact kind is invalid")
    return kind, _desired_identifier(value, "fact_id")


def _desired_relation_entity_ids(desired: object) -> frozenset[str]:
    entity_ids: set[str] = set()
    for relation in _values(desired, "manual_relations"):
        try:
            natural_key = getattr(relation, "natural_key")
        except AttributeError:
            raise ValueError("manual relation natural key is invalid") from None
        if type(natural_key) is not str:
            raise ValueError("manual relation natural key is invalid")
        try:
            natural = json.loads(natural_key)
        except json.JSONDecodeError:
            raise ValueError("manual relation natural key is invalid") from None
        if not isinstance(natural, Mapping):
            raise ValueError("manual relation natural key is invalid")
        entity_ids.update(
            (
                _string(natural.get("subject_entity_id")),
                _string(natural.get("object_entity_id")),
            )
        )
    return frozenset(entity_ids)


def _validate_identifier_sequence(value: object, error_message: str) -> tuple[str, ...]:
    """Validate and snapshot an identifier sequence parameter."""
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        raise ValueError(error_message)
    validated: list[str] = []
    for element in value:
        try:
            validated.append(_string(element))
        except ValueError:
            raise ValueError(error_message) from None
    return tuple(validated)


__all__ = ["has_external_fact_dependency", "validate_destructive_closure"]
