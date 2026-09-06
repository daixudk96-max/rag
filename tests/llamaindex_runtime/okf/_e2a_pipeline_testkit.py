"""Private test support utilities for E2a pipeline tests (Phase 15 Track A).

This module contains test-only fakes and factories. These are NOT acceptance evidence.
They exist solely to support unit test collection without production dependencies.
"""

from __future__ import annotations

from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult, Outcome

# Outcome type aligned with the real E2a contract ``Outcome`` literal.
# Only the five contract-valid outcomes are permitted; the stale ``error`` and
# ``rollback`` literals are intentionally absent.
E2aOutcomeType = Outcome


def _make_reconciliation_result(
    outcome: E2aOutcomeType = "no_op",
) -> E2aReconciliationResult:
    """Factory for minimal typed E2a reconciliation results (test support only)."""
    return E2aReconciliationResult(
        outcome=outcome,
        manifest_sha256="a" * 64,
        primary_dml_by_table={},
        denylist_dml_counts={},
        comparator_parity=None,
        stale_deletion_counts={},
        cache_invalidation_counts={},
        failure_audit_outcome=None,
        post_rollback_failure_audit_outcome=None,
    )


class _FakeReconciler:
    """Test-only reconciler stub (NOT acceptance evidence).

    Used by Wave 1 tests to verify pipeline integration without database dependencies.

    Call tracking is a single deterministic class-level integer with no metaclass,
    no ``__del__``, no GC/id lifecycle, and no race-prone per-instance aggregation.

    - ``_FakeReconciler.calls`` is the total call count across all instances.
    - ``_FakeReconciler.calls = 0`` resets the counter honestly (compatible API).
    - ``reset_calls()`` resets the counter to zero across all preexisting instances.
    """

    calls: int = 0

    def reconcile(self, connection: object, desired: object) -> E2aReconciliationResult:
        """Increment the class call counter and return a fake reconciliation result."""
        _FakeReconciler.calls += 1
        return _make_reconciliation_result()

    def reset_calls(self) -> None:
        """Reset the class-level call counter to zero.

        Honest across all preexisting instances: there is no per-instance state to
        leak, so a single integer assignment fully restores the initial condition.
        """
        _FakeReconciler.calls = 0
