"""Explicitly selected Stage 2R v1-to-v2 transition live cell (not collected).

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and the
live cell fails closed unless separately authorized. This selector is NOT
run during the Stage 2R delivery task; it is delivered for a separately
authorized live run.

PARTIAL(v1-v2)
    The real production v1-to-v2 materialization transition. Two real
    versions of one document are registered through the real
    ``PostgresRegistryWriter``; version 1 is materialized, then version 2
    with the default ``E2aReconciler()``. Both outcomes must be exactly
    ``changed`` (the v1-to-v2 ownership scope UPDATE on the shared,
    version-independent ownership row must succeed against the immediate
    non-deferrable ownership-scope foreign key because stale v1 evidence
    links are removed first). A fresh observer proves the retained ownership
    row is re-scoped to version 2 (version_id, scope_version_id,
    document_id all equal the v2 registration), that v2 manual evidence
    links exist on the retained ownership id with a matching v2 ownership
    scope, and that old v1 manual evidence links, evidence targets, and
    evidence rows are absent. Materialization-integrity transition
    regression ONLY; explicitly never C14 and never late-DML evidence.

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
from ._phase15_e2a_task88_stage2r_cells import _run_v1v2_transition_impl


def test_phase15_e2a_task88_v1_v2_materialization_integrity_live() -> None:
    """PARTIAL(v1-v2): true v1-to-v2 materialization-integrity regression.

    Boundary: materialization integrity of the real version transition only;
    explicitly never C14 and never late-DML evidence.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_v1v2_transition_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"v1-to-v2 transition cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "changed"
    assert observations.ownership_row_retained
    assert observations.ownership_scoped_to_second
    assert observations.second_scope_manual_links_present
    assert observations.first_scope_manual_links_absent
    assert observations.first_scope_evidence_absent
