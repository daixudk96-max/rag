"""
Phase 3 Real Quality Validation: Execution Script

This script executes real quality validation using:
1. Real PostgreSQL/pgvector registry data
2. ReasoningTreeBackend with LLM-based retrieval
3. 15-20 real business queries
4. Generate relevance judgment template for manual evaluation

Phase 3 Requirement: Real validation (not fixture-based)

Usage:
    python verification/phase3-real-validation/run_validation.py

Output:
    - validation_status.json: Database connection + validation readiness
    - retrieval_results.json: Top-k hits for each query
    - judgment_template.csv: Template for manual relevance assessment
"""

import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from types import ModuleType

# Add repo root to Python path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env before imports
from dotenv import load_dotenv

env_path = Path.cwd() / ".env"
if env_path.exists():
    load_dotenv(env_path)

import psycopg
from psycopg.rows import dict_row

from llamaindex_runtime.config import RuntimeSettings
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend

# Output directory and constants
OUTPUT_DIR = Path(__file__).parent
TOP_K = 5  # Retrieve top-5 hits per query

# Add OUTPUT_DIR to path for local imports
sys.path.insert(0, str(OUTPUT_DIR))
from business_queries import ALL_BUSINESS_QUERIES


OUTPUT_DIR = Path(__file__).parent
TOP_K = 5  # Retrieve top-5 hits per query

# Add OUTPUT_DIR to path for local imports
sys.path.insert(0, str(OUTPUT_DIR))

PHASE5_DIR = REPO_ROOT / "verification" / "phase5-evidence-chain-verification"
ACTIVE_VERSION_COUNTS_PATH = PHASE5_DIR / "verify_active_version_counts.py"


