"""Private support module for E2a desired-state building and state observation.

Task #87: This module owns the desired-state builders and the digest/count
helpers. Docker and connection lifecycle live in
``_real_e2a_reconciler_lifecycle``; the live acceptance suite and the
mechanical in-process authorization tests both consume this module.

Design:
- Immutable builders that return new ``E2aDesiredState`` instances; no
  mutation of the original.
- All state observation is per-connection and restricted to a single
  ``version_id`` scope.
- Denylist is a frozen set with existence-aware proof: absent tables are
  recorded as ``None`` (zero-capability) rather than fabricated counts.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

import psycopg
from psycopg import sql

from llamaindex_runtime.okf.e2a_contracts import (
    E2aDesiredState,
    E2aParent,
    E2aReconciliationResult,
    E2aSpan,
    Outcome,  # Production reconciliation Outcome
    canonical_json_sha256,
)
from scripts._rebuild_database_connection import DisposablePostgresqlTarget

from ._real_e2a_reconciler_lifecycle import (
    _open_verification_connection,
)

# Stale-deletion tables (closed set from e2a_materialization_repository)
_STALE_DELETION_TABLES = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
        "tree_nodes",
        "tree_node_spans",
        "entities",
        "relations",
        "evidence",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_manual_evidence_targets",
        "okf_sync_state",
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)

# Cache invalidation tables (exact production contract from e2a_contracts._E2A_CACHE_TABLES)
_CACHE_INVALIDATION_TABLES = frozenset(
    {
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)

# =============================================================================
# Tables and digest key map
# =============================================================================

# Tables the E2a contract populates from a minimal desired state.
# Used for counting rows in acceptance tests.
_PRIMARY_TABLES = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
        "tree_nodes",
        "tree_node_spans",
        "okf_sync_state",
    }
)
# Complete primary-table set from e2a_materialization_repository for result assertions.
_REPOSITORY_PRIMARY_TABLES = frozenset(
    {
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
        "tree_nodes",
        "tree_node_spans",
        "entities",
        "relations",
        "evidence",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_manual_evidence_targets",
        "okf_sync_state",
        "summaries",
        "node_embeddings",
        "semantic_distribution",
    }
)
_MAPPING_TABLES = frozenset({"vector_chunk_spans", "tree_node_spans"})
# Production denylist from e2a_contracts._E2A_DENYLIST_TABLES - authoritative.
# Existence-aware proof: tables absent from the schema are recorded as None.
_DENYLIST_TABLES = frozenset(
    {
        "chunk_entity_links",
        "node_entity_links",
        "entity_mentions",
        "entity_aliases",
        "entity_merge_log",
        "ner_entities",
        "ner_relations",
        "fusion_state",
        "r3_state",
        "external_projection_status",
    }
)
_SCOPED_PRIMARY_TABLES = frozenset(
    {"canonical_spans", "vector_chunks", "tree_nodes", "okf_sync_state"}
)
_TIMESTAMP_COLUMNS: dict[str, str] = {
    "canonical_spans": "created_at",
    "vector_chunks": "created_at",
    "tree_nodes": "created_at",
    "okf_sync_state": "last_synced_at",
}

# Digest key columns chosen so re-running with identical desired state produces
# the same digest and a no_op result.
_DIGEST_KEYS: dict[str, tuple[str, ...]] = {
    "canonical_spans": ("span_id", "version_id", "start_offset", "end_offset"),
    "vector_chunks": ("chunk_id", "version_id", "node_id"),
    "vector_chunk_spans": ("chunk_id", "span_id"),
    "tree_nodes": ("node_id", "version_id", "level_no", "title"),
    "tree_node_spans": ("node_id", "span_id"),
    "okf_sync_state": (
        "okf_file_path",
        "version_id",
        "status",
        "materialization_owner",
    ),
}


# =============================================================================
# Parent registration (real documents/document_versions rows)
# =============================================================================


def _register_parent(
    target: DisposablePostgresqlTarget, doc_id: str, version_id: str
) -> None:
    """Insert real documents + document_versions rows on a verification conn.

    Uses a deterministic SHA-256 content hash for reproducibility.
    """
    import hashlib

    content = f"task87:{doc_id}:{version_id}"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    conn = _open_verification_connection(target)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO documents (doc_id) VALUES (%s) "
                "ON CONFLICT (doc_id) DO NOTHING",
                (doc_id,),
            )
            cursor.execute(
                "INSERT INTO document_versions "
                "(version_id, doc_id, content_hash, version_no, is_active, status) "
                "VALUES (%s, %s, %s, 1, TRUE, 'active') "
                "ON CONFLICT (version_id) DO NOTHING",
                (version_id, doc_id, content_hash),
            )
    finally:
        conn.close()


# =============================================================================
# Desired-state builders (immutable)
# =============================================================================


def _build_manifest(
    doc_id: str, version_id: str, relpath: str, canonical_hash: str
) -> dict[str, Any]:
    """Construct the minimal corpus manifest for a single document."""
    return {
        "schema": "e2a-corpus-v1",
        "artifacts": [
            {
                "kind": "raw_pair",
                "path": relpath,
                "identity": f"{doc_id}:{version_id}",
                "canonical_hash": canonical_hash,
            }
        ],
    }


def _build_parent(
    doc_id: str, version_id: str, relpath: str, canonical_hash: str
) -> E2aParent:
    """Construct a single E2aParent with the supplied artifact hash."""
    return E2aParent(
        document_id=doc_id,
        version_id=version_id,
        relative_path=relpath,
        canonical_hash=canonical_hash,
    )


def _build_span(doc_id: str, version_id: str, span_id: str, text: str) -> E2aSpan:
    """Construct a single canonical span at offset 0."""
    return E2aSpan(
        document_id=doc_id,
        version_id=version_id,
        span_id=span_id,
        offset=0,
        text=text,
    )


def _build_tree_node(node_id: str, version_id: str, level_no: int, title: str) -> dict:
    """Build a minimal tree node dict."""
    return {
        "node_id": node_id,
        "version_id": version_id,
        "parent_node_id": None,
        "node_type": "section",
        "level_no": level_no,
        "title": title,
        "heading_path": title,
        "page_start": 1,
        "page_end": 1,
        "summary_text": None,
    }


def _build_chunk(
    chunk_id: str, version_id: str, node_id: str, text: str, chunk_order: int = 0
) -> dict:
    """Build a minimal vector chunk with deterministic embedding."""
    return {
        "chunk_id": chunk_id,
        "version_id": version_id,
        "chunk_type": "canonical_span",
        "chunk_order": chunk_order,
        "token_count": 5,
        "text_preview": text,
        "page_no": 1,
        "heading_path": "Test",
        "node_id": node_id,
        "embedding": [0.0] * 16,
    }


def _build_sync_row(
    relpath: str, doc_id: str, version_id: str, canonical_hash: str
) -> dict:
    """Build a single okf_sync_state row tied to the artifact hash."""
    return {
        "okf_file_path": relpath,
        "doc_id": doc_id,
        "version_id": version_id,
        "source_checksum": "0" * 64,
        "canonical_hash": canonical_hash,
        "status": "materialized",
        "materialization_owner": "e2a",
    }


def _build_desired(
    doc_id: str,
    version_id: str,
    *,
    canonical_hash: str,
    relpath: str,
    span_text: str,
    span_id: str,
    chunk_id: str,
    node_id: str,
) -> E2aDesiredState:
    """Build a non-empty E2aDesiredState with full link/sync closure."""
    manifest = _build_manifest(doc_id, version_id, relpath, canonical_hash)
    parent = _build_parent(doc_id, version_id, relpath, canonical_hash)
    span = _build_span(doc_id, version_id, span_id, span_text)
    node = _build_tree_node(node_id, version_id, 0, "Test Section")
    chunk = _build_chunk(chunk_id, version_id, node_id, span_text)
    sync_row = _build_sync_row(relpath, doc_id, version_id, canonical_hash)
    return E2aDesiredState(
        corpus_manifest=MappingProxyType(manifest),
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=(span,),
        vector_chunks=(chunk,),
        vector_chunk_span_links=(
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ),
        tree_nodes=(node,),
        tree_node_span_links=(
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0},
        ),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=(sync_row,),
        validation_metadata=MappingProxyType({"test": "real_acceptance"}),
        provenance_metadata=MappingProxyType({"authority": "task87"}),
    )


def _mutated_desired(
    original: E2aDesiredState,
    *,
    doc_id: str,
    version_id: str,
    relpath: str,
    span_id_added: str,
    chunk_id_added: str,
    new_canonical_hash: str,
) -> E2aDesiredState:
    """Build a fully valid second desired state whose manifest SHA differs."""
    manifest = _build_manifest(doc_id, version_id, relpath, new_canonical_hash)
    parent = _build_parent(doc_id, version_id, relpath, new_canonical_hash)
    new_span = _build_span(doc_id, version_id, span_id_added, "mutated text content")
    new_node_id = str(uuid4())
    new_node = _build_tree_node(new_node_id, version_id, 1, "Test Mutated Section")
    new_chunk = _build_chunk(
        chunk_id_added, version_id, new_node_id, "mutated text content", chunk_order=1
    )
    updated_sync: tuple[dict[str, str], ...] = tuple(
        dict(row, canonical_hash=new_canonical_hash) for row in original.sync_state_rows
    )
    return E2aDesiredState(
        corpus_manifest=MappingProxyType(manifest),
        corpus_manifest_sha256=canonical_json_sha256(manifest),
        parents=(parent,),
        canonical_spans=original.canonical_spans + (new_span,),
        vector_chunks=original.vector_chunks + (new_chunk,),
        vector_chunk_span_links=original.vector_chunk_span_links
        + ({"chunk_id": chunk_id_added, "span_id": span_id_added, "ordinal_no": 1},),
        tree_nodes=original.tree_nodes + (new_node,),
        tree_node_span_links=original.tree_node_span_links
        + ({"node_id": new_node_id, "span_id": span_id_added, "ordinal_no": 0},),
        manual_entities=(),
        manual_relations=(),
        manual_concepts=(),
        evidence_objects=(),
        evidence_links=(),
        ownership_facts=(),
        sync_state_rows=updated_sync,
        validation_metadata=original.validation_metadata,
        provenance_metadata=original.provenance_metadata,
    )


# =============================================================================
# Scope state observation
# =============================================================================


def _count_rows(conn: psycopg.Connection[Any], table: str) -> int:
    """Count rows in a table."""
    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def _max_timestamp(
    conn: psycopg.Connection[Any],
    table: str,
    *,
    version_id: str | None = None,
) -> str | None:
    """Return the maximum timestamp for a table, optionally scoped by version_id.

    For tables in _SCOPED_PRIMARY_TABLES, version_id must be provided to scope
    the query to a specific version.
    """
    column = _TIMESTAMP_COLUMNS.get(table, "created_at")
    if table in _SCOPED_PRIMARY_TABLES:
        if version_id is None:
            raise ValueError(f"version_id required for scoped table: {table}")
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT MAX({}) FROM {} WHERE version_id = %s").format(
                    sql.Identifier(column), sql.Identifier(table)
                ),
                (version_id,),
            )
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] is not None else None
    else:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT MAX({}) FROM {}").format(
                    sql.Identifier(column), sql.Identifier(table)
                )
            )
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] is not None else None


def _table_digest_scoped(
    conn: psycopg.Connection[Any],
    table: str,
    key_columns: tuple[str, ...],
    *,
    version_id: str,
    span_version: str | None = None,
) -> str:
    """Digest of a table's key columns restricted to a single scope."""
    concat_parts: list[sql.Composable] = []
    for i, col in enumerate(key_columns):
        if i > 0:
            concat_parts.append(sql.SQL(" || '|' || "))
        concat_parts.append(sql.SQL("{}::text").format(sql.Identifier(col)))
    concat_expr = sql.SQL("").join(concat_parts)
    order_parts = [sql.SQL("{}").format(sql.Identifier(col)) for col in key_columns]
    order_expr = sql.SQL(", ").join(order_parts)
    if table in _SCOPED_PRIMARY_TABLES:
        where: sql.Composable = sql.SQL("WHERE version_id = %s")
        params: tuple[Any, ...] = (version_id,)
    else:
        where = sql.SQL(
            "WHERE EXISTS (SELECT 1 FROM canonical_spans "
            "WHERE canonical_spans.span_id = {tbl}.span_id "
            "AND canonical_spans.version_id = %s)"
        ).format(tbl=sql.Identifier(table))
        params = (span_version or version_id,)
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "SELECT md5(COALESCE("
                "string_agg({concat_expr}, '|' ORDER BY {order_expr}), '')) "
                "FROM {tbl} {where}"
            ).format(
                concat_expr=concat_expr,
                order_expr=order_expr,
                tbl=sql.Identifier(table),
                where=where,
            ),
            params,
        )
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] else ""


