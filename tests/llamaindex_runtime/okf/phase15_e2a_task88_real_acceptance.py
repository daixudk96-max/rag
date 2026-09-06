"""Task #88 authorized global live acceptance selector (approved composed proof).

This module is the honest live acceptance surface of the Task #88 slice.
It is NOT collected by default pytest runs (``phase15_`` filename prefix,
which matches neither ``test_*.py`` nor ``*_test.py``), and its selected
live test fails closed before any session creation unless separately
authorized:

    test_task88_authorized_live_acceptance()
      -> _require_authorization()                 # hard RuntimeError if not
                                                  # separately authorized
      -> one ExitStack/DisposableE2aSession       # safe container values
      -> _run_late_dml_candidate_impl(session)    # one direct positional call
      -> RuntimeError(observations.error_reason)  # on failure, redacted
      -> 12 success assertions on the observations

The selected live test executes the approved formal composed proof behind
the shared required cell ``TASK88_REQUIRED_CELL_ID == "true_late_dml_failure"``:
the C14 late-DML candidate cell's live V1/V2 rollback/audit/observer
observations (the live component of the composed proof), pinned against the
production evidence UPSERT/``_issue`` ordering, the repository source order
before ``_upsert_evidence``, V2 preflight admission and bare-evidence
inventory exclusion, the migration 019 audit phase, and the explicit
rollback-result-map boundary. It is an explicit authorized live test,
never an unconditionally passing test, never a ``pytest.skip``, never an
``xfail``, and never a database command in itself (all database work lives
inside the helper cell).

Execution gate order for ANY future authorized live invocation (reviews
before live, exactly one general review and one DB/security review of the
final snapshot, then ONE authorized live selector invocation):

    LIVE_GATE_ORDER = (
        "unit_green",
        "general_review",
        "db_security_review",
        "authorized_live",
    )

Plan-gate corrections carried by this source (and asserted by
``CELL_PLAN`` in ``_phase15_e2a_task88_cells``):

1. Reviews before live: every cell descriptor requires the gate order.
2. Parent provenance: every parent-bearing cell declares required
   ``document_versions`` provenance (real PostgresRegistryWriter
   registration or an explicitly parameterized seed).
3. The failure-audit cell and the composed-proof required cell require an
   explicitly injected FRESH ATTESTED connection factory
   (``DisposableE2aSession.open_fresh_attested_connection`` per audit
   connection); the pure default constructor (None factory) is NOT an
   audit path.

Future live cells bridge ONLY through the current Task #87 harness
(``_phase15_e2a_harness_types`` / ``_phase15_e2a_harness_lifecycle``) and
production APIs; no trigger hacks, no handcrafted advisory-lock SQL, no
sleep/poll/retry-to-pass, no external vector projection, no
``dict.get(..., 0)`` hiding, no fake connection/cursor/repository/result
in this live source, and no broad ``except Exception``.
"""

from __future__ import annotations

import contextlib

from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
from ._phase15_e2a_harness_types import (
    _require_authorization,
    _validate_container_name,
)
from ._phase15_e2a_late_dml_candidate_cells import _run_late_dml_candidate_impl
from ._phase15_e2a_task88_cells import (
    AUDIT_CELL_ID,
    CELL_PLAN,
    LIVE_GATE_ORDER,
    PARENT_BEARING_CELL_IDS,
    TASK88_REQUIRED_CELL_ID,
)
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)

# Alias so the gate order is visible in the live source itself.
TASK88_LIVE_GATE_ORDER = LIVE_GATE_ORDER


def test_task88_authorized_live_acceptance() -> None:
    """Task #88 global live acceptance (approved composed proof; auth-first).

    Gate order (reviews before live): unit_green -> general_review ->
    db_security_review -> authorized_live. The authorization check is the
    FIRST statement and is never skipped; only after it may one
    ExitStack/DisposableE2aSession be opened (reusing the safe generated
    container name, ephemeral port, and generated password), exactly one
    direct positional ``_run_late_dml_candidate_impl(session)`` call run,
    and the 12 C14 observation fields asserted. On failure exactly one
    RuntimeError carries only ``observations.error_reason``.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_late_dml_candidate_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"Task #88 global acceptance cell failed: {observations.error_reason}"
        )
    assert observations.outcome_rolled_back_failure
    assert observations.failure_maps_empty
    assert observations.comparator_parity_none
    assert observations.audit_outcome_written
    assert observations.primary_closed
    assert observations.both_registry_versions_exist
    assert observations.bare_seed_durable
    assert observations.v1_materialization_absent
    assert observations.audit_count_one
    assert observations.audit_fields_match
    assert observations.audit_scope_manifest_matches
    assert observations.audit_diagnostic_matches


def test_task88_global_acceptance_metadata() -> None:
    """Non-live metadata companion: no authorization and no session.

    This test requires no authorization and no database; it pins the
    shared required-cell id, the reviews-before-live / parent-provenance /
    injected-attested-factory corrections on every future live cell
    descriptor, and the approved composed-proof descriptor of the
    required cell.
    """
    assert TASK88_REQUIRED_CELL_ID == "true_late_dml_failure"
    assert TASK88_LIVE_GATE_ORDER == LIVE_GATE_ORDER
    assert LIVE_GATE_ORDER == (
        "unit_green",
        "general_review",
        "db_security_review",
        "authorized_live",
    )
    for plan in CELL_PLAN:
        assert plan.requires_reviews_before_live is True
    for cell_id in PARENT_BEARING_CELL_IDS:
        plan = next(plan for plan in CELL_PLAN if plan.cell_id == cell_id)
        assert (
            plan.required_parent_provenance
        ), f"parent-bearing cell {cell_id} must declare required parent provenance"
    audit = next(plan for plan in CELL_PLAN if plan.cell_id == AUDIT_CELL_ID)
    assert audit.requires_injected_fresh_attested_factory is True
    assert audit.requires_reviews_before_live is True
    required = next(
        plan for plan in CELL_PLAN if plan.cell_id == TASK88_REQUIRED_CELL_ID
    )
    assert required.source_supported_facts, (
        "the composed-proof cell must carry non-empty concrete facts"
    )
    assert required.required_parent_provenance
    assert required.requires_injected_fresh_attested_factory is True
    assert required.requires_reviews_before_live is True