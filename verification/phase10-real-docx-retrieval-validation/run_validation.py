from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
DEFAULT_TOP_K = 5
MIN_HEADING_PATH_RATE = 0.20
QUERY_SET = [
    {"query_id": "Q01", "query_text": "AI产品经理的核心DNA是什么？"},
    {"query_id": "Q02", "query_text": "传统产品经理和AI产品经理的关注点有什么不同？"},
    {"query_id": "Q03", "query_text": "AI产品的智能来源是什么？"},
    {"query_id": "Q04", "query_text": "什么是数据闭环飞轮？为什么它重要？"},
    {"query_id": "Q05", "query_text": "抖音如何利用用户行为数据优化推荐？"},
    {"query_id": "Q06", "query_text": "特斯拉如何收集自动驾驶数据？"},
    {"query_id": "Q07", "query_text": "AI产品落地时第一个要思考的问题是什么？"},
    {"query_id": "Q08", "query_text": "如何处理不干净的数据？"},
    {"query_id": "Q09", "query_text": "李菲菲在AI 1.0时代遇到了什么数据问题？"},
    {"query_id": "Q10", "query_text": "传统软件和AI产品的输出特点有什么区别？"},
    {"query_id": "Q11", "query_text": "独家数据为什么是真正的护城河？"},
    {"query_id": "Q12", "query_text": "特斯拉的AB test预演如何对比用户操作和AI预演？"},
]

sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from llamaindex_runtime.ingestion.pipeline import IngestionPipeline  # noqa: E402
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf  # noqa: E402
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding  # noqa: E402
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
LOGGER = logging.getLogger(__name__)


class _FakeReconciler:
    """Fake reconciler for verification scripts (non-DB path).

    CLASSIFICATION: NON-E2A HISTORICAL/DIAGNOSTIC

    This reconciler is used by Phase 10 historical validation scripts for
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


class RealEmbedder:
    """Adapter to make SentenceTransformersEmbedding compatible with VectorLoader."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._st_embedder = SentenceTransformersEmbedding(model_name=model_name)

    def embed_text(self, text: str) -> list[float]:
        """Adapter method for VectorLoader compatibility."""
        return self._st_embedder._get_text_embedding(text)


