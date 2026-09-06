"""RED specifications for cursor-only, atomic E2a reconciliation."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from uuid import UUID

import psycopg
import pytest

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aManualFact,
    E2aOwnershipFact,
    E2aParent,
    E2aReconciliationResult,
    E2aSpan,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.vector.loader import VectorLoader

_REPOSITORY_MODULE = "llamaindex_runtime.okf.e2a_materialization_repository"
_RECONCILER_MODULE = "llamaindex_runtime.okf.e2a_reconciler"
_DIGEST = "a" * 64
_PRIMARY_TABLES = frozenset(
    {
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
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)
_DENYLIST_TABLES = frozenset(
    {
        "chunk_entity_links",
        "node_entity_links",
        "entity_mentions",
        "entity_aliases",
        "entity_merge_log",
        "ner_entities",
        "ner_relations",
        "fusion_state",
        "r3_state",
        "external_projection_status",
    }
)


def _repository_module() -> ModuleType:
    specification = importlib.util.find_spec(_REPOSITORY_MODULE)
    assert specification is not None, (
        "Wave 2 RED: llamaindex_runtime.okf.e2a_materialization_repository "
        "must provide the cursor-only reconciliation repository"
    )
    return importlib.import_module(_REPOSITORY_MODULE)


def _reconciler_module() -> ModuleType:
    specification = importlib.util.find_spec(_RECONCILER_MODULE)
    assert specification is not None, (
        "Wave 2 RED: llamaindex_runtime.okf.e2a_reconciler must provide "
        "transaction orchestration"
    )
    return importlib.import_module(_RECONCILER_MODULE)


def _uuid(number: int) -> str:
    return str(UUID(int=number))


def _desired(*, parent_count: int = 1) -> E2aDesiredState:
    parents = tuple(
        E2aParent(_uuid(index), _uuid(index + 100), f"raw/{index}.pair.json", _DIGEST)
        for index in range(1, parent_count + 1)
    )
    manifest = {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            }
            for parent in parents
        ],
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=parents,
        canonical_spans=(),
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
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _span_desired() -> E2aDesiredState:
    parent = _desired().parents[0]
    span = E2aSpan(parent.document_id, parent.version_id, _uuid(300), 0, "body")
    base = _desired()
    return E2aDesiredState(
        **{
            **base.__dict__,
            "canonical_spans": (span,),
        }
    )


def _relation_desired(*, confidence: float = 0.75) -> E2aDesiredState:
    subject_id, object_id = _uuid(401), _uuid(402)
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
        qualifiers={
            "negation": False,
            "condition": "when prescribed",
            "direction": "forward",
            "confidence": confidence,
            "qualifiers": {"labels": ["猫", "care"], "rank": 1},
        },
        natural_key=natural_key,
    )
    ownership = E2aOwnershipFact.create(
        relative_path=relation.relative_path,
        fact_kind="relation",
        fact_id=relation.fact_id,
        source_digest=relation.source_digest,
    )
    parent = _desired().parents[0]
    manifest = {
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": parent.relative_path,
                "identity": f"{parent.document_id}:{parent.version_id}",
                "canonical_hash": parent.canonical_hash,
            },
            {
                "kind": "relation",
                "path": relation.relative_path,
                "identity": relation.fact_id,
                "source_digest": relation.source_digest,
            },
        ]
    }
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
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
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _is_dml(statement: str) -> bool:
    return statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))


class _AdapterRegistry:
    def register_loader(self, _: str, __: object) -> None:
        return None


class _Cursor:
    def __init__(self, *, forbid_dml: bool = False) -> None:
        self.forbid_dml = forbid_dml
        self.calls: list[tuple[str, object | None]] = []
        self.adapters = _AdapterRegistry()
        self.connection = object()
        self.closed = 0
        self._last_statement = ""

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))
        if self.forbid_dml and _is_dml(statement):
            raise AssertionError(
                f"equivalent/rejected reconciliation issued DML: {statement}"
            )

    def fetchall(self) -> list[dict[str, object]]:
        parameters = self.calls[-1][1]
        is_parent_lock = "document_versions" in self._last_statement.lower()
        if is_parent_lock and isinstance(parameters, tuple) and len(parameters) == 2:
            return [{"doc_id": parameters[0], "version_id": parameters[1]}]
        return []

    def fetchone(self) -> object | None:
        # Return a row for INSERT...RETURNING statements (required for global tables)
        if "RETURNING" in self._last_statement.upper():
            return {"1": 1}
        return None

    def close(self) -> None:
        self.closed += 1


def _dml_statements(cursor: _Cursor) -> list[str]:
    return [statement for statement, _ in cursor.calls if _is_dml(statement)]


def _recorder(module: ModuleType) -> object:
    return module.DmlRecorder()


def test_repository_public_signature_is_cursor_only_and_does_not_own_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _repository_module()
    signature = inspect.signature(module.E2aMaterializationRepository.reconcile)
    cursor = _Cursor(forbid_dml=True)
    repository = module.E2aMaterializationRepository()

    monkeypatch.setattr(
        psycopg, "connect", lambda *_args, **_kwargs: pytest.fail("no connection")
    )
    result = repository.reconcile(cursor, _desired(), recorder=_recorder(module))

    assert list(signature.parameters) == ["self", "cursor", "desired", "recorder"]
    assert signature.parameters["recorder"].kind is inspect.Parameter.KEYWORD_ONLY
    assert result.outcome == "no_op"
    assert cursor.closed == 0
    assert _dml_statements(cursor) == []


def test_dml_recorder_separates_issued_primary_dml_from_measured_cache_effects() -> (
    None
):
    module = _repository_module()
    recorder = _recorder(module)
    direct_tables = _PRIMARY_TABLES - {
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }

    for table in sorted(direct_tables):
        recorder.record_issued(table=table, operation="DELETE")
    for table in ("summaries", "node_embeddings", "semantic_distribution"):
        recorder.record_cache_effect(table=table, count=1)
    for table in sorted(_DENYLIST_TABLES):
        with pytest.raises(ValueError, match="forbidden.*(DML|cascade)"):
            recorder.record_measured_effect(table=table, count=1, origin="cascade")

    assert recorder.issued_dml_by_table == {table: 1 for table in direct_tables}
    assert recorder.measured_cache_effects == {
        "summaries": 1,
        "node_embeddings": 1,
        "semantic_distribution": 1,
    }
    assert recorder.denylist_dml_counts == {table: 1 for table in _DENYLIST_TABLES}


def test_equivalent_empty_corpus_rerun_has_exact_zero_dml_including_sync_and_ownership() -> (
    None
):
    module = _repository_module()
    cursor = _Cursor(forbid_dml=True)

    result = module.E2aMaterializationRepository().reconcile(
        cursor, _desired(parent_count=0), recorder=_recorder(module)
    )

    assert result.outcome == "no_op"
    assert _dml_statements(cursor) == []
    assert {
        table: result.primary_dml_by_table.get(table, 0) for table in _PRIMARY_TABLES
    } == {table: 0 for table in _PRIMARY_TABLES}
    assert result.denylist_dml_counts == {table: 0 for table in _DENYLIST_TABLES}
    assert not any(
        "okf_rebuild_failure_audit" in statement for statement, _ in cursor.calls
    )


def test_reconciliation_never_delegates_to_legacy_registry_or_vector_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _repository_module()
    cursor = _Cursor()

    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("legacy registry/vector primitive is forbidden for E2a")

    for name in (
        "write_spans",
        "write_tree",
        "write_vector_chunks",
        "write_entities",
        "write_relations",
        "write_evidence_links",
        "write_chunk_entity_links",
        "write_node_entity_links",
    ):
        monkeypatch.setattr(PostgresRegistryWriter, name, forbidden)
    monkeypatch.setattr(VectorLoader, "load", forbidden)

    module.E2aMaterializationRepository().reconcile(
        cursor, _span_desired(), recorder=_recorder(module)
    )

    assert all(
        "postgresregistrywriter" not in statement.lower()
        for statement, _ in cursor.calls
    )


def test_orchestrator_locks_global_then_sorted_parents_then_existing_rows() -> None:
    module = _reconciler_module()
    cursor = _Cursor()
    repository_calls: list[object] = []

    class Repository:
        def reconcile(
            self, supplied: object, desired: object, *, recorder: object
        ) -> object:
            repository_calls.append((len(cursor.calls), supplied, desired, recorder))
            return E2aReconciliationResult(
                outcome="no_op",
                manifest_sha256=desired.corpus_manifest_sha256,
                primary_dml_by_table={},
                denylist_dml_counts={},
                comparator_parity=True,
                stale_deletion_counts={},
                cache_invalidation_counts={},
                failure_audit_outcome=None,
                post_rollback_failure_audit_outcome=None,
            )

    connection = _Connection(cursor)
    desired = _desired(parent_count=2)
    module.E2aReconciler(repository=Repository()).reconcile(connection, desired)

    statements = [statement for statement, _ in cursor.calls]
    advisory_indexes = [
        index
        for index, statement in enumerate(statements)
        if "pg_advisory_xact_lock" in statement
    ]
    row_lock_indexes = [
        index
        for index, statement in enumerate(statements)
        if "for update" in statement.lower()
    ]
    advisory_parameters = [cursor.calls[index][1] for index in advisory_indexes[1:]]

    assert len(advisory_indexes) == 1 + len(desired.parents)
    assert advisory_indexes == sorted(advisory_indexes)
    assert advisory_parameters == sorted(advisory_parameters, key=repr)
    assert len(row_lock_indexes) == len(desired.parents)
    assert min(row_lock_indexes) > max(advisory_indexes)
    assert all(
        "order by" not in statements[index].lower() for index in row_lock_indexes
    )
    assert all("for update" in statements[index].lower() for index in row_lock_indexes)
    row_lock_parameters = [cursor.calls[index][1] for index in row_lock_indexes]
    assert row_lock_parameters == sorted(row_lock_parameters, key=repr)
    assert repository_calls and repository_calls[0][1] is cursor
    assert max((*advisory_indexes, *row_lock_indexes)) < repository_calls[0][0]
    assert connection.commits == 1


class _DependencyCursor(_Cursor):
    def __init__(self, dependency: str) -> None:
        super().__init__(forbid_dml=True)
        self.dependency = dependency

    def fetchall(self) -> list[dict[str, object]]:
        statement = self._last_statement.lower()
        for field in ("span_id", "chunk_id", "node_id", "evidence_id"):
            if f"where {field} = any" in statement and "for update" in statement:
                parameters = self.calls[-1][1]
                assert isinstance(parameters, tuple) and len(parameters) == 1
                identifiers = parameters[0]
                assert isinstance(identifiers, list)
                return [{field: identifier} for identifier in sorted(identifiers)]
        if "select exists" in statement:
            return [{"present": self.dependency in statement}]
        if "canonical_spans" in statement and self.dependency in {
            "entity_mentions",
            "legacy_evidence",
        }:
            return [{"span_id": _uuid(501), "version_id": _uuid(101)}]
        if "vector_chunks" in statement and self.dependency == "chunk_entity_links":
            return [{"chunk_id": _uuid(502), "version_id": _uuid(101)}]
        if "tree_nodes" in statement and self.dependency == "node_entity_links":
            return [
                dict(node_id=_uuid(503), parent_node_id=None, version_id=_uuid(101)),
                dict(
                    node_id=_uuid(504),
                    parent_node_id=_uuid(503),
                    version_id=_uuid(101),
                ),
            ]
        if self.dependency == "node_entity_links" and "node_entity_links" in statement:
            return [{"node_id": _uuid(504)}]
        if self.dependency == "legacy_evidence" and "evidence_links" in statement:
            return [{"evidence_link_id": _uuid(505)}]
        return []

    def fetchone(self) -> object | None:
        if self.dependency in self._last_statement.lower():
            return {"present": True}
        return None


@pytest.mark.parametrize(
    ("dependency", "message"),
    (
        ("entity_mentions", "stale span"),
        ("legacy_evidence", "stale span"),
        ("chunk_entity_links", "stale chunk"),
        ("node_entity_links", "stale tree"),
    ),
)
def test_stale_closure_rejects_e2b_or_legacy_dependencies_without_any_mutation(
    dependency: str, message: str
) -> None:
    module = _repository_module()
    cursor = _DependencyCursor(dependency)

    with pytest.raises(ValueError, match=message):
        module.E2aMaterializationRepository().reconcile(
            cursor, _desired(), recorder=_recorder(module)
        )

    assert _dml_statements(cursor) == []
    assert any(
        dependency.replace("legacy_", "") in statement.lower()
        for statement, _ in cursor.calls
    )


class _RepairCursor(_Cursor):
    @property
    def rowcount(self) -> int:
        return 999

    def fetchall(self) -> list[dict[str, object]]:
        statement = self._last_statement.lower()
        for field in ("chunk_id", "node_id"):
            if f"where {field} = any" in statement and "for update" in statement:
                parameters = self.calls[-1][1]
                assert isinstance(parameters, tuple) and len(parameters) == 1
                identifiers = parameters[0]
                assert isinstance(identifiers, list)
                return [{field: identifier} for identifier in sorted(identifiers)]
        if "select exists" in statement:
            return [{"present": False}]
        if "tree_nodes" in statement:
            return [
                dict(node_id=_uuid(601), parent_node_id=None, version_id=_uuid(101)),
            ]
        if "vector_chunks" in statement:
            # fmt: off
            return [{
                "chunk_id": _uuid(602), "version_id": _uuid(101), "chunk_type": "canonical_span", "chunk_order": 0, "token_count": 2,
                "text_preview": "Admitted text.", "page_no": 1, "heading_path": "Guide", "node_id": _uuid(601), "embedding": [0.0] * 16,
            }]
            # fmt: on
        return []


def test_stale_node_repair_repoints_surviving_chunks_then_invalidates_caches() -> None:
    module = _repository_module()
    base = _desired()
    desired = E2aDesiredState(
        **{
            **base.__dict__,
            "tree_nodes": (
                {
                    "node_id": _uuid(603),
                    "version_id": base.parents[0].version_id,
                    "parent_node_id": None,
                    "node_type": "chapter",
                    "level_no": 0,
                    "title": "Guide",
                    "page_start": None,
                    "page_end": None,
                    "summary_text": None,
                    "heading_path": "Guide",
                },
            ),
            # fmt: off
            "vector_chunks": ({
                "chunk_id": _uuid(602), "version_id": base.parents[0].version_id, "chunk_type": "canonical_span", "chunk_order": 0, "token_count": 2,
                "text_preview": "Admitted text.", "page_no": 1, "heading_path": "Guide", "node_id": _uuid(603), "embedding": [0.0] * 16,
            },),
            # fmt: on
        }
    )
    cursor = _RepairCursor()

    result = module.E2aMaterializationRepository().reconcile(
        cursor, desired, recorder=_recorder(module)
    )

    sql = [statement.lower() for statement in _dml_statements(cursor)]
    repoint = next(i for i, s in enumerate(sql) if "update vector_chunks" in s)
    invalidate = [
        i
        for i, s in enumerate(sql)
        if any(
            t in s for t in ("summaries", "node_embeddings", "semantic_distribution")
        )
    ]
    delete_node = next(i for i, s in enumerate(sql) if "delete from tree_nodes" in s)

    assert repoint < min(invalidate) < delete_node
    assert result.stale_deletion_counts["tree_nodes"] == 1
    assert result.cache_invalidation_counts == {
        "summaries": 1,
        "node_embeddings": 1,
        "semantic_distribution": 1,
    }
    assert 999 not in result.cache_invalidation_counts.values()


class _OwnershipCursor(_Cursor):
    def __init__(self, dependency: str) -> None:
        super().__init__()
        self.dependency = dependency

    def fetchall(self) -> list[dict[str, object]]:
        statement = self._last_statement.lower()
        if "select exists" in statement:
            return [{"present": self.dependency in statement}]
        if (
            "from okf_manual_fact_ownership" in statement
            and "version_id is null" in statement
        ):
            return [
                {
                    "ownership_id": _uuid(701),
                    "okf_relative_path": "facts/entity.md",
                    "fact_kind": "entity",
                    "fact_id": _uuid(702),
                    "entity_id": _uuid(702),
                    "relation_id": None,
                    "source_digest": _DIGEST,
                    "document_id": None,
                    "version_id": None,
                    "scope_version_id": _uuid(0),
                }
            ]
        if statement == (
            "select entity_id from entities where entity_id = any(%s) "
            "order by entity_id for update"
        ):
            return [{"entity_id": _uuid(702)}]
        if "from entities" in statement:
            return [
                {
                    "entity_id": _uuid(702),
                    "entity_key": "global-entity",
                    "entity_type": "concept",
                    "canonical_name": "Global entity",
                }
            ]
        return []

    def fetchone(self) -> object | None:
        return (
            {"present": True}
            if self.dependency in self._last_statement.lower()
            else None
        )


@pytest.mark.parametrize(
    "dependency",
    (
        "entity_aliases",
        "relations",
        "evidence_links",
        "node_entity_links",
        "chunk_entity_links",
    ),
)
def test_removing_last_e2a_owner_preserves_global_fact_with_external_dependencies(
    dependency: str,
) -> None:
    module = _repository_module()
    cursor = _OwnershipCursor(dependency)

    module.E2aMaterializationRepository().reconcile(
        cursor, _desired(), recorder=_recorder(module)
    )

    dml = "\n".join(_dml_statements(cursor)).lower()
    assert "delete from entities" not in dml
    assert "delete from relations" not in dml
    assert f"delete from {dependency}" not in dml


def test_relation_diff_uses_null_safe_exact_fields_and_rejects_nonfinite_confidence() -> (
    None
):
    module = _repository_module()
    cursor = _Cursor()
    relation_state = _relation_desired()

    module.E2aMaterializationRepository().reconcile(
        cursor, relation_state, recorder=_recorder(module)
    )
    relation_sql = "\n".join(
        statement
        for statement in _dml_statements(cursor)
        if "relations" in statement.lower()
    ).lower()

    for field in ("negation", "condition", "direction", "confidence", "qualifiers"):
        assert f"{field} is distinct from" in relation_sql
    assert "::jsonb" in relation_sql
    assert "qualifiers is distinct from" in relation_sql
    assert "updated_at" not in relation_sql

    forged = _relation_desired()
    object.__setattr__(
        forged.manual_relations[0], "qualifiers", {"confidence": float("nan")}
    )
    with pytest.raises(ValueError, match="finite.*confidence"):
        module.E2aMaterializationRepository().reconcile(
            _Cursor(), forged, recorder=_recorder(module)
        )


@dataclass
class _Connection:
    cursor_value: _Cursor
    autocommit: bool = False
    rollback_error: Exception | None = None
    close_error: Exception | None = None
    commits: int = 0
    rollbacks: int = 0
    closed: int = 0

    def cursor(self, **_: object) -> _Cursor:
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


def test_precommit_failure_rolls_back_closes_primary_then_uses_fresh_redacted_bounded_audit() -> (
    None
):
    module = _reconciler_module()
    primary = _Connection(_Cursor())
    audit = _Connection(_Cursor())
    events: list[str] = []

    class FailingRepository:
        def reconcile(
            self, cursor: object, desired: object, *, recorder: object
        ) -> object:
            events.append("repository")
            raise RuntimeError("opaque-primary-failure")

    def audit_factory() -> _Connection:
        assert primary.rollbacks == 1
        assert primary.closed == 1
        events.append("fresh-audit")
        return audit

    reconciler = module.E2aReconciler(
        repository=FailingRepository(), failure_audit_connection_factory=audit_factory
    )
    result = reconciler.reconcile(primary, _desired())

    assert result.outcome == "rolled_back_failure"
    assert events == ["repository", "fresh-audit"]
    assert primary.rollbacks == primary.closed == 1
    assert audit.closed == 1
    audit_sql = "\n".join(statement for statement, _ in audit.cursor_value.calls)
    assert "okf_rebuild_failure_audit" in audit_sql
    assert "opaque-primary-failure" not in repr(audit.cursor_value.calls)
    assert result.post_rollback_failure_audit_outcome in {
        "written",
        "blocked",
        "failed",
    }


def test_primary_failure_with_unconfirmed_cleanup_becomes_outcome_unknown() -> None:
    module = _reconciler_module()
    cursor = _Cursor()
    primary = _Connection(
        cursor,
        rollback_error=RuntimeError("rollback"),
        close_error=RuntimeError("close"),
    )

    class FailingRepository:
        def reconcile(self, *_: object, **__: object) -> object:
            raise RuntimeError("primary")

    result = module.E2aReconciler(repository=FailingRepository()).reconcile(
        primary, _desired()
    )

    assert result.outcome == "outcome_unknown"
    assert result.reconciliation_required is True
    assert primary.rollbacks == 1
    assert primary.closed == 1


def test_commit_acknowledgement_failure_is_unknown_and_never_rolls_back() -> None:
    module = _reconciler_module()

    class CommitUnknownConnection(_Connection):
        def commit(self) -> None:
            self.commits += 1
            raise ConnectionError("commit acknowledgement lost")

    class NoOpRepository:
        def reconcile(self, _: object, desired: object, *, recorder: object) -> object:
            return E2aReconciliationResult(
                outcome="no_op",
                manifest_sha256=desired.corpus_manifest_sha256,
                primary_dml_by_table={},
                denylist_dml_counts={},
                comparator_parity=True,
                stale_deletion_counts={},
                cache_invalidation_counts={},
                failure_audit_outcome=None,
                post_rollback_failure_audit_outcome=None,
            )

    connection = CommitUnknownConnection(_Cursor())
    reconciler = module.E2aReconciler(
        repository=NoOpRepository(),
        failure_audit_connection_factory=lambda: pytest.fail(
            "post-commit uncertainty must not write a failure audit"
        ),
    )

    result = reconciler.reconcile(connection, _desired())

    assert result.outcome == "outcome_unknown"
    assert result.reconciliation_required is True
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed == 1
