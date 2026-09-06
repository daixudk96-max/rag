"""Explicitly selected Stage 2R C4 lock-release live cell (not collected).

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and the
live cell fails closed unless separately authorized.

PARTIAL(C4-lock-release)
    The same real collision setup as the superseded Stage 2 C4 cell: two
    real versions of one document, the second scope deliberately reusing the
    first scope's span id, through the default ``E2aReconciler()`` with no
    audit factory. The unwrapped exact ``ValueError`` is asserted, the
    primary is closed after rollback, a fresh observer sees unchanged state
    and zero durable audit rows. Then, after the collision rollback, a fresh
    attested reconciler connection re-reconciles the SAME first desired
    state (never the second one; no v1-to-v2 DML is performed) and must
    project the exact ``outcome == "no_op"`` with full zero primary-map
    semantics, and a fresh observer must still see the committed state
    durably — proving the rollback released every transaction-scoped
    advisory and table lock and the committed state is idempotently
    re-materializable. Boundary: lock release/idempotence only, never C14.

Security contract: the test itself performs no database work and no
reconciler construction; the helper cell absorbs all failures into a redacted
observation and the selector raises RuntimeError carrying only the
observation's bounded error_reason (the exception class name, never its
text). No URI, credential, target, container token, or raw fixture content
is ever printed, logged, or returned. Every resource is closed inside the
helper cell.
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
from ._phase15_e2a_task88_stage2r_cells import _run_c4_lock_release_impl


def test_phase15_e2a_task88_c4_lock_release_noop_live() -> None:
    """PARTIAL(C4-lock-release): lock release/idempotence after the rollback.

    Boundary: lock release and idempotence only, proven by re-reconciling the
    SAME first desired state (never second_desired, no v1-to-v2 DML); never
    C14.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c4_lock_release_impl(session)
    if not observations.success:
        raise RuntimeError(f"C4 lock-release cell failed: {observations.error_reason}")
    assert observations.first_outcome == "changed"
    assert observations.exact_error_match
    assert observations.error_is_value_error
    assert observations.primary_closed
    assert observations.state_unchanged
    assert observations.span_count_singleton
    assert observations.audit_row_count_zero
    assert observations.release_outcome_noop
    assert observations.release_zero_primary_counts
    assert observations.release_primary_shape_valid
    assert observations.release_observer_durable
