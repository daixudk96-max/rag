"""Explicitly selected live foundation cells for the E2A foundation tranche.

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and every
live cell fails closed unless separately authorized.

Each live cell is a partial proof; nothing here claims the whole tranche is
proven, and no cell asserts beyond its stated boundary.

PARTIAL(C13)
    Parent registration and provenance observation are proven through the
    real PostgresRegistryWriter over a temporary source file. This cell does
    not reconcile; boundary: registration only.

PARTIAL(C1)
    A single-parent full reconcile through the default repository is proven
    changed, with the full 15-key primary shape, the ten-key zero denylist
    map, manifest hash match, and durable observer state. Exact per-table
    statement counts beyond shape are not asserted; boundary: single-parent
    foundation.

PARTIAL(C11)
    The catalog-limited denylist boundary is proven: the five catalog-present
    denylist tables are observed with count queries before and after a
    foundation reconcile (with the observer transaction reset between the
    two count reads so the post-reconcile observation is isolation-level
    independent), and the five absent names are confirmed only through the
    information_schema catalog. Boundary: catalog-limited.

Security contract: all connections come from DisposableE2aSession
open_fresh_attested_connection calls; the registry writer connection is the
writer role, the reconcile connection is a fresh autocommit-False primary,
and the observer uses a separate fresh connection. No URI, credential,
target, container token, or raw fixture content is ever printed, logged, or
returned. Every resource is closed inside the helper cells, a session
setup failure propagates unmodified instead of being masked, and a failed
cell raises RuntimeError carrying only the observation's bounded
error_reason (the exception class name, never its text).
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
    _run_c1_reconcile_impl,
    _run_c11_impl,
    _run_c13_impl,
    _select_ephemeral_port,
)


def test_phase15_e2a_task88_c13_registration_live() -> None:
    """PARTIAL(C13): real parent registration and provenance observation.

    Boundary: registration only; no reconcile is attempted in this cell.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c13_impl(session)
    if not observations.success:
        raise RuntimeError(f"C13 live cell failed: {observations.error_reason}")
    assert observations.registered
    assert observations.provenance_matches
    assert observations.version_singleton


def test_phase15_e2a_task88_c1_reconcile_live() -> None:
    """PARTIAL(C1): single-parent full reconcile through the default repository.

    Boundary: single-parent foundation; exact per-table statement counts
    beyond the full shape are not asserted.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c1_reconcile_impl(session)
    if not observations.success:
        raise RuntimeError(f"C1 live cell failed: {observations.error_reason}")
    assert observations.outcome == "changed"
    assert observations.manifest_sha256_match
    assert observations.primary_shape_valid
    assert observations.denylist_zeros_valid
    assert observations.observer_durable


def test_phase15_e2a_task88_c11_denylist_catalog_live() -> None:
    """PARTIAL(C11): catalog-limited denylist boundary observations.

    The five absent names are confirmed only through the information_schema
    catalog; boundary: catalog-limited, no table-level query for absent
    names.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c11_impl(session)
    if not observations.success:
        raise RuntimeError(f"C11 live cell failed: {observations.error_reason}")
    assert observations.unchanged_valid
    assert all(observations.absent_catalog_flags.values())
    assert set(observations.ten_zero_map) == (
        set(observations.present_before) | set(observations.absent_catalog_flags)
    )
    assert all(value == 0 for value in observations.ten_zero_map.values())
