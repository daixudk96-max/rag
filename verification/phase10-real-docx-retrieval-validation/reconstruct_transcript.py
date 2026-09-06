from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
STRUCTURED_MARKDOWN_PATH = OUT_DIR / "12_structured_transcript.md"
DEFAULT_TOP_K = 5
MIN_HEADING_PATH_RATE = 0.20
HOTSPOT_METADATA_RATE_THRESHOLD = 0.90
NAVIGATION_PATH_RATE_THRESHOLD = 0.90
LEAF_BUCKET_SIZE = 8
ROOT_HEADING = "进阶版 RAG"
HOTSPOT_BACKEND_TYPE = os.getenv("PHASE10_RECONSTRUCTION_BACKEND_TYPE", "embedding").lower()
VALIDATION_SCOPE = "heuristic_structure_recovery_functional_check"
VALIDATION_LIMITATION = (
    "Document-specific deterministic keyword reconstruction; validates Phase 10 after hierarchy recovery, "
    "not independent hierarchy discovery or quality promotion."
)
DB_PERSISTENCE_MODE = "transaction_rolled_back_after_artifact_generation"
QUERY_SET = [
    {"query_id": "Q01", "query_text": "什么是混合检索？"},
    {"query_id": "Q02", "query_text": "混合检索相比单纯向量检索有什么优势？"},
    {"query_id": "Q03", "query_text": "结构化数据检索在 RAG 中解决什么问题？"},
    {"query_id": "Q04", "query_text": "混合检索和结构化数据检索分别适合什么场景？"},
    {"query_id": "Q05", "query_text": "如果用户问题涉及表格或数据库字段，应该如何检索？"},
    {"query_id": "Q06", "query_text": "文档里如何解释 keyword search 和 vector search 的结合？"},
    {"query_id": "Q07", "query_text": "RAG 系统为什么需要同时处理非结构化和结构化数据？"},
    {"query_id": "Q08", "query_text": "混合检索的整体流程是什么？"},
    {"query_id": "Q09", "query_text": "检索结果如何进行排序或融合？"},
    {"query_id": "Q10", "query_text": "结构化数据查询和普通文档召回有什么区别？"},
    {"query_id": "Q11", "query_text": "这节课提到的进阶版 RAG 核心能力有哪些？"},
    {"query_id": "Q12", "query_text": "如何判断一个问题应该走结构化检索还是文档检索？"},
]

sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from llamaindex_runtime.interfaces import CanonicalSpan  # noqa: E402
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.registry.tree_generator import TreeGenerator  # noqa: E402
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf  # noqa: E402
from llamaindex_runtime.vector.embedder import DeterministicEmbedder  # noqa: E402
from llamaindex_runtime.vector.loader import VectorLoader  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
LOGGER = logging.getLogger(__name__)


