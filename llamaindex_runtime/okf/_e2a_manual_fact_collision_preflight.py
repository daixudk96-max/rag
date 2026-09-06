"""Locked validation of pre-existing global E2a manual facts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol

from ._e2a_postgres_semantics import postgres_values_equal
from .e2a_contracts import E2aDesiredState, E2aManualFact, E2aOwnershipFact


class Cursor(Protocol):
    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...


_ENTITY_FIELDS = (
    "entity_id",
    "entity_key",
    "entity_type",
    "canonical_name",
    "description",
    "community_id",
)
_RELATION_FIELDS = (
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
    "description",
)
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
_Material = Callable[[E2aManualFact], Mapping[str, object]]


def preflight_manual_fact_collisions(cursor: Cursor, desired: E2aDesiredState) -> None:
    """Reject existing manual fact material that E2a cannot safely share."""
    entities = _facts(desired.manual_entities, "entity")
    relations = _facts(desired.manual_relations, "relation")
    entity_result = _base_rows(cursor, "entities", entities)
    relation_result = _base_rows(cursor, "relations", relations)
    ownership_result = _ownership_rows(cursor, (*entities, *relations))
    entity_rows = _rows(entity_result, _ENTITY_FIELDS, "manual fact base row")
    relation_rows = _rows(relation_result, _RELATION_FIELDS, "manual fact base row")
    owners = _rows(
        ownership_result,
        _OWNERSHIP_FIELDS,
        "manual fact ownership row",
    )
    facts = (*entities, *relations)
    valid_owners = _validated_owners(owners, facts)
    _validate_base_rows(entities, entity_rows, valid_owners, _entity_material)
    _validate_base_rows(relations, relation_rows, valid_owners, _relation_material)


def _facts(values: Sequence[E2aManualFact], kind: str) -> tuple[E2aManualFact, ...]:
    if any(
        type(value) is not E2aManualFact or value.fact_kind != kind for value in values
    ):
        raise ValueError("desired manual fact is invalid")
    facts = tuple(sorted(values, key=lambda value: value.fact_id))
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("desired manual fact identity is duplicated")
    return facts


def _base_rows(cursor: Cursor, table: str, facts: Sequence[E2aManualFact]) -> object:
    if not facts:
        return ()
    if table == "entities":
        statement = (
            "SELECT entity_id, entity_key, entity_type, canonical_name, description, "
            "community_id FROM entities WHERE entity_id = ANY(%s) OR entity_key = ANY(%s)"
        )
    elif table == "relations":
        statement = (
            "SELECT relation_id, relation_key, relation_type, source_entity_id, "
            "target_entity_id, negation, condition, direction, confidence, qualifiers, "
            "qualifiers IS NULL AS qualifiers_is_sql_null, description FROM relations "
            "WHERE relation_id = ANY(%s) OR relation_key = ANY(%s)"
        )
    else:
        raise ValueError("manual fact table is invalid")
    cursor.execute(
        statement,
        ([fact.fact_id for fact in facts], [fact.natural_key for fact in facts]),
    )
    return cursor.fetchall()


def _ownership_rows(cursor: Cursor, facts: Sequence[E2aManualFact]) -> object:
    if not facts:
        return ()
    cursor.execute(
        "SELECT ownership_id, okf_relative_path, fact_kind, fact_id, entity_id, "
        "relation_id, source_digest, document_id, version_id, scope_version_id "
        "FROM okf_manual_fact_ownership WHERE fact_id = ANY(%s)",
        ([fact.fact_id for fact in facts],),
    )
    return cursor.fetchall()


def _rows(
    value: object, fields: tuple[str, ...], description: str
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{description} result is invalid")
    expected = frozenset(fields)
    if any(not isinstance(row, Mapping) or frozenset(row) != expected for row in value):
        raise ValueError(f"{description} is malformed")
    return tuple(value)


def _validated_owners(
    rows: Sequence[Mapping[str, object]], facts: Sequence[E2aManualFact]
) -> Mapping[tuple[str, str], tuple[Mapping[str, object], ...]]:
    known = {(fact.fact_kind, fact.fact_id) for fact in facts}
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        key = _validate_owner(row)
        if key not in known:
            raise ValueError("manual fact ownership row is outside desired scope")
        grouped.setdefault(key, []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _validate_owner(row: Mapping[str, object]) -> tuple[str, str]:
    kind, fact_id = row["fact_kind"], row["fact_id"]
    if type(kind) is not str or kind not in {"entity", "relation"}:
        raise ValueError("manual fact ownership row is malformed")
    fact_kind: Literal["entity", "relation"] = (
        "entity" if kind == "entity" else "relation"
    )
    if row["entity_id"] != (fact_id if fact_kind == "entity" else None):
        raise ValueError("manual fact ownership target is malformed")
    if row["relation_id"] != (fact_id if fact_kind == "relation" else None):
        raise ValueError("manual fact ownership target is malformed")
    try:
        owner = E2aOwnershipFact.create(
            relative_path=row["okf_relative_path"],  # type: ignore[arg-type]
            fact_kind=fact_kind,
            fact_id=fact_id,  # type: ignore[arg-type]
            source_digest=row["source_digest"],  # type: ignore[arg-type]
            document_id=row["document_id"],  # type: ignore[arg-type]
            version_id=row["version_id"],  # type: ignore[arg-type]
            scope_version_id=row["scope_version_id"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError):
        raise ValueError("manual fact ownership row is malformed") from None
    if row["ownership_id"] != owner.ownership_id:
        raise ValueError("manual fact ownership identity is malformed")
    return fact_kind, owner.fact_id


def _validate_base_rows(
    facts: Sequence[E2aManualFact],
    rows: Sequence[Mapping[str, object]],
    owners: Mapping[tuple[str, str], tuple[Mapping[str, object], ...]],
    material: _Material,
) -> None:
    identifier = "entity_id" if material is _entity_material else "relation_id"
    natural_key = "entity_key" if material is _entity_material else "relation_key"
    for fact in facts:
        matches = tuple(
            row
            for row in rows
            if row[identifier] == fact.fact_id or row[natural_key] == fact.natural_key
        )
        _validate_base_match(fact, matches, owners, material, identifier, natural_key)


def _validate_base_match(
    fact: E2aManualFact,
    rows: Sequence[Mapping[str, object]],
    owners: Mapping[tuple[str, str], tuple[Mapping[str, object], ...]],
    material: _Material,
    identifier: str,
    natural_key: str,
) -> None:
    if not rows:
        if owners.get((fact.fact_kind, fact.fact_id)):
            raise ValueError("manual fact ownership exists without its base row")
        return
    if len(rows) != 1 or rows[0][identifier] != fact.fact_id:
        raise ValueError("manual fact natural key collides with another identifier")
    row = rows[0]
    expected = material(fact)
    if row[natural_key] != fact.natural_key:
        raise ValueError("manual fact base row has incompatible material")
    if not _material_equal(expected, row, material):
        raise ValueError("manual fact base row has incompatible material")
    if row["description"] is not None or (
        "community_id" in row and row["community_id"] is not None
    ):
        raise ValueError("manual fact base row has unmanaged enrichment")
    if not owners.get((fact.fact_kind, fact.fact_id)):
        raise ValueError("manual fact base row lacks compatible E2a ownership")


def _material_equal(
    expected: Mapping[str, object],
    row: Mapping[str, object],
    material: _Material,
) -> bool:
    """Compare expected material against row using field-aware PostgreSQL semantics."""
    for key in expected:
        if key not in row:
            return False

        expected_value = expected[key]
        row_value = row[key]

        # Field-aware comparison based on field type
        if material is _relation_material:
            # For relations, use field-specific semantics
            if key == "qualifiers":
                # qualifiers_is_sql_null flag is authoritative
                qualifiers_is_sql_null = row.get("qualifiers_is_sql_null")
                if type(qualifiers_is_sql_null) is not bool:
                    return False
                if qualifiers_is_sql_null is True:
                    # Row claims SQL-NULL qualifiers; expected must not match
                    return False
                # Only compare qualifiers with JSONB semantics when flag is False
                if not postgres_values_equal(expected_value, row_value, cast="jsonb"):
                    return False
            elif key == "confidence":
                # Use NUMERIC semantics for confidence
                if not postgres_values_equal(expected_value, row_value, cast=None):
                    return False
            else:
                # Other scalar fields: use ordinary PostgreSQL scalar semantics
                if not postgres_values_equal(expected_value, row_value, cast=None):
                    return False
        else:
            # For entities, use ordinary scalar semantics
            if not postgres_values_equal(expected_value, row_value, cast=None):
                return False

    return True


def _entity_material(fact: E2aManualFact) -> Mapping[str, object]:
    natural = _natural_object(fact)
    return {
        "entity_key": fact.natural_key,
        "entity_type": natural.get("entity_type"),
        "canonical_name": natural.get("title"),
    }


def _relation_material(fact: E2aManualFact) -> Mapping[str, object]:
    natural = _natural_object(fact)
    qualifiers = fact.qualifiers
    nested = qualifiers.get("qualifiers", {})
    confidence = qualifiers.get("confidence")
    if (
        not isinstance(nested, Mapping)
        or type(natural.get("subject_entity_id")) is not str
        or type(natural.get("predicate")) is not str
        or type(natural.get("object_entity_id")) is not str
        or type(qualifiers.get("negation", False)) is not bool
        or qualifiers.get("condition") is not None
        and type(qualifiers["condition"]) is not str
        or qualifiers.get("direction") is not None
        and type(qualifiers["direction"]) is not str
    ):
        raise ValueError("manual relation material is invalid")
    _finite_confidence(confidence)
    return {
        "relation_key": fact.natural_key,
        "relation_type": natural["predicate"],
        "source_entity_id": natural["subject_entity_id"],
        "target_entity_id": natural["object_entity_id"],
        "negation": qualifiers.get("negation", False),
        "condition": qualifiers.get("condition"),
        "direction": qualifiers.get("direction"),
        "confidence": confidence,
        "qualifiers": nested,
    }


def _finite_confidence(value: object) -> None:
    if value is None:
        return
    if type(value) is int:
        numeric = float(value)
    elif type(value) is float:
        numeric = value
    else:
        raise ValueError("manual relation material is invalid")
    if not math.isfinite(numeric):
        raise ValueError("manual relation material is invalid")


def _natural_object(fact: E2aManualFact) -> Mapping[str, object]:
    try:
        value = json.loads(fact.natural_key)
    except json.JSONDecodeError:
        raise ValueError("manual fact natural key is invalid") from None
    if not isinstance(value, Mapping):
        raise ValueError("manual fact natural key is invalid")
    return value


__all__ = ["preflight_manual_fact_collisions"]