class RealEmbedding:
    """Adapter for query embedding."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(name: str, payload: dict[str, Any]) -> None:
    (OUT_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )


def safe_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_doc_path() -> Path | None:
    raw_path = os.getenv("REAL_VALIDATION_DOCUMENT_PATH")
    if not raw_path:
        return None
    return Path(raw_path).expanduser().resolve()


def count_non_empty(values: list[dict[str, Any]], key: str) -> int:
    return sum(1 for item in values if item.get(key))


def build_base_payload(doc_path: Path | None) -> dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "validation_script_version": "2026-06-12-v2",
        "git_commit_sha": safe_git_commit(),
        "source_document": "ANONYMIZED_LOCAL_DOCX" if doc_path is not None else None,
        "source_document_location": "local_user_supplied_path_redacted" if doc_path is not None else None,
    }


def build_summary(
    *,
    doc_path: Path,
    env: dict[str, Any],
    ingest: dict[str, Any],
    tree_vector: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    status = evidence["functional_status"]
    return "\n".join(
        [
            "# Phase 10 Real DOCX Retrieval Validation Summary",
            "",
            f"**Status:** {status}",
            f"**Generated:** {now_iso()}",
            "",
            "## Source Document",
            "",
            f"- Path: `ANONYMIZED_LOCAL_DOCX` (local user path redacted)",
            "- Theme: 进阶版 RAG / 混合检索 / 结构化数据检索",
            "",
            "## Environment",
            "",
            f"- document_exists: `{env['document_exists']}`",
            f"- database_url_configured: `{env['database_url_configured']}` (raw value not printed)",
            f"- db_reachable: `{env['db_reachable']}`",
            "",
            "## Ingestion",
            "",
            f"- doc_id: `{ingest.get('doc_id')}`",
            f"- version_id: `{ingest.get('version_id')}`",
            f"- canonical_spans: `{ingest.get('canonical_spans_count')}`",
            f"- spans_with_heading_path: `{ingest.get('spans_with_heading_path')}`",
            f"- heading_path_rate: `{ingest.get('heading_path_rate')}`",
            f"- dropped_nodes: `{ingest.get('dropped_nodes')}`",
            f"- hierarchy_precondition_status: `{ingest.get('hierarchy_precondition_status')}`",
            "",
            "## Tree / Vector Status",
            "",
            f"- tree_nodes: `{tree_vector.get('tree_nodes_count')}`",
            f"- non_root_nodes: `{tree_vector.get('non_root_nodes_count')}`",
            f"- tree_node_spans: `{tree_vector.get('tree_node_spans_count')}`",
            f"- vector_chunks: `{tree_vector.get('vector_chunks_count')}`",
            f"- vector_chunk_spans: `{tree_vector.get('vector_chunk_spans_count')}`",
            f"- vector_chunks_with_node_id: `{tree_vector.get('vector_chunks_with_node_id')}`",
            f"- vector_chunks_with_embedding: `{tree_vector.get('vector_chunks_with_embedding')}`",
            "",
            "## Retrieval Evidence Chain",
            "",
            f"- query_count: `{evidence.get('query_count')}`",
            f"- query_failures: `{evidence.get('query_failures')}`",
            f"- total_hits: `{evidence.get('total_hits')}`",
            f"- zero_chunk_hits: `{evidence.get('zero_chunk_hits')}`",
            f"- parent_only_hits: `{evidence.get('parent_only_hits')}`",
            f"- hotspot_metadata_hits: `{evidence.get('hotspot_metadata_hits')}`",
            f"- navigation_path_hits: `{evidence.get('navigation_path_hits')}`",
            f"- subtree_hotspot_traversal_hits: `{evidence.get('subtree_hotspot_traversal_hits')}`",
            "",
            "## Functional Decision",
            "",
            f"- functional_status: `{evidence.get('functional_status')}`",
            f"- rationale: {evidence.get('rationale')}",
            "",
            "## Quality / Level Decision",
            "",
            "- Quality metrics are not calculated because hotspot-specific human judgments are pending and this run produced no retrievable hits.",
            "- `Level_2` remains authoritative.",
            "",
            "## Generated Artifacts",
            "",
            "- `01_environment_check.json`",
            "- `02_document_ingestion_status.json`",
            "- `03_tree_vector_status.json`",
            "- `04_query_set.json`",
            "- `05_hotspot_retrieval_results.json`",
            "- `06_evidence_chain_report.json`",
            "- `07_judgment_template.csv`",
            "- `07_judgment_template_metadata.json`",
            "- `08_quality_metrics.json`",
            "- `09_level_assessment.json`",
            "- `10_validation_summary.md`",
            "- `11_failure_diagnosis.json` (if diagnosis is run)",
            "",
        ]
    )


def build_retrieval_rationale(
    *,
    total_hits: int,
    query_failures: int,
    hierarchy_precondition_status: str,
    zero_chunk_count: int,
    parent_only_count: int,
) -> str:
    if hierarchy_precondition_status != "PASS":
        return (
            "The DOCX was parsed as a flat transcript with insufficient heading hierarchy. "
            "Tree/vector materialization succeeded, but the source does not provide parent-child structure needed "
            "to validate parent-hotspot-to-child-evidence traversal."
        )
    if query_failures:
        return "One or more retrieval queries failed; inspect per-query errors."
    if total_hits == 0:
        return "All queries executed, but hotspot retrieval returned zero hits."
    if zero_chunk_count or parent_only_count:
        return "Retrieval returned hits, but evidence-chain integrity failed."
    return "All queries returned evidence-bearing hits with hotspot/navigation metadata preserved."


def write_judgment_template(all_hits: list[dict[str, Any]]) -> None:
    fieldnames = [
        "query_id",
        "query_text",
        "rank",
        "heading_path",
        "text_preview",
        "chunk_id",
        "node_id",
        "hotspot_node_id",
        "navigation_path",
        "relevance",
        "evidence_quality",
        "answer_support",
        "comment",
    ]
    with (OUT_DIR / "07_judgment_template.csv").open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for hit in all_hits:
            writer.writerow(
                {
                    "query_id": hit.get("query_id"),
                    "query_text": hit.get("query_text"),
                    "rank": hit.get("rank"),
                    "heading_path": hit.get("heading_path"),
                    "text_preview": hit.get("text_preview"),
                    "chunk_id": hit.get("chunk_id"),
                    "node_id": hit.get("node_id"),
                    "hotspot_node_id": hit.get("hotspot_node_id"),
                    "navigation_path": " > ".join(str(item) for item in hit.get("navigation_path", [])),
                    "relevance": "",
                    "evidence_quality": "",
                    "answer_support": "",
                    "comment": "",
                }
            )
    write_json(
        "07_judgment_template_metadata.json",
        {
            "generated_at": now_iso(),
            "field_rules": {
                "relevance": ["relevant", "partially_relevant", "irrelevant"],
                "evidence_quality": ["strong", "weak", "none"],
                "answer_support": ["supports_answer", "context_only", "no_support"],
                "comment": "free text",
            },
            "note": "The current run may contain zero rows if retrieval produced no hits.",
        },
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    load_dotenv(REPO_ROOT / ".env", override=False)
    doc_path = resolve_doc_path()
    db_url = os.getenv("DATABASE_URL")

    env_payload = {
        **build_base_payload(doc_path),
        "document_exists": bool(doc_path and doc_path.exists()),
        "database_url_configured": bool(db_url),
        "database_url_raw_value_printed": False,
        "db_reachable": False,
        "registry_check": "not_run",
    }

    if doc_path is None:
        env_payload["failure"] = "REAL_VALIDATION_DOCUMENT_PATH is not configured"
        write_json("01_environment_check.json", env_payload)
        LOGGER.error("REAL_VALIDATION_DOCUMENT_PATH is not configured")
        return 2
    if not doc_path.exists():
        env_payload["failure"] = "source document not found"
        write_json("01_environment_check.json", env_payload)
        LOGGER.error("source document not found")
        return 2
    env_payload["document_sha256"] = file_sha256(doc_path)
    env_payload["document_identity_note"] = "Local path and file URI are redacted from artifacts; SHA-256 is retained for reproducibility."
    if not db_url:
        env_payload["failure"] = "DATABASE_URL is not configured"
        write_json("01_environment_check.json", env_payload)
        LOGGER.error("DATABASE_URL is not configured")
        return 2

    try:
        return run_validation(doc_path=doc_path, db_url=db_url, env_payload=env_payload)
    except psycopg.OperationalError as exc:
        env_payload["db_reachable"] = False
        env_payload["failure"] = f"Database connection failed: {type(exc).__name__}"
        write_json("01_environment_check.json", env_payload)
        LOGGER.error("database connection failed")
        return 2


def run_validation(*, doc_path: Path, db_url: str, env_payload: dict[str, Any]) -> int:
    retrieval_results: dict[str, Any] = {
        **build_base_payload(doc_path),
        "queries": [],
    }

    with psycopg.connect(db_url) as conn:
        conn.execute("SELECT 1")
        env_payload["db_reachable"] = True
        registry = PostgresRegistryWriter(conn)
        env_payload["registry_check"] = "PASS" if registry.healthcheck() else "FAIL"
        write_json("01_environment_check.json", env_payload)

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=OUT_DIR / "e2a_bundle",
            connection_factory=lambda: conn,
            reconciler=_FakeReconciler(),
        )
        ingest_result = pipeline.ingest(doc_path, title="[20] 进阶版RAG 混合检索+结构化数据检索 原文")
        version_id = ingest_result.version_id
        doc_id = ingest_result.doc_id
        spans = registry.query_spans_by_version(version_id)
        spans_with_heading_path = sum(1 for span in spans if span.get("heading_path"))
        heading_path_rate = spans_with_heading_path / len(spans) if spans else 0.0
        hierarchy_precondition_status = "PASS" if heading_path_rate >= MIN_HEADING_PATH_RATE else "FAIL"

        ingest_payload = {
            **build_base_payload(doc_path),
            "doc_id": doc_id,
            "version_id": version_id,
            "source_uri": "LOCAL_FILE_URI_REDACTED",
            "canonical_spans_count": len(spans),
            "dropped_nodes": ingest_result.dropped_nodes,
            "spans_with_heading_path": spans_with_heading_path,
            "spans_without_heading_path": len(spans) - spans_with_heading_path,
            "heading_path_rate": heading_path_rate,
            "hierarchy_precondition_status": hierarchy_precondition_status,
            "hierarchy_precondition_threshold": MIN_HEADING_PATH_RATE,
            "sample_spans": [
                {
                    "span_id": row["span_id"],
                    "heading_path": row.get("heading_path"),
                    "page_no": row.get("page_no"),
                    "text_preview": (row.get("raw_text") or "")[:240],
                }
                for row in spans[:10]
            ],
            "status": "PASS" if len(spans) > 0 else "FAIL",
        }
        write_json("02_document_ingestion_status.json", ingest_payload)
        if not spans:
            LOGGER.error("ingestion produced zero canonical spans")
            return 1

        if not registry.query_tree_nodes_by_version(version_id):
            generated = TreeGenerator().generate_tree(spans, version_id=version_id)
            registry.write_tree(
                version_id=version_id,
                nodes=generated["nodes"],
                node_spans=generated["node_spans"],
            )
        nodes = registry.query_tree_nodes_by_version(version_id)
        node_spans = registry.query_tree_node_spans_by_version(version_id)

        real_embedder = RealEmbedder(model_name="all-MiniLM-L6-v2")
        loader_result = VectorLoader(embed_dim=384, embedder=real_embedder).load(conn, version_id)
        chunks = registry.query_vector_chunks_by_version(version_id)
        chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)

        vector_chunks_with_node_id = sum(1 for row in chunks if row.get("node_id") is not None)
        vector_chunks_with_embedding = sum(1 for row in chunks if row.get("embedding") is not None)
        non_root_nodes = sum(1 for row in nodes if row.get("parent_node_id") is not None)
        tree_vector_payload = {
            **build_base_payload(doc_path),
            "doc_id": doc_id,
            "version_id": version_id,
            "tree_nodes_count": len(nodes),
            "root_nodes_count": sum(1 for row in nodes if row.get("parent_node_id") is None),
            "non_root_nodes_count": non_root_nodes,
            "tree_node_spans_count": len(node_spans),
            "vector_loader_result": loader_result,
            "vector_chunks_count": len(chunks),
            "vector_chunk_spans_count": len(chunk_spans),
            "vector_chunks_with_node_id": vector_chunks_with_node_id,
            "vector_chunks_with_embedding": vector_chunks_with_embedding,
            "heading_path_non_empty_count": count_non_empty(nodes, "heading_path"),
            "mapped_chunks_rate": vector_chunks_with_node_id / len(chunks) if chunks else 0.0,
            "embedding_rate": vector_chunks_with_embedding / len(chunks) if chunks else 0.0,
            "sample_nodes": [
                {
                    "node_id": row["node_id"],
                    "parent_node_id": row.get("parent_node_id"),
                    "level_no": row.get("level_no"),
                    "heading_path": row.get("heading_path"),
                    "summary_preview": (row.get("summary_text") or "")[:240],
                }
                for row in nodes[:15]
            ],
            "status": "PASS" if nodes and chunks and vector_chunks_with_node_id > 0 and vector_chunks_with_embedding > 0 else "FAIL",
        }
        write_json("03_tree_vector_status.json", tree_vector_payload)

        write_json(
            "04_query_set.json",
            {
                **build_base_payload(doc_path),
                "query_count": len(QUERY_SET),
                "queries": QUERY_SET,
                "query_quality": {
                    "duplicate_count": len(QUERY_SET) - len({item["query_text"] for item in QUERY_SET}),
                    "min_query_length": min(len(item["query_text"]) for item in QUERY_SET),
                    "max_query_length": max(len(item["query_text"]) for item in QUERY_SET),
                    "avg_query_length": sum(len(item["query_text"]) for item in QUERY_SET) / len(QUERY_SET),
                },
            },
        )

        embed_model = RealEmbedding(model_name="all-MiniLM-L6-v2")
        query_failures = 0
        all_hits: list[dict[str, Any]] = []
        for query in QUERY_SET:
            query_id = query["query_id"]
            query_text = query["query_text"]
            query_record: dict[str, Any] = {"query_id": query_id, "query_text": query_text, "status": "PASS", "hits": []}
            try:
                hits = retrieve_tree_hits_from_pdf(
                    doc_path,
                    query=query_text,
                    embed_model=embed_model,  # type: ignore[arg-type]
                    similarity_top_k=DEFAULT_TOP_K,
                    registry=registry,
                    version_id=version_id,
                    backend_type="embedding",
                )
            except (psycopg.Error, ValueError, KeyError, RuntimeError) as exc:
                query_failures += 1
                query_record.update(
                    {
                        "status": "FAIL",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                retrieval_results["queries"].append(query_record)
                continue

            for rank, hit in enumerate(hits, start=1):
                normalized = {
                    "query_id": query_id,
                    "query_text": query_text,
                    "rank": rank,
                    "score": hit.get("score"),
                    "node_id": hit.get("node_id"),
                    "chunk_id": hit.get("chunk_id"),
                    "chunk_id_missing": hit.get("chunk_id_missing"),
                    "span_ids": hit.get("span_ids", []),
                    "heading_path": hit.get("heading_path"),
                    "text_preview": hit.get("text_preview"),
                    "hotspot_node_id": hit.get("hotspot_node_id"),
                    "navigation_node_ids": hit.get("navigation_node_ids", []),
                    "navigation_path": hit.get("navigation_path", []),
                    "drill_depth": hit.get("drill_depth"),
                    "backend_source": hit.get("backend_source"),
                    "retrieval_path": hit.get("retrieval_path"),
                }
                query_record["hits"].append(normalized)
                all_hits.append(normalized)
            retrieval_results["queries"].append(query_record)

        retrieval_results["query_count"] = len(QUERY_SET)
        retrieval_results["query_failures"] = query_failures
        retrieval_results["total_hits"] = len(all_hits)
        write_json("05_hotspot_retrieval_results.json", retrieval_results)

        zero_chunk_hits = [hit for hit in all_hits if hit.get("chunk_id_missing") is True or str(hit.get("chunk_id")) == str(uuid.UUID(int=0))]
        parent_only_hits = [hit for hit in all_hits if not hit.get("span_ids")]
        missing_node_hits = [hit for hit in all_hits if not hit.get("node_id")]
        empty_preview_hits = [hit for hit in all_hits if not (hit.get("text_preview") or "").strip()]
        hotspot_metadata_hits = [hit for hit in all_hits if hit.get("hotspot_node_id")]
        navigation_path_hits = [hit for hit in all_hits if hit.get("navigation_path")]
        subtree_hotspot_hits = [hit for hit in all_hits if hit.get("retrieval_path") == "subtree_hotspot_traversal"]

        total_hits = len(all_hits)
        functional_pass = (
            hierarchy_precondition_status == "PASS"
            and query_failures == 0
            and total_hits > 0
            and len(zero_chunk_hits) == 0
            and len(parent_only_hits) == 0
            and (len(hotspot_metadata_hits) / total_hits if total_hits else 0.0) >= 0.90
            and (len(navigation_path_hits) / total_hits if total_hits else 0.0) >= 0.90
        )
        evidence_payload = {
            **build_base_payload(doc_path),
            "doc_id": doc_id,
            "version_id": version_id,
            "query_count": len(QUERY_SET),
            "query_failures": query_failures,
            "total_hits": total_hits,
            "zero_chunk_hits": len(zero_chunk_hits),
            "parent_only_hits": len(parent_only_hits),
            "missing_span_hits": len(parent_only_hits),
            "missing_node_hits": len(missing_node_hits),
            "empty_preview_hits": len(empty_preview_hits),
            "hotspot_metadata_hits": len(hotspot_metadata_hits),
            "navigation_path_hits": len(navigation_path_hits),
            "subtree_hotspot_traversal_hits": len(subtree_hotspot_hits),
            "hotspot_metadata_rate": len(hotspot_metadata_hits) / total_hits if total_hits else 0.0,
            "navigation_path_rate": len(navigation_path_hits) / total_hits if total_hits else 0.0,
            "subtree_hotspot_traversal_rate": len(subtree_hotspot_hits) / total_hits if total_hits else 0.0,
            "functional_status": "PASS" if functional_pass else "FAIL",
            "hierarchy_precondition_status": hierarchy_precondition_status,
            "rationale": build_retrieval_rationale(
                total_hits=total_hits,
                query_failures=query_failures,
                hierarchy_precondition_status=hierarchy_precondition_status,
                zero_chunk_count=len(zero_chunk_hits),
                parent_only_count=len(parent_only_hits),
            ),
            "failure_samples": {
                "zero_chunk_hits": zero_chunk_hits[:5],
                "parent_only_hits": parent_only_hits[:5],
                "empty_preview_hits": empty_preview_hits[:5],
            },
        }
        write_json("06_evidence_chain_report.json", evidence_payload)
        write_judgment_template(all_hits)
        write_quality_artifacts(all_hits=all_hits, evidence_payload=evidence_payload)

        summary = build_summary(doc_path=doc_path, env=env_payload, ingest=ingest_payload, tree_vector=tree_vector_payload, evidence=evidence_payload)
        (OUT_DIR / "10_validation_summary.md").write_text(summary, encoding="utf-8")

    LOGGER.info("real DOCX hotspot retrieval validation completed")
    LOGGER.info("artifacts_dir=%s", OUT_DIR)
    LOGGER.info("functional_status=%s", evidence_payload["functional_status"])
    LOGGER.info("canonical_spans=%s", ingest_payload["canonical_spans_count"])
    LOGGER.info("tree_nodes=%s", tree_vector_payload["tree_nodes_count"])
    LOGGER.info("vector_chunks=%s", tree_vector_payload["vector_chunks_count"])
    LOGGER.info("query_count=%s", evidence_payload["query_count"])
    LOGGER.info("query_failures=%s", evidence_payload["query_failures"])
    LOGGER.info("total_hits=%s", evidence_payload["total_hits"])
    return 0


def write_quality_artifacts(*, all_hits: list[dict[str, Any]], evidence_payload: dict[str, Any]) -> None:
    metric_status = "NOT_CALCULATED_NO_HITS" if not all_hits else "NOT_CALCULATED_PENDING_JUDGMENTS"
    metric_reason = (
        "Retrieval produced zero hits, so hotspot-specific judgments cannot be collected for this run."
        if not all_hits
        else "Hotspot-specific human judgments are required before hit_rate/top1/stability can be calculated honestly."
    )
    write_json(
        "08_quality_metrics.json",
        {
            "generated_at": now_iso(),
            "status": metric_status,
            "reason": metric_reason,
            "judgment_template": "07_judgment_template.csv",
            "metrics": {
                "hit_rate": None,
                "top1_relevance": None,
                "top3_has_relevant": None,
                "top5_has_relevant": None,
                "stability": None,
            },
        },
    )
    write_json(
        "09_level_assessment.json",
        {
            "generated_at": now_iso(),
            "status": "LEVEL_2_PRESERVED_FUNCTIONAL_VALIDATION_FAILED"
            if evidence_payload["functional_status"] != "PASS"
            else "LEVEL_2_PRESERVED_PENDING_HOTSPOT_JUDGMENTS",
            "level": "Level_2",
            "reason": evidence_payload["rationale"],
            "next_allowed_action": "prepare_hierarchical_or_segmented_transcript_then_rerun_hotspot_validation"
            if evidence_payload["functional_status"] != "PASS"
            else "complete_07_judgment_template_then_calculate_quality_metrics",
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
