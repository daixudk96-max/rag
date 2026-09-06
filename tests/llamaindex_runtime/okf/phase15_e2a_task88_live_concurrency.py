"""Explicitly selected Task #88 Stage 4 live cell (C6 advisory-lock concurrency).

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and the
live cell fails closed unless separately authorized.

- PARTIAL(C6) advisory-lock concurrency: a hooked default reconciler (AB)
  materializes a minimal single-parent foundation state on its own fresh
  attested manual-transaction primary and holds the production scope locks
  at its post-lock hook; a second bare default reconciler (ABC) reconciles
  the identical desired state on its own fresh attested primary and blocks
  on the same whole-corpus advisory lock; a third fresh attested observer
  runs exactly ONE advisory-lock catalog query while AB holds the locks and
  must see exactly one common advisory-lock tuple (AB granted, ABC
  waiting) with the documented key-half mapping. After the release, the
  real post-release outcomes are asserted truthfully (AB "changed", ABC
  "no_op") and both workers are joined with bounded cleanup timeouts.
  Boundary: one contended whole-corpus advisory lock tuple under one
  interleaving, never any other cell, never any late-DML path, never any
  performance property, never any task-level or phase-level status claim.

Security contract: the test itself performs no database work and no
reconciler construction; the helper cell absorbs all failures into a
redacted observation and the selector raises RuntimeError carrying only
the observation's bounded error_reason (the exception class name, never
its text). No URI, credential, target, container token, or raw fixture
content is ever printed, logged, or returned. Every resource is closed
inside the helper cell.
"""

from __future__ import annotations

import contextlib

from ._phase15_e2a_harness_lifecycle import DisposableE2aSession
from ._phase15_e2a_harness_types import (
    _require_authorization,
    _validate_container_name,
)
from ._phase15_e2a_task88_concurrency_cells import _run_c6_impl
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)


def test_phase15_e2a_task88_c6_advisory_lock_concurrency_live() -> None:
    """PARTIAL(C6): one contended whole-corpus advisory lock tuple.

    AB (hooked default reconciler) holds the production scope locks at its
    post-lock hook while ABC (bare default reconciler) blocks on the same
    whole-corpus advisory lock; a fresh read-only observer captures exactly
    one common advisory-lock tuple with AB granted and ABC waiting, mapped
    to the documented key halves. After the release both workers join with
    bounded timeouts and the real post-release outcomes are asserted
    truthfully. Boundary: advisory-lock concurrency evidence only, never
    any other cell, never any late-DML path, never any performance
    property, and never any task-level or phase-level status claim.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c6_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C6 advisory-lock cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "no_op"
    assert observations.common_tuple_exact
    assert observations.lock_mapping_exact
    assert observations.threads_joined_cleanly
