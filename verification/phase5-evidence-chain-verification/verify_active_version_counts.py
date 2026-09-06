"""Active-version evidence-chain diagnostics for Phase 5 validation.

This utility scopes evidence-chain counts to a single active document version so
Phase 5 can distinguish missing materialization from global metric drift.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

OUTPUT_DIR = Path(__file__).parent
OUTPUT_FILE = OUTPUT_DIR / "active_version_counts.json"
MIN_HEADING_PATH_RATE = 0.95


def parse_version_id(value: str) -> uuid.UUID:
    """Parse a user-supplied version UUID, failing before any SQL executes."""
    try:
        return uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid version_id: {value}") from exc


def resolve_latest_active_version_id(conn: psycopg.Connection) -> uuid.UUID | None:
    """Resolve the most recent active document version from the registry."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT version_id
            FROM document_versions
            WHERE is_active = TRUE
            ORDER BY activated_at DESC NULLS LAST,
                     registered_at DESC NULLS LAST,
                     version_no DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if row is None:
        return None
    return uuid.UUID(str(row["version_id"]))


def _stats_from_counts(counts: dict[str, object]) -> dict[str, object]:
    stats = counts.get("stats")
    if isinstance(stats, dict):
        return stats
    return counts


def classify_evidence_chain_state(counts: dict[str, object]) -> str:
    """Classify active-version evidence-chain readiness from count metrics."""
    stats = _stats_from_counts(counts)
    canonical_spans = int(stats.get("canonical_spans") or 0)
    vector_chunks = int(stats.get("vector_chunks") or 0)
    vector_chunks_with_node_id = int(stats.get("vector_chunks_with_node_id") or 0)
    vector_chunk_spans = int(stats.get("vector_chunk_spans") or 0)
    tree_node_spans = int(stats.get("tree_node_spans") or 0)
    heading_path_rate = float(stats.get("heading_path_rate") or 0.0)

    if canonical_spans == 0:
        return "missing_canonical_spans"
    if vector_chunks == 0 or vector_chunk_spans == 0:
        return "missing_vector_materialization"
    if vector_chunks_with_node_id < vector_chunks or tree_node_spans == 0:
        return "missing_node_chunk_mapping"
    if heading_path_rate < MIN_HEADING_PATH_RATE:
        return "missing_heading_paths"
    return "evidence_chain_ready"


def compute_active_version_counts(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
) -> dict[str, object]:
    """Compute version-scoped evidence-chain diagnostics through registry APIs."""
    registry = PostgresRegistryWriter(conn)
    spans = registry.query_spans_by_version(version_id)
    chunks = registry.query_vector_chunks_by_version(version_id)
    vector_chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)
    tree_node_spans = registry.query_tree_node_spans_by_version(version_id)

    canonical_spans = len(spans)
    canonical_spans_with_heading_path = sum(
        1 for span in spans if span.get("heading_path") is not None
    )
    vector_chunks = len(chunks)
    vector_chunks_with_node_id = sum(
        1 for chunk in chunks if chunk.get("node_id") is not None
    )

    stats: dict[str, object] = {
        "canonical_spans": canonical_spans,
        "canonical_spans_with_heading_path": canonical_spans_with_heading_path,
        "heading_path_rate": (
            canonical_spans_with_heading_path / canonical_spans
            if canonical_spans
            else 0.0
        ),
        "vector_chunks": vector_chunks,
        "vector_chunks_with_node_id": vector_chunks_with_node_id,
        "mapped_chunks_rate": (
            vector_chunks_with_node_id / vector_chunks if vector_chunks else 0.0
        ),
        "vector_chunk_spans": len(vector_chunk_spans),
        "tree_node_spans": len(tree_node_spans),
    }
    classification = classify_evidence_chain_state(stats)
    return {
        "active_version_id": str(version_id),
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "data_available": canonical_spans > 0,
        "stats": stats,
        "classification": classification,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute active-version-scoped evidence-chain counts."
    )
    parser.add_argument(
        "--version-id",
        help="Explicit active document version UUID. Defaults to latest active version.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="JSON report path.",
    )
    return parser


def main() -> int:
    """CLI entry point for active-version evidence-chain diagnostics."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        report: dict[str, Any] = {
            "active_version_id": None,
            "database_url_configured": False,
            "data_available": False,
            "stats": {},
            "classification": "missing_canonical_spans",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    try:
        explicit_version_id = (
            parse_version_id(args.version_id) if args.version_id is not None else None
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            version_id = explicit_version_id or resolve_latest_active_version_id(conn)
            if version_id is None:
                report = {
                    "active_version_id": None,
                    "database_url_configured": True,
                    "data_available": False,
                    "stats": {},
                    "classification": "missing_canonical_spans",
                }
            else:
                report = compute_active_version_counts(conn, version_id)
    except psycopg.Error as exc:
        report = {
            "active_version_id": str(explicit_version_id) if explicit_version_id else None,
            "database_url_configured": True,
            "data_available": False,
            "stats": {},
            "classification": "missing_canonical_spans",
            "connection_status": f"Connection failed: {type(exc).__name__}",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("data_available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
