"""Secret-safe DB readiness gate for Phase 7 evidence-chain rerun.

Loads the repository-root `.env` file before DB access and writes only sanitized
readiness metadata to `db_readiness.json`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env before database access (follows verification script convention)
from dotenv import load_dotenv  # noqa: E402

env_path = REPO_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

LOGGER = logging.getLogger(__name__)
PHASE7_DIR = Path(__file__).parent
OUTPUT_FILE = PHASE7_DIR / "db_readiness.json"
TABLES_CHECKED = [
    "document_versions",
    "canonical_spans",
    "vector_chunks",
    "vector_chunk_spans",
    "tree_node_spans",
]


def parse_version_id(value: str) -> uuid.UUID:
    """Parse an explicit version UUID before any database query runs."""
    try:
        return uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid version_id: {value}") from exc


def _base_report() -> dict[str, object]:
    return {
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "connection_status": "not_configured",
        "active_version_id": None,
        "tables_checked": TABLES_CHECKED,
        "ready_for_materialization": False,
        "blocking_reasons": [],
    }


def _write_report(report: dict[str, object], output: Path = OUTPUT_FILE) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _resolve_latest_active_version_id(conn: psycopg.Connection) -> uuid.UUID | None:
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


def build_db_readiness_report(
    version_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """Build a sanitized readiness report without exposing connection secrets."""
    report = _base_report()
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        report["blocking_reasons"] = ["database_url_not_configured"]
        return report

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            active_version_id = version_id or _resolve_latest_active_version_id(conn)
    except psycopg.OperationalError as exc:
        LOGGER.warning("Phase 7 DB readiness connection failed: %s", type(exc).__name__)
        report.update(
            {
                "database_url_configured": True,
                "connection_status": "connection_failed",
                "blocking_reasons": ["connection_failed"],
            }
        )
        return report
    except psycopg.Error as exc:
        LOGGER.warning("Phase 7 DB readiness query failed: %s", type(exc).__name__)
        report.update(
            {
                "database_url_configured": True,
                "connection_status": "database_error",
                "blocking_reasons": ["database_error"],
            }
        )
        return report

    if active_version_id is None:
        report.update(
            {
                "database_url_configured": True,
                "connection_status": "no_active_version",
                "blocking_reasons": ["active_version_missing"],
            }
        )
        return report

    report.update(
        {
            "database_url_configured": True,
            "connection_status": "connected",
            "active_version_id": str(active_version_id),
            "ready_for_materialization": True,
            "blocking_reasons": [],
        }
    )
    return report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Phase 7 DB readiness.")
    parser.add_argument("--version-id", help="Explicit active document version UUID.")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    return parser


def main() -> int:
    """CLI entry point for the secret-safe readiness gate."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        explicit_version_id = (
            parse_version_id(args.version_id) if args.version_id is not None else None
        )
    except ValueError as exc:
        report = _base_report()
        report.update(
            {
                "database_url_configured": bool(os.getenv("DATABASE_URL")),
                "connection_status": "invalid_version_id",
                "blocking_reasons": ["invalid_version_id"],
            }
        )
        _write_report(report, args.output)
        print(str(exc), file=sys.stderr)
        return 2

    report = build_db_readiness_report(explicit_version_id)
    _write_report(report, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ready_for_materialization") else 1


if __name__ == "__main__":
    raise SystemExit(main())