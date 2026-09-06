"""Explicitly selected Task #88 Stage 3 live cells (C7/C8/C9/C10/C12).

This module is intentionally NOT collected by default test name discovery
(the ``phase15_`` filename prefix matches neither ``test_*.py`` nor
``*_test.py``). It runs only when explicitly selected by file path, and every
live cell fails closed unless separately authorized.

- PARTIAL(C7) stale span deletion: materialize a minimal valid single-parent
  foundation state, then a second desired state retires the single span while
  retaining its chunk/node/entity/ownership/sync rows. Asserts the sparse
  stale-ID count map exactly and the committed row-count absence of each
  stale identifier in canonical_spans, tree_node_spans, and
  vector_chunk_spans. Stale-ID counts are identifier-set sizes; absence is
  asserted by committed row counts. The cell never equates statement counts
  with row counts and never C14.
- PARTIAL(C8) chunk repoint: retain the foundation chunk while replacing its
  stale tree node with the deterministic ``_tree_repair_targets`` candidate
  (a fresh root node in the same version). Asserts the retained chunk points
  at the expected target and the old node id is absent. Ordering is treated
  as source-backed program order plus post-state, never as observed
  interleaving. Never C14.
- PARTIAL(C9) cache invalidation: seed cache rows only after the actual tree
  node exists — 16-dimensional chunk vectors stay 16-dimensional while
  node_embeddings are 384-dimensional. Asserts the measured
  cache_invalidation_counts (summaries/node_embeddings/semantic_distribution
  each exactly 1) plus join-free committed post-delete cache absence. The
  production JOIN-based measurement query is never used as the final absence
  probe. Never C14.
- PARTIAL(C10) destructive closure: seed one real ``entity_mentions`` row
  against an existing canonical span that the second desired state retires.
  Requires the exact fail-closed pre-DML ValueError from the default
  ``E2aReconciler()``, then a fresh observer proves span, dependency, and
  parent state intact. Simulates a foreign dependency only; never invokes or
  claims E2b and is never C14 or late-DML evidence.
- PARTIAL(C12) parentless cleanup: reconcile a parent-bearing desired state,
  then a parentless desired state with all parent-scoped collections empty
  and no global manual facts. Derived E2a state/sync is cleaned while the
  registry document/version rows remain; a second empty run must be an exact
  no-op. The cell never claims shared-global manual-fact preservation and is
  never C14.

Security contract: the tests themselves perform no database work and no
reconciler construction; each helper cell absorbs all failures into a
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
from ._phase15_e2a_task88_live_cells import (
    _generate_safe_container_name,
    _generate_test_password,
    _select_ephemeral_port,
)
from ._phase15_e2a_task88_stage3_cells import (
    _run_c7_impl,
    _run_c8_impl,
    _run_c9_impl,
    _run_c10_impl,
    _run_c12_impl,
)


def test_phase15_e2a_task88_c7_stale_span_deletion_live() -> None:
    """PARTIAL(C7): stale span deletion proves the sparse stale-ID map.

    The single canonical span is retired by the second desired state while
    the chunk, tree node, entity, ownership, and sync rows are retained. The
    sparse stale-ID count map must be exact and a fresh observer proves the
    committed row-count absence of the stale span id in canonical_spans,
    tree_node_spans, and vector_chunk_spans. The cell never equates
    statement counts with row counts. Boundary: stale span deletion only,
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
        observations = _run_c7_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C7 stale-deletion cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "changed"
    assert observations.stale_map_exact_sparse
    assert observations.canonical_span_absent
    assert observations.tree_node_span_absent
    assert observations.vector_chunk_span_absent
    assert observations.retained_intact


def test_phase15_e2a_task88_c8_chunk_repoint_live() -> None:
    """PARTIAL(C8): chunk repoint proves the deterministic repair target.

    The foundation chunk is retained while its stale tree node is replaced
    by a fresh root node in the same version; the deterministic repair
    target comes from the production ``_tree_repair_targets`` authority. A
    fresh observer proves the retained chunk points at the expected target
    and the old node id is absent from tree_nodes. Ordering is
    source-backed program order plus post-state, never observed
    interleaving. Boundary: chunk repoint only, never C14.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c8_impl(session)
    if not observations.success:
        raise RuntimeError(f"C8 chunk-repoint cell failed: {observations.error_reason}")
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "changed"
    assert observations.chunk_retained
    assert observations.chunk_repoints_to_expected_target
    assert observations.old_node_absent


def test_phase15_e2a_task88_c9_cache_invalidation_live() -> None:
    """PARTIAL(C9): cache invalidation proves measured counts and absence.

    Cache rows are seeded only after the actual tree node exists: one
    summaries row, one node_embeddings row (384-dimensional), and one
    semantic_distribution row. The second reconcile retires that node; the
    measured cache invalidation counts must be exactly 1 per cache table,
    and a fresh observer proves join-free committed post-delete absence per
    cache table. The production JOIN-based measurement query is never used
    as the final absence probe. Boundary: cache invalidation only, never
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
        observations = _run_c9_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C9 cache-invalidation cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.second_outcome == "changed"
    assert observations.measured_counts_exact
    assert observations.summary_absent
    assert observations.node_embedding_absent
    assert observations.semantic_distribution_absent
    assert observations.old_node_absent


def test_phase15_e2a_task88_c10_destructive_closure_live() -> None:
    """PARTIAL(C10): destructive closure proves the fail-closed pre-DML guard.

    One real ``entity_mentions`` row is seeded against the existing
    canonical span that the second desired state retires; the default
    ``E2aReconciler()`` must raise the exact fail-closed pre-DML ValueError
    and close the primary after rollback. A fresh observer then proves the
    span, its tree-node-span link, the mention row, and the parent
    document/version rows are all intact. This simulates a foreign
    dependency only; never E2b, never C14, and never late-DML evidence.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c10_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C10 destructive-closure cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.exact_error_match
    assert observations.primary_closed
    assert observations.span_still_present
    assert observations.span_link_still_present
    assert observations.mention_still_present
    assert observations.parent_document_present
    assert observations.parent_version_present


def test_phase15_e2a_task88_c12_parentless_cleanup_live() -> None:
    """PARTIAL(C12): parentless cleanup proves derived-state cleaning.

    A parent-bearing foundation is materialized, then a parentless desired
    state with all parent-scoped collections empty and no global manual
    facts cleans every E2a-derived row while the registry document/version
    rows remain. A second empty run must be an exact no-op with empty stale
    and cache maps. The cell never claims shared-global manual-fact
    preservation. Boundary: parentless cleanup only, never C14.
    """
    _require_authorization()
    with contextlib.ExitStack() as stack:
        session = DisposableE2aSession(
            container_name=_validate_container_name(_generate_safe_container_name()),
            port=_select_ephemeral_port(),
            password=_generate_test_password(),
        )
        stack.enter_context(session)
        observations = _run_c12_impl(session)
    if not observations.success:
        raise RuntimeError(
            f"C12 parentless-cleanup cell failed: {observations.error_reason}"
        )
    assert observations.first_outcome == "changed"
    assert observations.cleanup_outcome == "changed"
    assert observations.second_noop_exact
    assert observations.no_global_manual_facts
    assert observations.canonical_spans_cleaned
    assert observations.vector_chunks_cleaned
    assert observations.tree_nodes_cleaned
    assert observations.evidence_cleaned
    assert observations.ownership_cleaned
    assert observations.sync_cleaned
    assert observations.entities_cleaned
    assert observations.registry_document_retained
    assert observations.registry_version_retained
