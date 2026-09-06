"""Explicitly selected Task #88 C7R corrected stale span deletion live cell.

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and the
live cell fails closed unless separately authorized.

- PARTIAL(C7R) corrected sparse stale-ID map: the Stage 3 C7 helper
  asserted a five-key sparse stale-ID count map for the span-retired second
  desired state, wrongly including an evidence_links entry, and the
  original cell failed on that exact sparse-map assertion. This NEW
  identity supersedes that failed outcome ONLY as a corrected partial
  sparse-map contract: the span-retired second state must report exactly
  the four keys tree_node_spans, vector_chunk_spans, evidence, and
  canonical_spans (each exactly 1) and must NOT report an evidence_links
  key, because the span-retired state retires the desired evidence_links
  collection and evidence links are deleted by stale evidence ids via
  DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS rather than by stale link ids. The
  correction does not erase the recorded failure of the original identity,
  and this cell is never C14, never Task #88 completion, and never Phase 15
  completion evidence.

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
from ._phase15_e2a_task88_c7r_cells import _run_c7r_impl
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)


def test_phase15_e2a_task88_c7r_stale_span_deletion_live() -> None:
    """PARTIAL(C7R): corrected sparse stale-ID map for the span-retired state.

    The single canonical span is retired by the second desired state while
    the chunk, tree node, entity, ownership, and sync rows are retained.
    The sparse stale-ID count map must be exactly the four corrected keys
    (tree_node_spans, vector_chunk_spans, evidence, canonical_spans, each
    exactly 1) with no evidence_links key, and a fresh observer proves the
    committed row-count absence of the stale span id in canonical_spans,
    tree_node_spans, and vector_chunk_spans. The cell never equates
    statement counts with row counts and is never C14 or completion
    evidence.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c7r_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C7R stale-deletion cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "changed"
    assert observations.stale_map_exact_sparse
    assert observations.evidence_links_key_absent
    assert observations.canonical_span_absent
    assert observations.tree_node_span_absent
    assert observations.vector_chunk_span_absent
    assert observations.retained_intact
