"""Real E2aReconciler acceptance tests with disposable PostgreSQL.

Task #87: Evidence-capable foundation proving default repository execution.

This module is LIVE and requires explicit authorization
(``OKF_E2A_DISPOSABLE_TEST_AUTHORIZED=separately-authorized``). The negative
proof is in ``test_real_e2a_reconciler_authorization.py``; the in-process
harness contract is exercised in ``test_real_e2a_reconciler_harness_unit.py``.
"""

# ruff: noqa: F811  # pytest fixture import pattern

from __future__ import annotations

from typing import cast

import psycopg

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aReconciliationResult,
    canonical_json,
)
from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler, _Connection
from scripts._rebuild_database_connection import DisposablePostgresqlTarget

from ._real_e2a_reconciler_lifecycle import (
    _EXPECTED_DATABASE,
    _open_manual_connection,
    _open_verification_connection,
    disposable_postgres_target,  # noqa: F401, F811  # pytest fixture
)
from ._real_e2a_reconciler_testkit import (
    _all_denylist_counts,
    _assert_all_denylist_zero,
    _assert_full_result_fields,
    _build_desired,
    _max_timestamp,
    _mutated_desired,
    _register_parent,
    _scope_row_counts,
    _scope_snapshot,
)
from ._real_e2a_reconciler_types import ScopeSnapshot


def _close_if_open(conn: psycopg.Connection) -> None:
    """Close a connection only if it is not already closed."""
    if not conn.closed:
        conn.close()


def _reconcile(
    target: DisposablePostgresqlTarget, desired: E2aDesiredState
) -> E2aReconciliationResult:
    """Open a manual connection, run reconcile, and return the result."""
    conn = _open_manual_connection(target)
    try:
        result = E2aReconciler().reconcile(cast(_Connection, conn), desired)
        assert type(result) is E2aReconciliationResult
        return result
    finally:
        _close_if_open(conn)


def _make_desired(
    doc_id: str,
    version_id: str,
    *,
    canonical_hash: str,
    span_text: str,
) -> E2aDesiredState:
    return _build_desired(
        doc_id=doc_id,
        version_id=version_id,
        canonical_hash=canonical_hash,
        relpath=f"raw/{doc_id}.okf",
        span_text=span_text,
        span_id=str(__import__("uuid").uuid4()),
        chunk_id=str(__import__("uuid").uuid4()),
        node_id=version_id,
    )


def test_first_reconcile_with_valid_desired_state_returns_changed(
    disposable_postgres_target: DisposablePostgresqlTarget,
) -> None:
    """First reconcile returns ``changed`` and populates only the legal tables."""
    from uuid import uuid4

    doc_id, version_id = str(uuid4()), str(uuid4())
    _register_parent(disposable_postgres_target, doc_id, version_id)
    desired = _make_desired(
        doc_id,
        version_id,
        canonical_hash="a" * 64,
        span_text="Test span for E2a reconciler acceptance",
    )
    pre = _snapshot(disposable_postgres_target, doc_id, version_id)
    result = _reconcile(disposable_postgres_target, desired)
    _assert_full_result_fields(
        result,
        "changed",
        desired.corpus_manifest_sha256,
    )
    primary = dict(result.primary_dml_by_table)
    for t in ("canonical_spans", "vector_chunks", "tree_nodes", "okf_sync_state"):
        assert primary[t] > 0, f"{t} must have >0 inserts"
    assert all(v == 0 for v in dict(result.denylist_dml_counts).values())
    post = _snapshot(disposable_postgres_target, doc_id, version_id)
    for t, snap in post.counts.items():
        assert snap > pre.counts[t], f"{t} count must increase"
    for t, d in post.digests.items():
        assert d != "" and d != pre.digests[t], f"{t} digest must change"
    assert pre.sync_ts is None or post.sync_ts != pre.sync_ts
    _assert_all_denylist_zero(post.denylist)


