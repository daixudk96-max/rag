#!/usr/bin/env python3
"""
Real Document Validation Runner — Measure hybrid_cluster selector quality
===========================================================

Two-phase execution:
  Phase 1 (--phase retrieve): DB setup + ingest + tree + vector + retrieve + judgment template
  Phase 2 (--phase score): Integrity gate + metrics + level assessment + summary

Key difference from Phase 8: Phase 8 used ReasoningTreeBackend (LLM navigation),
this runner uses embedding backend with hybrid_cluster selector (current production path).

Caveats (MUST appear in summary.md):
  1. NOT algorithm-comparable: Phase 8 = reasoning, this run = embedding + hybrid_cluster
  2. AI-judged proxy: Relevance scored by AI reading corpus, not human annotation
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ⚠️ CRITICAL: Set selector BEFORE any llamaindex imports
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"

import importlib.util
from dotenv import load_dotenv
import psycopg

# Import helpers from existing scripts
PROJECT_ROOT = Path(__file__).parent.parent.parent
util_spec = importlib.util.spec_from_file_location(
    "run_pageindex_helpers",
    str(PROJECT_ROOT / "scripts/run_pageindex_real_retrieval_workflow.py")
)
helpers_module = importlib.util.module_from_spec(util_spec)
util_spec.loader.exec_module(helpers_module)

ensure_local_pgvector_container = helpers_module.ensure_local_pgvector_container
database_is_reachable = helpers_module.database_is_reachable
apply_migrations = helpers_module.apply_migrations
# Load environment
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Import runtime components
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline  # noqa: E402
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf  # noqa: E402
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding  # noqa: E402


class _FakeReconciler:
    """Fake reconciler for verification scripts (non-DB path).

    CLASSIFICATION: NON-E2A HISTORICAL/DIAGNOSTIC

    This reconciler is used by historical real-document validation scripts for
    retrieval testing WITHOUT database reconciliation. It returns a typed-shaped
    E2aReconciliationResult for ingestion pipeline compatibility, but this is
    NOT a real E2a reconciliation and MUST NOT be used for Phase 15 acceptance.

    Phase 15 acceptance requires actual E2aReconciler provenance plus disposable
    database authorization. This fake reconciler is structurally excluded from
    the Phase 15 acceptance route.

    See: verification/phase15-okf-ingestion-pipeline/run_e2a_verification.py
    """

    def reconcile(self, connection: object, desired: object) -> object:
        return E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

# Embedding adapters (copy from phase11 runner)
class RealEmbedder:
    """Adapter to make SentenceTransformersEmbedding compatible with VectorLoader."""
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self._st_embedder = SentenceTransformersEmbedding(model_name=model_name)

    def embed_text(self, text: str) -> list[float]:
        """Adapter method for VectorLoader compatibility."""
        return self._st_embedder._get_text_embedding(text)

class RealEmbedding:
    """Embedding model wrapper for retrieve_tree_hits_from_pdf"""
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
CORPUS_PATH = PROJECT_ROOT / "PageIndex完整功能分析与集成方案.md"
BUSINESS_QUERIES_PATH = PROJECT_ROOT / "verification/phase3-real-validation/business_queries.py"
DEFAULT_TOP_K = 5
EMBED_DIM = 384  # all-MiniLM-L6-v2 dimension

# Full migrations (including vector extensions)
FULL_MIGRATIONS = (
    "001_initial.sql",
    "002_version_lifecycle.sql",
    "003_tree_persistence.sql",
    "004_vector_extension.sql",  # ← CRITICAL for VectorLoader
    "005_kg_extension.sql",
    "006_kg_graphrag_enrichment.sql",
    "007_processing_status.sql",
    "008_evidence_object.sql",
    "009_kag_schema.sql",
    "010_summary_index.sql",
    "011_evidence_dedup_key.sql",
    "012_mapping_table_enrichment.sql",
    "013_node_embeddings.sql",  # ← CRITICAL for hybrid_cluster
    "014_semantic_distribution.sql",  # ← CRITICAL for hybrid_cluster
)

# Metric thresholds (locked)
MIN_HIT_RATE = 0.80
MIN_TOP1_RELEVANCE = 0.90
MIN_STABILITY = 0.85

# Output directory
OUTPUT_DIR = Path(__file__).parent

# Helpers
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_json(path: Path, data: Dict) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def safe_git_commit() -> Optional[str]:
    """Read-only git rev-parse (no commit/tag/push)"""
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None

def load_business_queries() -> List[Any]:
    """Load 20 business queries from phase3 module"""
    spec = importlib.util.spec_from_file_location(
        "business_queries", str(BUSINESS_QUERIES_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.ALL_BUSINESS_QUERIES)


def get_embedding_column_dimension(conn: psycopg.Connection) -> Optional[int]:
    """Return pgvector dimension for vector_chunks.embedding, if declared."""
    row = conn.execute(
        """
        SELECT format_type(attribute.atttypid, attribute.atttypmod)
        FROM pg_attribute AS attribute
        WHERE attribute.attrelid = 'vector_chunks'::regclass
          AND attribute.attname = 'embedding'
          AND NOT attribute.attisdropped
        """
    ).fetchone()
    if not row or not row[0]:
        return None
    type_name = str(row[0])
    if not type_name.startswith("vector(") or not type_name.endswith(")"):
        return None
    return int(type_name.removeprefix("vector(").removesuffix(")"))


# Phase 1: Retrieve
def phase_retrieve() -> None:
    """Execute retrieval pipeline and generate judgment template"""

    # 01 Environment check
    env_check = {
        "timestamp": now_iso(),
        "corpus_path": str(CORPUS_PATH),
        "corpus_exists": CORPUS_PATH.exists(),
        "document_sha256": file_sha256(CORPUS_PATH) if CORPUS_PATH.exists() else None,
        "database_url_configured": bool(os.environ.get("DATABASE_URL")),
        "hotspot_selector": os.environ.get("RAG_TREE_HOTSPOT_SELECTOR"),
        "git_commit": safe_git_commit(),
    }

    if not CORPUS_PATH.exists():
        print(f"[ERROR] Corpus not found: {CORPUS_PATH}")
        write_json(OUTPUT_DIR / "01_environment_check.json", env_check)
        sys.exit(2)

    if not env_check["database_url_configured"]:
        print("[ERROR] DATABASE_URL not set")
        write_json(OUTPUT_DIR / "01_environment_check.json", env_check)
        sys.exit(2)

    write_json(OUTPUT_DIR / "01_environment_check.json", env_check)

    # DB setup
    db_url = os.environ["DATABASE_URL"]

    if not database_is_reachable(db_url):
        print("[DB] Starting pgvector container...")
        ensure_local_pgvector_container(db_url)

    print("[DB] Applying migrations...")
    apply_migrations(
        database_url=db_url,
        migrations_dir=PROJECT_ROOT / "llamaindex_runtime/registry/migrations",
        migration_files=FULL_MIGRATIONS
    )

    # Connect + healthcheck
    conn = psycopg.connect(db_url)
    conn.execute("SELECT 1")
    env_check["db_reachable"] = True

    embedding_dim = get_embedding_column_dimension(conn)
    env_check["embedding_column_dimension"] = embedding_dim
    if embedding_dim != EMBED_DIM:
        env_check["failure"] = (
            f"vector_chunks.embedding dimension is {embedding_dim}; "
            f"expected {EMBED_DIM}. Refusing to mutate shared DB schema."
        )
        write_json(OUTPUT_DIR / "01_environment_check.json", env_check)
        print(f"[ERROR] {env_check['failure']}")
        sys.exit(2)

    registry = PostgresRegistryWriter(conn)
    env_check["registry_check"] = "PASS" if registry.healthcheck() else "FAIL"
    write_json(OUTPUT_DIR / "01_environment_check.json", env_check)

    # 02 Ingestion
    print("[INGEST] Processing corpus...")
    pipeline = IngestionPipeline(
        registry=registry,
        bundle_root=OUTPUT_DIR / "e2a_bundle",
        connection_factory=lambda: conn,
        reconciler=_FakeReconciler(),
    )
    ingest_result = pipeline.ingest(
        CORPUS_PATH,
        title="[real-doc] PageIndex完整功能分析与集成方案"
    )
    version_id = ingest_result.version_id
    doc_id = ingest_result.doc_id

    # Query spans
    spans = registry.query_spans_by_version(version_id)

    ingestion_status = {
        "timestamp": now_iso(),
        "version_id": str(version_id),
        "doc_id": str(doc_id),
        "span_count": len(spans),
        "heading_path_rate": (
            sum(1 for s in spans if s.get("heading_path")) / len(spans)
            if spans else 0.0
        ),
        "status": "PASS" if len(spans) > 0 else "FAIL",
    }

    if len(spans) == 0:
        print("[ERROR] No spans extracted")
        write_json(OUTPUT_DIR / "02_document_ingestion_status.json", ingestion_status)
        sys.exit(1)

    write_json(OUTPUT_DIR / "02_document_ingestion_status.json", ingestion_status)

    # 03 Tree + Vector
    print("[TREE] Generating tree...")
    if not registry.query_tree_nodes_by_version(version_id):
        generated = TreeGenerator().generate_tree(spans, version_id=version_id)
        registry.write_tree(
            version_id=version_id,
            nodes=generated["nodes"],
            node_spans=generated["node_spans"],
        )

    nodes = registry.query_tree_nodes_by_version(version_id)
    node_spans = registry.query_tree_node_spans_by_version(version_id)

    print("[VECTOR] Loading embeddings...")
    embedder = RealEmbedder()
    loader_result = VectorLoader(embed_dim=EMBED_DIM, embedder=embedder).load(
        conn, version_id
    )

    chunks = registry.query_vector_chunks_by_version(version_id)

    tree_vector_status = {
        "timestamp": now_iso(),
        "version_id": str(version_id),
        "tree_nodes_count": len(nodes),
        "root_nodes_count": sum(1 for n in nodes if not n.get("parent_node_id")),
        "non_root_nodes_count": sum(1 for n in nodes if n.get("parent_node_id")),
        "tree_node_spans_count": len(node_spans),
        "vector_loader_result": loader_result,
        "vector_chunks_count": len(chunks),
        "vector_chunks_with_node_id": sum(1 for c in chunks if c.get("node_id")),
        "vector_chunks_with_embedding": sum(1 for c in chunks if c.get("embedding")),
        "status": "PASS" if len(nodes) > 0 and len(chunks) > 0 else "FAIL",
    }

    write_json(OUTPUT_DIR / "03_tree_vector_status.json", tree_vector_status)

    # 04 Query set
    queries = load_business_queries()

    query_set = {
        "timestamp": now_iso(),
        "query_count": len(queries),
        "queries": [
            {"query_id": q.query_id, "query_text": q.query_text}
            for q in queries
        ],
    }

    write_json(OUTPUT_DIR / "04_query_set.json", query_set)

    # 05 Retrieval
    print("[RETRIEVE] Running retrieval with embedding+hybrid_cluster...")
    embed_model = RealEmbedding()

    retrieval_results = {
        "timestamp": now_iso(),
        "version_id": str(version_id),
        "corpus_sha256": env_check["document_sha256"],
        "hotspot_selector": "hybrid_cluster",
        "backend_type": "embedding",
        "query_count": len(queries),
        "top_k": DEFAULT_TOP_K,
        "results": [],
        "query_failures": 0,
    }

    for query in queries:
        query_record = {
            "query_id": query.query_id,
            "query_text": query.query_text,
            "status": "PASS",
            "hits": [],
        }

        try:
            hits = retrieve_tree_hits_from_pdf(
                CORPUS_PATH,
                query=query.query_text,
                embed_model=embed_model,
                similarity_top_k=DEFAULT_TOP_K,
                registry=registry,
                version_id=version_id,
                backend_type="embedding"  # ← Force embedding+hybrid_cluster
            )

            for rank, hit in enumerate(hits, start=1):
                normalized = {
                    "hit_rank": rank,
                    "node_id": hit.get("node_id"),
                    "chunk_id": hit.get("chunk_id"),
                    "score": hit.get("score"),
                    "text_preview": (hit.get("text_preview") or "")[:200],
                    "heading_path": hit.get("heading_path"),
                    "page_no": hit.get("page_no") or "N/A",
                    "relevance_score": None,  # Placeholder
                }
                query_record["hits"].append(normalized)

            query_record["hit_count"] = len(query_record["hits"])
            retrieval_results["results"].append(query_record)

        except Exception as e:
            retrieval_results["query_failures"] += 1
            query_record.update({
                "status": "FAIL",
                "error_type": type(e).__name__,
                "hit_count": 0,
            })
            retrieval_results["results"].append(query_record)

    write_json(OUTPUT_DIR / "05_retrieval_results.json", retrieval_results)
    write_json(OUTPUT_DIR / "retrieval_results.json", retrieval_results)  # Canonical name

    # 06 Evidence chain report (diagnostics)
    total_hits = sum(len(r["hits"]) for r in retrieval_results["results"])
    zero_chunk_hits = sum(
        1 for r in retrieval_results["results"]
        for h in r["hits"]
        if not h["text_preview"]
    )
    parent_only_hits = sum(
        1 for r in retrieval_results["results"]
        for h in r["hits"]
        if h["heading_path"] and not h["text_preview"]
    )
    missing_node_hits = sum(
        1 for r in retrieval_results["results"]
        for h in r["hits"]
        if not h.get("node_id")
    )
    missing_chunk_hits = sum(
        1 for r in retrieval_results["results"]
        for h in r["hits"]
        if not h.get("chunk_id")
    )
    heading_path_hits = sum(
        1 for r in retrieval_results["results"]
        for h in r["hits"]
        if h.get("heading_path")
    )
    queries_with_hits = sum(1 for r in retrieval_results["results"] if r.get("hit_count", 0) > 0)
    zero_hit_queries = retrieval_results["query_count"] - queries_with_hits

    evidence_chain_report = {
        "timestamp": now_iso(),
        "total_hits": total_hits,
        "queries_with_hits": queries_with_hits,
        "zero_hit_queries": zero_hit_queries,
        "zero_hit_query_rate": zero_hit_queries / retrieval_results["query_count"] if retrieval_results["query_count"] else 0.0,
        "zero_chunk_hits": zero_chunk_hits,
        "parent_only_hits": parent_only_hits,
        "missing_node_hits": missing_node_hits,
        "missing_chunk_hits": missing_chunk_hits,
        "chunk_id_present_rate": (total_hits - missing_chunk_hits) / total_hits if total_hits else 0.0,
        "heading_path_rate": heading_path_hits / total_hits if total_hits else 0.0,
        "measured_not_assumed": True,
    }

    write_json(OUTPUT_DIR / "06_evidence_chain_report.json", evidence_chain_report)

    # 07 Judgment template CSV
    import csv

    csv_path = OUTPUT_DIR / "judgment_template.csv"

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "query_id", "hit_rank", "node_id",
            "heading_path", "page_no", "text_preview",
            "is_relevant", "relevance_score",
            "judgment_category", "judgment_notes"
        ])

        for result in retrieval_results["results"]:
            for hit in result["hits"]:
                writer.writerow([
                    result["query_id"],
                    hit["hit_rank"],
                    hit["node_id"],
                    hit["heading_path"] or "",
                    hit.get("page_no") or "N/A",
                    hit["text_preview"] or "",
                    "<is_relevant>",  # Placeholder
                    "0.00",  # Placeholder (⚠️ AI must use 0.05 for irrelevant)
                    "<category>",  # Placeholder
                    "<notes>"  # Placeholder
                ])

    judgment_metadata = {
        "timestamp": now_iso(),
        "template_path": str(csv_path),
        "row_count": total_hits,
        "placeholder_warning": (
            "AI must fill is_relevant, relevance_score (use 0.05 for irrelevant, NOT 0.00), "
            "judgment_category, judgment_notes. Empty category with 0.00 is treated as placeholder."
        ),
    }

    write_json(OUTPUT_DIR / "07_judgment_template_metadata.json", judgment_metadata)

    # 08/09 NULL placeholders (pending score phase)
    quality_metrics = {
        "timestamp": now_iso(),
        "status": "NOT_CALCULATED_PENDING_JUDGMENTS",
        "hit_rate": None,
        "top1_relevance": None,
        "stability": None,
    }

    write_json(OUTPUT_DIR / "08_quality_metrics.json", quality_metrics)

    level_assessment = {
        "timestamp": now_iso(),
        "version_id": str(version_id),
        "query_count": len(queries),
        "judgment_count": 0,
        "status": "LEVEL_2_PRESERVED_PENDING_HOTSPOT_JUDGMENTS",
        "metrics": quality_metrics,
        "thresholds": {
            "hit_rate": MIN_HIT_RATE,
            "top1_relevance": MIN_TOP1_RELEVANCE,
            "stability": MIN_STABILITY,
        },
        "level": {
            "level": "Level_2",
            "level_description": "能查但质量未验证",
        },
    }

    write_json(OUTPUT_DIR / "09_level_assessment.json", level_assessment)

    # Print next steps
    print("\n" + "="*60)
    print("Phase 1 (retrieve) complete.")
    print("="*60)
    print(f"Retrieved {total_hits} hits across {len(queries)} queries.")
    print(f"Judgment template: {csv_path}")
    print("\nNext steps:")
    print("1. AI reads corpus + hits → fills judgment_completed.csv")
    print("2. Run: python run_validation.py --phase score")
    print("="*60)

# Phase 2: Score
def phase_score() -> None:
    """Integrity gate + calculate metrics + level assessment"""

    # Load retrieval results
    retrieval_path = OUTPUT_DIR / "retrieval_results.json"
    if not retrieval_path.exists():
        print("[ERROR] retrieval_results.json not found — run --phase retrieve first")
        sys.exit(1)

    retrieval_results = json.load(open(retrieval_path, encoding='utf-8'))

    # Load judgment CSV
    judgment_path = OUTPUT_DIR / "judgment_completed.csv"
    if not judgment_path.exists():
        print(f"[ERROR] {judgment_path} not found — AI must fill judgments first")
        sys.exit(1)

    import csv
    judgments = []

    with open(judgment_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            judgments.append(row)

    # Inline integrity gate
    integrity_report = {
        "timestamp": now_iso(),
        "checks": {},
        "passed": True,
        "violations": [],
    }

    # Check 1: Retrieval exists
    integrity_report["checks"]["retrieval_exists"] = retrieval_path.exists()

    # Check 2: Query count
    integrity_report["checks"]["query_count_correct"] = (
        retrieval_results.get("query_count") == 20
    )

    # Check 3: Results non-empty
    integrity_report["checks"]["results_non_empty"] = (
        len(retrieval_results.get("results", [])) > 0
    )

    # Check 4: Hits have rank+node_id
    integrity_report["checks"]["hits_have_rank_node_id"] = all(
        "hit_rank" in h and "node_id" in h
        for r in retrieval_results["results"]
        for h in r["hits"]
    )

    # Check 5: Judgment CSV has 10 columns (phase8 schema)
    expected_cols = [
        "query_id", "hit_rank", "node_id",
        "heading_path", "page_no", "text_preview",
        "is_relevant", "relevance_score",
        "judgment_category", "judgment_notes"
    ]

    with open(judgment_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        actual_cols = next(reader)

    integrity_report["checks"]["judgment_columns_complete"] = (
        actual_cols == expected_cols
    )

    # Check 6: Row alignment
    expected_rows = sum(len(r["hits"]) for r in retrieval_results["results"])
    integrity_report["checks"]["row_count_aligned"] = (
        len(judgments) == expected_rows
    )

    # Check 7: (query_id, hit_rank) sets match
    retrieval_pairs = set(
        (r["query_id"], h["hit_rank"])
        for r in retrieval_results["results"]
        for h in r["hits"]
    )
    judgment_pairs = set(
        (j["query_id"], int(j["hit_rank"]))
        for j in judgments
    )
    integrity_report["checks"]["query_rank_pairs_match"] = (
        retrieval_pairs == judgment_pairs
    )

    # Check 8: No placeholders
    placeholder_rows = [
        (i, j) for i, j in enumerate(judgments)
        if (
            j["is_relevant"].startswith("<") or
            (j["relevance_score"] == "0.00" and not j["judgment_category"]) or
            j["judgment_category"].startswith("<") or
            j["judgment_notes"].startswith("<")
        )
    ]

    integrity_report["checks"]["no_placeholders"] = (
        len(placeholder_rows) == 0
    )

    if placeholder_rows:
        integrity_report["violations"].append({
            "type": "placeholder_rows",
            "count": len(placeholder_rows),
            "examples": placeholder_rows[:5],
        })

    # Check 9: Same corpus (sha256 match)
    corpus_sha256 = file_sha256(CORPUS_PATH)
    version_sha256 = retrieval_results.get("corpus_sha256")

    integrity_report["checks"]["corpus_sha256_match"] = (
        corpus_sha256 == version_sha256
    )

    # Evaluate pass/fail
    all_checks_passed = all(integrity_report["checks"].values())

    if not all_checks_passed:
        integrity_report["passed"] = False

    write_json(OUTPUT_DIR / "validation_integrity_report.json", integrity_report)

    if not all_checks_passed:
        print("\n[INTEGRITY GATE] FAILED")
        print("Violations:")
        for k, v in integrity_report["checks"].items():
            if not v:
                print(f"  - {k}: FAIL")
        print("\nMetrics remain NULL. Fix violations before proceeding.")
        sys.exit(1)

    print("[INTEGRITY GATE] PASSED")

    # Import metric functions from phase8
    metrics_spec = importlib.util.spec_from_file_location(
        "phase8_metrics",
        str(PROJECT_ROOT / "verification/phase8-matched-validation-rerun/calculate_phase8_metrics.py")
    )
    metrics_module = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics_module)

    calculate_hit_rate = metrics_module.calculate_hit_rate
    calculate_top1_relevance = metrics_module.calculate_top1_relevance
    calculate_stability = metrics_module.calculate_stability
    assess_level = metrics_module.assess_level
    Judgment = metrics_module.Judgment
    _parse_bool = metrics_module._parse_bool
    _parse_page_no = metrics_module._parse_page_no

    # Convert judgments to Judgment objects
    judgment_objs = []
    for j in judgments:
        judgment_objs.append(Judgment(
            query_id=j["query_id"],
            hit_rank=int(j["hit_rank"]),
            node_id=j["node_id"],
            heading_path=j["heading_path"],
            page_no=_parse_page_no(j.get("page_no", "")),
            text_preview=j["text_preview"],
            is_relevant=_parse_bool(j["is_relevant"]),
            relevance_score=float(j["relevance_score"]),
            judgment_category=j["judgment_category"],
            judgment_notes=j["judgment_notes"],
        ))

    # Calculate metrics
    hit_rate = calculate_hit_rate(judgment_objs, retrieval_results)
    top1_relevance = calculate_top1_relevance(judgment_objs)
    stability = calculate_stability(judgment_objs, retrieval_results)

    queries_with_hits = sum(1 for r in retrieval_results["results"] if r.get("hit_count", 0) > 0)
    zero_hit_queries = retrieval_results["query_count"] - queries_with_hits

    metrics = {
        "hit_rate": hit_rate,
        "top1_relevance": top1_relevance,
        "stability": stability,
    }

    # Assess level
    level_info = assess_level(hit_rate, top1_relevance, stability)

    # Write quality metrics
    quality_metrics = {
        "timestamp": now_iso(),
        "status": "CALCULATED",
        **metrics,
    }

    write_json(OUTPUT_DIR / "08_quality_metrics.json", quality_metrics)

    # Write level assessment
    level_assessment = {
        "timestamp": now_iso(),
        "version_id": retrieval_results["version_id"],
        "query_count": retrieval_results["query_count"],
        "judgment_count": len(judgments),
        "status": "LEVEL_ASSessed",
        "metrics": quality_metrics,
        "thresholds": {
            "hit_rate": MIN_HIT_RATE,
            "top1_relevance": MIN_TOP1_RELEVANCE,
            "stability": MIN_STABILITY,
        },
        "level": level_info,
    }

    write_json(OUTPUT_DIR / "09_level_assessment.json", level_assessment)

    # Write summary.md
    summary_lines = [
        "# Real Document Validation Summary — hybrid_cluster Selector Quality",
        "",
        f"**Date**: {now_iso()}",
        f"**Version ID**: {retrieval_results['version_id']}",
        f"**Corpus**: PageIndex完整功能分析与集成方案.md",
        f"**Selector**: hybrid_cluster (embedding backend)",
        f"**Queries**: {retrieval_results['query_count']}",
        f"**Queries with hits**: {queries_with_hits}",
        f"**Zero-hit queries**: {zero_hit_queries}",
        f"**Hits**: {len(judgments)}",
        "",
        "## Quality Metrics",
        "",
        f"| Metric | Value | Threshold | Pass |",
        f"|--------|-------|-----------|------|",
        f"| hit_rate | {hit_rate:.2f} | {MIN_HIT_RATE:.2f} | {'✅' if hit_rate >= MIN_HIT_RATE else '❌'} |",
        f"| top1_relevance | {top1_relevance:.2f} | {MIN_TOP1_RELEVANCE:.2f} | {'✅' if top1_relevance >= MIN_TOP1_RELEVANCE else '❌'} |",
        f"| stability | {stability:.2f} | {MIN_STABILITY:.2f} | {'✅' if stability >= MIN_STABILITY else '❌'} |",
        "",
        f"**Level**: {level_info['level']} — {level_info['level_description']}",
        "",
        "## Comparison with Phase 8",
        "",
        "| Run | Backend | Selector | hit_rate | top1 | stability | Level |",
        "|-----|---------|----------|----------|------|-----------|-------|",
        "| Phase 8 | ReasoningTreeBackend | (ignored) | 0.70 | 0.59 | 0.65 | Level_2 |",
        f"| This run | embedding | hybrid_cluster | {hit_rate:.2f} | {top1_relevance:.2f} | {stability:.2f} | {level_info['level']} |",
        "",
        "## ⚠️ CRITICAL CAVEATS",
        "",
        "**Caveat 1 — Not Algorithm-Comparable**",
        "",
        "Phase 8 used `ReasoningTreeBackend` (LLM navigation path). This run uses",
        "`embedding` backend with `hybrid_cluster` selector. These are **different",
        "retrieval algorithms**. This is a **new measurement**, not a regression test",
        "or improvement comparison.",
        "",
        "**Caveat 2 — AI-Judged Proxy**",
        "",
        "Relevance judgments were produced by AI reading the corpus and scoring hits.",
        "This is a **directional proxy**, not human-annotated ground truth. Does not",
        "constitute certification-level Level promotion.",
        "",
        "**Caveat 3 — Chinese Corpus with English-Centric Embedding Model**",
        "",
        "This run used `all-MiniLM-L6-v2` (384 dimensions), which is English-centric.",
        "The corpus and queries are Chinese, so this likely depresses retrieval quality.",
        "The low score is still a valid production-path measurement for the current",
        "configuration, but it should not be treated as the ceiling of a Chinese-capable",
        "embedding model.",
        "",
        "## Failure Breakdown",
        "",
        f"- Zero-hit queries: {zero_hit_queries}/{retrieval_results['query_count']}",
        f"- Total retrieved hits: {len(judgments)} (expected upper bound: {retrieval_results['query_count'] * retrieval_results.get('top_k', 0)})",
        "- Result: Level_2 is preserved; no Level promotion is justified.",
        "",
        "## Provenance",
        "",
        f"- Corpus SHA256: `{corpus_sha256}`",
        f"- Git commit: `{safe_git_commit()}`",
        f"- Selector env: `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster`",
        f"- Backend: `embedding` (forced via parameter)",
        f"- Judgment source: AI in-context reading",
        "",
        "## Artifacts",
        "",
        "- `01_environment_check.json`",
        "- `02_document_ingestion_status.json`",
        "- `03_tree_vector_status.json`",
        "- `04_query_set.json`",
        "- `05_retrieval_results.json`",
        "- `06_evidence_chain_report.json`",
        "- `07_judgment_template_metadata.json`",
        "- `judgment_completed.csv`",
        "- `08_quality_metrics.json`",
        "- `09_level_assessment.json`",
        "- `validation_integrity_report.json`",
        "- `summary.md` (this file)",
    ]

    with open(OUTPUT_DIR / "summary.md", 'w', encoding='utf-8') as f:
        f.write("\n".join(summary_lines))

    print("\n" + "="*60)
    print("Phase 2 (score) complete.")
    print("="*60)
    print(f"hit_rate: {hit_rate:.2f}")
    print(f"top1_relevance: {top1_relevance:.2f}")
    print(f"stability: {stability:.2f}")
    print(f"Level: {level_info['level']}")
    print(f"\nSummary: {OUTPUT_DIR / 'summary.md'}")
    print("="*60)

# Main
def main() -> None:
    parser = argparse.ArgumentParser(description="Real document validation runner")
    parser.add_argument("--phase", required=True, choices=["retrieve", "score"])

    args = parser.parse_args()

    if args.phase == "retrieve":
        phase_retrieve()
    elif args.phase == "score":
        phase_score()

if __name__ == "__main__":
    main()