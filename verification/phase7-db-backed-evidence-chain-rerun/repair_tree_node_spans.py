"""Repair missing Phase 7 tree_node_spans from existing spans and tree nodes.

The script reconstructs provenance links by matching canonical span heading paths
to existing tree node heading paths after separator normalization. It writes only
sanitized status metadata and never serializes database connection strings.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env before database access.
env_path = REPO_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402

LOGGER = logging.getLogger(__name__)
PHASE7_DIR = Path(__file__).parent
READINESS_FILE = PHASE7_DIR / "db_readiness.json"
OUTPUT_FILE = PHASE7_DIR / "tree_node_span_repair.json"


def normalize_heading_path(value: object) -> tuple[str, ...]:
    """Normalize tree/span heading paths to comparable path components."""
    if value is None:
        return ("(root)",)
    text = str(value).strip()
    if not text:
        return ("(root)",)
    separator = " > " if " > " in text else "/"
    parts = tuple(part.strip() for part in text.split(separator) if part.strip())
    return parts or ("(root)",)


def load_active_version_id(path: Path = READINESS_FILE) -> uuid.UUID:
    """Load the active version ID selected by the Phase 7 readiness gate."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    version_id = payload.get("active_version_id")
    if not version_id:
        raise ValueError("active_version_id_missing")
    return uuid.UUID(str(version_id))


def read_canonical_spans(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
) -> list[dict[str, object]]:
    """Read canonical spans required for node-span repair."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT span_id, heading_path, start_offset "
            "FROM canonical_spans WHERE version_id = %s ORDER BY start_offset",
            (str(version_id),),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def read_tree_nodes(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
) -> list[dict[str, object]]:
    """Read existing tree nodes required for node-span repair."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT node_id, heading_path, level_no "
            "FROM tree_nodes WHERE version_id = %s ORDER BY level_no, heading_path",
            (str(version_id),),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def build_span_node_mappings(
    *,
    spans: list[dict[str, object]],
    nodes: list[dict[str, object]],
) -> dict[str, object]:
    """Build tree_node_spans rows by normalized heading-path equality."""
    node_by_path: dict[tuple[str, ...], uuid.UUID] = {}
    for node in nodes:
        path = normalize_heading_path(node.get("heading_path"))
        node_by_path[path] = uuid.UUID(str(node["node_id"]))

    ordinals_by_node: dict[uuid.UUID, int] = defaultdict(int)
    mappings: list[dict[str, object]] = []
    unmatched_span_ids: list[uuid.UUID] = []

    sorted_spans = sorted(
        spans,
        key=lambda span: (
            int(span.get("start_offset") or 0),
            str(span.get("span_id") or ""),
        ),
    )
    for span in sorted_spans:
        span_path = normalize_heading_path(span.get("heading_path"))
        node_id = None
        # Nearest-parent fallback: match full span path first, then ancestors.
        for depth in range(len(span_path), 0, -1):
            node_id = node_by_path.get(span_path[:depth])
            if node_id is not None:
                break
        span_id = uuid.UUID(str(span["span_id"]))
        if node_id is None:
            unmatched_span_ids.append(span_id)
            continue
        ordinal = ordinals_by_node[node_id]
        ordinals_by_node[node_id] = ordinal + 1
        mappings.append(
            {
                "node_id": node_id,
                "span_id": span_id,
                "ordinal_no": ordinal,
            }
        )

    return {
        "mappings": mappings,
        "unmatched_span_ids": unmatched_span_ids,
    }


def write_missing_tree_node_spans(
    conn: psycopg.Connection,
    mappings: list[dict[str, object]],
) -> int:
    """Insert missing tree_node_spans rows idempotently."""
    inserted = 0
    with conn.transaction(), conn.cursor() as cur:
        for mapping in mappings:
            cur.execute(
                "INSERT INTO tree_node_spans (node_id, span_id, ordinal_no) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (node_id, span_id) DO NOTHING",
                (
                    str(mapping["node_id"]),
                    str(mapping["span_id"]),
                    mapping["ordinal_no"],
                ),
            )
            inserted += int(cur.rowcount or 0)
    return inserted


def count_linked_chunks(
    conn: psycopg.Connection, version_id: uuid.UUID
) -> dict[str, int]:
    """Count vector chunk mapping readiness for the repaired version."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT COUNT(*) AS total, "
            "COUNT(node_id) AS linked "
            "FROM vector_chunks WHERE version_id = %s",
            (str(version_id),),
        )
        row = cur.fetchone()
    return {
        "vector_chunks": int(row["total"]),
        "vector_chunks_with_node_id": int(row["linked"]),
    }


def write_report(report: dict[str, object], path: Path = OUTPUT_FILE) -> None:
    """Write a sanitized repair report."""
    path.write_text(
        json.dumps(report, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def repair_tree_node_spans() -> dict[str, object]:
    """Repair missing tree_node_spans and rerun vector-node linking."""
    version_id = load_active_version_id()
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return {
            "status": "blocked",
            "active_version_id": str(version_id),
            "database_url_configured": False,
            "blocking_reasons": ["database_url_not_configured"],
        }

    with psycopg.connect(db_url, connect_timeout=10) as conn:
        spans = read_canonical_spans(conn, version_id)
        nodes = read_tree_nodes(conn, version_id)
        mapping_result = build_span_node_mappings(spans=spans, nodes=nodes)
        mappings = mapping_result["mappings"]
        unmatched = mapping_result["unmatched_span_ids"]

        if not spans or not nodes or not mappings or unmatched:
            report = {
                "status": "blocked",
                "active_version_id": str(version_id),
                "database_url_configured": True,
                "spans_seen": len(spans),
                "tree_nodes_seen": len(nodes),
                "mappings_generated": len(mappings),
                "unmatched_span_count": len(unmatched),
                "blocking_reasons": ["tree_node_span_mapping_incomplete"],
            }
            write_report(report)
            return report

        inserted = write_missing_tree_node_spans(conn, mappings)
        loader_result = VectorLoader(embed_dim=16).load(conn, version_id)
        chunk_counts = count_linked_chunks(conn, version_id)
        status = (
            "completed"
            if chunk_counts["vector_chunks"] > 0
            and chunk_counts["vector_chunks_with_node_id"]
            == chunk_counts["vector_chunks"]
            else "partial"
        )
        report = {
            "status": status,
            "active_version_id": str(version_id),
            "database_url_configured": True,
            "spans_seen": len(spans),
            "tree_nodes_seen": len(nodes),
            "mappings_generated": len(mappings),
            "mappings_inserted": inserted,
            "unmatched_span_count": len(unmatched),
            "vector_loader_result": loader_result,
            **chunk_counts,
        }
        write_report(report)
        return report


def main() -> int:
    """CLI entry point for Phase 7 tree-node span repair."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    try:
        report = repair_tree_node_spans()
    except psycopg.OperationalError as exc:
        LOGGER.warning(
            "Tree-node span repair connection failed: %s", type(exc).__name__
        )
        report = {
            "status": "blocked",
            "database_url_configured": bool(os.getenv("DATABASE_URL")),
            "blocking_reasons": ["connection_failed"],
        }
        write_report(report)
    except (json.JSONDecodeError, OSError, ValueError, KeyError) as exc:
        LOGGER.warning("Tree-node span repair failed: %s", type(exc).__name__)
        report = {
            "status": "blocked",
            "database_url_configured": bool(os.getenv("DATABASE_URL")),
            "blocking_reasons": ["repair_input_invalid"],
        }
        write_report(report)

    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