def _scope_snapshot(
    conn: psycopg.Connection[Any], doc_id: str, version_id: str
) -> MappingProxyType[str, str]:
    """Return frozen table-specific digests of state restricted to this scope."""
    return MappingProxyType(
        {
            "canonical_spans": _table_digest_scoped(
                conn,
                "canonical_spans",
                _DIGEST_KEYS["canonical_spans"],
                version_id=version_id,
            ),
            "vector_chunks": _table_digest_scoped(
                conn,
                "vector_chunks",
                _DIGEST_KEYS["vector_chunks"],
                version_id=version_id,
            ),
            "vector_chunk_spans": _table_digest_scoped(
                conn,
                "vector_chunk_spans",
                _DIGEST_KEYS["vector_chunk_spans"],
                version_id="",
                span_version=version_id,
            ),
            "tree_nodes": _table_digest_scoped(
                conn,
                "tree_nodes",
                _DIGEST_KEYS["tree_nodes"],
                version_id=version_id,
            ),
            "tree_node_spans": _table_digest_scoped(
                conn,
                "tree_node_spans",
                _DIGEST_KEYS["tree_node_spans"],
                version_id="",
                span_version=version_id,
            ),
            "okf_sync_state": _table_digest_scoped(
                conn,
                "okf_sync_state",
                _DIGEST_KEYS["okf_sync_state"],
                version_id=version_id,
            ),
        }
    )


