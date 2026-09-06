"""Regression coverage for E2a relation inventory and cursor JSON parity."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID

import pytest

from llamaindex_runtime.okf import (
    _e2a_materialization_inventory as inventory,
    e2a_reconciler as reconciler_module,
)
from llamaindex_runtime.okf.e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aEvidenceObject,
    E2aEvidenceReference,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)

_DIGEST = "a" * 64


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[Mapping[str, object]]:
        return []


def _manual_relation_desired(nested_qualifiers: object) -> E2aDesiredState:
    subject_id, object_id = str(UUID(int=401)), str(UUID(int=402))
    natural_key = canonical_json(
        {
            "subject_entity_id": subject_id,
            "predicate": "treats",
            "object_entity_id": object_id,
        }
    )
    relation = E2aManualFact(
        deterministic_id("relation", natural_key),
        "relation",
        "relations/cat-treats.md",
        _DIGEST,
        qualifiers={"qualifiers": nested_qualifiers},
        natural_key=natural_key,
    )
    ownership = E2aOwnershipFact.create(
        relative_path=relation.relative_path,
        fact_kind="relation",
        fact_id=relation.fact_id,
        source_digest=relation.source_digest,
    )
    manifest = {
        "artifacts": [
            {
                "kind": "relation",
                "path": relation.relative_path,
                "identity": relation.fact_id,
                "source_digest": relation.source_digest,
            }
        ]
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
        manual_entities=(),
        manual_relations=(relation,),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(ownership,),
        sync_state_rows=(),
        validation_metadata={},
        provenance_metadata={"authority": "okf"},
    )


def test_relation_qualifiers_require_an_object_but_allow_nested_json_null() -> None:
    valid_cursor = _Cursor()
    E2aMaterializationRepository().reconcile(
        valid_cursor,
        _manual_relation_desired({"extension": {"nullable": None}}),
        recorder=DmlRecorder(),
    )
    assert any(
        statement.startswith("INSERT INTO relations")
        for statement, _ in valid_cursor.calls
    )

    invalid_cursor = _Cursor()
    with pytest.raises(ValueError, match="relation qualifiers must be an object"):
        E2aMaterializationRepository().reconcile(
            invalid_cursor,
            _manual_relation_desired(None),
            recorder=DmlRecorder(),
        )

    assert invalid_cursor.calls == []


class _InventoryDesired:
    parents: tuple[object, ...]
    canonical_spans: tuple[object, ...] = ()
    vector_chunks: tuple[object, ...] = ()
    tree_nodes: tuple[object, ...] = ()
    evidence_objects: tuple[object, ...] = ()
    evidence_links: tuple[object, ...] = ()
    ownership_facts: tuple[object, ...] = ()
    manual_entities: tuple[object, ...] = ()
    sync_state_rows: tuple[object, ...] = ()

    def __init__(self, *, parents: tuple[object, ...]) -> None:
        self.parents = parents
        self.manual_relations = ({"fact_id": "relation-1"},)


class _RelationInventoryCursor(_Cursor):
    def __init__(self, *, qualifiers_is_sql_null: bool | None = None) -> None:
        super().__init__()
        self._qualifiers_is_sql_null = qualifiers_is_sql_null

    def fetchall(self) -> list[Mapping[str, object]]:
        statement = self.calls[-1][0]
        if self._qualifiers_is_sql_null is not None and "FROM relations" in statement:
            return [
                {
                    "relation_id": "relation-1",
                    "relation_key": "key",
                    "relation_type": "type",
                    "source_entity_id": "source",
                    "target_entity_id": "target",
                    "negation": False,
                    "condition": None,
                    "direction": None,
                    "confidence": None,
                    "qualifiers": None,
                    "qualifiers_is_sql_null": self._qualifiers_is_sql_null,
                }
            ]
        return []


def test_relation_inventory_transports_and_normalizes_sql_null_separately_from_json_null() -> (
    None
):
    desired = _InventoryDesired(parents=())
    sql_null_cursor = _RelationInventoryCursor(qualifiers_is_sql_null=True)
    json_null_cursor = _RelationInventoryCursor(qualifiers_is_sql_null=False)

    sql_null_scope = inventory.load_existing_scope(sql_null_cursor, desired)
    json_null_scope = inventory.load_existing_scope(json_null_cursor, desired)

    sql_null_row = sql_null_scope["relations"][0]
    json_null_row = json_null_scope["relations"][0]
    assert "qualifiers_is_sql_null" not in sql_null_row
    assert sql_null_row["qualifiers"] is not None
    assert json_null_row["qualifiers"] is None
    assert sql_null_row["qualifiers"] is not json_null_row["qualifiers"]


def test_parent_scoped_relation_inventory_requests_sql_null_discriminator() -> None:
    cursor = _RelationInventoryCursor()

    inventory.load_existing_scope(
        cursor,
        _InventoryDesired(parents=({"version_id": "version-1"},)),
    )

    relation_statements = [
        statement for statement, _ in cursor.calls if "FROM relations" in statement
    ]
    assert len(relation_statements) == 2
    assert all(
        "qualifiers IS NULL AS qualifiers_is_sql_null" in statement
        for statement in relation_statements
    )


class _ConfigurableAdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _ConfigurableCursor(_Cursor):
    def __init__(self) -> None:
        super().__init__()
        self.adapters = _ConfigurableAdapterRegistry()
        self.connection = object()

    def close(self) -> None:
        return None


class _ConfigurableConnection:
    autocommit = False

    def __init__(self) -> None:
        self.cursor_value = _ConfigurableCursor()
        self.commits = 0

    def close(self) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("no-op reconciliation must not roll back")

    def cursor(self, **_: object) -> _ConfigurableCursor:
        return self.cursor_value


class _NoOpRepository:
    def reconcile(self, *_: object, **__: object) -> object:
        return object()


def test_primary_cursor_uses_decimal_json_loaders_without_touching_global_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, object]] = []

    def configure(loads: object, *, context: object) -> None:
        calls.append((loads, context))

    monkeypatch.setattr(reconciler_module, "set_json_loads", configure)
    connection = _ConfigurableConnection()
    reconciler_module.E2aReconciler(repository=_NoOpRepository()).reconcile(
        connection, _manual_relation_desired({})
    )

    assert len(calls) == 1
    loads, context = calls[0]
    assert context is connection.cursor_value
    assert callable(loads)
    assert loads('{"fraction":1.125}')["fraction"] == Decimal("1.125")  # type: ignore[operator]


def _forged_evidence_confidence_desired() -> E2aDesiredState:
    document_id, version_id, span_id = (
        str(UUID(int=value)) for value in (701, 702, 703)
    )
    subject_id, object_id = (str(UUID(int=value)) for value in (705, 706))
    natural_key = canonical_json(
        {
            "subject_entity_id": subject_id,
            "predicate": "supports",
            "object_entity_id": object_id,
        }
    )
    relation = E2aManualFact(
        deterministic_id("relation", natural_key),
        "relation",
        "relations/forged-confidence.md",
        _DIGEST,
        qualifiers={},
        natural_key=natural_key,
    )
    ownership = E2aOwnershipFact.create(
        relative_path=relation.relative_path,
        fact_kind="relation",
        fact_id=relation.fact_id,
        source_digest=relation.source_digest,
        document_id=document_id,
        version_id=version_id,
    )
    evidence = E2aEvidenceObject.create(
        version_id=version_id, entity_id=None, relation_id=relation.fact_id
    )
    link = E2aEvidenceReference(
        document_id,
        version_id,
        span_id,
        None,
        relation.fact_id,
        evidence.evidence_id,
        ownership.ownership_id,
        ownership.scope_version_id,
    )
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": "raw/forged.pair.json",
                "identity": f"{document_id}:{version_id}",
                "canonical_hash": _DIGEST,
            },
            {
                "kind": "relation",
                "path": relation.relative_path,
                "identity": relation.fact_id,
                "source_digest": relation.source_digest,
            },
        ]
    }
    desired = E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(E2aParent(document_id, version_id, "raw/forged.pair.json", _DIGEST),),
        canonical_spans=(E2aSpan(document_id, version_id, span_id, 0, "evidence"),),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(relation,),
        manual_concepts=(),
        evidence_objects=(evidence,),
        evidence_links=(link,),
        ownership_facts=(ownership,),
        sync_state_rows=(),
        validation_metadata={},
        provenance_metadata={"authority": "okf"},
    )
    object.__setattr__(link, "confidence", float("nan"))
    return desired


def test_forged_evidence_link_confidence_fails_before_inventory_cursor_activity() -> (
    None
):
    cursor = _Cursor()

    with pytest.raises(ValueError, match="confidence"):
        E2aMaterializationRepository().reconcile(
            cursor,
            _forged_evidence_confidence_desired(),
            recorder=DmlRecorder(),
        )

    assert cursor.calls == []