class _FakeReconciler:
    """Fake reconciler for verification scripts (non-DB path).

    CLASSIFICATION: NON-E2A HISTORICAL/DIAGNOSTIC

    This reconciler is used by Phase 10 historical diagnostic scripts for
    transcript reconstruction WITHOUT database reconciliation. It returns a
    typed-shaped E2aReconciliationResult for ingestion pipeline compatibility,
    but this is NOT a real E2a reconciliation and MUST NOT be used for Phase 15
    acceptance.

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


class _ValidationRollback(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("rollback validation transaction")
        self.payload = payload


_METADATA_PATTERNS = (
    re.compile(r"^发言人\s+\d{1,2}:\d{2}(?::\d{2})?$"),
    re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}$"),
    re.compile(r"^\[?\d+\]?--.*MP_原文(?:\.docx)?$", re.IGNORECASE),
)

_TOPIC_KEYWORDS = {
    "混合检索": (
        "混合检索",
        "关键词检索",
        "关键词",
        "向量检索",
        "语义向量",
        "多路检索",
        "多路召回",
        "重排",
        "融合",
        "排序",
        "keyword",
        "vector",
        "rerank",
    ),
    "结构化数据检索": (
        "结构化",
        "表格",
        "数据库",
        "字段",
        "sql",
        "SQL",
        "schema",
        "结构化数据",
        "结构化查询",
    ),
    "检索路由与数据源选择": (
        "数据源",
        "路由",
        "工具",
        "API",
        "调用",
        "应该如何检索",
        "走结构化",
        "文档检索",
    ),
    "RAG 检索流程": (
        "RAG",
        "知识库",
        "问答",
        "检索",
        "召回",
        "chunk",
        "上下文",
    ),
}

_LEAF_KEYWORDS = {
    "关键词与向量互补": ("关键词", "向量", "语义向量", "精准匹配", "灵活性"),
    "多路召回与重排融合": ("多路", "召回", "重排", "融合", "排序"),
    "结构化查询与字段匹配": ("结构化", "表格", "数据库", "字段", "SQL", "sql"),
    "检索路由与数据源选择": ("数据源", "路由", "工具", "应该", "选择"),
    "RAG 检索执行流程": ("RAG", "知识库", "问答", "检索", "上下文"),
}


class DeterministicQueryEmbedding:
    def __init__(self, dim: int = 16) -> None:
        self._embedder = DeterministicEmbedder(dim=dim)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._embedder.embed_text(query)


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


def build_base_payload() -> dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "validation_script_version": "2026-06-12-reconstruction-v1",
        "git_commit_sha": safe_git_commit(),
        "source_document": "ANONYMIZED_LOCAL_DOCX",
        "source_document_location": "local_user_supplied_path_redacted",
    }


def resolve_doc_path() -> Path | None:
    raw_path = os.getenv("REAL_VALIDATION_DOCUMENT_PATH")
    if not raw_path:
        return None
    return Path(raw_path).expanduser().resolve()


def load_json_artifact(name: str) -> dict[str, Any] | None:
    path = OUT_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_metadata_line(text: str) -> bool:
    value = text.strip()
    if not value:
        return True
    return any(pattern.match(value) for pattern in _METADATA_PATTERNS)


def clean_transcript_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        text = str(row.get("raw_text") or "").strip()
        if is_metadata_line(text):
            continue
        cleaned.append(
            {
                **row,
                "raw_text": text,
                "source_ordinal": ordinal,
            }
        )
    return cleaned


def classify_topic(text: str) -> str:
    value = text.strip()
    if not value:
        return "其他"
    topic_scores: dict[str, int] = {}
    for topic, keywords in _TOPIC_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in value)
        if score:
            topic_scores[topic] = score
    if not topic_scores:
        return "其他"
    return max(topic_scores.items(), key=lambda item: item[1])[0]


def classify_leaf(text: str, topic: str, ordinal: int) -> str:
    value = text.strip()
    leaf_scores: dict[str, int] = {}
    for leaf, keywords in _LEAF_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in value)
        if score:
            leaf_scores[leaf] = score
    if leaf_scores:
        leaf = max(leaf_scores.items(), key=lambda item: item[1])[0]
    elif topic == "其他":
        leaf = "主题过渡与补充"
    else:
        leaf = f"{topic}主题片段"
    bucket_no = ordinal // LEAF_BUCKET_SIZE + 1
    return f"{bucket_no:02d} {leaf}"


def build_heading_path(*, text: str, ordinal: int, previous_topic: str | None) -> str:
    topic = classify_topic(text)
    if topic == "其他" and previous_topic:
        topic = previous_topic
    elif topic == "其他":
        topic = "RAG 检索流程"
    leaf = classify_leaf(text, topic, ordinal)
    return f"{ROOT_HEADING} > {topic} > {leaf}"


def build_reconstructed_span_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned_rows = clean_transcript_rows(rows)
    reconstructed: list[dict[str, Any]] = []
    previous_topic: str | None = None
    for ordinal, row in enumerate(cleaned_rows):
        text = str(row["raw_text"]).strip()
        heading_path = build_heading_path(
            text=text,
            ordinal=ordinal,
            previous_topic=previous_topic,
        )
        parts = heading_path.split(" > ")
        if len(parts) != 3:
            raise RuntimeError(f"unexpected reconstructed heading_path format: {heading_path}")
        topic = parts[1]
        previous_topic = topic
        reconstructed.append(
            {
                **row,
                "raw_text": text,
                "heading_path": heading_path,
                "reconstructed_ordinal": ordinal,
                "topic": topic,
            }
        )
    return reconstructed


def write_structured_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["heading_path"])].append(row)

    lines = [
        f"# {ROOT_HEADING}",
        "",
        "<!-- Local source path redacted. Generated for Phase 10 heuristic transcript hierarchy recovery validation. -->",
        "",
        f"<!-- Scope: {VALIDATION_SCOPE}. Limitation: {VALIDATION_LIMITATION} -->",
        "",
    ]
    current_topic: str | None = None
    for heading_path, group_rows in sorted(grouped.items(), key=lambda item: item[1][0]["reconstructed_ordinal"]):
        _, topic, leaf = heading_path.split(" > ", maxsplit=2)
        if topic != current_topic:
            lines.extend([f"## {topic}", ""])
            current_topic = topic
        lines.extend([f"### {leaf}", ""])
        for row in group_rows:
            lines.extend([str(row["raw_text"]), ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_canonical_spans(
    *,
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    rows: list[dict[str, Any]],
) -> tuple[CanonicalSpan, ...]:
    spans: list[CanonicalSpan] = []
    offset = 0
    for ordinal, row in enumerate(rows):
        text = str(row["raw_text"]).strip()
        headings = tuple(str(row["heading_path"]).split(" > "))
        span_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{doc_id}|{version_id}|reconstructed|{ordinal}|{row.get('source_ordinal')}|{row.get('span_id')}|{text}",
        )
        spans.append(
            CanonicalSpan(
                doc_id=doc_id,
                version_id=version_id,
                span_id=span_id,
                text=text,
                page_no=row.get("page_no"),
                headings=headings,
                offset=offset,
            )
        )
        offset += len(text) + 1
    return tuple(spans)


def resolve_source_version(
    *,
    conn: psycopg.Connection,
    registry: PostgresRegistryWriter,
    doc_path: Path,
) -> uuid.UUID:
    artifact = load_json_artifact("02_document_ingestion_status.json")
    if artifact and artifact.get("version_id"):
        return uuid.UUID(str(artifact["version_id"]))

    from llamaindex_runtime.ingestion.pipeline import IngestionPipeline

    result = IngestionPipeline(
        registry=registry,
        bundle_root=STRUCTURED_MARKDOWN_PATH.parent / "e2a_bundle",
        connection_factory=lambda: conn,
        reconciler=_FakeReconciler(),
    ).ingest(
        doc_path,
        title="[20] 进阶版RAG 混合检索+结构化数据检索 原文",
    )
    return result.version_id


def register_reconstructed_version(
    *,
    registry: PostgresRegistryWriter,
    rows: list[dict[str, Any]],
) -> tuple[uuid.UUID, uuid.UUID, tuple[CanonicalSpan, ...]]:
    registered = registry.register_document(
        source_path=STRUCTURED_MARKDOWN_PATH,
        source_uri=(
            "local-structured-transcript-redacted://transient/"
            f"{file_sha256(STRUCTURED_MARKDOWN_PATH)}/{uuid.uuid4()}"
        ),
        title="[20] 进阶版RAG 结构化转录稿 heading_path reconstruction",
    )
    existing_spans = registry.query_spans_by_version(registered.version_id)
    if existing_spans:
        spans = tuple(
            CanonicalSpan(
                doc_id=registered.doc_id,
                version_id=registered.version_id,
                span_id=row["span_id"],
                text=row["raw_text"],
                page_no=row.get("page_no"),
                headings=tuple(str(row["heading_path"]).split(" > ")) if row.get("heading_path") else (),
                offset=row["start_offset"],
            )
            for row in existing_spans
        )
        return registered.doc_id, registered.version_id, spans

    spans = build_canonical_spans(
        doc_id=registered.doc_id,
        version_id=registered.version_id,
        rows=rows,
    )
    registry.write_spans(version_id=registered.version_id, spans=spans)
    return registered.doc_id, registered.version_id, spans


def ensure_tree_and_vectors(
    *,
    conn: psycopg.Connection,
    registry: PostgresRegistryWriter,
    version_id: uuid.UUID,
) -> dict[str, Any]:
    spans = registry.query_spans_by_version(version_id)
    if not registry.query_tree_nodes_by_version(version_id):
        generated = TreeGenerator().generate_tree(spans, version_id=version_id)
        registry.write_tree(
            version_id=version_id,
            nodes=generated["nodes"],
            node_spans=generated["node_spans"],
        )
    loader_result = VectorLoader(embed_dim=16).load(conn, version_id)
    nodes = registry.query_tree_nodes_by_version(version_id)
    chunks = registry.query_vector_chunks_by_version(version_id)
    chunk_spans = registry.query_vector_chunk_spans_by_version(version_id)
    node_spans = registry.query_tree_node_spans_by_version(version_id)
    return {
        "spans_count": len(spans),
        "spans_with_heading_path": sum(1 for row in spans if row.get("heading_path")),
        "tree_nodes_count": len(nodes),
        "root_nodes_count": sum(1 for row in nodes if row.get("parent_node_id") is None),
        "non_root_nodes_count": sum(1 for row in nodes if row.get("parent_node_id") is not None),
        "tree_node_spans_count": len(node_spans),
        "vector_loader_result": loader_result,
        "vector_chunks_count": len(chunks),
        "vector_chunk_spans_count": len(chunk_spans),
        "vector_chunks_with_node_id": sum(1 for row in chunks if row.get("node_id") is not None),
        "vector_chunks_with_embedding": sum(1 for row in chunks if row.get("embedding") is not None),
        "sample_nodes": [
            {
                "node_id": row["node_id"],
                "parent_node_id": row.get("parent_node_id"),
                "level_no": row.get("level_no"),
                "heading_path": row.get("heading_path"),
                "summary_preview": (row.get("summary_text") or "")[:240],
            }
            for row in nodes[:20]
        ],
    }


def run_retrieval(
    *,
    registry: PostgresRegistryWriter,
    version_id: uuid.UUID,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    embed_model = DeterministicQueryEmbedding(dim=16)
    query_failures = 0
    all_hits: list[dict[str, Any]] = []
    query_records: list[dict[str, Any]] = []

    for query in QUERY_SET:
        query_id = query["query_id"]
        query_text = query["query_text"]
        query_record: dict[str, Any] = {"query_id": query_id, "query_text": query_text, "status": "PASS", "hits": []}
        try:
            hits = retrieve_tree_hits_from_pdf(
                STRUCTURED_MARKDOWN_PATH,
                query=query_text,
                embed_model=embed_model,  # type: ignore[arg-type]
                similarity_top_k=DEFAULT_TOP_K,
                registry=registry,
                version_id=version_id,
                backend_type=HOTSPOT_BACKEND_TYPE,
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
            query_records.append(query_record)
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
        query_records.append(query_record)

    return (
        {
            **build_base_payload(),
            "validation_scope": VALIDATION_SCOPE,
            "validation_limitation": VALIDATION_LIMITATION,
            "backend_type": HOTSPOT_BACKEND_TYPE,
            "query_count": len(QUERY_SET),
            "query_failures": query_failures,
            "total_hits": len(all_hits),
            "queries": query_records,
        },
        all_hits,
    )


def build_evidence_payload(
    *,
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    tree_vector: dict[str, Any],
    retrieval_results: dict[str, Any],
    all_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    total_hits = len(all_hits)
    zero_chunk_hits = [hit for hit in all_hits if hit.get("chunk_id_missing") is True or str(hit.get("chunk_id")) == str(uuid.UUID(int=0))]
    parent_only_hits = [hit for hit in all_hits if not hit.get("span_ids")]
    missing_node_hits = [hit for hit in all_hits if not hit.get("node_id")]
    empty_preview_hits = [hit for hit in all_hits if not (hit.get("text_preview") or "").strip()]
    hotspot_metadata_hits = [hit for hit in all_hits if hit.get("hotspot_node_id")]
    navigation_path_hits = [hit for hit in all_hits if hit.get("navigation_path")]
    subtree_hotspot_hits = [hit for hit in all_hits if hit.get("retrieval_path") == "subtree_hotspot_traversal"]
    heading_path_rate = (
        tree_vector["spans_with_heading_path"] / tree_vector["spans_count"]
        if tree_vector["spans_count"]
        else 0.0
    )
    hierarchy_precondition_status = "PASS" if heading_path_rate >= MIN_HEADING_PATH_RATE else "FAIL"
    functional_pass = (
        hierarchy_precondition_status == "PASS"
        and retrieval_results["query_failures"] == 0
        and total_hits > 0
        and len(zero_chunk_hits) == 0
        and len(parent_only_hits) == 0
        and (len(hotspot_metadata_hits) / total_hits if total_hits else 0.0) >= HOTSPOT_METADATA_RATE_THRESHOLD
        and (len(navigation_path_hits) / total_hits if total_hits else 0.0) >= NAVIGATION_PATH_RATE_THRESHOLD
    )
    rationale = (
        "Structured transcript reconstruction produced hierarchical heading_path values, tree/vector materialization succeeded, "
        "and hotspot retrieval returned final evidence-bearing child hits."
        if functional_pass
        else "Structured transcript reconstruction ran, but the evidence-chain pass criteria were not fully met."
    )
    return {
        **build_base_payload(),
        "validation_scope": VALIDATION_SCOPE,
        "validation_limitation": VALIDATION_LIMITATION,
        "backend_type": HOTSPOT_BACKEND_TYPE,
        "db_persistence_mode": DB_PERSISTENCE_MODE,
        "doc_id": doc_id,
        "version_id": version_id,
        "query_count": len(QUERY_SET),
        "query_failures": retrieval_results["query_failures"],
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
        "heading_path_rate": heading_path_rate,
        "hierarchy_precondition_status": hierarchy_precondition_status,
        "functional_status": "PASS" if functional_pass else "FAIL",
        "rationale": rationale,
        "failure_samples": {
            "zero_chunk_hits": zero_chunk_hits[:5],
            "parent_only_hits": parent_only_hits[:5],
            "empty_preview_hits": empty_preview_hits[:5],
        },
    }


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
    with (OUT_DIR / "15_reconstructed_judgment_template.csv").open("w", newline="", encoding="utf-8") as csvfile:
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


def build_summary(
    *,
    source_version_id: uuid.UUID,
    reconstructed_doc_id: uuid.UUID,
    reconstructed_version_id: uuid.UUID,
    reconstruction: dict[str, Any],
    tree_vector: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 10 Reconstructed Transcript Hotspot Validation Summary",
            "",
            f"**Status:** {evidence['functional_status']}",
            f"**Generated:** {now_iso()}",
            "",
            "## Reconstruction",
            "",
            f"- validation_scope: `{VALIDATION_SCOPE}`",
            f"- validation_limitation: {VALIDATION_LIMITATION}",
            f"- backend_type: `{HOTSPOT_BACKEND_TYPE}`",
            f"- db_persistence_mode: `{DB_PERSISTENCE_MODE}`",
            f"- source_version_id: `{source_version_id}`",
            f"- reconstructed_doc_id: `{reconstructed_doc_id}`",
            f"- reconstructed_version_id: `{reconstructed_version_id}`",
            "- source document path: `ANONYMIZED_LOCAL_DOCX` (local path redacted)",
            "- structured markdown: `12_structured_transcript.md`",
            f"- source_spans: `{reconstruction['source_spans_count']}`",
            f"- content_spans_after_metadata_filter: `{reconstruction['content_spans_count']}`",
            f"- reconstructed_heading_path_rate: `{reconstruction['heading_path_rate']}`",
            "",
            "## Tree / Vector Status",
            "",
            f"- tree_nodes: `{tree_vector['tree_nodes_count']}`",
            f"- non_root_nodes: `{tree_vector['non_root_nodes_count']}`",
            f"- tree_node_spans: `{tree_vector['tree_node_spans_count']}`",
            f"- vector_chunks: `{tree_vector['vector_chunks_count']}`",
            f"- vector_chunk_spans: `{tree_vector['vector_chunk_spans_count']}`",
            f"- vector_chunks_with_node_id: `{tree_vector['vector_chunks_with_node_id']}`",
            f"- vector_chunks_with_embedding: `{tree_vector['vector_chunks_with_embedding']}`",
            "",
            "## Retrieval Evidence Chain",
            "",
            f"- query_count: `{evidence['query_count']}`",
            f"- query_failures: `{evidence['query_failures']}`",
            f"- total_hits: `{evidence['total_hits']}`",
            f"- zero_chunk_hits: `{evidence['zero_chunk_hits']}`",
            f"- parent_only_hits: `{evidence['parent_only_hits']}`",
            f"- hotspot_metadata_hits: `{evidence['hotspot_metadata_hits']}`",
            f"- navigation_path_hits: `{evidence['navigation_path_hits']}`",
            f"- subtree_hotspot_traversal_hits: `{evidence['subtree_hotspot_traversal_hits']}`",
            f"- hierarchy_precondition_status: `{evidence['hierarchy_precondition_status']}`",
            "",
            "## Decision",
            "",
            f"- functional_status: `{evidence['functional_status']}`",
            f"- rationale: {evidence['rationale']}",
            "- Quality metrics still require hotspot-specific human judgments before any Level promotion.",
            "- `Level_2` remains authoritative until judged quality metrics are calculated.",
            "",
        ]
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    load_dotenv(REPO_ROOT / ".env", override=False)
    doc_path = resolve_doc_path()
    db_url = os.getenv("DATABASE_URL")
    if doc_path is None:
        LOGGER.error("REAL_VALIDATION_DOCUMENT_PATH is not configured")
        return 2
    if not doc_path.exists():
        LOGGER.error("source document not found")
        return 2
    if not db_url:
        LOGGER.error("DATABASE_URL is not configured")
        return 2

    try:
        with psycopg.connect(db_url) as conn:
            try:
                with conn.transaction():
                    # The reconstructed document/version is materialized only inside
                    # this transaction. Raising _ValidationRollback lets psycopg roll
                    # back DB writes while preserving the local validation payload.
                    payload = run_reconstruction_validation(conn=conn, doc_path=doc_path)
                    raise _ValidationRollback(payload)
            except _ValidationRollback as rollback:
                payload = rollback.payload
    except psycopg.OperationalError:
        LOGGER.error("database connection failed")
        return 2
    except (RuntimeError, ValueError, KeyError) as exc:
        LOGGER.error("reconstructed validation failed: %s", type(exc).__name__)
        return 1

    LOGGER.info("reconstructed transcript validation completed")
    LOGGER.info("functional_status=%s", payload["evidence"]["functional_status"])
    LOGGER.info("source_spans=%s", payload["reconstruction"]["source_spans_count"])
    LOGGER.info("content_spans=%s", payload["reconstruction"]["content_spans_count"])
    LOGGER.info("tree_nodes=%s", payload["tree_vector"]["tree_nodes_count"])
    LOGGER.info("non_root_nodes=%s", payload["tree_vector"]["non_root_nodes_count"])
    LOGGER.info("vector_chunks=%s", payload["tree_vector"]["vector_chunks_count"])
    LOGGER.info("query_count=%s", payload["evidence"]["query_count"])
    LOGGER.info("query_failures=%s", payload["evidence"]["query_failures"])
    LOGGER.info("total_hits=%s", payload["evidence"]["total_hits"])
    return 0


def run_reconstruction_validation(*, conn: psycopg.Connection, doc_path: Path) -> dict[str, Any]:
    registry = PostgresRegistryWriter(conn)
    if not registry.healthcheck():
        raise RuntimeError("registry healthcheck failed")

    source_version_id = resolve_source_version(conn=conn, registry=registry, doc_path=doc_path)
    source_spans = registry.query_spans_by_version(source_version_id)
    reconstructed_rows = build_reconstructed_span_rows(source_spans)
    if not reconstructed_rows:
        raise RuntimeError("transcript reconstruction produced zero content spans")

    write_structured_markdown(reconstructed_rows, STRUCTURED_MARKDOWN_PATH)
    reconstructed_doc_id, reconstructed_version_id, reconstructed_spans = register_reconstructed_version(
        registry=registry,
        rows=reconstructed_rows,
    )
    tree_vector = ensure_tree_and_vectors(
        conn=conn,
        registry=registry,
        version_id=reconstructed_version_id,
    )
    retrieval_results, all_hits = run_retrieval(
        registry=registry,
        version_id=reconstructed_version_id,
    )
    evidence = build_evidence_payload(
        doc_id=reconstructed_doc_id,
        version_id=reconstructed_version_id,
        tree_vector=tree_vector,
        retrieval_results=retrieval_results,
        all_hits=all_hits,
    )

    topic_counts = Counter(row["topic"] for row in reconstructed_rows)
    reconstruction_payload = {
        **build_base_payload(),
        "source_document_sha256": file_sha256(doc_path),
        "validation_scope": VALIDATION_SCOPE,
        "validation_limitation": VALIDATION_LIMITATION,
        "backend_type": HOTSPOT_BACKEND_TYPE,
        "db_persistence_mode": DB_PERSISTENCE_MODE,
        "source_version_id": source_version_id,
        "reconstructed_doc_id": reconstructed_doc_id,
        "reconstructed_version_id": reconstructed_version_id,
        "source_spans_count": len(source_spans),
        "content_spans_count": len(reconstructed_rows),
        "reconstructed_spans_count": len(reconstructed_spans),
        "metadata_rows_removed": len(source_spans) - len(reconstructed_rows),
        "heading_path_rate": 1.0 if reconstructed_rows else 0.0,
        "topic_counts": dict(topic_counts),
        "structured_markdown_artifact": "12_structured_transcript.md",
        "sample_reconstructed_spans": [
            {
                "source_span_id": row.get("span_id"),
                "heading_path": row.get("heading_path"),
                "text_preview": row.get("raw_text", "")[:240],
            }
            for row in reconstructed_rows[:12]
        ],
    }

    write_json("12_reconstruction_report.json", reconstruction_payload)
    write_json("13_reconstructed_hotspot_retrieval_results.json", retrieval_results)
    write_json("14_reconstructed_evidence_chain_report.json", evidence)
    write_judgment_template(all_hits)
    summary = build_summary(
        source_version_id=source_version_id,
        reconstructed_doc_id=reconstructed_doc_id,
        reconstructed_version_id=reconstructed_version_id,
        reconstruction=reconstruction_payload,
        tree_vector=tree_vector,
        evidence=evidence,
    )
    (OUT_DIR / "16_reconstructed_validation_summary.md").write_text(summary, encoding="utf-8")

    return {
        "reconstruction": reconstruction_payload,
        "tree_vector": tree_vector,
        "retrieval_results": retrieval_results,
        "evidence": evidence,
    }


if __name__ == "__main__":
    raise SystemExit(main())