def test_equivalent_second_reconcile_returns_no_op_without_churn(
    disposable_postgres_target: DisposablePostgresqlTarget,
) -> None:
    """Second reconcile with the SAME desired state is a deterministic no_op."""
    from uuid import uuid4

    doc_id, version_id = str(uuid4()), str(uuid4())
    _register_parent(disposable_postgres_target, doc_id, version_id)
    desired = _make_desired(
        doc_id,
        version_id,
        canonical_hash="b" * 64,
        span_text="Test span for E2a reconciler acceptance",
    )
    first = _reconcile(disposable_postgres_target, desired)
    assert first.outcome == "changed" and first.failure_audit_outcome is None
    mid = _snapshot(disposable_postgres_target, doc_id, version_id)
    _assert_all_denylist_zero(mid.denylist)
    second = _reconcile(disposable_postgres_target, desired)
    _assert_full_result_fields(
        second,
        "no_op",
        desired.corpus_manifest_sha256,
    )
    for axis in (
        second.primary_dml_by_table,
        second.denylist_dml_counts,
        second.stale_deletion_counts,
        second.cache_invalidation_counts,
    ):
        assert all(v == 0 for v in dict(axis).values())
    after = _snapshot(disposable_postgres_target, doc_id, version_id)
    assert after.counts == mid.counts
    assert after.digests == mid.digests
    assert after.sync_ts == mid.sync_ts


def test_manifest_changing_mutation_returns_changed_with_new_sha(
    disposable_postgres_target: DisposablePostgresqlTarget,
) -> None:
    """A fully valid second desired state produces a different manifest SHA."""
    from uuid import uuid4

    doc_id, version_id = str(uuid4()), str(uuid4())
    _register_parent(disposable_postgres_target, doc_id, version_id)
    d1 = _make_desired(
        doc_id,
        version_id,
        canonical_hash="c" * 64,
        span_text="Test span for E2a reconciler acceptance",
    )
    d2 = _mutated_desired(
        d1,
        doc_id=doc_id,
        version_id=version_id,
        relpath=f"raw/{doc_id}.okf",
        span_id_added=str(uuid4()),
        chunk_id_added=str(uuid4()),
        new_canonical_hash="d" * 64,
    )
    assert d1.corpus_manifest_sha256 != d2.corpus_manifest_sha256
    canonical_json(d2.corpus_manifest)
    first = _reconcile(disposable_postgres_target, d1)
    assert first.outcome == "changed"
    pre = _snapshot(disposable_postgres_target, doc_id, version_id)
    second = _reconcile(disposable_postgres_target, d2)
    _assert_full_result_fields(second, "changed", d2.corpus_manifest_sha256)
    assert second.manifest_sha256 == d2.corpus_manifest_sha256
    assert second.manifest_sha256 != first.manifest_sha256
    post = _snapshot(disposable_postgres_target, doc_id, version_id)
    assert post.counts["canonical_spans"] > pre.counts["canonical_spans"]
    assert post.counts["vector_chunks"] > pre.counts["vector_chunks"]
    assert post.digests["canonical_spans"] != pre.digests["canonical_spans"]
    assert post.digests["vector_chunks"] != pre.digests["vector_chunks"]