def _load_active_version_counts_module() -> ModuleType:
    """Load the Phase 5 active-version diagnostics helper from its script path."""
    spec = importlib.util.spec_from_file_location(
        "phase5_verify_active_version_counts",
        ACTIVE_VERSION_COUNTS_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {ACTIVE_VERSION_COUNTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_database_connection() -> dict:
    """Check PostgreSQL database connection and active-version data status."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return {
            "database_url_configured": False,
            "connection_status": "DATABASE_URL not configured",
            "data_available": False,
        }

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            writer = PostgresRegistryWriter(conn)

            if not writer.healthcheck():
                return {
                    "database_url_configured": True,
                    "connection_status": "Healthcheck failed",
                    "data_available": False,
                }

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT COUNT(*) FROM documents")
                doc_count = cur.fetchone()["count"]

                cur.execute(
                    "SELECT COUNT(*) FROM document_versions WHERE is_active = TRUE"
                )
                version_count = cur.fetchone()["count"]

                cur.execute(
                    "SELECT MAX(level_no) FROM tree_nodes WHERE version_id IN "
                    "(SELECT version_id FROM document_versions WHERE is_active = TRUE)"
                )
                max_level = cur.fetchone()["max"] or 0

            counts_module = _load_active_version_counts_module()
            active_version_id = counts_module.resolve_latest_active_version_id(conn)
            active_counts = None
            if active_version_id is not None:
                active_counts = counts_module.compute_active_version_counts(
                    conn,
                    active_version_id,
                )

            if active_counts is not None:
                diagnostics = active_counts["stats"]
                chunk_count = int(diagnostics["vector_chunks"])
                mapped_count = int(diagnostics["vector_chunks_with_node_id"])
                heading_count = int(diagnostics["canonical_spans_with_heading_path"])
                span_count = int(diagnostics["canonical_spans"])
                stats = {
                    "documents": doc_count,
                    "active_versions": version_count,
                    "chunks": chunk_count,
                    "mapped_chunks": mapped_count,
                    "mapped_chunks_rate": diagnostics["mapped_chunks_rate"],
                    "tree_max_level": max_level,
                    "heading_path_complete": heading_count,
                    "heading_path_rate": diagnostics["heading_path_rate"],
                }
                evidence_chain_diagnostics = {
                    **diagnostics,
                    "classification": active_counts["classification"],
                }
                stats_scope = "active_version"
            else:
                stats = {
                    "documents": doc_count,
                    "active_versions": version_count,
                    "chunks": 0,
                    "mapped_chunks": 0,
                    "mapped_chunks_rate": 0.0,
                    "tree_max_level": max_level,
                    "heading_path_complete": 0,
                    "heading_path_rate": 0.0,
                }
                evidence_chain_diagnostics = {
                    "canonical_spans": 0,
                    "canonical_spans_with_heading_path": 0,
                    "vector_chunks": 0,
                    "vector_chunks_with_node_id": 0,
                    "vector_chunk_spans": 0,
                    "tree_node_spans": 0,
                    "classification": "missing_canonical_spans",
                }
                stats_scope = "active_version"

            return {
                "database_url_configured": True,
                "connection_status": "Connected successfully",
                "data_available": doc_count > 0 and version_count > 0,
                "stats_scope": stats_scope,
                "stats": stats,
                "evidence_chain_diagnostics": evidence_chain_diagnostics,
                "active_version_id": str(active_version_id) if active_version_id else None,
            }

    except psycopg.Error as e:
        return {
            "database_url_configured": True,
            "connection_status": f"Connection failed: {type(e).__name__}: {e}",
            "data_available": False,
            "error_type": type(e).__name__,
        }
    except Exception as e:
        return {
            "database_url_configured": True,
            "connection_status": f"Unexpected error: {type(e).__name__}: {e}",
            "data_available": False,
            "error_type": type(e).__name__,
        }


def execute_retrieval_for_queries(
    version_id: uuid.UUID, registry: PostgresRegistryWriter
) -> list[dict]:
    """Execute LLM-based retrieval for all business queries."""
    settings = RuntimeSettings.from_env()
    backend = ReasoningTreeBackend(
        llm_model=settings.llm_model,
        documents=None,  # Use registry data
    )

    results = []
    for query in ALL_BUSINESS_QUERIES:
        print(f"Executing query {query.query_id}: {query.query_text}")

        try:
            hits = backend.retrieve_tree_hits(
                query_text=query.query_text,
                version_id=version_id,
                registry=registry,
                limit=TOP_K,
            )

            # Convert hits to dict format
            hits_data = [
                {
                    "rank": idx + 1,
                    "node_id": str(hit.node_id),
                    "heading_path": hit.heading_path,
                    "page_no": hit.page_no,
                    "text_preview": hit.text_preview[:200] if hit.text_preview else "",
                    "score": hit.score,
                    "backend_source": hit.backend_source,
                    "retrieval_path": hit.retrieval_path,
                }
                for idx, hit in enumerate(hits)
            ]

            results.append(
                {
                    "query_id": query.query_id,
                    "query_text": query.query_text,
                    "category": query.category,
                    "difficulty": query.difficulty,
                    "expected_answer_type": query.expected_answer_type,
                    "hit_count": len(hits),
                    "hits": hits_data,
                    "retrieval_status": "success",
                }
            )

        except Exception as e:
            results.append(
                {
                    "query_id": query.query_id,
                    "query_text": query.query_text,
                    "category": query.category,
                    "difficulty": query.difficulty,
                    "expected_answer_type": query.expected_answer_type,
                    "hit_count": 0,
                    "hits": [],
                    "retrieval_status": f"failed: {type(e).__name__}: {e}",
                }
            )

    return results


def generate_judgment_template(retrieval_results: list[dict]) -> str:
    """Generate CSV template for manual relevance judgment."""
    rows = []
    rows.append(
        "query_id,hit_rank,node_id,heading_path,page_no,text_preview,is_relevant,relevance_score,judgment_category,judgment_notes"
    )

    for query_result in retrieval_results:
        if query_result["retrieval_status"] != "success":
            continue

        query_id = query_result["query_id"]
        for hit in query_result["hits"]:
            row = (
                f"{query_id},{hit['rank']},{hit['node_id']},"
                f"{hit['heading_path']},{hit['page_no'] or 'N/A'},"
                f'"{hit["text_preview"][:100]}...",'  # Truncate
                f"True/False,0.00,<category>,<notes>"
            )
            rows.append(row)

    return "\n".join(rows)


def main():
    """Execute Phase 3 real quality validation."""
    print("=" * 80)
    print("Phase 3 Real Quality Validation")
    print("=" * 80)

    # Step 1: Check database connection
    print("\nStep 1: Checking database connection...")
    db_status = check_database_connection()

    # Save database status
    status_file = OUTPUT_DIR / "validation_status.json"
    with status_file.open("w", encoding="utf-8") as f:
        json.dump(db_status, f, indent=2, ensure_ascii=False)
    print(f"Database status saved to {status_file}")

    print(f"Connection status: {db_status['connection_status']}")
    if "stats" in db_status:
        print(f"Data stats:")
        for key, value in db_status["stats"].items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2%}")
            else:
                print(f"  {key}: {value}")

    # Step 2: Check if database has data
    if not db_status.get("data_available", False):
        print("\n[ERROR] Database not available or no data found.")
        print("\nRequired actions:")
        print("1. Start PostgreSQL database (Docker container)")
        print("   docker run --name rag-pg -e POSTGRES_USER=postgres")
        print("   -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=rag")
        print("   -p 5432:5432 -d pgvector/pgvector:pg15")
        print("2. Run migrations: python run_migrations.py")
        print("3. Ingest document: python scripts/run_pageindex_real_retrieval_workflow.py")
        print("\nValidation cannot proceed without real database data.")
        sys.exit(1)

    # Step 3: Execute retrieval
    print("\nStep 2: Executing LLM-based retrieval for 20 business queries...")
    version_id = uuid.UUID(db_status["active_version_id"])

    db_url = os.getenv("DATABASE_URL", "")
    with psycopg.connect(db_url) as conn:
        registry = PostgresRegistryWriter(conn)
        retrieval_results = execute_retrieval_for_queries(version_id, registry)

    # Save retrieval results
    results_file = OUTPUT_DIR / "retrieval_results.json"
    with results_file.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "validation_date": datetime.utcnow().isoformat(),
                "version_id": str(version_id),
                "query_count": len(retrieval_results),
                "top_k": TOP_K,
                "results": retrieval_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Retrieval results saved to {results_file}")

    # Step 4: Generate judgment template
    print("\nStep 3: Generating manual relevance judgment template...")
    judgment_csv = generate_judgment_template(retrieval_results)

    template_file = OUTPUT_DIR / "judgment_template.csv"
    with template_file.open("w", encoding="utf-8") as f:
        f.write(judgment_csv)
    print(f"Judgment template saved to {template_file}")

    # Summary
    print("\n" + "=" * 80)
    print("Phase 3 Real Quality Validation - Execution Complete")
    print("=" * 80)
    print(f"Queries executed: {len(retrieval_results)}")
    success_count = sum(1 for r in retrieval_results if r["retrieval_status"] == "success")
    print(f"Successful retrievals: {success_count}/{len(retrieval_results)}")
    print(f"\nNext step: Manual relevance judgment")
    print(f"1. Open {template_file}")
    print(f"2. Fill is_relevant, relevance_score, judgment_category for each hit")
    print(f"3. Save as judgment_completed.csv")
    print(f"4. Run calculate_metrics.py to compute Level assessment")


if __name__ == "__main__":
    main()