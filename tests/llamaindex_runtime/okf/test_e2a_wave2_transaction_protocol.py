"""RED contracts for E2a's primary transaction boundary and parent locks."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest

from llamaindex_runtime.okf._e2a_psycopg_rows import e2a_dict_row
from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
    canonical_json_sha256,
)
from llamaindex_runtime.okf.e2a_reconciler import (
    E2aMaterializationInput,
    E2aReconciler,
    _close_quietly,
)

_DIGEST = "a" * 64


def _identifier(number: int) -> str:
    return str(UUID(int=number))


def _desired() -> E2aDesiredState:
    parent = E2aParent(
        document_id=_identifier(1),
        version_id=_identifier(101),
        relative_path="raw/one.pair.json",
        canonical_hash=_DIGEST,
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
        ],
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
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata={},
        provenance_metadata={"authority": "okf"},
    )


def _materialization_input(state: E2aDesiredState) -> E2aMaterializationInput:
    return E2aMaterializationInput(
        admitted=state,
        span_records=(),
        parent_source_checksums={state.parents[0].version_id: _DIGEST},
    )


def _result(state: E2aDesiredState) -> E2aReconciliationResult:
    return E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )


def _is_dml(statement: str) -> bool:
    return (
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "MERGE"))
    )


class _AdapterRegistry:
    def __init__(self) -> None:
        self.loaders: list[tuple[str, object]] = []

    def register_loader(self, name: str, loader: object) -> None:
        self.loaders.append((name, loader))


class _Cursor:
    def __init__(
        self,
        *,
        parent_rows: list[object] | None = None,
        fail_scope_lock: bool = False,
        close_error: Exception | None = None,
        has_adaptation_context: bool = True,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.closed = 0
        self._parent_rows = parent_rows or []
        self._fail_scope_lock = fail_scope_lock
        self._close_error = close_error
        self._last_statement = ""
        self.connection = object()
        if has_adaptation_context:
            self.adapters = _AdapterRegistry()

    def execute(self, statement: str, parameters: object | None = None) -> None:
        self._last_statement = statement
        self.calls.append((statement, parameters))
        if self._fail_scope_lock and "pg_advisory_xact_lock" in statement:
            raise RuntimeError("scope lock failed")

    def fetchall(self) -> list[object]:
        if "document_versions" in self._last_statement.lower():
            return list(self._parent_rows)
        return []

    def close(self) -> None:
        self.closed += 1
        if self._close_error is not None:
            raise self._close_error


class _Connection:
    def __init__(
        self,
        cursor: _Cursor,
        *,
        autocommit: object = False,
        has_autocommit: bool = True,
        rollback_error: Exception | None = None,
        close_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        object.__setattr__(self, "_track_autocommit_writes", False)
        object.__setattr__(self, "autocommit_writes", [])
        if has_autocommit:
            object.__setattr__(self, "autocommit", autocommit)
        object.__setattr__(self, "_track_autocommit_writes", True)
        self.cursor_value = cursor
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.commit_error = commit_error
        self.cursor_row_factories: list[object | None] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def __setattr__(self, name: str, value: object) -> None:
        if name == "autocommit" and self.__dict__.get(
            "_track_autocommit_writes", False
        ):
            self.autocommit_writes.append(value)
        object.__setattr__(self, name, value)

    def cursor(self, *, row_factory: object | None = None) -> _Cursor:
        self.cursor_row_factories.append(row_factory)
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class _Repository:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[object, E2aDesiredState, object]] = []
        self._failure = failure

    def reconcile(
        self,
        cursor: object,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        self.calls.append((cursor, desired, recorder))
        if self._failure is not None:
            raise self._failure
        return _result(desired)


class _Builder:
    def __init__(self, state: E2aDesiredState) -> None:
        self.calls: list[object] = []
        self._state = state

    def build(self, source: object) -> E2aDesiredState:
        self.calls.append(source)
        return self._state


def _matching_parent_rows(state: E2aDesiredState) -> list[object]:
    parent = state.parents[0]
    return [{"doc_id": parent.document_id, "version_id": parent.version_id}]


@pytest.mark.parametrize(
    ("autocommit", "has_autocommit"),
    ((True, True), (None, False), (1, True)),
    ids=("true", "missing", "non_boolean"),
)
def test_reconciler_rejects_non_manual_transaction_before_any_primary_activity(
    autocommit: object,
    has_autocommit: bool,
) -> None:
    state = _desired()
    builder = _Builder(state)
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(
        cursor,
        autocommit=autocommit,
        has_autocommit=has_autocommit,
    )
    audit_factory_calls: list[None] = []

    def audit_factory() -> _Connection:
        audit_factory_calls.append(None)
        return _Connection(_Cursor())

    reconciler = E2aReconciler(
        repository=_Repository(),
        builder=builder,
        failure_audit_connection_factory=audit_factory,
    )

    with pytest.raises(ValueError, match="autocommit"):
        reconciler.reconcile(connection, _materialization_input(state))

    assert builder.calls == []
    assert connection.cursor_row_factories == []
    assert connection.commits == connection.rollbacks == connection.closed == 0
    assert cursor.calls == []
    assert audit_factory_calls == []
    assert connection.autocommit_writes == []


@pytest.mark.parametrize(
    "parent_rows",
    (
        [],
        lambda state: _matching_parent_rows(state) * 2,
        lambda state: [(state.parents[0].document_id, state.parents[0].version_id)],
        lambda state: [{"version_id": state.parents[0].version_id}],
        lambda state: [
            {
                "doc_id": state.parents[0].document_id,
                "version_id": state.parents[0].version_id,
                "unexpected": "field",
            }
        ],
        lambda state: [
            {
                "doc_id": UUID(state.parents[0].document_id),
                "version_id": UUID(state.parents[0].version_id),
            }
        ],
        lambda state: [
            {"doc_id": _identifier(2), "version_id": state.parents[0].version_id}
        ],
        lambda state: [
            {"doc_id": state.parents[0].document_id, "version_id": _identifier(102)}
        ],
    ),
    ids=(
        "zero_rows",
        "duplicate_rows",
        "tuple_row",
        "missing_doc_id",
        "extra_field",
        "native_uuid",
        "wrong_doc_id",
        "wrong_version_id",
    ),
)
def test_reconciler_rejects_malformed_parent_lock_rows_before_repository_or_dml(
    parent_rows: list[object] | Callable[[E2aDesiredState], list[object]],
) -> None:
    state = _desired()
    rows = parent_rows(state) if callable(parent_rows) else parent_rows
    cursor = _Cursor(parent_rows=rows)
    connection = _Connection(cursor)
    repository = _Repository()
    reconciler = E2aReconciler(repository=repository)

    with pytest.raises(ValueError, match="parent.*(lock|row)|lock.*parent"):
        reconciler.reconcile(connection, state)

    assert repository.calls == []
    assert not any(_is_dml(statement) for statement, _ in cursor.calls)
    assert connection.commits == 0
    assert connection.cursor_row_factories == [e2a_dict_row]


@pytest.mark.parametrize("failure_stage", ("repository", "lock"))
@pytest.mark.parametrize("cleanup_failure", ("cursor", "rollback", "close"))
def test_failed_primary_cleanup_never_opens_failure_audit_connection(
    failure_stage: str,
    cleanup_failure: str,
) -> None:
    state = _desired()
    cursor = _Cursor(
        parent_rows=_matching_parent_rows(state),
        fail_scope_lock=failure_stage == "lock",
        close_error=(
            RuntimeError("cursor close failed") if cleanup_failure == "cursor" else None
        ),
    )
    connection = _Connection(
        cursor,
        rollback_error=(
            RuntimeError("rollback failed") if cleanup_failure == "rollback" else None
        ),
        close_error=(
            RuntimeError("close failed") if cleanup_failure == "close" else None
        ),
    )
    repository = _Repository(
        failure=(
            RuntimeError("repository failed") if failure_stage == "repository" else None
        )
    )
    audit_factory_calls: list[None] = []

    def audit_factory() -> _Connection:
        audit_factory_calls.append(None)
        return _Connection(_Cursor())

    result = E2aReconciler(
        repository=repository,
        failure_audit_connection_factory=audit_factory,
    ).reconcile(connection, state)

    assert result.outcome == "outcome_unknown"
    assert result.reconciliation_required is True
    assert result.failure_audit_outcome is None
    assert result.post_rollback_failure_audit_outcome is None
    assert audit_factory_calls == []
    assert connection.rollbacks == connection.closed == 1
    assert connection.commits == 0
    assert (len(repository.calls) == 0) is (failure_stage == "lock")


def test_unconfirmed_primary_cleanup_is_unknown_without_an_audit_factory() -> None:
    state = _desired()
    cursor = _Cursor(
        parent_rows=_matching_parent_rows(state),
        close_error=RuntimeError("cursor close failed"),
    )
    primary = _Connection(
        cursor,
        rollback_error=RuntimeError("rollback failed"),
        close_error=RuntimeError("connection close failed"),
    )

    result = E2aReconciler(
        repository=_Repository(failure=RuntimeError("repository failed"))
    ).reconcile(primary, state)

    assert result.outcome == "outcome_unknown"
    assert result.reconciliation_required is True
    assert result.post_rollback_failure_audit_outcome is None
    assert primary.commits == 0
    assert primary.rollbacks == primary.closed == cursor.closed == 1


def test_confirmed_cleanup_writes_failure_audit_on_fresh_connection() -> None:
    state = _desired()
    primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))
    audit = _Connection(_Cursor())
    repository = _Repository(failure=RuntimeError("repository failed"))
    audit_factory_calls: list[None] = []

    def audit_factory() -> _Connection:
        assert primary.rollbacks == primary.closed == 1
        audit_factory_calls.append(None)
        return audit

    result = E2aReconciler(
        repository=repository,
        failure_audit_connection_factory=audit_factory,
    ).reconcile(primary, state)

    assert result.outcome == "rolled_back_failure"
    assert result.reconciliation_required is False
    assert result.post_rollback_failure_audit_outcome == "written"
    assert audit_factory_calls == [None]
    assert primary.commits == 0
    assert primary.rollbacks == primary.closed == 1
    assert primary.cursor_row_factories == [e2a_dict_row]
    assert audit.commits == audit.closed == 1
    assert audit.cursor_row_factories == [None]
    assert any(
        "okf_rebuild_failure_audit" in statement
        for statement, _ in audit.cursor_value.calls
    )
    assert not any(
        "okf_rebuild_failure_audit" in statement
        for statement, _ in primary.cursor_value.calls
    )


def test_commit_acknowledgement_uncertainty_never_rolls_back_or_audits() -> None:
    state = _desired()
    primary = _Connection(
        _Cursor(parent_rows=_matching_parent_rows(state)),
        commit_error=ConnectionError("commit acknowledgement lost"),
    )
    audit_factory_calls: list[None] = []

    def audit_factory() -> _Connection:
        audit_factory_calls.append(None)
        return _Connection(_Cursor())

    result = E2aReconciler(
        repository=_Repository(),
        failure_audit_connection_factory=audit_factory,
    ).reconcile(primary, state)

    assert result.outcome == "outcome_unknown"
    assert result.reconciliation_required is True
    assert result.failure_audit_outcome is None
    assert result.post_rollback_failure_audit_outcome is None
    assert primary.commits == 1
    assert primary.rollbacks == 0
    assert primary.closed == 1
    assert primary.cursor_row_factories == [e2a_dict_row]
    assert audit_factory_calls == []


def test_primary_cursor_without_psycopg_adaptation_context_fails_before_repository_activity() -> (
    None
):
    state = _desired()
    cursor = _Cursor(
        parent_rows=_matching_parent_rows(state), has_adaptation_context=False
    )
    connection = _Connection(cursor)
    repository = _Repository()

    with pytest.raises(ValueError, match="adaptation context"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert repository.calls == []
    assert cursor.calls == []
    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == cursor.closed == 1


class _CloseFailure:
    def close(self) -> None:
        raise RuntimeError("close failed")


class _InvalidResult:
    pass


class _RepositoryWithResult:
    def __init__(self, *, result: E2aReconciliationResult) -> None:
        self._result = result

    def reconcile(
        self,
        cursor: object,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> E2aReconciliationResult:
        return self._result


class _RepositoryWithInvalidResult:
    def __init__(self, *, result: object) -> None:
        self._result = result

    def reconcile(
        self,
        cursor: object,
        desired: E2aDesiredState,
        *,
        recorder: object,
    ) -> object:
        return self._result


@pytest.mark.parametrize(
    "invalid_result",
    (
        pytest.param(None, id="none"),
        pytest.param(_InvalidResult(), id="wrong_type"),
        pytest.param("not_a_result", id="string"),
    ),
)
def test_repository_returns_invalid_result_type_rolls_back_without_commit(
    invalid_result: object,
) -> None:
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    repository = _RepositoryWithInvalidResult(result=invalid_result)

    with pytest.raises(TypeError, match="repository result"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_repository_returns_wrong_manifest_rolls_back_without_commit() -> None:
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    result = E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256="b" * 64,  # Wrong manifest SHA256
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )
    repository = _RepositoryWithResult(result=result)

    with pytest.raises(ValueError, match="manifest_sha256"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_repository_returns_reconciliation_required_rolls_back_without_commit() -> None:
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    result = E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
        reconciliation_required=True,
    )
    repository = _RepositoryWithResult(result=result)

    with pytest.raises(ValueError, match="reconciliation_required"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_repository_returns_invalid_outcome_rolls_back_without_commit() -> None:
    """RED: Repository result outcome must be 'changed' or 'no_op', not 'rolled_back_failure'."""
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    result = E2aReconciliationResult(
        outcome="rolled_back_failure",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=None,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )
    repository = _RepositoryWithResult(result=result)

    with pytest.raises(ValueError, match="outcome"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_repository_returns_failure_audit_outcome_rolls_back_without_commit() -> None:
    """RED: Repository result must not have non-null failure_audit_outcome at commit time."""
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    result = E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome="written",
        post_rollback_failure_audit_outcome=None,
    )
    repository = _RepositoryWithResult(result=result)

    with pytest.raises(ValueError, match="failure_audit_outcome"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_repository_returns_post_rollback_failure_audit_outcome_rolls_back_without_commit() -> (
    None
):
    """RED: Repository result must not have non-null post_rollback_failure_audit_outcome at commit time."""
    state = _desired()
    cursor = _Cursor(parent_rows=_matching_parent_rows(state))
    connection = _Connection(cursor)
    result = E2aReconciliationResult(
        outcome="no_op",
        manifest_sha256=state.corpus_manifest_sha256,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=True,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome="written",
    )
    repository = _RepositoryWithResult(result=result)

    with pytest.raises(ValueError, match="post_rollback_failure_audit_outcome"):
        E2aReconciler(repository=repository).reconcile(connection, state)

    assert connection.commits == 0
    assert connection.rollbacks == connection.closed == 1


def test_close_results_explicitly_represent_success_and_failure() -> None:
    assert _close_quietly(_Cursor()) is True
    assert _close_quietly(_CloseFailure()) is False


def test_committed_success_with_connection_close_failure_keeps_committed_result_and_requires_reconciliation() -> (
    None
):
    state = _desired()
    primary = _Connection(
        _Cursor(parent_rows=_matching_parent_rows(state)),
        close_error=RuntimeError("primary close failed"),
    )
    audit_factory_calls: list[None] = []

    def audit_factory() -> _Connection:
        audit_factory_calls.append(None)
        return _Connection(_Cursor())

    result = E2aReconciler(
        repository=_Repository(),
        failure_audit_connection_factory=audit_factory,
    ).reconcile(primary, state)

    assert result.outcome == "no_op"
    assert result.reconciliation_required is True
    assert primary.commits == primary.closed == 1
    assert primary.rollbacks == 0
    assert audit_factory_calls == []


def test_committed_success_with_cursor_close_failure_keeps_committed_result_and_requires_reconciliation() -> (
    None
):
    state = _desired()
    cursor = _Cursor(
        parent_rows=_matching_parent_rows(state),
        close_error=RuntimeError("primary cursor close failed"),
    )
    primary = _Connection(cursor)

    result = E2aReconciler(repository=_Repository()).reconcile(primary, state)

    assert result.outcome == "no_op"
    assert result.reconciliation_required is True
    assert primary.commits == primary.closed == cursor.closed == 1
    assert primary.rollbacks == 0


@pytest.mark.parametrize("cleanup_failure", ("cursor", "connection"))
def test_audit_close_failure_reports_cleanup_uncertainty(cleanup_failure: str) -> None:
    state = _desired()
    primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))
    audit_cursor = _Cursor(
        close_error=(
            RuntimeError("audit cursor close failed")
            if cleanup_failure == "cursor"
            else None
        )
    )
    audit = _Connection(
        audit_cursor,
        close_error=(
            RuntimeError("audit connection close failed")
            if cleanup_failure == "connection"
            else None
        ),
    )

    result = E2aReconciler(
        repository=_Repository(failure=RuntimeError("repository failed")),
        failure_audit_connection_factory=lambda: audit,
    ).reconcile(primary, state)

    assert result.outcome == "rolled_back_failure"
    assert result.post_rollback_failure_audit_outcome == "written_cleanup_unconfirmed"
    assert primary.rollbacks == primary.closed == 1
    assert audit.commits == audit.closed == audit_cursor.closed == 1


def test_audit_commit_exception_reports_acknowledgement_uncertainty() -> None:
    state = _desired()
    primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))
    audit = _Connection(_Cursor(), commit_error=ConnectionError("audit commit lost"))

    result = E2aReconciler(
        repository=_Repository(failure=RuntimeError("repository failed")),
        failure_audit_connection_factory=lambda: audit,
    ).reconcile(primary, state)

    assert result.outcome == "rolled_back_failure"
    assert result.reconciliation_required is False
    assert result.post_rollback_failure_audit_outcome == "outcome_unknown"
    assert primary.rollbacks == primary.closed == 1
    assert audit.commits == audit.closed == 1
    assert audit.rollbacks == 0
