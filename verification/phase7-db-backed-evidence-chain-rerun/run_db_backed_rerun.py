"""Run Phase 7 DB-backed evidence-chain rerun with blocked fallbacks.

Loads the repository-root `.env` file before DB access and writes only sanitized
rerun artifacts; raw connection strings are never serialized.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env before database access (follows verification script convention)
from dotenv import load_dotenv  # noqa: E402

env_path = REPO_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

import psycopg  # noqa: E402

sys.path.insert(0, str(REPO_ROOT))

from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402

LOGGER = logging.getLogger(__name__)
PHASE7_DIR = Path(__file__).parent
PHASE5_DIR = REPO_ROOT / "verification" / "phase5-evidence-chain-verification"
COUNTS_MODULE_PATH = PHASE5_DIR / "verify_active_version_counts.py"
READINESS_FILE = PHASE7_DIR / "db_readiness.json"
BEFORE_FILE = PHASE7_DIR / "active_version_counts.before.json"
MATERIALIZATION_FILE = PHASE7_DIR / "vector_loader_materialization.json"
AFTER_FILE = PHASE7_DIR / "active_version_counts.after.json"


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
    """Parse an explicit version UUID before database work starts."""
    try:
        return uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid version_id: {value}") from exc


def load_readiness(path: Path = READINESS_FILE) -> dict[str, object]:
    """Load the readiness artifact, returning a blocked shape if absent."""
    if not path.exists():
        return {
            "database_url_configured": False,
            "connection_status": "readiness_missing",
            "active_version_id": None,
            "ready_for_materialization": False,
            "blocking_reasons": ["db_readiness_missing"],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )


def _blocking_reasons(readiness: dict[str, object]) -> list[str]:
    reasons = readiness.get("blocking_reasons", [])
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons]
    return [str(reasons)]


def write_blocked_artifact(
    path: Path,
    readiness: dict[str, object],
    stage: str,
) -> dict[str, object]:
    """Write a stage artifact when DB readiness blocks materialization."""
    payload: dict[str, object] = {
        "status": "blocked",
        "stage": stage,
        "active_version_id": readiness.get("active_version_id"),
        "database_url_configured": bool(readiness.get("database_url_configured")),
        "blocking_reasons": _blocking_reasons(readiness),
    }
    _write_json(path, payload)
    return payload


def _resolve_version_id(
    readiness: dict[str, object],
    explicit_version_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if explicit_version_id is not None:
        return explicit_version_id
    value = readiness.get("active_version_id")
    if value is None or value == "":
        return None
    return uuid.UUID(str(value))


def _write_all_blocked(readiness: dict[str, object]) -> dict[str, object]:
    before = write_blocked_artifact(BEFORE_FILE, readiness, "before_counts")
    materialization = write_blocked_artifact(
        MATERIALIZATION_FILE,
        readiness,
        "vector_materialization",
    )
    after = write_blocked_artifact(AFTER_FILE, readiness, "after_counts")
    return {"before": before, "materialization": materialization, "after": after}


def run_rerun(version_id: uuid.UUID | None = None) -> dict[str, object]:
    """Run before counts, vector materialization, and after counts for one version."""
    readiness = load_readiness()
    if readiness.get("ready_for_materialization") is not True:
        return {"status": "blocked", **_write_all_blocked(readiness)}

    target_version_id = _resolve_version_id(readiness, version_id)
    if target_version_id is None:
        blocked = {**readiness, "blocking_reasons": ["active_version_missing"]}
        return {"status": "blocked", **_write_all_blocked(blocked)}

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        blocked = {**readiness, "blocking_reasons": ["database_url_not_configured"]}
        return {"status": "blocked", **_write_all_blocked(blocked)}

    counts_module = _load_counts_module()
    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            before = counts_module.compute_active_version_counts(
                conn, target_version_id
            )
            _write_json(BEFORE_FILE, before)

            loader_result = VectorLoader(embed_dim=16).load(conn, target_version_id)
            after = counts_module.compute_active_version_counts(conn, target_version_id)
            changed = before.get("stats") != after.get("stats")
            materialization = {
                "status": "completed",
                "active_version_id": str(target_version_id),
                "loader_result": loader_result,
                "changed": changed,
            }
            _write_json(MATERIALIZATION_FILE, materialization)
            _write_json(AFTER_FILE, after)
    except psycopg.OperationalError as exc:
        LOGGER.warning(
            "Phase 7 DB-backed rerun connection failed: %s", type(exc).__name__
        )
        blocked = {**readiness, "blocking_reasons": ["connection_failed"]}
        return {"status": "blocked", **_write_all_blocked(blocked)}
    except psycopg.Error as exc:
        LOGGER.warning("Phase 7 DB-backed rerun database error: %s", type(exc).__name__)
        blocked = {**readiness, "blocking_reasons": ["database_error"]}
        return {"status": "blocked", **_write_all_blocked(blocked)}

    return {
        "status": "completed",
        "active_version_id": str(target_version_id),
        "before_file": str(BEFORE_FILE),
        "materialization_file": str(MATERIALIZATION_FILE),
        "after_file": str(AFTER_FILE),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 7 DB-backed rerun.")
    parser.add_argument(
        "--version-id", help="Explicit version UUID; defaults to readiness target."
    )
    return parser


def main() -> int:
    """CLI entry point for Phase 7 before/materialization/after rerun."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    try:
        explicit_version_id = (
            parse_version_id(args.version_id) if args.version_id is not None else None
        )
    except ValueError as exc:
        readiness = {
            "database_url_configured": bool(os.getenv("DATABASE_URL")),
            "active_version_id": None,
            "blocking_reasons": ["invalid_version_id"],
        }
        _write_all_blocked(readiness)
        print(str(exc), file=sys.stderr)
        return 2

    result = run_rerun(explicit_version_id)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())