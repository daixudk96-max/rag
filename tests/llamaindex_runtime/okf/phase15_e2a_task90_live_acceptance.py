"""Task #90 authorized live acceptance selector (controlled producer).

This module is the honest live acceptance surface of the Task #90 slice.
It is NOT collected by default pytest runs (``phase15_`` filename prefix,
which matches neither ``test_*.py`` nor ``*_test.py``), and its selected
live test fails closed before any session creation unless separately
authorized:

    test_task90_authorized_live_acceptance()
      -> _require_authorization()                    # hard RuntimeError if not
                                                     # separately authorized
      -> one ExitStack/DisposableE2aSession          # safe container values
      -> _run_task90_live_proof(session)             # one direct positional call
      -> RuntimeError(observations.error_reason)     # on failure, redacted
      -> 14 success assertions on the observations

The selected live test executes the Task #90 controlled producer's live
component exactly once: real strict E2A admission of one complete M-D-S-M
raw pair (markdown + spans sidecar + pair manifest) with one real canonical
span, and one manual relation whose ``evidence`` resolves to that admitted
span (so the admitted state carries a NON-EMPTY evidence object/link); a
first reconcile with the DEFAULT ``E2aReconciler()`` (default
``E2aMaterializationRepository``, no fake repository or builder injection);
an equivalent rerun that MUST be ``no_op`` with every real primary DML
table count exactly 0; independent fresh-observer full-collection scope
snapshots before/after the rerun that MUST be equal; and the build + verify
of a process-local structural binding over the exact first-reconcile result
object -- all within the same invocation, before a redacted canonical
artifact dict is produced. It is an explicit authorized live test, never an
unconditionally passing test, never a ``pytest.skip``, never an ``xfail``,
and never a database command in itself (all database work lives inside the
helper cell).

All database work lives in the helper; this module never opens a
connection, never reads an environment variable, never creates a session
at module level, and never prints or logs a URI, credential, target, or
raw corpus text.
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
from ._phase15_e2a_task90_live_cells import _run_task90_live_proof
from ._phase15_e2a_task90_types import (
    REQUIRED_OBSERVATION_FIELDS,
    Task90Observations,
)


def test_task90_authorized_live_acceptance() -> None:
    """Task #90 controlled live acceptance (real producer; auth-first).

    The authorization check is the FIRST statement and is never skipped;
    only after it may one ExitStack/DisposableE2aSession be opened
    (reusing the safe generated container name, ephemeral port, and
    generated password), exactly one direct positional
    ``_run_task90_live_proof(session)`` call run, and the 14 observation
    fields asserted. On failure exactly one RuntimeError carries only
    ``observations.error_reason``.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_task90_live_proof(session)
    if not observations.success:
        raise RuntimeError(
            f"Task #90 acceptance cell failed: {observations.error_reason}"
        )
    assert observations.admitted_state_complete
    assert observations.admitted_has_manual_relation
    assert observations.admitted_has_raw_pair
    assert observations.admitted_has_resolved_evidence
    assert observations.reconcile_first_changed
    assert observations.rerun_no_op
    assert observations.rerun_primary_dml_all_zero
    assert observations.denylist_exact_zero
    assert observations.default_reconciler_default_repository
    assert observations.exact_returned_objects_kept
    assert observations.pre_post_scope_snapshots_equal
    assert observations.binding_built_in_invocation
    assert observations.binding_verifies
    assert observations.artifact_redacted


def test_task90_live_acceptance_metadata() -> None:
    """Non-live metadata companion: no authorization and no session.

    This test requires no authorization and no database; it pins the
    Task #90 observation surface (14 fields).
    """
    assert len(REQUIRED_OBSERVATION_FIELDS) == 14
    assert REQUIRED_OBSERVATION_FIELDS == frozenset(Task90Observations._fields) - {
        "success",
        "error_reason",
    }
