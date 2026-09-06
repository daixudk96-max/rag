"""Phase 8 matched retrieval and judgment-template generator.

This runner is isolated from Phase 3/4 artifacts. It generates fresh retrieval
rows and a placeholder-only judgment template from the Phase 8 preflight active
version. It writes sanitized blocker metadata when any entry gate fails.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

import psycopg

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.backend_adapter import BackendHit
from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend

PHASE8_DIR = Path(__file__).parent
PREFLIGHT_FILE = PHASE8_DIR / "phase8_preflight_status.json"
VALIDATION_STATUS_FILE = PHASE8_DIR / "validation_status.json"
RETRIEVAL_RESULTS_FILE = PHASE8_DIR / "retrieval_results.json"
JUDGMENT_TEMPLATE_FILE = PHASE8_DIR / "judgment_template.csv"
BUSINESS_QUERIES_FILE = (
    REPO_ROOT / "verification" / "phase3-real-validation" / "business_queries.py"
)
TOP_K = 5
EXPECTED_QUERY_COUNT = 20
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
REQUIREMENT_ID = "REQ-P8-MATCHED-VALIDATION-RERUN"
READY_STATUS = "MATCHED_RETRIEVAL_READY"
BLOCKED_STATUS = "MATCHED_RETRIEVAL_BLOCKED"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write a JSON object with UTF-8 encoding."""
    PHASE8_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_preflight() -> dict[str, object]:
    """Load Phase 8 preflight status."""
    if not PREFLIGHT_FILE.exists():
        return {}
    try:
        payload = json.loads(PREFLIGHT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def ensure_preflight_ready(preflight: dict[str, object]) -> None:
    """Raise when Phase 8 preflight has not allowed retrieval."""
    if preflight.get("ready_for_matched_validation") is not True:
        raise RuntimeError("preflight_not_ready")
    if preflight.get("next_allowed_action") != "run_matched_retrieval":
        raise RuntimeError("preflight_not_ready")
    if not preflight.get("active_version_id"):
        raise RuntimeError("active_version_id_missing")


def _connect_timeout_seconds() -> int:
    """Return DB connection timeout from env with a safe default."""
    raw_timeout = os.getenv("PHASE8_DB_CONNECT_TIMEOUT_SECONDS", "")
    if not raw_timeout:
        return DEFAULT_CONNECT_TIMEOUT_SECONDS
    try:
        timeout = int(raw_timeout)
    except ValueError:
        return DEFAULT_CONNECT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_CONNECT_TIMEOUT_SECONDS


def check_database_connection() -> dict[str, object]:
    """Return sanitized database connection readiness metadata."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return {
            "database_url_configured": False,
            "connection_status": "not_configured",
            "blocking_reasons": ["database_url_not_configured"],
        }

    try:
        with psycopg.connect(
            db_url, connect_timeout=_connect_timeout_seconds()
        ) as conn:
            registry = PostgresRegistryWriter(conn)
            healthy = registry.healthcheck()
    except psycopg.OperationalError:
        return {
            "database_url_configured": True,
            "connection_status": "connection_failed",
            "blocking_reasons": ["connection_failed"],
        }

    return {
        "database_url_configured": True,
        "connection_status": "connected" if healthy else "healthcheck_failed",
        "blocking_reasons": [] if healthy else ["healthcheck_failed"],
    }


def _load_business_queries_module() -> ModuleType:
    """Load the Phase 3 business-query module from its script path."""
    spec = importlib.util.spec_from_file_location(
        "phase3_business_queries", BUSINESS_QUERIES_FILE
    )
    if spec is None or spec.loader is None:
        raise ImportError("business_queries_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hit_to_row(hit: BackendHit, rank: int) -> dict[str, object]:
    """Convert a BackendHit into a serializable retrieval row."""
    return {
        "rank": rank,
        "node_id": str(hit.node_id),
        "chunk_id": str(hit.chunk_id) if hit.chunk_id is not None else None,
        "span_ids": [str(span_id) for span_id in hit.span_ids],
        "heading_path": hit.heading_path,
        "page_no": hit.page_no,
        "text_preview": hit.text_preview,
        "score": hit.score,
        "backend_source": hit.backend_source,
        "retrieval_path": hit.retrieval_path,
    }


def _retrieval_failure_payload(query: object, exc: Exception) -> dict[str, object]:
    """Build a sanitized fail-closed retrieval failure payload."""
    return {
        "query_id": str(getattr(query, "query_id", "")),
        "query_text": str(getattr(query, "query_text", "")),
        "category": str(getattr(query, "category", "")),
        "expected_answer_type": str(getattr(query, "expected_answer_type", "")),
        "difficulty": str(getattr(query, "difficulty", "")),
        "hit_count": 0,
        "hits": [],
        "status": "failed",
        "failure_type": type(exc).__name__,
    }


def execute_retrieval_for_queries(
    version_id: uuid.UUID, registry: PostgresRegistryWriter
) -> list[dict[str, object]]:
    """Execute reasoning retrieval for the Phase 3 20-query business set."""
    query_module = _load_business_queries_module()
    queries = list(query_module.ALL_BUSINESS_QUERIES)
    backend = ReasoningTreeBackend()
    results: list[dict[str, object]] = []

    for query in queries:
        query_id = str(query.query_id)
        query_text = str(query.query_text)
        try:
            hits = backend.retrieve_tree_hits(
                query_text=query_text,
                version_id=version_id,
                registry=registry,
                limit=TOP_K,
            )
            hit_rows = [_hit_to_row(hit, index + 1) for index, hit in enumerate(hits)]
            results.append(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "category": str(query.category),
                    "expected_answer_type": str(query.expected_answer_type),
                    "difficulty": str(query.difficulty),
                    "hit_count": len(hit_rows),
                    "hits": hit_rows,
                    "status": "completed",
                }
            )
        except (RuntimeError, ValueError, TypeError) as exc:
            # Fail closed per query while preserving only a sanitized exception type.
            results.append(_retrieval_failure_payload(query, exc))

    return results


def _validated_hit_rows(query_result: dict[str, object]) -> list[dict[str, object]]:
    """Return validated hit rows from a retrieval result."""
    hits = query_result.get("hits", [])
    if not isinstance(hits, list):
        raise ValueError("retrieval_hits_invalid")
    valid_hits: list[dict[str, object]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            raise ValueError("retrieval_hit_invalid")
        for field in ("rank", "node_id"):
            if field not in hit:
                raise ValueError("retrieval_hit_invalid")
        try:
            uuid.UUID(str(hit["node_id"]))
        except ValueError as exc:
            raise ValueError("retrieval_node_id_invalid_uuid") from exc
        valid_hits.append(hit)
    return valid_hits


def generate_judgment_template(retrieval_results: list[dict[str, object]]) -> str:
    """Generate placeholder-only CSV text for human relevance judgment."""
    fieldnames = [
        "query_id",
        "hit_rank",
        "node_id",
        "heading_path",
        "page_no",
        "text_preview",
        "is_relevant",
        "relevance_score",
        "judgment_category",
        "judgment_notes",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for query_result in retrieval_results:
        hits = _validated_hit_rows(query_result)
        for hit in hits:
            writer.writerow(
                {
                    "query_id": query_result.get("query_id", ""),
                    "hit_rank": hit.get("rank", ""),
                    "node_id": hit.get("node_id", ""),
                    "heading_path": hit.get("heading_path") or "",
                    "page_no": (
                        hit.get("page_no") if hit.get("page_no") is not None else "N/A"
                    ),
                    "text_preview": hit.get("text_preview") or "",
                    "is_relevant": "True/False",
                    "relevance_score": "0.00",
                    "judgment_category": "<category>",
                    "judgment_notes": "<notes>",
                }
            )
    return output.getvalue()


def write_blocked_outputs(reason: str, details: dict[str, object]) -> int:
    """Write fail-closed retrieval status artifacts."""
    blocking_reasons = details.get("blocking_reasons")
    if not isinstance(blocking_reasons, list) or not blocking_reasons:
        blocking_reasons = [reason]
    status = {
        "requirement_id": REQUIREMENT_ID,
        "status": BLOCKED_STATUS,
        "validation_date": _utc_now(),
        "query_count_expected": EXPECTED_QUERY_COUNT,
        "query_count_completed": 0,
        "total_hit_rows": 0,
        "retrieval_failures": 0,
        "blocking_reasons": list(dict.fromkeys(str(item) for item in blocking_reasons)),
        "details": details,
        "next_allowed_action": "fix_blockers_before_integrity_gate",
        "level_baseline": "Level 2 remains authoritative",
    }
    _write_json(VALIDATION_STATUS_FILE, status)
    return 1


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 8 matched retrieval.")
    parser.add_argument("--version-id", type=str, default=None)
    return parser


def main() -> int:
    """CLI entry point for Phase 8 matched retrieval."""
    args = _build_arg_parser().parse_args()
    preflight = load_preflight()
    try:
        ensure_preflight_ready(preflight)
    except RuntimeError as exc:
        return write_blocked_outputs(str(exc), {"blocking_reasons": [str(exc)]})

    db_status = check_database_connection()
    db_blockers = db_status.get("blocking_reasons", [])
    if isinstance(db_blockers, list) and db_blockers:
        return write_blocked_outputs(str(db_blockers[0]), db_status)

    version_text = str(args.version_id or preflight.get("active_version_id") or "")
    try:
        version_id = uuid.UUID(version_text)
    except ValueError:
        return write_blocked_outputs(
            "active_version_id_invalid",
            {"blocking_reasons": ["active_version_id_invalid"]},
        )

    db_url = os.getenv("DATABASE_URL", "")
    try:
        with psycopg.connect(
            db_url, connect_timeout=_connect_timeout_seconds()
        ) as conn:
            registry = PostgresRegistryWriter(conn)
            results = execute_retrieval_for_queries(version_id, registry)
    except psycopg.OperationalError:
        return write_blocked_outputs(
            "connection_failed",
            {
                "database_url_configured": bool(db_url),
                "blocking_reasons": ["connection_failed"],
            },
        )

    completed = [result for result in results if result.get("status") == "completed"]
    failures = [result for result in results if result.get("status") != "completed"]
    total_hit_rows = sum(int(result.get("hit_count") or 0) for result in results)
    retrieval_payload = {
        "requirement_id": REQUIREMENT_ID,
        "validation_date": _utc_now(),
        "version_id": str(version_id),
        "query_count": len(results),
        "top_k": TOP_K,
        "results": results,
    }
    _write_json(RETRIEVAL_RESULTS_FILE, retrieval_payload)
    JUDGMENT_TEMPLATE_FILE.write_text(
        generate_judgment_template(results),
        encoding="utf-8",
        newline="",
    )

    status = (
        READY_STATUS
        if len(completed) == EXPECTED_QUERY_COUNT and not failures
        else BLOCKED_STATUS
    )
    blockers = [] if status == READY_STATUS else ["retrieval_failures_present"]
    validation_status = {
        "requirement_id": REQUIREMENT_ID,
        "status": status,
        "validation_date": retrieval_payload["validation_date"],
        "active_version_id": str(version_id),
        "query_count_expected": EXPECTED_QUERY_COUNT,
        "query_count_completed": len(completed),
        "total_hit_rows": total_hit_rows,
        "retrieval_failures": len(failures),
        "blocking_reasons": blockers,
        "next_allowed_action": (
            "run_integrity_gate" if status == READY_STATUS else "rerun_retrieval"
        ),
        "level_baseline": "Level 2 remains authoritative",
    }
    _write_json(VALIDATION_STATUS_FILE, validation_status)
    print(json.dumps(validation_status, indent=2, ensure_ascii=False))
    return 0 if status == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
