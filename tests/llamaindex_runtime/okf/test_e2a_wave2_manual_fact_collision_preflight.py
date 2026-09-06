"""RED cursor-fake contracts for owner-aware manual-fact collision preflight.

These regressions intentionally exercise the caller-owned transaction path without a
PostgreSQL connection.  They describe the Phase 15 #64 boundary that must reject
ambiguous global entity/relation material before E2a issues any primary DML.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aManualFact,
    E2aOwnershipFact,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

_DIGEST = "a" * 64
_ENTITY_NATURAL_KEY = canonical_json(
    {"entity_type": "concept", "title": "Mañana 🐈 % _ ' SQL"}
)
_RELATION_NATURAL_KEY = canonical_json(
    {
        "subject_entity_id": str(UUID(int=8101)),
        "predicate": "supports",
        "object_entity_id": str(UUID(int=8102)),
    }
)
_TABLE_LOCKS = (
    "LOCK TABLE entities IN EXCLUSIVE MODE NOWAIT",
    "LOCK TABLE relations IN EXCLUSIVE MODE NOWAIT",
    "LOCK TABLE okf_manual_fact_ownership IN EXCLUSIVE MODE NOWAIT",
)
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


def _manual_fact(kind: str) -> E2aManualFact:
    if kind == "entity":
        natural_key = _ENTITY_NATURAL_KEY
    elif kind == "relation":
        natural_key = _RELATION_NATURAL_KEY
    else:
        raise AssertionError(f"unsupported fact kind: {kind}")
    return E2aManualFact(
        fact_id=deterministic_id(kind, natural_key),
        fact_kind=kind,  # type: ignore[arg-type]
        relative_path=f"facts/{kind}.md",
        source_digest=_DIGEST,
        qualifiers=(
            {}
            if kind == "entity"
            else {
                "negation": False,
                "condition": None,
                "direction": None,
                "qualifiers": {},
            }
        ),
        natural_key=natural_key,
    )


def _desired(kinds: tuple[str, ...], *, entity_owner_count: int = 1) -> E2aDesiredState:
    facts = tuple(_manual_fact(kind) for kind in kinds)
    ownership = tuple(
        E2aOwnershipFact.create(
            relative_path=(
                fact.relative_path
                if index == 1
                else f"facts/{fact.fact_kind}-owner-{index}.md"
            ),
            fact_kind=fact.fact_kind,  # type: ignore[arg-type]
            fact_id=fact.fact_id,
            source_digest=fact.source_digest,
        )
        for fact in facts
        for index in range(
            1, entity_owner_count + 1 if fact.fact_kind == "entity" else 2
        )
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": owner.fact_kind,
                "path": owner.relative_path,
                "identity": owner.fact_id,
                "source_digest": owner.source_digest,
            }
            for owner in ownership
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(),
        canonical_spans=(),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=tuple(fact for fact in facts if fact.fact_kind == "entity"),
        manual_relations=tuple(fact for fact in facts if fact.fact_kind == "relation"),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=ownership,
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _entity_row(
    fact: E2aManualFact,
    *,
    entity_id: str | None = None,
    entity_type: str = "concept",
    canonical_name: str = "Mañana 🐈 % _ ' SQL",
    description: str | None = None,
    community_id: str | None = None,
) -> dict[str, object]:
    return {
        "entity_id": entity_id or fact.fact_id,
        "entity_key": fact.natural_key,
        "entity_type": entity_type,
        "canonical_name": canonical_name,
        "description": description,
        "community_id": community_id,
    }


def _relation_row(
    fact: E2aManualFact,
    *,
    relation_id: str | None = None,
    relation_type: str = "supports",
    confidence: object = None,
    qualifiers: object = None,
    qualifiers_is_sql_null: bool = False,
    description: str | None = None,
) -> dict[str, object]:
    natural = json.loads(fact.natural_key)
    persisted_qualifiers = (
        {} if qualifiers is None and not qualifiers_is_sql_null else qualifiers
    )
    return {
        "relation_id": relation_id or fact.fact_id,
        "relation_key": fact.natural_key,
        "relation_type": relation_type,
        "source_entity_id": natural["subject_entity_id"],
        "target_entity_id": natural["object_entity_id"],
        "negation": False,
        "condition": None,
        "direction": None,
        "confidence": confidence,
        "qualifiers": persisted_qualifiers,
        "qualifiers_is_sql_null": qualifiers_is_sql_null,
        "description": description,
    }


def _ownership_row(owner: E2aOwnershipFact) -> dict[str, object]:
    return {
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


def _normalized(statement: str) -> str:
    return " ".join(statement.lower().split())


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


def _preflight_by_natural_key(statement: str, key_field: str) -> bool:
    return f"{key_field} = any(%s)" in _normalized(statement)


def _project(
    row: Mapping[str, object], statement: str, fields: Sequence[str]
) -> dict[str, object]:
    projection = _normalized(statement).partition(" from ")[0]
    return {field: row[field] for field in fields if field in projection}


class _AdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _CollisionCursor:
    """A read-only cursor fake that exposes collision rows only to preflight SQL."""

    def __init__(
        self,
        *,
        entity_rows: Sequence[Mapping[str, object]] = (),
        relation_rows: Sequence[Mapping[str, object]] = (),
        ownership_rows: Sequence[Mapping[str, object]] = (),
        preflight_only_base: bool = False,
        preflight_only_ownership: bool = False,
        malformed_preflight_row: Mapping[str, object] | None = None,
        malformed_preflight_target: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.adapters = _AdapterRegistry()
        self.connection = object()
        self._last_statement = ""
        self._entity_rows = tuple(entity_rows)
        self._relation_rows = tuple(relation_rows)
        self._ownership_rows = tuple(ownership_rows)
        self._preflight_only_base = preflight_only_base
        self._preflight_only_ownership = preflight_only_ownership
        self._malformed_preflight_row = malformed_preflight_row
        self._malformed_preflight_target = malformed_preflight_target

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = _normalized(self._last_statement)
        if "select exists" in statement:
            return [{"present": False}]
        if "from entities" in statement:
            return self._base_rows(
                statement,
                table="entities",
                key_field="entity_key",
                fields=_ENTITY_FIELDS,
                rows=self._entity_rows,
            )
        if "from relations" in statement:
            return self._base_rows(
                statement,
                table="relations",
                key_field="relation_key",
                fields=_RELATION_FIELDS,
                rows=self._relation_rows,
            )
        if "from okf_manual_fact_ownership" in statement:
            return self._ownership_rows_for(statement)
        return []

    def _base_rows(
        self,
        statement: str,
        *,
        table: str,
        key_field: str,
        fields: Sequence[str],
        rows: Sequence[Mapping[str, object]],
    ) -> list[Mapping[str, object]]:
        is_preflight = _preflight_by_natural_key(statement, key_field)
        if is_preflight and self._malformed_preflight_target == table:
            assert self._malformed_preflight_row is not None
            return [self._malformed_preflight_row]
        if self._preflight_only_base and not is_preflight:
            return []
        return [_project(row, statement, fields) for row in rows]

    def _ownership_rows_for(self, statement: str) -> list[Mapping[str, object]]:
        is_preflight = "fact_id = any(%s)" in statement
        if is_preflight and self._malformed_preflight_target == "ownership":
            assert self._malformed_preflight_row is not None
            return [self._malformed_preflight_row]
        if self._preflight_only_ownership and not is_preflight:
            return []
        return [
            _project(row, statement, _OWNERSHIP_FIELDS) for row in self._ownership_rows
        ]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, cursor: _CollisionCursor) -> None:
        self.autocommit = False
        self.cursor_value = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self.commit_after_call_count: int | None = None

    def cursor(self, *, row_factory: object | None = None) -> _CollisionCursor:
        del row_factory
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1
        self.commit_after_call_count = len(self.cursor_value.calls)

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


def _reconcile(
    cursor: _CollisionCursor, desired: E2aDesiredState
) -> tuple[_Connection, object]:
    connection = _Connection(cursor)
    result = E2aReconciler().reconcile(connection, desired)
    return connection, result


def _table_lock_calls(cursor: _CollisionCursor) -> list[tuple[str, object | None]]:
    return [
        (statement, parameters)
        for statement, parameters in cursor.calls
        if statement.lstrip().upper().startswith("LOCK TABLE")
    ]


def _assert_table_locks(cursor: _CollisionCursor) -> list[int]:
    assert _table_lock_calls(cursor) == [
        (statement, None) for statement in _TABLE_LOCKS
    ]
    return [
        index
        for index, (statement, _) in enumerate(cursor.calls)
        if statement in _TABLE_LOCKS
    ]


def _assert_list_binding(parameters: object | None, expected: list[str]) -> None:
    assert type(parameters) is tuple
    assert expected in parameters
    assert all(type(value) is list for value in parameters if isinstance(value, list))


def _assert_collision_preflight(
    cursor: _CollisionCursor, desired: E2aDesiredState
) -> list[int]:
    indexes: list[int] = []
    expected = (
        (
            "entities",
            "entity_id",
            "entity_key",
            _ENTITY_FIELDS,
            list(sorted(fact.fact_id for fact in desired.manual_entities)),
            list(sorted(fact.natural_key for fact in desired.manual_entities)),
        ),
        (
            "relations",
            "relation_id",
            "relation_key",
            _RELATION_FIELDS,
            list(sorted(fact.fact_id for fact in desired.manual_relations)),
            list(sorted(fact.natural_key for fact in desired.manual_relations)),
        ),
    )
    for table, id_field, key_field, fields, ids, keys in expected:
        if not ids:
            continue
        reads = [
            (index, statement, parameters)
            for index, (statement, parameters) in enumerate(cursor.calls)
            if f"from {table}" in _normalized(statement)
            and _preflight_by_natural_key(statement, key_field)
        ]
        assert reads, f"{table} collision preflight must read by ID and natural key"
        for index, statement, parameters in reads:
            normalized = _normalized(statement)
            assert f"{id_field} = any(%s)" in normalized
            assert f"{key_field} = any(%s)" in normalized
            assert all(field in normalized.partition(" from ")[0] for field in fields)
            _assert_list_binding(parameters, ids)
            _assert_list_binding(parameters, keys)
            indexes.append(index)

    fact_ids = list(
        sorted(
            fact.fact_id
            for fact in (*desired.manual_entities, *desired.manual_relations)
        )
    )
    ownership_reads = [
        (index, statement, parameters)
        for index, (statement, parameters) in enumerate(cursor.calls)
        if "from okf_manual_fact_ownership" in _normalized(statement)
        and "fact_id = any(%s)" in _normalized(statement)
    ]
    assert ownership_reads, "preflight must inspect every owner for desired facts"
    for index, statement, parameters in ownership_reads:
        normalized = _normalized(statement)
        assert "ownership_id = any(%s)" not in normalized
        assert all(
            field in normalized.partition(" from ")[0] for field in _OWNERSHIP_FIELDS
        )
        _assert_list_binding(parameters, fact_ids)
        indexes.append(index)
    return indexes


def _assert_preflight_precedes_dml(
    cursor: _CollisionCursor, desired: E2aDesiredState
) -> None:
    lock_indexes = _assert_table_locks(cursor)
    collision_indexes = _assert_collision_preflight(cursor, desired)
    dml_indexes = [
        index for index, (statement, _) in enumerate(cursor.calls) if _is_dml(statement)
    ]
    assert lock_indexes and collision_indexes and dml_indexes
    assert max(lock_indexes) < min(collision_indexes) < min(dml_indexes)


def _assert_locks_precede_preflight_no_dml_required(
    cursor: _CollisionCursor, desired: E2aDesiredState
) -> None:
    """Assert locks precede preflight; DML optional for semantic-equality no-op cases."""
    lock_indexes = _assert_table_locks(cursor)
    collision_indexes = _assert_collision_preflight(cursor, desired)
    dml_indexes = [
        index for index, (statement, _) in enumerate(cursor.calls) if _is_dml(statement)
    ]
    assert lock_indexes and collision_indexes
    if dml_indexes:
        assert max(lock_indexes) < min(collision_indexes) < min(dml_indexes)
    else:
        assert max(lock_indexes) < min(collision_indexes)


def _relation_desired(qualifiers: Mapping[str, object]) -> E2aDesiredState:
    base = _desired(("relation",))
    original = base.manual_relations[0]
    relation = E2aManualFact(
        fact_id=original.fact_id,
        fact_kind="relation",
        relative_path=original.relative_path,
        source_digest=original.source_digest,
        qualifiers=qualifiers,
        natural_key=original.natural_key,
    )
    return E2aDesiredState(
        **{
            **base.__dict__,
            "manual_relations": (relation,),
        }
    )


def _failure_cursor(
    *,
    kind: str,
    base_row: Mapping[str, object] | None = None,
    ownership_rows: Sequence[Mapping[str, object]] = (),
    preflight_only_base: bool = False,
    preflight_only_ownership: bool = True,
) -> tuple[E2aDesiredState, _CollisionCursor]:
    desired = _desired((kind,))
    return (
        desired,
        _CollisionCursor(
            entity_rows=(base_row,) if kind == "entity" and base_row else (),
            relation_rows=(base_row,) if kind == "relation" and base_row else (),
            ownership_rows=ownership_rows,
            preflight_only_base=preflight_only_base,
            preflight_only_ownership=preflight_only_ownership,
        ),
    )


def test_missing_facts_are_insert_eligible_only_after_locked_collision_preflight() -> (
    None
):
    desired = _desired(("entity", "relation"), entity_owner_count=2)
    cursor = _CollisionCursor()

    connection, result = _reconcile(cursor, desired)

    _assert_preflight_precedes_dml(cursor, desired)
    assert connection.autocommit is False
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.commit_after_call_count == len(cursor.calls)
    assert result.outcome == "changed"
    assert any(
        "into entities" in _normalized(statement)
        for statement, _ in cursor.calls
        if _is_dml(statement)
    )
    assert any(
        "into relations" in _normalized(statement)
        for statement, _ in cursor.calls
        if _is_dml(statement)
    )


def test_exact_okf_owned_entity_is_shared_by_multiple_compatible_desired_owners() -> (
    None
):
    desired = _desired(("entity",), entity_owner_count=2)
    entity = desired.manual_entities[0]
    persisted_owner = _ownership_row(desired.ownership_facts[0])
    cursor = _CollisionCursor(
        entity_rows=(_entity_row(entity),), ownership_rows=(persisted_owner,)
    )

    connection, result = _reconcile(cursor, desired)

    _assert_preflight_precedes_dml(cursor, desired)
    entity_dml = [
        statement
        for statement, _ in cursor.calls
        if _is_dml(statement) and "into entities" in _normalized(statement)
    ]
    assert connection.commits == 1
    assert result.outcome == "changed"
    assert entity_dml == []
    assert any(
        "into okf_manual_fact_ownership" in _normalized(statement)
        for statement, _ in cursor.calls
        if _is_dml(statement)
    )


@pytest.mark.parametrize(
    ("kind", "case"),
    (
        ("entity", "owner_without_base"),
        ("entity", "different_id_same_natural_key"),
        ("entity", "existing_id_without_owner"),
        ("entity", "material_mismatch"),
        ("entity", "unmanaged_material"),
        ("relation", "different_id_same_natural_key"),
        ("relation", "material_mismatch"),
        ("relation", "unmanaged_material"),
    ),
)
def test_collision_preflight_rejects_ambiguous_or_unmanaged_existing_material(
    kind: str, case: str
) -> None:
    desired = _desired((kind,))
    fact = (
        desired.manual_entities[0] if kind == "entity" else desired.manual_relations[0]
    )
    valid_owner = _ownership_row(desired.ownership_facts[0])
    if kind == "entity":
        row: Mapping[str, object] | None = _entity_row(fact)
    else:
        row = _relation_row(fact)

    ownership_rows: tuple[Mapping[str, object], ...] = (valid_owner,)
    preflight_only_base = False
    if case == "owner_without_base":
        row = None
    elif case == "different_id_same_natural_key":
        identifier = str(UUID(int=9001 if kind == "entity" else 9002))
        row = (
            _entity_row(fact, entity_id=identifier)
            if kind == "entity"
            else _relation_row(fact, relation_id=identifier)
        )
        ownership_rows = ()
        preflight_only_base = True
    elif case == "existing_id_without_owner":
        ownership_rows = ()
    elif case == "material_mismatch":
        row = (
            _entity_row(fact, entity_type="legacy_concept")
            if kind == "entity"
            else _relation_row(fact, relation_type="legacy_supports")
        )
    elif case == "unmanaged_material":
        row = (
            _entity_row(
                fact,
                description="legacy unmanaged description",
                community_id=str(UUID(int=9003)),
            )
            if kind == "entity"
            else _relation_row(
                fact, description="legacy unmanaged relation description"
            )
        )
    else:
        raise AssertionError(f"unsupported collision case: {case}")

    desired, cursor = _failure_cursor(
        kind=kind,
        base_row=row,
        ownership_rows=ownership_rows,
        preflight_only_base=preflight_only_base,
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError):
        E2aReconciler().reconcile(connection, desired)

    _assert_table_locks(cursor)
    _assert_collision_preflight(cursor, desired)
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    "malformed_case",
    ("partial_shape", "wrong_target", "wrong_scope", "wrong_identity"),
)
def test_collision_preflight_fails_closed_for_malformed_existing_ownership(
    malformed_case: str,
) -> None:
    desired = _desired(("entity",))
    fact = desired.manual_entities[0]
    owner = _ownership_row(desired.ownership_facts[0])
    if malformed_case == "partial_shape":
        malformed: Mapping[str, object] = {"ownership_id": owner["ownership_id"]}
    elif malformed_case == "wrong_target":
        malformed = {
            **owner,
            "entity_id": None,
            "relation_id": fact.fact_id,
        }
    elif malformed_case == "wrong_scope":
        malformed = {
            **owner,
            "scope_version_id": str(UUID(int=9004)),
            "document_id": None,
            "version_id": None,
        }
    elif malformed_case == "wrong_identity":
        malformed = {**owner, "ownership_id": str(UUID(int=9005))}
    else:
        raise AssertionError(f"unsupported malformed ownership case: {malformed_case}")
    cursor = _CollisionCursor(
        entity_rows=(_entity_row(fact),),
        preflight_only_ownership=True,
        malformed_preflight_row=malformed,
        malformed_preflight_target="ownership",
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError):
        E2aReconciler().reconcile(connection, desired)

    _assert_table_locks(cursor)
    _assert_collision_preflight(cursor, desired)
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("kind", "target"),
    (("entity", "entities"), ("relation", "relations"), ("entity", "ownership")),
)
def test_collision_preflight_rejects_partial_base_or_owner_rows_before_dml(
    kind: str, target: str
) -> None:
    desired = _desired((kind,))
    fact = (
        desired.manual_entities[0] if kind == "entity" else desired.manual_relations[0]
    )
    partial = (
        {"entity_id": fact.fact_id}
        if target == "entities"
        else (
            {"relation_id": fact.fact_id}
            if target == "relations"
            else {"ownership_id": desired.ownership_facts[0].ownership_id}
        )
    )
    cursor = _CollisionCursor(
        preflight_only_base=True,
        preflight_only_ownership=True,
        malformed_preflight_row=partial,
        malformed_preflight_target=target,
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError):
        E2aReconciler().reconcile(connection, desired)

    _assert_table_locks(cursor)
    _assert_collision_preflight(cursor, desired)
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_uses_postgres_semantic_parity_for_confidence_and_qualifiers() -> (
    None
):
    """Semantically equal existing relation produces no-op; no material mismatch raised."""
    desired = _relation_desired(
        {
            "negation": False,
            "confidence": 0.75,
            "qualifiers": {"labels": ["猫"], "rank": 1},
        }
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(
                fact,
                confidence=Decimal("0.75"),
                qualifiers={"labels": ["猫"], "rank": Decimal("1.0")},
            ),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    result = E2aReconciler().reconcile(connection, desired)

    _assert_locks_precede_preflight_no_dml_required(cursor, desired)
    assert result.outcome == "no_op"
    assert connection.commits == 1
    assert connection.rollbacks == 0


@pytest.mark.parametrize(
    ("confidence_mismatch", "qualifiers_mismatch"),
    (
        (Decimal("0.751"), None),
        (None, {"labels": ["猫"], "rank": 2}),
    ),
)
def test_collision_preflight_rejects_numeric_or_jsonb_material_mismatch(
    confidence_mismatch: object,
    qualifiers_mismatch: object,
) -> None:
    desired = _relation_desired(
        {
            "negation": False,
            "confidence": 0.75,
            "qualifiers": {"labels": ["猫"], "rank": 1},
        }
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(
                fact,
                confidence=confidence_mismatch,
                qualifiers=qualifiers_mismatch,
            ),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_distinguishes_sql_null_from_json_null_qualifiers() -> None:
    desired = _relation_desired(
        {"negation": False, "confidence": None, "qualifiers": {}}
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(_relation_row(fact, qualifiers_is_sql_null=True),),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_rejects_bool_vs_int_distinction_in_jsonb() -> None:
    """RED: JSONB distinguishes true from 1; production should reject bool/int mismatch."""
    desired = _relation_desired(
        {"negation": False, "confidence": None, "qualifiers": {"flag": True}}
    )
    fact = desired.manual_relations[0]
    # Existing has int 1 instead of bool True
    cursor = _CollisionCursor(
        relation_rows=(_relation_row(fact, qualifiers={"flag": 1}),),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_rejects_decimal_to_float_precision_loss() -> None:
    """RED: Decimal with more precision than float should not match float approximation."""
    # Desired: float 1.1234567890123457 (the closest float representation)
    # Existing: Decimal("1.12345678901234567890") (more precision than float can represent)
    # Production converts Decimal to float, losing precision and matching the desired.
    # Correct behavior: should detect mismatch and raise.
    desired = _relation_desired(
        {"negation": False, "confidence": 1.1234567890123457, "qualifiers": {}}
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(
                fact,
                confidence=Decimal("1.12345678901234567890"),
                qualifiers={},
            ),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_rejects_non_finite_confidence_in_existing_row() -> None:
    """RED: Existing row with non-finite confidence should be rejected, not treated as equal."""
    import math

    desired = _relation_desired(
        {"negation": False, "confidence": 0.75, "qualifiers": {}}
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(
                fact,
                confidence=math.inf,
                qualifiers={},
            ),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material|finite"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_rejects_non_finite_in_nested_qualifiers() -> None:
    """RED: Existing row with non-finite value in nested qualifiers should be rejected."""
    import math

    desired = _relation_desired(
        {"negation": False, "confidence": None, "qualifiers": {"score": 1.0}}
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(
                fact,
                qualifiers={"score": math.inf},
            ),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material|finite"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_collision_preflight_treats_explicit_sql_null_flag_as_authoritative_over_matching_qualifiers_value() -> (
    None
):
    """RED: the explicit qualifiers_is_sql_null flag must be authoritative.

    An otherwise-matching relation row whose qualifiers value is {} but whose
    qualifiers_is_sql_null flag is True claims a SQL-NULL column. The preflight
    must raise a material mismatch because the flag is authoritative, instead
    of silently accepting {} == {}.
    """
    desired = _relation_desired(
        {"negation": False, "confidence": None, "qualifiers": {}}
    )
    fact = desired.manual_relations[0]
    cursor = _CollisionCursor(
        relation_rows=(
            _relation_row(fact, qualifiers={}, qualifiers_is_sql_null=True),
        ),
        ownership_rows=(_ownership_row(desired.ownership_facts[0]),),
    )
    connection = _Connection(cursor)

    with pytest.raises(ValueError, match="material"):
        E2aReconciler().reconcile(connection, desired)

    assert connection.commits == 0
    assert connection.rollbacks == 1