def _scope_row_counts(
    conn: psycopg.Connection[Any], doc_id: str, version_id: str
) -> MappingProxyType[str, int]:
    """Count rows for each primary table, restricted to this scope; return frozen mapping."""
    counts: dict[str, int] = {}
    for table in _PRIMARY_TABLES:
        with conn.cursor() as cursor:
            if table in _SCOPED_PRIMARY_TABLES:
                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FROM {} WHERE version_id = %s").format(
                        sql.Identifier(table)
                    ),
                    (version_id,),
                )
            else:
                cursor.execute(
                    sql.SQL(
                        "SELECT COUNT(*) FROM {tbl} m "
                        "WHERE EXISTS (SELECT 1 FROM canonical_spans s "
                        "WHERE s.span_id = m.span_id AND s.version_id = %s)"
                    ).format(tbl=sql.Identifier(table)),
                    (version_id,),
                )
            row = cursor.fetchone()
            counts[table] = int(row[0]) if row else 0
    return MappingProxyType(counts)


def _table_exists(conn: psycopg.Connection[Any], table: str) -> bool:
    """Check if a table exists in the public schema using to_regclass."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (f"public.{table}",),
        )
        row = cursor.fetchone()
        return bool(row and row[0])


def _all_denylist_counts(
    conn: psycopg.Connection[Any],
) -> MappingProxyType[str, int | None]:
    """Count rows in denylist tables that exist; record None for absent tables; return frozen mapping."""
    counts: dict[str, int | None] = {}
    for table in _DENYLIST_TABLES:
        if _table_exists(conn, table):
            counts[table] = _count_rows(conn, table)
        else:
            counts[table] = None
    return MappingProxyType(counts)


def _assert_all_denylist_zero(counts: Mapping[str, int | None]) -> None:
    """Assert exact 10 denylist keys, each zero (if exist) or absent (if not created).

    This proves:
    - Exactly the 10 denylist tables are present as keys
    - Existing tables have exact built-in int count of 0
    - Absent tables have None value
    - No missing keys, no extra keys, no bool values
    """
    # Exact key set
    assert (
        set(counts.keys()) == _DENYLIST_TABLES
    ), f"denylist must have exact 10 keys: {sorted(_DENYLIST_TABLES)}"
    # Validate each value
    for table, status in counts.items():
        if status is None:
            # Absent table - valid
            continue
        # Existing table - must be exact int 0
        assert (
            type(status) is int
        ), f"denylist[{table}] must be exact built-in int, got {type(status).__name__}"
        assert status == 0, f"denylist table {table!r} must be zero, got {status}"


# =============================================================================
# Result assertion
# =============================================================================


def _is_exact_int(value: object) -> bool:
    """Return True only for exact built-in int (reject bool/subclasses)."""
    return type(value) is int


def _assert_full_result_fields(
    result: E2aReconciliationResult,
    expected_outcome: Outcome,
    expected_manifest_sha: str,
) -> None:
    """Assert every E2aReconciliationResult field with exact type checking.

    This proves the repository's full set of primary tables is present (zeros included)
    and all ten denylist keys are present with exact value zero.
    Uses production Outcome from e2a_contracts for expected_outcome contract.

    Success outcomes (changed, no_op):
    - parity is True (exact bool)
    - failure_audit_outcome is None
    - post_rollback_failure_audit_outcome is None
    - reconciliation_required is False
    """
    # Exact type
    assert type(result) is E2aReconciliationResult
    # Exact outcome and manifest
    assert result.outcome == expected_outcome
    assert result.manifest_sha256 == expected_manifest_sha
    # For changed/no_op success, parity must be True (exact)
    if expected_outcome in ("changed", "no_op"):
        assert (
            result.comparator_parity is True
        ), f"success outcome {expected_outcome} requires parity=True"
        assert (
            result.failure_audit_outcome is None
        ), f"success outcome {expected_outcome} requires failure_audit_outcome=None"
        assert (
            result.post_rollback_failure_audit_outcome is None
        ), f"success outcome {expected_outcome} requires post_rollback_audit=None"
        # reconciliation_required must be False for all success outcomes
        assert (
            result.reconciliation_required is False
        ), f"success outcome {expected_outcome} requires reconciliation_required=False"
    else:
        # Failure outcomes
        assert result.comparator_parity in (True, False, None)
        assert isinstance(result.failure_audit_outcome, (str, type(None)))
        assert isinstance(result.post_rollback_failure_audit_outcome, (str, type(None)))
        assert type(result.reconciliation_required) is bool
    # Exact 15 primary keys, each exact built-in nonnegative int
    assert (
        set(result.primary_dml_by_table.keys()) == _REPOSITORY_PRIMARY_TABLES
    ), "primary mapping must include all 15 repository tables"
    for key, value in result.primary_dml_by_table.items():
        assert _is_exact_int(value), f"primary[{key}] must be exact built-in int"
        assert value >= 0, f"primary[{key}] must be nonnegative"
    # Exact 10 denylist keys, each exact built-in int == 0
    assert (
        set(result.denylist_dml_counts.keys()) == _DENYLIST_TABLES
    ), "denylist must include all 10 tables"
    for key, value in result.denylist_dml_counts.items():
        assert _is_exact_int(value), f"denylist[{key}] must be exact built-in int"
        assert value == 0, f"denylist[{key}] must be zero"
    # Stale keys restricted to closed stale-deletion table set with exact nonnegative ints
    assert set(result.stale_deletion_counts.keys()).issubset(
        _STALE_DELETION_TABLES
    ), "stale keys must be subset of stale-deletion tables"
    for key, value in result.stale_deletion_counts.items():
        assert _is_exact_int(value), f"stale[{key}] must be exact built-in int"
        assert value >= 0, f"stale[{key}] must be nonnegative"
    # Cache keys restricted exactly to three cache tables allowlist with exact nonnegative ints
    assert set(result.cache_invalidation_counts.keys()).issubset(
        _CACHE_INVALIDATION_TABLES
    ), "cache keys must be subset of cache tables"
    for key, value in result.cache_invalidation_counts.items():
        assert _is_exact_int(value), f"cache[{key}] must be exact built-in int"
        assert value >= 0, f"cache[{key}] must be nonnegative"


__all__ = [
    "_PRIMARY_TABLES",
    "_MAPPING_TABLES",
    "_DENYLIST_TABLES",
    "_CACHE_INVALIDATION_TABLES",
    "_STALE_DELETION_TABLES",
    "_SCOPED_PRIMARY_TABLES",
    "_TIMESTAMP_COLUMNS",
    "_DIGEST_KEYS",
    "_register_parent",
    "_build_manifest",
    "_build_parent",
    "_build_span",
    "_build_tree_node",
    "_build_chunk",
    "_build_sync_row",
    "_build_desired",
    "_mutated_desired",
    "_count_rows",
    "_max_timestamp",
    "_table_digest_scoped",
    "_scope_snapshot",
    "_scope_row_counts",
    "_table_exists",
    "_all_denylist_counts",
    "_assert_all_denylist_zero",
    "_assert_full_result_fields",
]
