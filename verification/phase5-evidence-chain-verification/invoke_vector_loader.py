"""Invoke VectorLoader materialization for the active version.

Phase 5 uses this as an explicit, idempotent checkpoint between tree/span
materialization and retrieval validation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.vector.loader import VectorLoader

OUTPUT_DIR = Path(__file__).parent
COUNTS_MODULE_PATH = OUTPUT_DIR / "verify_active_version_counts.py"
OUTPUT_FILE = OUTPUT_DIR / "vector_loader_materialization.json"


def _load_counts_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "phase5_verify_active_version_counts",
        COUNTS_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {COUNTS_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_version_id(value: str) -> uuid.UUID:
    """Parse a user-supplied version UUID before any database mutation."""
    try:
        return uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid version_id: {value}") from exc


def resolve_latest_active_version_id(conn: psycopg.Connection) -> uuid.UUID | None:
    """Resolve the most recent active document version."""
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


def materialize_chunks_for_version(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
) -> dict[str, object]:
    """Run VectorLoader.load and capture before/after active-version counts."""
    counts_module = _load_counts_module()
    before = counts_module.compute_active_version_counts(conn, version_id)
    loader_result = VectorLoader(embed_dim=16).load(conn, version_id)
    after = counts_module.compute_active_version_counts(conn, version_id)
    changed = before.get("stats") != after.get("stats")

    report: dict[str, object] = {
        "active_version_id": str(version_id),
        "before": before,
        "loader_result": loader_result,
        "after": after,
        "changed": changed,
    }
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize vector chunks for an active document version."
    )
    parser.add_argument("--version-id", help="Explicit version UUID; defaults to latest active.")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        explicit_version_id = (
            parse_version_id(args.version_id) if args.version_id is not None else None
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not configured", file=sys.stderr)
        return 1

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            version_id = explicit_version_id or resolve_latest_active_version_id(conn)
            if version_id is None:
                print("No active version found", file=sys.stderr)
                return 1
            report = materialize_chunks_for_version(conn, version_id)
    except psycopg.Error as exc:
        print(f"Connection failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
