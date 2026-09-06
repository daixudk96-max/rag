"""Explicitly selected live transition cells for the Task #88 Stage 2 tranche.

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and every
live cell fails closed unless separately authorized.

Each live cell is a partial proof; nothing here claims the whole tranche is
proven, and no cell asserts beyond its stated boundary.

PARTIAL(C2)
    A manifest-only mutation (extra top-level manifest key with a recomputed
    canonical hash) is projected to the FIXED outcome ``no_op`` from
    production source: the manifest hash appears in no sync-state field and
    in no DML template, the repository outcome is ``changed`` iff any primary
    count is positive, and the contract graph reads only the ``artifacts``
    manifest key. The cell asserts zero primary DML, comparator parity, the
    unchanged committed state, and absent ``last_synced_at`` churn; it never
    accepts either outcome opportunistically. Boundary: single parent.

PARTIAL(C3)
    Two real versions of one document are registered; the second scope
    deliberately reuses the first scope's span id. The exact global
    primary-key preflight rejection message is compared against the
    production template and committed state is unchanged on a fresh observer.
    Boundary: default construction is required so the exact preflight error
    is observable at all.

PARTIAL(C4)
    The same real collision through the default ``E2aReconciler()`` with no
    audit factory: the unwrapped exact ``ValueError`` is asserted, the
    primary is closed after rollback, a fresh observer sees unchanged state
    and zero durable audit rows, and a later fresh reconcile with a fresh
    span id succeeds (no lingering transaction-scoped lock). Boundary: the
    unwrapped exception identity itself is pinned only by the non-live double
    contract, never fabricated here.

PARTIAL(C5)
    A real manual-fact preflight collision: the conflicting base ``entities``
    material is seeded with narrowly scoped parameterized SQL on its own
    fresh attested connection, the audit factory is explicitly injected, and
    the reconcile returns ``rolled_back_failure`` with empty failure maps,
    ``comparator_parity is None``, and exactly one durable append-only audit
    row with exact fields. This is preflight rollback plus audit ONLY; it is
    never late-DML evidence and never C14. Boundary: preflight only.

Security contract: all connections come from DisposableE2aSession
open_fresh_attested_connection calls; the registry writer, every reconcile
primary, the C5 seed, the injected audit factory, and every observer are
each their own fresh attested connection/transaction. Role separation here
means independent fresh attested connections and transactions, not distinct
PostgreSQL principals; no principal or security model is implied or
changed. No URI, credential, target, container token, or raw fixture
content is ever printed, logged, or returned. Every resource is closed
inside the helper cells, a session setup failure propagates unmodified
instead of being masked, and a failed cell raises RuntimeError carrying only
the observation's bounded error_reason (the exception class name, never its
text).
"""

from __future__ import annotations

import contextlib

from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
from ._phase15_e2a_harness_types import (
    _require_authorization,
    _validate_container_name,
)
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)
from ._phase15_e2a_task88_transition_cells import (
    _run_c2_impl,
    _run_c3_impl,
    _run_c4_impl,
    _run_c5_impl,
)


def test_phase15_e2a_task88_c2_manifest_mutation_noop_live() -> None:
    """PARTIAL(C2): manifest-only mutation projects to the fixed no_op.

    Boundary: single parent; the projection is asserted exactly, never
    flexibly as changed or no_op.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c2_impl(session)
    if not observations.success:
        raise RuntimeError(f"C2 live cell failed: {observations.error_reason}")
    assert observations.first_outcome == "changed"
    assert observations.outcome_fixed_match
    assert observations.zero_primary_counts
    assert observations.primary_shape_valid
    assert observations.comparator_parity_true
    assert observations.manifest_sha256_match
    assert observations.state_unchanged
    assert observations.timestamp_churn_absent


def test_phase15_e2a_task88_c3_preflight_rejection_live() -> None:
    """PARTIAL(C3): exact global primary-key preflight rejection.

    Boundary: the exact message is compared inside the helper against the
    production template; only the bounded match flag leaves the frame.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c3_impl(session)
    if not observations.success:
        raise RuntimeError(f"C3 live cell failed: {observations.error_reason}")
    assert observations.first_outcome == "changed"
    assert observations.exact_error_match
    assert observations.error_is_value_error
    assert observations.state_unchanged
    assert observations.span_count_singleton


def test_phase15_e2a_task88_c4_default_failure_contract_live() -> None:
    """PARTIAL(C4): default reconciler failure contract on the same collision.

    Boundary: unwrapped exact error, rolled-back and closed primary, zero
    durable audit rows, and a later fresh reconcile unlocked.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c4_impl(session)
    if not observations.success:
        raise RuntimeError(f"C4 live cell failed: {observations.error_reason}")
    assert observations.first_outcome == "changed"
    assert observations.exact_error_match
    assert observations.error_is_value_error
    assert observations.primary_closed
    assert observations.state_unchanged
    assert observations.span_count_singleton
    assert observations.audit_row_count_zero
    assert observations.later_reconcile_changed


def test_phase15_e2a_task88_c5_audited_preflight_rollback_live() -> None:
    """PARTIAL(C5): audited preflight rollback on a seeded material conflict.

    Boundary: preflight rollback plus audit only; never late-DML evidence,
    never C14.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c5_impl(session)
    if not observations.success:
        raise RuntimeError(f"C5 live cell failed: {observations.error_reason}")
    assert observations.outcome_rolled_back_failure
    assert observations.failure_maps_empty
    assert observations.comparator_parity_none
    assert observations.audit_outcome_written
    assert observations.audit_count_one
    assert observations.audit_fields_match
    assert observations.audit_scope_manifest_matches
    assert observations.audit_diagnostic_matches
    assert observations.append_only_triggers_present
