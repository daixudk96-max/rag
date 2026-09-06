"""Corrected Task #88 C7R live cell helper (sibling of the Stage 3 helper).

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides ONE
explicitly selected live cell in a NEW identity (C7R) that supersedes the
failed Stage 3 C7 identity ONLY as a corrected partial sparse-map contract.

- PARTIAL(C7R) corrected sparse stale-ID map: the Stage 3 C7 helper
  asserted a five-key sparse stale-ID count map for the span-retired second
  desired state, wrongly including an evidence_links entry. Production
  never records that key: the span-retired state retires the desired
  evidence_links collection, the scope inventory therefore returns an empty
  evidence-links identifier set, and the stale-evidence cleanup records an
  evidence_links count only for nonempty stale link sets. Evidence links
  are still deleted by stale evidence ids via
  DELETE_EVIDENCE_LINKS_BY_EVIDENCE_IDS. This cell asserts the exact
  corrected four-key map (tree_node_spans, vector_chunk_spans, evidence,
  canonical_spans, each exactly 1) with NO evidence_links key, exposes the
  explicit absence of that key as a separate observation, and a fresh
  observer proves the committed row-count absence of the stale span id in
  canonical_spans, tree_node_spans, and vector_chunk_spans. Stale-ID
  counts are identifier-set sizes; absence is asserted by committed row
  counts; the cell never equates statement counts with row counts. This
  correction does NOT erase the recorded failure of the original C7
  identity and is never C14, never Task #88 completion, and never Phase 15
  completion evidence.

Security contract (identical to the Stage 3 tranche): no environment
variable access of any kind; no DATABASE_URL anywhere; no URI, credential,
target, container token, or raw fixture content is ever printed, logged,
returned, or included in observation reprs. All connections come from
DisposableE2aSession.open_fresh_attested_connection. The registry writer,
every reconciler primary, and every observer are separate fresh attested
connections/transactions. Role separation means independent fresh attested
connections/transactions, not distinct PostgreSQL principals; no principal
or security model is implied or changed. Every cursor and connection is
closed in a finally block; the reconciler closes its primary on success and
on failure, and this frame also closes it in a finally path (the close is
idempotent). Failures are absorbed into redacted observations that carry a
bounded class/type-only diagnostic; exception messages, args, and reprs
never leave the helper. No test framework machinery, no skip or xfail
mechanics, no fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from ._phase15_e2a_task88_live_cells import (
    _FIXTURE_TITLE,
    _SOURCE_URI,
    _build_foundation_desired_state,
    _close_quietly,
    _create_source_fixture,
    _error_reason,
    _open_observer_connection,
    _open_reconciler_primary_connection,
    _open_writer_connection,
)


class C7RStaleDeletionObservations(NamedTuple):
    """Redacted observations for the C7R stale span deletion cell."""

    first_outcome: str = ""
    second_outcome: str = ""
    stale_map_exact_sparse: bool = False
    evidence_links_key_absent: bool = False
    canonical_span_absent: bool = False
    tree_node_span_absent: bool = False
    vector_chunk_span_absent: bool = False
    retained_intact: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C7RStaleDeletionObservations({rendered}, details=<redacted>)"


def _unlink_quietly(path: Path | None) -> None:
    """Remove a temp fixture path without surfacing cleanup failures."""
    if path is None:
        return
    try:
        path.unlink()
    except Exception:
        pass


def _register_single_document(writer_conn: Any) -> tuple[Path, Any]:
    """Register one real document version through the real registry writer."""
    from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

    source_path = _create_source_fixture()
    registration = PostgresRegistryWriter(writer_conn).register_document(
        source_path=source_path,
        source_uri=_SOURCE_URI,
        title=_FIXTURE_TITLE,
    )
    return source_path, registration


def _span_retired_state(desired: Any) -> Any:
    """Return the foundation state with the single span and its links retired.

    Chunk, tree node, entity, ownership, and sync rows are retained (minimal
    span removal).
    """
    from dataclasses import replace

    return replace(
        desired,
        canonical_spans=(),
        vector_chunk_span_links=(),
        tree_node_span_links=(),
        evidence_objects=(),
        evidence_links=(),
    )


def _run_c7r_impl(session: Any) -> C7RStaleDeletionObservations:
    """Run the C7R stale span deletion cell (details in the module docstring)."""
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    source_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    second_primary_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        source_path, registration = _register_single_document(writer_conn)
        desired_a = _build_foundation_desired_state(registration, source_path)
        primary_conn = _open_reconciler_primary_connection(session)
        result_a = E2aReconciler().reconcile(primary_conn, desired_a)

        span_id = str(desired_a.canonical_spans[0].span_id)
        chunk_id = str(desired_a.vector_chunks[0]["chunk_id"])
        node_id = str(desired_a.tree_nodes[0]["node_id"])
        desired_b = _span_retired_state(desired_a)

        second_primary_conn = _open_reconciler_primary_connection(session)
        result_b = E2aReconciler().reconcile(second_primary_conn, desired_b)
        sparse_exact = result_b.stale_deletion_counts == {
            "tree_node_spans": 1,
            "vector_chunk_spans": 1,
            "evidence": 1,
            "canonical_spans": 1,
        }
        evidence_links_absent = "evidence_links" not in result_b.stale_deletion_counts

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT COUNT(*) FROM canonical_spans WHERE span_id = %s", (span_id,)
        )
        canonical_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM tree_node_spans WHERE span_id = %s", (span_id,)
        )
        node_span_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM vector_chunk_spans WHERE span_id = %s", (span_id,)
        )
        chunk_span_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM vector_chunks WHERE chunk_id = %s", (chunk_id,)
        )
        chunk_retained = observer_cursor.fetchone() == (1,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM tree_nodes WHERE node_id = %s", (node_id,)
        )
        node_retained = observer_cursor.fetchone() == (1,)
        retained_intact = chunk_retained and node_retained

        return C7RStaleDeletionObservations(
            first_outcome=result_a.outcome,
            second_outcome=result_b.outcome,
            stale_map_exact_sparse=sparse_exact,
            evidence_links_key_absent=evidence_links_absent,
            canonical_span_absent=canonical_absent,
            tree_node_span_absent=node_span_absent,
            vector_chunk_span_absent=chunk_span_absent,
            retained_intact=retained_intact,
        )
    except Exception as failure:
        return C7RStaleDeletionObservations(
            success=False,
            error_reason=_error_reason("c7r_stale_span_deletion_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)
