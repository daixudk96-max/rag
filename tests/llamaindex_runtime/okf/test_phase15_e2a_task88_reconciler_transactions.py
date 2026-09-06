"""Task #88 reconciler transaction-boundary protocol pins (non-live).

This module is one of three focused Task #88 unit modules split from the
original oversized single-file RED surface. It pins, entirely WITHOUT a
database and using narrow recording doubles from
``_phase15_e2a_task88_testkit``:

- the default ``E2aReconciler`` repository contract for
  ``E2aDesiredState`` (real ``E2aMaterializationRepository``, no fake
  repository),
- the failure-audit factory distinction (None factory rethrows; an
  injected fresh factory audits instead),
- ``post_lock_sync_hook`` validation and exact placement (after scope
  locks, before preflights),
- strict ``autocommit is False`` enforcement before any activity,
- commit-error ``outcome_unknown`` behavior WITHOUT a failure audit.

No database, no Docker, and no live selector is exercised here.
"""

from __future__ import annotations

import pytest

from llamaindex_runtime.okf._e2a_psycopg_rows import e2a_dict_row
from llamaindex_runtime.okf.e2a_contracts import (
    _E2A_DENYLIST_TABLES,
    DmlRecorder,
    E2aDesiredState,
    E2aReconciliationResult,
)
from llamaindex_runtime.okf.e2a_materialization_repository import (
    E2aMaterializationRepository,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

from ._phase15_e2a_task88_testkit import (
    _Builder,
    _Connection,
    _Cursor,
    _desired_empty,
    _desired_full,
    _is_dml,
    _matching_parent_rows,
    _materialization_input,
    _Repository,
)


class TestE2aReconcilerDefaultRepositoryContract:
    """E2aReconciler() default repository contract for E2aDesiredState."""

    def test_default_repository_is_materialization_repository(self) -> None:
        assert type(E2aReconciler()._repository) is E2aMaterializationRepository

    def test_default_repository_accepts_desired_state_and_commits_no_op(self) -> None:
        state = _desired_empty()
        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        result = E2aReconciler().reconcile(connection, state)

        assert result.outcome == "no_op"
        assert result.manifest_sha256 == state.corpus_manifest_sha256
        assert result.reconciliation_required is False
        assert result.comparator_parity is True
        assert all(count == 0 for count in result.primary_dml_by_table.values())
        assert len(result.primary_dml_by_table) == 15
        assert set(result.denylist_dml_counts) == set(_E2A_DENYLIST_TABLES)
        assert all(count == 0 for count in result.denylist_dml_counts.values())
        assert connection.commits == 1
        assert connection.rollbacks == 0
        assert connection.closed == 1
        assert connection.cursor_row_factories == [e2a_dict_row]
        assert not any(_is_dml(statement) for statement, _ in cursor.calls)

    def test_materialization_repository_validates_recorder_and_desired(self) -> None:
        repository = E2aMaterializationRepository()
        with pytest.raises(TypeError, match="recorder must be DmlRecorder"):
            repository.reconcile(
                _Cursor(), _desired_empty(), recorder=object()  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="desired state must be E2aDesiredState"):
            repository.reconcile(
                _Cursor(), object(), recorder=DmlRecorder()  # type: ignore[arg-type]
            )


class TestFailureAuditFactoryDistinction:
    """Default None factory rethrows; injected fresh factory audits instead."""

    def test_default_none_factory_rethrows_primary_failure(self) -> None:
        state = _desired_empty()
        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        with pytest.raises(RuntimeError, match="repository failed"):
            E2aReconciler(
                repository=_Repository(failure=RuntimeError("repository failed"))
            ).reconcile(connection, state)

        assert connection.commits == 0
        assert connection.rollbacks == connection.closed == 1
        assert not any(
            "okf_rebuild_failure_audit" in statement for statement, _ in cursor.calls
        )

    def test_injected_factory_returns_rolled_back_failure_with_audit(self) -> None:
        state = _desired_empty()
        primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))
        audit_cursor = _Cursor()
        audit = _Connection(audit_cursor)
        audit_factory_calls: list[None] = []

        def audit_factory() -> _Connection:
            audit_factory_calls.append(None)
            return audit

        result = E2aReconciler(
            repository=_Repository(failure=RuntimeError("repository failed")),
            failure_audit_connection_factory=audit_factory,
        ).reconcile(primary, state)

        assert result.outcome == "rolled_back_failure"
        assert result.reconciliation_required is False
        assert result.manifest_sha256 == state.corpus_manifest_sha256
        assert result.failure_audit_outcome is None
        assert result.post_rollback_failure_audit_outcome == "written"
        assert audit_factory_calls == [None]
        assert audit is not primary
        assert audit_cursor is not primary.cursor_value
        assert primary.commits == 0
        assert primary.rollbacks == primary.closed == 1
        assert audit.commits == audit.closed == 1
        assert audit.rollbacks == 0
        assert any(
            "okf_rebuild_failure_audit" in statement
            for statement, _ in audit_cursor.calls
        )
        assert not any(
            "okf_rebuild_failure_audit" in statement
            for statement, _ in primary.cursor_value.calls
        )

    def test_factory_connection_error_reports_failed_outcome(self) -> None:
        state = _desired_empty()
        primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))

        def failing_factory() -> _Connection:
            raise ConnectionError("audit connection refused")

        result = E2aReconciler(
            repository=_Repository(failure=RuntimeError("repository failed")),
            failure_audit_connection_factory=failing_factory,
        ).reconcile(primary, state)

        assert result.outcome == "rolled_back_failure"
        assert result.post_rollback_failure_audit_outcome == "failed"
        assert primary.rollbacks == primary.closed == 1


