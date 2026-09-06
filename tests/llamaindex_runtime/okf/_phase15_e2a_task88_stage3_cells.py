"""Live cells for the Task #88 Stage 3 tranche (sibling of the Stage 1/2/2R helpers).

This helper module is never collected by default test name discovery (the
``_`` prefix keeps it out of normal test collection). It provides five
explicitly selected live cells in NEW identities (C7/C8/C9/C10/C12); the
superseded Stage 2 C4/C5 identities are never reused, renamed, or extended
here.

- PARTIAL(C7) stale span deletion: a minimal valid single-parent foundation
  state is materialized, then a second desired state retires the single span
  (its chunk/node/entity/ownership/sync rows are retained). The sparse
  stale-ID count map is asserted exactly and a fresh observer proves the
  committed row-count absence of the stale span id in canonical_spans,
  tree_node_spans, and vector_chunk_spans. Stale-ID counts are
  identifier-set sizes; absence is asserted by committed row counts; the
  cell never equates statement counts with row counts.
- PARTIAL(C8) chunk repoint: the foundation chunk is retained while its tree
  node is replaced by a fresh deterministic repair target (a new root node in
  the same version; ``_tree_repair_targets`` picks roots first, sorted by
  (version_id, node_id)). A fresh observer proves the retained chunk points
  at the expected target and the old node id is absent from tree_nodes.
  Ordering is treated as source-backed program order (repair before stale
  node deletion in the repository) plus post-state, never as observed
  interleaving.
- PARTIAL(C9) cache invalidation: cache rows (summaries, node_embeddings
  with 384-dimensional vectors, semantic_distribution) are seeded only AFTER
  the real tree node exists, on a fresh attested seed connection. The second
  reconcile retires that node and the measured ``cache_invalidation_counts``
  must be exactly 1 per cache table (the production JOIN-based measurement).
  A fresh observer then proves join-free committed post-delete absence per
  cache table; the production JOIN-based measurement query is never used as
  the final absence probe.
- PARTIAL(C10) destructive closure: one real ``entity_mentions`` row is
  seeded against an existing canonical span that the second desired state
  retires. The default ``E2aReconciler()`` (no audit factory) must fail
  closed BEFORE any DML with the exact production-anchored ValueError
  "stale span has entity_mentions dependencies", the primary is closed after
  rollback, and a fresh observer proves the span, its tree-node-span link,
  the mention row, and the parent document/version rows are all intact. This
  simulates a foreign dependency only; it never invokes or claims E2b and is
  never C14 or late-DML evidence.
- PARTIAL(C12) parentless cleanup: a parent-bearing foundation is
  materialized, then a parentless desired state with all collections empty
  and NO global manual facts is reconciled twice. The first run must clean
  every E2a-derived row (spans, links, chunks, nodes, evidence, ownership,
  entities, sync) while the registry document/version rows remain; the
  second run must be an exact no-op (outcome "no_op", zero primary DML,
  empty stale and cache maps). The cell never claims shared-global
  manual-fact preservation and is never C14.

Security contract (identical to the Stage 1/2/2R tranches): no environment
variable access of any kind; no DATABASE_URL anywhere; no URI, credential,
target, container token, or raw fixture content is ever printed, logged,
returned, or included in observation reprs. All connections come from
DisposableE2aSession.open_fresh_attested_connection. The registry writer,
every reconciler primary, every seed, and every observer are separate fresh
attested connections/transactions. Role separation means independent fresh
attested connections/transactions, not distinct PostgreSQL principals; no
principal or security model is implied or changed. Every cursor and
connection is closed in a finally block; the reconciler closes its primary
on success and on failure, and this frame also closes it in a finally path
(the close is idempotent). Failures are absorbed into redacted observations
that carry a bounded class/type-only diagnostic; exception messages, args,
and reprs never leave the helper. No test framework machinery, no skip or
xfail mechanics, no fakes.
"""

from __future__ import annotations

import uuid
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

# Exact production-anchored fail-closed guard raised by
# validate_destructive_closure when entity_mentions references a stale span.
_EXPECTED_ENTITY_MENTIONS_GUARD_MESSAGE = "stale span has entity_mentions dependencies"


