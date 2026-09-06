"""Live cells for the Task #88 Stage 2R tranche (sibling of the Stage 2 helper).

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides two
explicitly selected live cells in clearly NEW identities; the superseded
Stage 2 C4 identity (``_run_c4_impl``) is one-run and is never reused,
renamed, or extended here.

- PARTIAL(C4-lock-release): the same real collision setup as the superseded
  C4 cell (two real versions of one document, second scope reusing the first
  scope's span id, default ``E2aReconciler()`` with no audit factory). The
  unwrapped exact ``ValueError`` is asserted, the primary is closed after
  rollback, a fresh observer sees unchanged state and zero durable audit
  rows, and THEN a fresh attested reconciler connection re-reconciles the
  SAME ``first_desired`` state (never ``second_desired``; no v1-to-v2 DML is
  ever performed). The release reconcile must project the exact
  ``outcome == "no_op"`` with full zero primary-map semantics, and a fresh
  observer must still see the committed first state durably. Success proves
  the collision rollback released every transaction-scoped advisory and
  table lock (a residual lock would block or fail the fresh connection) and
  that the committed state is idempotently re-materializable. Boundary:
  lock release/idempotence only, never C14.
- PARTIAL(v1-v2): the real production v1-to-v2 materialization transition.
  Two real versions of the same document are registered through the real
  ``PostgresRegistryWriter``; version 1 is materialized, then version 2 with
  the default ``E2aReconciler()``. Both outcomes must be exactly
  ``changed``. A fresh observer proves the version-independent ownership row
  is retained but re-scoped to version 2 (version_id, scope_version_id,
  document_id all equal the v2 registration), that v2 manual evidence links
  exist with a matching v2 ownership scope on the retained ownership id,
  and that old v1 manual evidence links, evidence targets, and evidence rows
  are absent. This is a materialization-integrity transition regression
  ONLY; it is explicitly never C14 and never late-DML evidence.

Security contract (identical to the Stage 1 and Stage 2 tranches):

- No environment variable access of any kind; no DATABASE_URL anywhere.
- No URI, credential, target, container token, or raw fixture content is ever
  printed, logged, returned, or included in observation reprs.
- All connections come from DisposableE2aSession.open_fresh_attested_connection.
- The registry writer, every reconciler primary, and every observer are
  separate fresh attested connections/transactions. Role separation means
  independent fresh attested connections/transactions, not distinct
  PostgreSQL principals; no principal or security model is implied or changed.
- Every cursor and connection is closed in a finally block; the reconciler
  closes its primary on success and on failure, and this frame also closes it
  in a finally path (the close is idempotent).
- Failures are absorbed into redacted observations that carry a bounded
  class/type-only diagnostic; exception messages, args, and reprs never
  leave the helper.
- No test framework machinery, no skip or xfail mechanics, no fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from ._phase15_e2a_task88_live_cells import (
    _PRIMARY_TABLE_NAMES,
    _build_foundation_desired_state,
    _close_quietly,
    _error_reason,
    _open_observer_connection,
    _open_reconciler_primary_connection,
    _open_writer_connection,
    _verify_durable_state,
)
from ._phase15_e2a_task88_transition_cells import (
    _build_colliding_state,
    _expected_span_collision_message,
    _register_transition_pair,
    _span_total,
)


class C4LockReleaseObservations(NamedTuple):
    """Redacted observations for the C4 lock-release/idempotence cell."""

    first_outcome: str
    exact_error_match: bool
    error_is_value_error: bool
    primary_closed: bool
    state_unchanged: bool
    span_count_singleton: bool
    audit_row_count_zero: bool
    release_outcome_noop: bool
    release_zero_primary_counts: bool
    release_primary_shape_valid: bool
    release_observer_durable: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "C4LockReleaseObservations(first_outcome="
            + repr(self.first_outcome)
            + ", exact_error_match="
            + repr(self.exact_error_match)
            + ", error_is_value_error="
            + repr(self.error_is_value_error)
            + ", primary_closed="
            + repr(self.primary_closed)
            + ", state_unchanged="
            + repr(self.state_unchanged)
            + ", span_count_singleton="
            + repr(self.span_count_singleton)
            + ", audit_row_count_zero="
            + repr(self.audit_row_count_zero)
            + ", release_outcome_noop="
            + repr(self.release_outcome_noop)
            + ", release_zero_primary_counts="
            + repr(self.release_zero_primary_counts)
            + ", release_primary_shape_valid="
            + repr(self.release_primary_shape_valid)
            + ", release_observer_durable="
            + repr(self.release_observer_durable)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


class V1V2TransitionObservations(NamedTuple):
    """Redacted observations for the v1-to-v2 materialization-integrity cell."""

    first_outcome: str
    second_outcome: str
    ownership_row_retained: bool
    ownership_scoped_to_second: bool
    second_scope_manual_links_present: bool
    first_scope_manual_links_absent: bool
    first_scope_evidence_absent: bool
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        return (
            "V1V2TransitionObservations(first_outcome="
            + repr(self.first_outcome)
            + ", second_outcome="
            + repr(self.second_outcome)
            + ", ownership_row_retained="
            + repr(self.ownership_row_retained)
            + ", ownership_scoped_to_second="
            + repr(self.ownership_scoped_to_second)
            + ", second_scope_manual_links_present="
            + repr(self.second_scope_manual_links_present)
            + ", first_scope_manual_links_absent="
            + repr(self.first_scope_manual_links_absent)
            + ", first_scope_evidence_absent="
            + repr(self.first_scope_evidence_absent)
            + ", details=<redacted>, success="
            + repr(self.success)
            + ")"
        )


def _run_c4_lock_release_impl(session: Any) -> C4LockReleaseObservations:
    """Run the C4 lock-release/idempotence cell (new identity, never the old C4).

    The collision setup, exact preflight error, primary closure, unchanged
    observer state, and zero audit rows are asserted exactly as in the
    superseded cell. Then, after the collision rollback, a FRESH attested
    reconciler connection re-reconciles the SAME ``first_desired`` state
    (never ``second_desired``; no v1-to-v2 DML). The release reconcile must
    project ``outcome == "no_op"`` with zero primary DML and a valid primary
    map shape, and a fresh observer must still see the committed first state
    durably — proving the rollback released every transaction-scoped
    advisory and table lock and the state is idempotently re-materializable.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    first_path: Path | None = None
    second_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    collision_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    release_conn: Any = None
    release_observer_conn: Any = None
    release_observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        first_path, first_registration, second_path, second_registration = (
            _register_transition_pair(writer_conn)
        )
        first_desired = _build_foundation_desired_state(first_registration, first_path)
        first_span_id = first_desired.canonical_spans[0].span_id

        primary_conn = _open_reconciler_primary_connection(session)
        first_result = E2aReconciler().reconcile(primary_conn, first_desired)

        second_desired = _build_foundation_desired_state(
            second_registration, second_path
        )
        colliding = _build_colliding_state(second_desired, first_span_id)
        expected_message = _expected_span_collision_message(
            first_span_id, first_registration.version_id
        )

        collision_conn = _open_reconciler_primary_connection(session)
        failure: Exception | None = None
        try:
            E2aReconciler().reconcile(collision_conn, colliding)
        except Exception as error:
            failure = error
        if failure is None:
            raise ValueError("expected unwrapped preflight ValueError")
        exact_error_match = isinstance(failure, ValueError) and failure.args == (
            expected_message,
        )
        primary_closed = bool(collision_conn.closed)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        state_unchanged = _verify_durable_state(
            observer_cursor, first_registration, first_desired
        )
        span_singleton = _span_total(observer_cursor) == 1
        observer_cursor.execute("SELECT COUNT(*) FROM okf_rebuild_failure_audit")
        audit_zero = observer_cursor.fetchone() == (0,)

        # Lock-release proof: re-reconcile the SAME first desired state on a
        # fresh attested connection after the collision rollback. This never
        # performs v1-to-v2 DML; success plus the exact no_op projection and
        # zero primary counts proves the transaction-scoped advisory locks and
        # table locks were released and the committed state is idempotent.
        release_conn = _open_reconciler_primary_connection(session)
        release_result = E2aReconciler().reconcile(release_conn, first_desired)
        release_noop = release_result.outcome == "no_op"
        release_zero = all(
            value == 0 for value in release_result.primary_dml_by_table.values()
        )
        release_shape = set(release_result.primary_dml_by_table) == _PRIMARY_TABLE_NAMES

        release_observer_conn = _open_observer_connection(session)
        release_observer_cursor = release_observer_conn.cursor()
        release_durable = _verify_durable_state(
            release_observer_cursor, first_registration, first_desired
        )

        return C4LockReleaseObservations(
            first_outcome=first_result.outcome,
            exact_error_match=exact_error_match,
            error_is_value_error=isinstance(failure, ValueError),
            primary_closed=primary_closed,
            state_unchanged=state_unchanged,
            span_count_singleton=span_singleton,
            audit_row_count_zero=audit_zero,
            release_outcome_noop=release_noop,
            release_zero_primary_counts=release_zero,
            release_primary_shape_valid=release_shape,
            release_observer_durable=release_durable,
            success=True,
        )
    except Exception as failure:
        return C4LockReleaseObservations(
            first_outcome="",
            exact_error_match=False,
            error_is_value_error=False,
            primary_closed=False,
            state_unchanged=False,
            span_count_singleton=False,
            audit_row_count_zero=False,
            release_outcome_noop=False,
            release_zero_primary_counts=False,
            release_primary_shape_valid=False,
            release_observer_durable=False,
            success=False,
            error_reason=_error_reason("c4_lock_release_cell_failed", failure),
        )
    finally:
        _close_quietly(release_observer_cursor)
        _close_quietly(release_observer_conn)
        _close_quietly(release_conn)
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(collision_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        for path in (first_path, second_path):
            if path is not None:
                try:
                    path.unlink()
                except Exception:
                    pass


def _run_v1v2_transition_impl(session: Any) -> V1V2TransitionObservations:
    """Run the true v1-to-v2 materialization-integrity transition regression.

    Two real versions of one document are registered through the real
    registry writer; version 1 is materialized, then version 2 with the
    default ``E2aReconciler()``. Both outcomes must be exactly ``changed``.
    A fresh observer then proves the version-independent ownership row is
    retained but re-scoped to version 2, that v2 manual evidence links exist
    on the retained ownership id with a matching v2 ownership scope, and
    that old v1 manual evidence links, evidence targets, and evidence rows
    are absent. Materialization-integrity transition regression ONLY;
    explicitly never C14 and never late-DML evidence.
    """
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    first_path: Path | None = None
    second_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    second_primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        first_path, first_registration, second_path, second_registration = (
            _register_transition_pair(writer_conn)
        )
        first_desired = _build_foundation_desired_state(first_registration, first_path)
        v1_version_id = str(first_registration.version_id)
        v2_version_id = str(second_registration.version_id)

        primary_conn = _open_reconciler_primary_connection(session)
        first_result = E2aReconciler().reconcile(primary_conn, first_desired)

        second_desired = _build_foundation_desired_state(
            second_registration, second_path
        )
        second_primary_conn = _open_reconciler_primary_connection(session)
        second_result = E2aReconciler().reconcile(second_primary_conn, second_desired)

        ownership = first_desired.ownership_facts[0]
        second_doc_id = str(second_registration.doc_id)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT version_id, scope_version_id, document_id "
            "FROM okf_manual_fact_ownership WHERE ownership_id = %s",
            (ownership.ownership_id,),
        )
        row = observer_cursor.fetchone()
        ownership_retained = row is not None
        ownership_scoped_second = (
            row is not None
            and str(row[0]) == v2_version_id
            and str(row[1]) == v2_version_id
            and str(row[2]) == second_doc_id
        )
        observer_cursor.execute(
            "SELECT COUNT(*) FROM evidence_links WHERE source_kind = %s "
            "AND ownership_scope_version_id = %s AND ownership_id = %s",
            ("manual_okf", v2_version_id, ownership.ownership_id),
        )
        second_scope_links_present = observer_cursor.fetchone() == (1,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM evidence_links WHERE source_kind = %s "
            "AND ownership_scope_version_id = %s",
            ("manual_okf", v1_version_id),
        )
        first_scope_links_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM okf_manual_evidence_targets WHERE version_id = %s",
            (v1_version_id,),
        )
        first_scope_targets_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM evidence WHERE version_id = %s",
            (v1_version_id,),
        )
        first_scope_evidence_absent = observer_cursor.fetchone() == (0,)

        return V1V2TransitionObservations(
            first_outcome=first_result.outcome,
            second_outcome=second_result.outcome,
            ownership_row_retained=ownership_retained,
            ownership_scoped_to_second=ownership_scoped_second,
            second_scope_manual_links_present=second_scope_links_present,
            first_scope_manual_links_absent=(
                first_scope_links_absent and first_scope_targets_absent
            ),
            first_scope_evidence_absent=first_scope_evidence_absent,
            success=True,
        )
    except Exception as failure:
        return V1V2TransitionObservations(
            first_outcome="",
            second_outcome="",
            ownership_row_retained=False,
            ownership_scoped_to_second=False,
            second_scope_manual_links_present=False,
            first_scope_manual_links_absent=False,
            first_scope_evidence_absent=False,
            success=False,
            error_reason=_error_reason("v1v2_transition_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        for path in (first_path, second_path):
            if path is not None:
                try:
                    path.unlink()
                except Exception:
                    pass
