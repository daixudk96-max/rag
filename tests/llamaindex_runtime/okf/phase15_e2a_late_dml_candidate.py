"""Explicitly selected Phase 15 Task #88 C14 late-DML candidate live cell (not collected).

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and the
live cell fails closed unless separately authorized.

PARTIAL(C14-candidate)
    Two real versions of one document are registered through the real
    ``PostgresRegistryWriter`` path. A V1-complete/V2-empty two-parent
    desired state is built, and a bare evidence seed (desired V1 evidence
    ID, real V2 registered version ID) is committed on its own fresh seed
    connection before any V1 materialization. Production reconciliation
    emits real earlier primary DML, then the production evidence upsert
    guard raises ``ValueError``; the primary transaction rolls back and an
    independently opened, fresh-attested connection commits the durable
    failure audit. A fresh observer verifies both registry versions, the
    durable bare seed, zero V1 materialization, and the exact audit row
    (``rollback_confirmed=True``, ``failure_phase=parent_reconciliation``,
    ``scope_count=2``, exact scope manifest/hash, diagnostic exactly
    ``{"error_type": "ValueError"}``). This is PARTIAL(C14-candidate)
    evidence only: its live rollback/audit/observer observations form the
    live component of the approved formal composed proof for the Task #88
    required cell ``true_late_dml_failure``. Standalone execution of this
    candidate selector does not itself close Task #88, #79, or Phase 15.

Security contract: the test itself performs no database work and no
reconciler construction; the helper cell absorbs all failures into a
redacted observation and the selector raises RuntimeError carrying only the
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
from ._phase15_e2a_late_dml_candidate_cells import _run_late_dml_candidate_impl
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)


def test_phase15_e2a_late_dml_candidate_live() -> None:
    """PARTIAL(C14-candidate): late evidence-upsert failure with durable audit.

    Boundary: this standalone candidate execution does not itself close Task
    #88, #79, or Phase 15; its live rollback/audit/observer observations are
    the live component of the approved formal composed proof.
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
            f"late-DML candidate cell failed: {observations.error_reason}"
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