class C7StaleDeletionObservations(NamedTuple):
    """Redacted observations for the C7 stale span deletion cell."""

    first_outcome: str = ""
    second_outcome: str = ""
    stale_map_exact_sparse: bool = False
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
        return f"C7StaleDeletionObservations({rendered}, details=<redacted>)"


class C8ChunkRepointObservations(NamedTuple):
    """Redacted observations for the C8 chunk repoint cell."""

    first_outcome: str = ""
    second_outcome: str = ""
    chunk_retained: bool = False
    chunk_repoints_to_expected_target: bool = False
    old_node_absent: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C8ChunkRepointObservations({rendered}, details=<redacted>)"


class C9CacheInvalidationObservations(NamedTuple):
    """Redacted observations for the C9 cache invalidation cell."""

    first_outcome: str = ""
    second_outcome: str = ""
    measured_counts_exact: bool = False
    summary_absent: bool = False
    node_embedding_absent: bool = False
    semantic_distribution_absent: bool = False
    old_node_absent: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C9CacheInvalidationObservations({rendered}, details=<redacted>)"


class C10DestructiveClosureObservations(NamedTuple):
    """Redacted observations for the C10 destructive closure cell."""

    first_outcome: str = ""
    exact_error_match: bool = False
    primary_closed: bool = False
    span_still_present: bool = False
    span_link_still_present: bool = False
    mention_still_present: bool = False
    parent_document_present: bool = False
    parent_version_present: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C10DestructiveClosureObservations({rendered}, details=<redacted>)"


class C12ParentlessCleanupObservations(NamedTuple):
    """Redacted observations for the C12 parentless cleanup cell."""

    first_outcome: str = ""
    cleanup_outcome: str = ""
    second_noop_exact: bool = False
    no_global_manual_facts: bool = False
    canonical_spans_cleaned: bool = False
    vector_chunks_cleaned: bool = False
    tree_nodes_cleaned: bool = False
    evidence_cleaned: bool = False
    ownership_cleaned: bool = False
    sync_cleaned: bool = False
    entities_cleaned: bool = False
    registry_document_retained: bool = False
    registry_version_retained: bool = False
    success: bool = True
    error_reason: str = ""

    def __repr__(self) -> str:
        rendered = ", ".join(
            f"{key}={value!r}"
            for key, value in self._asdict().items()
            if key != "error_reason"
        )
        return f"C12ParentlessCleanupObservations({rendered}, details=<redacted>)"


def _open_seed_connection(session: Any) -> Any:
    """Open the seed role on its own fresh attested connection."""
    return session.open_fresh_attested_connection()


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


def _node_replaced_state(desired: Any, new_node_id: str) -> Any:
    """Replace the single root node with a fresh node id (chunk repoint).

    The retained chunk and the tree-node-span link move to the new node; all
    other rows are unchanged. The new node is a root, so it is the
    deterministic ``_tree_repair_targets`` candidate for the version.
    """
    from dataclasses import replace

    old_node = desired.tree_nodes[0]
    old_node_id = str(old_node["node_id"])
    new_node = dict(old_node)
    new_node["node_id"] = new_node_id
    new_node["parent_node_id"] = None
    nodes = tuple(
        new_node if str(row["node_id"]) == old_node_id else row
        for row in desired.tree_nodes
    )
    node_links = tuple(
        {**row, "node_id": new_node_id} if str(row["node_id"]) == old_node_id else row
        for row in desired.tree_node_span_links
    )
    chunks = tuple(
        {**row, "node_id": new_node_id} if str(row["node_id"]) == old_node_id else row
        for row in desired.vector_chunks
    )
    return replace(
        desired,
        vector_chunks=chunks,
        tree_nodes=nodes,
        tree_node_span_links=node_links,
    )


def _parentless_empty_state() -> Any:
    """Parentless desired state: all collections empty, no global manual facts."""
    from types import MappingProxyType

    from llamaindex_runtime.okf.e2a_contracts import (
        E2aDesiredState,
        canonical_json_sha256,
    )

    manifest = {"schema": "e2a-corpus-v1", "artifacts": []}
    return E2aDesiredState(
        corpus_manifest=manifest,
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(),
        canonical_spans=(),
        vector_chunks=(),
        vector_chunk_span_links=(),
        tree_nodes=(),
        tree_node_span_links=(),
        manual_entities=(),
        manual_relations=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(),
        validation_metadata=MappingProxyType({}),
        provenance_metadata=MappingProxyType({"authority": "okf"}),
    )