class TestPostLockSyncHookContract:
    """Exact post_lock_sync_hook validation and placement (non-live protocol)."""

    def test_hook_rejects_non_callable_with_exact_value_error(self) -> None:
        with pytest.raises(
            ValueError, match="post_lock_sync_hook must be callable or None"
        ):
            E2aReconciler(post_lock_sync_hook="not callable")  # type: ignore[arg-type]

    def test_hook_none_default_no_call(self) -> None:
        state = _desired_empty()
        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        result = E2aReconciler(repository=_Repository()).reconcile(connection, state)

        assert result.outcome == "no_op"
        assert connection.commits == 1

    def test_hook_called_exactly_once_after_locks_before_preflights(self) -> None:
        state = _desired_full()
        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        timeline: list[tuple[str, int]] = []

        def hook() -> None:
            timeline.append(("hook", len(cursor.calls)))

        class _TimelineRepository(_Repository):
            def reconcile(
                self,
                cursor: object,
                desired: E2aDesiredState,
                *,
                recorder: object,
            ) -> E2aReconciliationResult:
                assert isinstance(cursor, _Cursor)
                timeline.append(("repository", len(cursor.calls)))
                return super().reconcile(cursor, desired, recorder=recorder)

        connection = _Connection(cursor)

        result = E2aReconciler(
            repository=_TimelineRepository(),
            post_lock_sync_hook=hook,
        ).reconcile(connection, state)

        assert result.outcome == "no_op"
        lock_indexes = [
            index
            for index, (statement, _) in enumerate(cursor.calls)
            if statement.lstrip().startswith("LOCK TABLE")
        ]
        assert lock_indexes, "scope locks must be issued"
        assert len(timeline) == 2, "hook must be called exactly once"
        assert timeline[0][0] == "hook"
        assert timeline[1][0] == "repository"
        hook_position = timeline[0][1]
        repository_position = timeline[1][1]
        assert max(lock_indexes) < hook_position, "hook must run after scope locks"
        assert (
            hook_position < repository_position
        ), "hook must run before the repository"

    def test_hook_strict_zero_arguments(self) -> None:
        state = _desired_empty()

        def zero_argument_hook() -> None:
            return None

        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        result = E2aReconciler(
            repository=_Repository(),
            post_lock_sync_hook=zero_argument_hook,
        ).reconcile(connection, state)

        assert result.outcome == "no_op"
        assert connection.commits == 1

    def test_hook_exception_triggers_rollback_and_rethrow_without_factory(self) -> None:
        state = _desired_empty()

        def failing_hook() -> None:
            raise RuntimeError("hook failed")

        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        with pytest.raises(RuntimeError, match="hook failed"):
            E2aReconciler(
                repository=_Repository(),
                post_lock_sync_hook=failing_hook,
            ).reconcile(connection, state)

        assert connection.commits == 0
        assert connection.rollbacks == connection.closed == 1

    def test_hook_exception_with_factory_returns_rolled_back_failure(self) -> None:
        state = _desired_empty()

        def failing_hook() -> None:
            raise RuntimeError("hook failed")

        primary = _Connection(_Cursor(parent_rows=_matching_parent_rows(state)))
        audit = _Connection(_Cursor())

        result = E2aReconciler(
            repository=_Repository(),
            failure_audit_connection_factory=lambda: audit,
            post_lock_sync_hook=failing_hook,
        ).reconcile(primary, state)

        assert result.outcome == "rolled_back_failure"
        assert result.post_rollback_failure_audit_outcome == "written"
        assert primary.commits == 0
        assert primary.rollbacks == primary.closed == 1
        assert audit.commits == audit.closed == 1


class TestStrictManualTransaction:
    """autocommit must be exactly False before any primary activity."""

    @pytest.mark.parametrize(
        ("autocommit", "has_autocommit"),
        ((True, True), (None, False), (1, True)),
        ids=("true", "missing", "non_boolean"),
    )
    def test_reconciler_rejects_non_manual_transaction_before_any_activity(
        self,
        autocommit: object,
        has_autocommit: bool,
    ) -> None:
        state = _desired_empty()
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

        with pytest.raises(
            ValueError, match="connection autocommit must be exactly False"
        ):
            reconciler.reconcile(connection, _materialization_input(state))

        assert builder.calls == []
        assert connection.cursor_row_factories == []
        assert connection.commits == connection.rollbacks == connection.closed == 0
        assert cursor.calls == []
        assert audit_factory_calls == []
        assert connection.autocommit_writes == []

    def test_autocommit_false_connection_never_writes_autocommit(self) -> None:
        state = _desired_empty()
        cursor = _Cursor(parent_rows=_matching_parent_rows(state))
        connection = _Connection(cursor)

        result = E2aReconciler(repository=_Repository()).reconcile(connection, state)

        assert result.outcome == "no_op"
        assert connection.autocommit_writes == []


class TestCommitErrorOutcomeUnknown:
    """Commit acknowledgement loss is outcome_unknown with NO failure audit."""

    def test_commit_error_is_outcome_unknown_without_failure_audit(self) -> None:
        state = _desired_empty()
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
        assert audit_factory_calls == []
        assert primary.commits == 1
        assert primary.rollbacks == 0
        assert primary.closed == 1
        assert primary.cursor_value.closed == 1
        assert not any(
            "okf_rebuild_failure_audit" in statement
            for statement, _ in primary.cursor_value.calls
        )