def test_cross_scope_same_global_primary_key_is_rejected(
    disposable_postgres_target: DisposablePostgresqlTarget,
) -> None:
    """Scope B with a global PK already owned by A is rejected, A unchanged."""
    from uuid import uuid4

    d_a, v_a, d_b, v_b = (str(uuid4()) for _ in range(4))
    _register_parent(disposable_postgres_target, d_a, v_a)
    _register_parent(disposable_postgres_target, d_b, v_b)
    shared = str(uuid4())
    # Force both to share the same global span_id.
    desired_a = _build_desired(
        doc_id=d_a,
        version_id=v_a,
        canonical_hash="e" * 64,
        relpath=f"raw/{d_a}.okf",
        span_text="A",
        span_id=shared,
        chunk_id=str(uuid4()),
        node_id=v_a,
    )
    desired_b = _build_desired(
        doc_id=d_b,
        version_id=v_b,
        canonical_hash="f" * 64,
        relpath=f"raw/{d_b}.okf",
        span_text="B",
        span_id=shared,
        chunk_id=str(uuid4()),
        node_id=v_b,
    )
    a_result = _reconcile(disposable_postgres_target, desired_a)
    _assert_full_result_fields(
        a_result,
        "changed",
        desired_a.corpus_manifest_sha256,
    )
    a_pre = _snapshot(disposable_postgres_target, d_a, v_a)
    b_pre = _snapshot(disposable_postgres_target, d_b, v_b)
    b_conn = _open_manual_connection(disposable_postgres_target)
    try:
        E2aReconciler().reconcile(b_conn, desired_b)  # type: ignore[arg-type]
        raise AssertionError("expected ValueError")
    except ValueError as e:
        # Exact message string check
        expected = f"global canonical_spans span_id={shared} is owned by incompatible scope version {v_a}"
        assert str(e) == expected
    assert b_conn.closed, "reconciler must close connection before rollback"
    a_post = _snapshot(disposable_postgres_target, d_a, v_a)
    b_post = _snapshot(disposable_postgres_target, d_b, v_b)
    assert a_post.counts == a_pre.counts
    assert a_post.digests == a_pre.digests
    assert b_post.counts == b_pre.counts
    assert b_post.digests == b_pre.digests
    _assert_all_denylist_zero(b_post.denylist)


def test_default_repository_observation_proves_execution(
    disposable_postgres_target: DisposablePostgresqlTarget,
) -> None:
    """Reconciler with no injected repository actually writes to the DB."""
    from uuid import uuid4

    doc_id, version_id = str(uuid4()), str(uuid4())
    _register_parent(disposable_postgres_target, doc_id, version_id)
    desired = _make_desired(
        doc_id,
        version_id,
        canonical_hash="0" * 64,
        span_text="Default repository observation",
    )
    result = _reconcile(disposable_postgres_target, desired)
    _assert_full_result_fields(
        result,
        "changed",
        desired.corpus_manifest_sha256,
    )
    snap = _snapshot(disposable_postgres_target, doc_id, version_id)
    for t in ("canonical_spans", "vector_chunks", "tree_nodes", "okf_sync_state"):
        assert snap.counts[t] > 0, f"{t} must be populated by default repo"
    assert snap.counts["vector_chunk_spans"] > 0
    assert snap.counts["tree_node_spans"] > 0


# Snapshot helper used by every test; kept here so the acceptance module is self-contained.
def _snapshot(
    target: DisposablePostgresqlTarget, doc_id: str, version_id: str
) -> ScopeSnapshot:
    """Capture counts, digests, sync timestamp, and denylist in one connection.

    Returns exact ScopeSnapshot with frozen mappings attributes.
    """
    from types import MappingProxyType

    conn = _open_verification_connection(target)
    try:
        counts = _scope_row_counts(conn, doc_id, version_id)
        digests = _scope_snapshot(conn, doc_id, version_id)
        denylist = _all_denylist_counts(conn)
        sync_ts = _max_timestamp(conn, "okf_sync_state", version_id=version_id)
        # Construct ScopeSnapshot with frozen copies
        return ScopeSnapshot(
            counts=MappingProxyType(dict(counts)),
            digests=MappingProxyType(dict(digests)),
            denylist=MappingProxyType(dict(denylist)),
            sync_ts=sync_ts,
        )
    finally:
        conn.close()


# Pytest fixture glue: import the fixture from the lifecycle module so the
# graph remains the same, but expose it under the acceptance module's namespace.
def pytest_fixture_or_skip() -> None:  # pragma: no cover - import shim
    """Import-shim marker (the fixture itself is in _real_e2a_reconciler_lifecycle)."""
    from ._real_e2a_reconciler_lifecycle import (
        disposable_postgres_target,  # noqa: F401
    )


_ = _EXPECTED_DATABASE  # silence unused-import lint