def _run_c7_impl(session: Any) -> C7StaleDeletionObservations:
    """Run the C7 stale span deletion cell (details in the module docstring)."""
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
            "evidence_links": 1,
            "evidence": 1,
            "canonical_spans": 1,
        }

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

        return C7StaleDeletionObservations(
            first_outcome=result_a.outcome,
            second_outcome=result_b.outcome,
            stale_map_exact_sparse=sparse_exact,
            canonical_span_absent=canonical_absent,
            tree_node_span_absent=node_span_absent,
            vector_chunk_span_absent=chunk_span_absent,
            retained_intact=retained_intact,
        )
    except Exception as failure:
        return C7StaleDeletionObservations(
            success=False,
            error_reason=_error_reason("c7_stale_span_deletion_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)


def _run_c8_impl(session: Any) -> C8ChunkRepointObservations:
    """Run the C8 chunk repoint cell (details in the module docstring)."""
    from llamaindex_runtime.okf.e2a_materialization_repository import (
        _tree_repair_targets,
    )
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

        old_node_id = str(desired_a.tree_nodes[0]["node_id"])
        chunk_id = str(desired_a.vector_chunks[0]["chunk_id"])
        desired_b = _node_replaced_state(desired_a, str(uuid.uuid4()))

        second_primary_conn = _open_reconciler_primary_connection(session)
        result_b = E2aReconciler().reconcile(second_primary_conn, desired_b)
        version_id = str(registration.version_id)
        expected_target = _tree_repair_targets(desired_b.tree_nodes)[version_id]

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT node_id FROM vector_chunks WHERE chunk_id = %s", (chunk_id,)
        )
        row = observer_cursor.fetchone()
        chunk_target = str(row[0]) if row is not None else ""
        observer_cursor.execute(
            "SELECT COUNT(*) FROM tree_nodes WHERE node_id = %s", (old_node_id,)
        )
        old_node_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM vector_chunks WHERE chunk_id = %s", (chunk_id,)
        )
        chunk_retained = observer_cursor.fetchone() == (1,)

        return C8ChunkRepointObservations(
            first_outcome=result_a.outcome,
            second_outcome=result_b.outcome,
            chunk_retained=chunk_retained,
            chunk_repoints_to_expected_target=chunk_target == expected_target,
            old_node_absent=old_node_absent,
        )
    except Exception as failure:
        return C8ChunkRepointObservations(
            success=False,
            error_reason=_error_reason("c8_chunk_repoint_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)


def _run_c9_impl(session: Any) -> C9CacheInvalidationObservations:
    """Run the C9 cache invalidation cell (details in the module docstring)."""
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    source_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    second_primary_conn: Any = None
    seed_conn: Any = None
    seed_cursor: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        source_path, registration = _register_single_document(writer_conn)
        desired_a = _build_foundation_desired_state(registration, source_path)
        primary_conn = _open_reconciler_primary_connection(session)
        result_a = E2aReconciler().reconcile(primary_conn, desired_a)

        old_node_id = str(desired_a.tree_nodes[0]["node_id"])
        version_id = str(registration.version_id)
        embedding_literal = (
            "[" + ",".join(str(float(index)) for index in range(384)) + "]"
        )
        seed_conn = _open_seed_connection(session)
        seed_cursor = seed_conn.cursor()
        seed_cursor.execute(
            "INSERT INTO summaries (summary_id, version_id, node_id, summary_text) "
            "VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), version_id, old_node_id, "seeded summary"),
        )
        seed_cursor.execute(
            "INSERT INTO node_embeddings (node_id, embedding_model, "
            "embedding_vector) VALUES (%s, %s, %s::vector)",
            (old_node_id, "e2a-stage3-test", embedding_literal),
        )
        seed_cursor.execute(
            "INSERT INTO semantic_distribution (node_id, version_id) "
            "VALUES (%s, %s)",
            (old_node_id, version_id),
        )
        seed_conn.commit()

        desired_b = _node_replaced_state(desired_a, str(uuid.uuid4()))
        second_primary_conn = _open_reconciler_primary_connection(session)
        result_b = E2aReconciler().reconcile(second_primary_conn, desired_b)
        measured_exact = result_b.cache_invalidation_counts == {
            "summaries": 1,
            "node_embeddings": 1,
            "semantic_distribution": 1,
        }

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT COUNT(*) FROM summaries WHERE node_id = %s", (old_node_id,)
        )
        summary_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM node_embeddings WHERE node_id = %s", (old_node_id,)
        )
        embedding_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM semantic_distribution WHERE node_id = %s",
            (old_node_id,),
        )
        distribution_absent = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM tree_nodes WHERE node_id = %s", (old_node_id,)
        )
        old_node_absent = observer_cursor.fetchone() == (0,)

        return C9CacheInvalidationObservations(
            first_outcome=result_a.outcome,
            second_outcome=result_b.outcome,
            measured_counts_exact=measured_exact,
            summary_absent=summary_absent,
            node_embedding_absent=embedding_absent,
            semantic_distribution_absent=distribution_absent,
            old_node_absent=old_node_absent,
        )
    except Exception as failure:
        return C9CacheInvalidationObservations(
            success=False,
            error_reason=_error_reason("c9_cache_invalidation_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(seed_cursor)
        _close_quietly(seed_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)


def _run_c10_impl(session: Any) -> C10DestructiveClosureObservations:
    """Run the C10 destructive closure cell (details in the module docstring)."""
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    source_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    second_primary_conn: Any = None
    seed_conn: Any = None
    seed_cursor: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        source_path, registration = _register_single_document(writer_conn)
        desired_a = _build_foundation_desired_state(registration, source_path)
        primary_conn = _open_reconciler_primary_connection(session)
        result_a = E2aReconciler().reconcile(primary_conn, desired_a)

        span_id = str(desired_a.canonical_spans[0].span_id)
        mention_id = str(uuid.uuid4())
        seed_conn = _open_seed_connection(session)
        seed_cursor = seed_conn.cursor()
        seed_cursor.execute(
            "INSERT INTO entity_mentions (mention_id, entity_id, span_id, "
            "char_start, char_end, mention_text, confidence, source, "
            "okf_file_path, okf_paragraph_id) "
            "VALUES (%s, NULL, %s, 0, 1, %s, NULL, %s, NULL, NULL)",
            (mention_id, span_id, "seeded mention", "okf"),
        )
        seed_conn.commit()

        desired_b = _span_retired_state(desired_a)
        second_primary_conn = _open_reconciler_primary_connection(session)
        failure: Exception | None = None
        try:
            E2aReconciler().reconcile(second_primary_conn, desired_b)
        except Exception as error:
            failure = error
        if failure is None:
            raise ValueError("expected unwrapped destructive-closure ValueError")
        exact_match = isinstance(failure, ValueError) and failure.args == (
            _EXPECTED_ENTITY_MENTIONS_GUARD_MESSAGE,
        )
        primary_closed = bool(second_primary_conn.closed)

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute(
            "SELECT COUNT(*) FROM canonical_spans WHERE span_id = %s", (span_id,)
        )
        span_present = observer_cursor.fetchone() == (1,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM tree_node_spans WHERE span_id = %s", (span_id,)
        )
        link_present = observer_cursor.fetchone() == (1,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM entity_mentions WHERE mention_id = %s",
            (mention_id,),
        )
        mention_present = observer_cursor.fetchone() == (1,)
        doc_id = str(registration.doc_id)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM documents WHERE doc_id = %s", (doc_id,)
        )
        document_present = observer_cursor.fetchone() == (1,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM document_versions WHERE version_id = %s",
            (str(registration.version_id),),
        )
        version_present = observer_cursor.fetchone() == (1,)

        return C10DestructiveClosureObservations(
            first_outcome=result_a.outcome,
            exact_error_match=exact_match,
            primary_closed=primary_closed,
            span_still_present=span_present,
            span_link_still_present=link_present,
            mention_still_present=mention_present,
            parent_document_present=document_present,
            parent_version_present=version_present,
        )
    except Exception as failure:
        return C10DestructiveClosureObservations(
            success=False,
            error_reason=_error_reason("c10_destructive_closure_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(second_primary_conn)
        _close_quietly(seed_cursor)
        _close_quietly(seed_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)


def _run_c12_impl(session: Any) -> C12ParentlessCleanupObservations:
    """Run the C12 parentless cleanup cell (details in the module docstring)."""
    from llamaindex_runtime.okf.e2a_reconciler import E2aReconciler

    source_path: Path | None = None
    writer_conn: Any = None
    primary_conn: Any = None
    cleanup_conn: Any = None
    noop_conn: Any = None
    observer_conn: Any = None
    observer_cursor: Any = None
    try:
        writer_conn = _open_writer_connection(session)
        source_path, registration = _register_single_document(writer_conn)
        desired_a = _build_foundation_desired_state(registration, source_path)
        primary_conn = _open_reconciler_primary_connection(session)
        result_a = E2aReconciler().reconcile(primary_conn, desired_a)

        desired_empty = _parentless_empty_state()
        no_global_facts = (
            not desired_empty.manual_entities
            and not desired_empty.manual_relations
            and not desired_empty.manual_concepts
            and not desired_empty.ownership_facts
        )

        cleanup_conn = _open_reconciler_primary_connection(session)
        cleanup_result = E2aReconciler().reconcile(cleanup_conn, desired_empty)

        noop_conn = _open_reconciler_primary_connection(session)
        noop_result = E2aReconciler().reconcile(noop_conn, desired_empty)
        noop_exact = (
            noop_result.outcome == "no_op"
            and all(value == 0 for value in noop_result.primary_dml_by_table.values())
            and noop_result.stale_deletion_counts == {}
            and noop_result.cache_invalidation_counts == {}
        )

        observer_conn = _open_observer_connection(session)
        observer_cursor = observer_conn.cursor()
        observer_cursor.execute("SELECT COUNT(*) FROM canonical_spans")
        spans_cleaned = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM vector_chunks")
        chunks_cleaned = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM tree_nodes")
        nodes_cleaned = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM evidence")
        evidence_rows = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM evidence_links")
        evidence_links_rows = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM okf_manual_evidence_targets")
        targets_rows = observer_cursor.fetchone() == (0,)
        evidence_cleaned = evidence_rows and evidence_links_rows and targets_rows
        observer_cursor.execute("SELECT COUNT(*) FROM okf_manual_fact_ownership")
        ownership_cleaned = observer_cursor.fetchone() == (0,)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM okf_sync_state " "WHERE materialization_owner = 'e2a'"
        )
        sync_cleaned = observer_cursor.fetchone() == (0,)
        observer_cursor.execute("SELECT COUNT(*) FROM entities")
        entities_cleaned = observer_cursor.fetchone() == (0,)
        doc_id = str(registration.doc_id)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM documents WHERE doc_id = %s", (doc_id,)
        )
        document_retained = observer_cursor.fetchone() == (1,)
        version_id = str(registration.version_id)
        observer_cursor.execute(
            "SELECT COUNT(*) FROM document_versions WHERE version_id = %s",
            (version_id,),
        )
        version_retained = observer_cursor.fetchone() == (1,)

        return C12ParentlessCleanupObservations(
            first_outcome=result_a.outcome,
            cleanup_outcome=cleanup_result.outcome,
            second_noop_exact=noop_exact,
            no_global_manual_facts=no_global_facts,
            canonical_spans_cleaned=spans_cleaned,
            vector_chunks_cleaned=chunks_cleaned,
            tree_nodes_cleaned=nodes_cleaned,
            evidence_cleaned=evidence_cleaned,
            ownership_cleaned=ownership_cleaned,
            sync_cleaned=sync_cleaned,
            entities_cleaned=entities_cleaned,
            registry_document_retained=document_retained,
            registry_version_retained=version_retained,
        )
    except Exception as failure:
        return C12ParentlessCleanupObservations(
            success=False,
            error_reason=_error_reason("c12_parentless_cleanup_cell_failed", failure),
        )
    finally:
        _close_quietly(observer_cursor)
        _close_quietly(observer_conn)
        _close_quietly(noop_conn)
        _close_quietly(cleanup_conn)
        _close_quietly(primary_conn)
        _close_quietly(writer_conn)
        _unlink_quietly(source_path)
