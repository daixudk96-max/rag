"""Pure E2a desired-state construction and root transaction orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol, cast

from psycopg.abc import AdaptContext
from psycopg.rows import RowFactory
from psycopg.types.json import set_json_loads

# TreeGenerator is re-exported for test monkeypatch compatibility
# (tests patch e2a_reconciler.TreeGenerator to inject test generators)
from llamaindex_runtime.registry.tree_generator import (
    TreeGenerator as TreeGenerator,
)

from ._e2a_manual_fact_collision_preflight import preflight_manual_fact_collisions
from ._e2a_materialization_input import (
    E2aDesiredStateBuilder as E2aDesiredStateBuilder,
    E2aMaterializationInput as E2aMaterializationInput,
)
from ._e2a_psycopg_rows import e2a_dict_row
from .e2a_contracts import (
    DmlRecorder,
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
    canonical_json,
)
from .e2a_materialization_repository import E2aMaterializationRepository

_MANUAL_FACT_TABLE_LOCKS = (
    "LOCK TABLE entities IN EXCLUSIVE MODE NOWAIT",
    "LOCK TABLE relations IN EXCLUSIVE MODE NOWAIT",
    "LOCK TABLE okf_manual_fact_ownership IN EXCLUSIVE MODE NOWAIT",
)


class _Closable(Protocol):
    """Protocol for objects with a close method."""

    def close(self) -> None: ...


class _Cursor(Protocol):
    def close(self) -> None: ...

    def execute(self, statement: str, parameters: object | None = None) -> None: ...

    def fetchall(self) -> object: ...

    def fetchone(self) -> Mapping[str, object] | None: ...


class _Connection(Protocol):
    autocommit: bool

    def close(self) -> None: ...

    def commit(self) -> None: ...

    def cursor(
        self, *, row_factory: RowFactory[dict[str, object]] | None = None
    ) -> _Cursor: ...

    def rollback(self) -> None: ...


class _Repository(Protocol):
    def reconcile(
        self,
        cursor: _Cursor,
        desired: E2aDesiredState,
        *,
        recorder: DmlRecorder,
    ) -> E2aReconciliationResult: ...


@dataclass(frozen=True)
class _ResourceCloseStatus:
    cursor_close_confirmed: bool
    connection_close_confirmed: bool

    @property
    def confirmed(self) -> bool:
        return self.cursor_close_confirmed and self.connection_close_confirmed


@dataclass(frozen=True)
class _PrimaryCleanupStatus:
    cursor_close_confirmed: bool
    rollback_confirmed: bool
    close_confirmed: bool

    @property
    def confirmed(self) -> bool:
        return (
            self.cursor_close_confirmed
            and self.rollback_confirmed
            and self.close_confirmed
        )


@dataclass(frozen=True)
class _AuditWriteResult:
    outcome: str
    cleanup: _ResourceCloseStatus | None


class E2aReconciler:
    """Own one primary transaction while delegating SQL to a cursor-only repository."""

    def __init__(
        self,
        *,
        repository: _Repository | None = None,
        builder: E2aDesiredStateBuilder | None = None,
        failure_audit_connection_factory: Callable[[], _Connection] | None = None,
        post_lock_sync_hook: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository or E2aMaterializationRepository()
        self._builder = builder
        self._failure_audit_connection_factory = failure_audit_connection_factory
        if post_lock_sync_hook is not None and not callable(post_lock_sync_hook):
            raise ValueError("post_lock_sync_hook must be callable or None")
        self._post_lock_sync_hook = post_lock_sync_hook

    def reconcile(
        self,
        connection: _Connection,
        desired: E2aDesiredState | E2aMaterializationInput,
    ) -> E2aReconciliationResult:
        _require_manual_transaction(connection)
        state = self._materialize_before_locks(desired)
        cursor: _Cursor | None = None
        try:
            cursor = connection.cursor(row_factory=e2a_dict_row)
            _configure_primary_json_loads(cursor)
            self._acquire_scope_locks(cursor, state)
            if self._post_lock_sync_hook is not None:
                self._post_lock_sync_hook()
            _preflight_global_primary_keys(cursor, state)
            preflight_manual_fact_collisions(cursor, state)
            result = self._repository.reconcile(cursor, state, recorder=DmlRecorder())
            _validate_repository_result(result, state)
            try:
                connection.commit()
            except Exception:
                _close_resources(cursor, connection)
                return _outcome_unknown(result)
            committed_cleanup = _close_resources(cursor, connection)
            if not committed_cleanup.confirmed:
                return _committed_cleanup_unconfirmed(result)
            return result
        except Exception as failure:
            cursor_close_confirmed = _close_quietly(cursor)
            cleanup = _rollback_and_close(
                connection,
                cursor_close_confirmed=cursor_close_confirmed,
            )
            if not cleanup.confirmed:
                return _cleanup_outcome_unknown(state)
            if self._failure_audit_connection_factory is None:
                raise failure
            audit_result = self._write_failure_audit(
                state,
                failure,
                rollback_confirmed=cleanup.rollback_confirmed,
            )
            return E2aReconciliationResult(
                outcome="rolled_back_failure",
                manifest_sha256=state.corpus_manifest_sha256,
                primary_dml_by_table={},
                denylist_dml_counts={},
                comparator_parity=None,
                stale_deletion_counts={},
                cache_invalidation_counts={},
                failure_audit_outcome=None,
                post_rollback_failure_audit_outcome=audit_result.outcome,
            )

    def _materialize_before_locks(
        self, desired: E2aDesiredState | E2aMaterializationInput
    ) -> E2aDesiredState:
        if type(desired) is E2aDesiredState:
            return desired
        if type(desired) is not E2aMaterializationInput:
            raise TypeError(
                "desired state must be E2aDesiredState or materialization input"
            )
        if self._builder is None:
            raise ValueError("materialization input requires an E2aDesiredStateBuilder")
        return self._builder.build(desired)

    def _acquire_scope_locks(self, cursor: _Cursor, desired: E2aDesiredState) -> None:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("okf:e2a:whole-corpus",),
        )
        parents = tuple(
            sorted(
                desired.parents,
                key=lambda parent: (parent.document_id, parent.version_id),
            )
        )
        for parent in parents:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"okf:e2a:parent:{parent.document_id}:{parent.version_id}",),
            )
        for parent in parents:
            cursor.execute(
                "SELECT doc_id, version_id FROM document_versions "
                "WHERE doc_id = %s AND version_id = %s FOR UPDATE",
                (parent.document_id, parent.version_id),
            )
            _validate_parent_lock_rows(cursor.fetchall(), parent)
        for statement in _MANUAL_FACT_TABLE_LOCKS:
            cursor.execute(statement)

    def _write_failure_audit(
        self,
        desired: E2aDesiredState,
        failure: Exception,
        *,
        rollback_confirmed: bool,
    ) -> _AuditWriteResult:
        audit_factory = self._failure_audit_connection_factory
        if audit_factory is None:
            return _AuditWriteResult("failed", None)
        try:
            audit_connection = audit_factory()
        except Exception:
            return _AuditWriteResult("failed", None)
        audit_cursor: _Cursor | None = None
        try:
            audit_cursor = audit_connection.cursor()
            scope = {
                "manifest_sha256": desired.corpus_manifest_sha256,
                "parent_count": len(desired.parents),
                "version_ids": [parent.version_id for parent in desired.parents[:100]],
            }
            audit_cursor.execute(
                "INSERT INTO okf_rebuild_failure_audit ("
                "audit_id, rebuild_run_id, failure_category, failure_code, failure_phase, "
                "rollback_confirmed, scope_count, scope_manifest, scope_manifest_sha256, "
                "failing_doc_id, failing_version_id, diagnostic"
                ") VALUES (gen_random_uuid(), gen_random_uuid(), %s, %s, %s, %s, %s, "
                "%s::jsonb, %s, NULL, NULL, %s::jsonb)",
                (
                    "internal",
                    "internal_failure",
                    "parent_reconciliation",
                    rollback_confirmed,
                    max(1, len(desired.parents)),
                    canonical_json(scope),
                    desired.corpus_manifest_sha256,
                    canonical_json({"error_type": type(failure).__name__[:64]}),
                ),
            )
        except Exception:
            outcome = "failed"
        else:
            try:
                audit_connection.commit()
            except Exception:
                outcome = "outcome_unknown"
            else:
                outcome = "written"
        cleanup = _close_resources(audit_cursor, audit_connection)
        if outcome == "written" and not cleanup.confirmed:
            outcome = "written_cleanup_unconfirmed"
        return _AuditWriteResult(outcome, cleanup)


def _configure_primary_json_loads(cursor: _Cursor) -> None:
    set_json_loads(
        lambda value: json.loads(value, parse_float=Decimal),
        context=_adaptation_context(cursor),
    )


def _adaptation_context(cursor: _Cursor) -> AdaptContext:
    adapters = getattr(cursor, "adapters", None)
    if not callable(getattr(adapters, "register_loader", None)):
        raise ValueError("primary cursor lacks a Psycopg adaptation context")
    if getattr(cursor, "connection", None) is None:
        raise ValueError("primary cursor lacks a Psycopg adaptation context")
    return cast(AdaptContext, cursor)


def _require_manual_transaction(connection: _Connection) -> None:
    try:
        autocommit = connection.autocommit
    except AttributeError:
        raise ValueError("connection autocommit must be exactly False") from None
    if type(autocommit) is not bool or autocommit is not False:
        raise ValueError("connection autocommit must be exactly False")


def _validate_parent_lock_rows(rows: object, parent: E2aParent) -> None:
    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
        raise ValueError("parent lock rows are invalid")
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise ValueError("parent lock row is invalid")
    row = rows[0]
    if set(row) != {"doc_id", "version_id"}:
        raise ValueError("parent lock row is invalid")
    document_id, version_id = row["doc_id"], row["version_id"]
    if (
        type(document_id) is not str
        or not document_id
        or type(version_id) is not str
        or not version_id
        or document_id != parent.document_id
        or version_id != parent.version_id
    ):
        raise ValueError("parent lock row does not match requested parent")


def _close_quietly(value: _Closable | None) -> bool:
    """Attempt resource cleanup and report whether the close was confirmed."""
    if value is None:
        return True
    try:
        value.close()
    except Exception:
        return False
    return True


def _close_resources(
    cursor: _Cursor | None, connection: _Connection
) -> _ResourceCloseStatus:
    return _ResourceCloseStatus(
        cursor_close_confirmed=_close_quietly(cursor),
        connection_close_confirmed=_close_quietly(connection),
    )


def _rollback_and_close(
    connection: _Connection,
    *,
    cursor_close_confirmed: bool,
) -> _PrimaryCleanupStatus:
    try:
        connection.rollback()
    except Exception:
        rollback_confirmed = False
    else:
        rollback_confirmed = True
    try:
        connection.close()
    except Exception:
        close_confirmed = False
    else:
        close_confirmed = True
    return _PrimaryCleanupStatus(
        cursor_close_confirmed=cursor_close_confirmed,
        rollback_confirmed=rollback_confirmed,
        close_confirmed=close_confirmed,
    )


def _committed_cleanup_unconfirmed(
    result: E2aReconciliationResult,
) -> E2aReconciliationResult:
    return replace(result, reconciliation_required=True)


def _cleanup_outcome_unknown(desired: E2aDesiredState) -> E2aReconciliationResult:
    return E2aReconciliationResult(
        outcome="outcome_unknown",
        manifest_sha256=desired.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=None,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
        reconciliation_required=True,
    )


def _outcome_unknown(result: E2aReconciliationResult) -> E2aReconciliationResult:
    return E2aReconciliationResult(
        outcome="outcome_unknown",
        manifest_sha256=result.manifest_sha256,
        primary_dml_by_table=result.primary_dml_by_table,
        denylist_dml_counts=result.denylist_dml_counts,
        comparator_parity=result.comparator_parity,
        stale_deletion_counts=result.stale_deletion_counts,
        cache_invalidation_counts=result.cache_invalidation_counts,
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
        reconciliation_required=True,
    )


_E2A_GLOBAL_SCOPE_VERSION_ID = "00000000-0000-0000-0000-000000000000"


def _preflight_global_primary_keys(cursor: _Cursor, desired: E2aDesiredState) -> None:
    """Reject cross-scope takeover of global primary keys before repository DML.

    Checks ALL global tables before raising any error, ensuring comprehensive
    preflight coverage regardless of which table has a collision.
    """
    version_ids = {parent.version_id for parent in desired.parents}
    collisions: list[str] = []
    vector_chunks = cast("tuple[Mapping[str, object], ...]", desired.vector_chunks)
    tree_nodes = cast("tuple[Mapping[str, object], ...]", desired.tree_nodes)

    _check_global_rows(
        cursor,
        table="canonical_spans",
        id_field="span_id",
        ids=[span.span_id for span in desired.canonical_spans],
        version_field="version_id",
        version_ids=version_ids,
        collisions=collisions,
    )
    _check_global_rows(
        cursor,
        table="vector_chunks",
        id_field="chunk_id",
        ids=[str(chunk["chunk_id"]) for chunk in vector_chunks],
        version_field="version_id",
        version_ids=version_ids,
        collisions=collisions,
    )
    _check_global_rows(
        cursor,
        table="tree_nodes",
        id_field="node_id",
        ids=[str(node["node_id"]) for node in tree_nodes],
        version_field="version_id",
        version_ids=version_ids,
        collisions=collisions,
    )
    _check_global_rows(
        cursor,
        table="evidence",
        id_field="evidence_id",
        ids=[obj.evidence_id for obj in desired.evidence_objects],
        version_field="version_id",
        version_ids=version_ids,
        collisions=collisions,
    )
    _check_global_evidence_links(cursor, desired, version_ids, collisions)

    if collisions:
        raise ValueError(collisions[0])


def _check_global_rows(
    cursor: _Cursor,
    *,
    table: str,
    id_field: str,
    ids: list[str],
    version_field: str,
    version_ids: set[str],
    collisions: list[str],
) -> None:
    """Check that global rows are not owned by a different scope version."""
    if not ids:
        return
    cursor.execute(
        f"SELECT {id_field}, {version_field} FROM {table} WHERE {id_field} = ANY(%s)",
        (ids,),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence):
        raise ValueError(f"{table} global preflight rows are invalid")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{table} global preflight row is invalid")
        row_id = row.get(id_field)
        row_version = row.get(version_field)
        if type(row_id) is not str or type(row_version) is not str:
            raise ValueError(f"{table} global preflight row is invalid")
        if row_version not in version_ids:
            collisions.append(
                f"global {table} {id_field}={row_id} is owned by incompatible scope version {row_version}"
            )


def _check_global_evidence_links(
    cursor: _Cursor,
    desired: E2aDesiredState,
    version_ids: set[str],
    collisions: list[str],
) -> None:
    """Check that evidence_links are either manual_okf or owned by compatible scope."""
    link_ids = [link.evidence_link_id for link in desired.evidence_links]
    if not link_ids:
        return
    cursor.execute(
        "SELECT evidence_link_id, version_id, source_kind FROM evidence_links "
        "WHERE evidence_link_id = ANY(%s)",
        (link_ids,),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence):
        raise ValueError("evidence_links global preflight rows are invalid")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("evidence_links global preflight row is invalid")
        link_id = row.get("evidence_link_id")
        row_version = row.get("version_id")
        source_kind = row.get("source_kind")
        if (
            type(link_id) is not str
            or type(row_version) is not str
            or type(source_kind) is not str
        ):
            raise ValueError("evidence_links global preflight row is invalid")
        if source_kind != "manual_okf":
            collisions.append(
                f"global evidence_links evidence_link_id={link_id} has source_kind={source_kind}, "
                "expected manual_okf"
            )
        elif row_version not in version_ids:
            collisions.append(
                f"global evidence_links evidence_link_id={link_id} is owned by incompatible "
                f"scope version {row_version}"
            )


def _validate_repository_result(
    result: object, desired: E2aDesiredState
) -> E2aReconciliationResult:
    """Validate that repository returned a proper reconciliation result."""
    if type(result) is not E2aReconciliationResult:
        raise TypeError(
            f"repository result must be E2aReconciliationResult, got {type(result).__name__}"
        )
    validated = cast(E2aReconciliationResult, result)
    if validated.manifest_sha256 != desired.corpus_manifest_sha256:
        raise ValueError(
            "repository result manifest_sha256 does not match desired state"
        )
    if validated.reconciliation_required:
        raise ValueError("repository result must not have reconciliation_required=True")
    if validated.outcome not in ("changed", "no_op"):
        raise ValueError(
            f"repository result outcome must be 'changed' or 'no_op', got {validated.outcome!r}"
        )
    if validated.failure_audit_outcome is not None:
        raise ValueError(
            "repository result must not have non-null failure_audit_outcome"
        )
    if validated.post_rollback_failure_audit_outcome is not None:
        raise ValueError(
            "repository result must not have non-null post_rollback_failure_audit_outcome"
        )
    return validated


__all__ = ["E2aDesiredStateBuilder", "E2aMaterializationInput", "E2aReconciler"]
