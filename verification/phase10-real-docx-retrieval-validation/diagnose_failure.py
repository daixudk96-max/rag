from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
QUERY_FALLBACK = "什么是混合检索？"

sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402
from llamaindex_runtime.tree.semantic_distribution import (  # noqa: E402
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    SubtreeHotspotSelector,
)
from llamaindex_runtime.vector.embedder import DeterministicEmbedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
LOGGER = logging.getLogger(__name__)


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


def load_json_artifact(name: str) -> dict[str, Any]:
    path = OUT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_query() -> str:
    query_artifact = OUT_DIR / "04_query_set.json"
    if not query_artifact.exists():
        return QUERY_FALLBACK
    payload = json.loads(query_artifact.read_text(encoding="utf-8"))
    queries = payload.get("queries") or []
    if not queries:
        return QUERY_FALLBACK
    return str(queries[0].get("query_text") or QUERY_FALLBACK)


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        LOGGER.error("DATABASE_URL is not configured")
        return 2

    ingestion = load_json_artifact("02_document_ingestion_status.json")
    version_id = uuid.UUID(str(ingestion["version_id"]))
    query = resolve_query()

    try:
        with psycopg.connect(db_url) as conn:
            payload = build_diagnosis(conn=conn, version_id=version_id, query=query)
    except psycopg.OperationalError:
        LOGGER.error("database connection failed")
        return 2

    diagnosis_path = OUT_DIR / "11_failure_diagnosis.json"
    diagnosis_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )
    if not diagnosis_path.exists() or diagnosis_path.stat().st_size == 0:
        LOGGER.error("diagnosis file write failed")
        return 3

    LOGGER.info("diagnosis written to %s", diagnosis_path)
    LOGGER.info("spans_without_heading_path=%s", payload["spans_without_heading_path"])
    LOGGER.info("tree_nodes_count=%s", payload["tree_nodes_count"])
    LOGGER.info("non_root_nodes_count=%s", payload["non_root_nodes_count"])
    LOGGER.info("selected_hotspots=%s", len(payload["selected_hotspots"]))
    return 0


def build_diagnosis(*, conn: psycopg.Connection, version_id: uuid.UUID, query: str) -> dict[str, Any]:
    registry = PostgresRegistryWriter(conn)
    spans = registry.query_spans_by_version(version_id)
    nodes = registry.query_tree_nodes_by_version(version_id)
    chunks = registry.query_vector_chunks_by_version(version_id)
    report = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )
    query_embedding = DeterministicEmbedder(dim=16).embed_text(query)
    hotspots = SubtreeHotspotSelector().select_hotspots(
        query_embedding=query_embedding,
        node_stats=report["node_stats"],
        tree_signals=report["tree_signals"],
        limit=5,
    )
    policy = BaselineTreeBranchDecisionPolicy(
        dispersion_threshold=1.0,
        entropy_threshold=0.5,
    )
    node_by_id = {node["node_id"]: node for node in nodes}
    children_by_parent: dict[str, list[str]] = {}
    for node in nodes:
        parent_id = node.get("parent_node_id")
        if parent_id is not None:
            children_by_parent.setdefault(str(parent_id), []).append(str(node["node_id"]))

    diagnostic_stats = []
    for stats in report["node_stats"]:
        node_id = stats["node_id"]
        node = node_by_id.get(node_id, {})
        enriched = {
            **stats,
            "query_distance": 1.0,
            "parent_query_distance": 1.0,
        }
        decision = policy.decide_branch_action(
            node_stats=enriched,
            tree_signals=report["tree_signals"],
        )
        diagnostic_stats.append(
            {
                "node_id": node_id,
                "heading_path": node.get("heading_path"),
                "parent_node_id": node.get("parent_node_id"),
                "child_count": len(children_by_parent.get(str(node_id), [])),
                "chunk_count": len(stats.get("chunk_ids", [])),
                "subtree_chunk_count": len(stats.get("subtree_chunk_ids", [])),
                "direct_support_count": stats.get("direct_support_count"),
                "support_count": stats.get("support_count"),
                "is_route_node": stats.get("is_route_node"),
                "dispersion": stats.get("dispersion"),
                "entropy": stats.get("entropy"),
                "baseline_policy_decision_at_query_distance_1": decision,
            }
        )

    return {
        "version_id": version_id,
        "query": query,
        "span_count": len(spans),
        "spans_with_heading_path": sum(1 for span in spans if span.get("heading_path")),
        "spans_without_heading_path": sum(1 for span in spans if not span.get("heading_path")),
        "tree_nodes_count": len(nodes),
        "root_nodes_count": sum(1 for node in nodes if node.get("parent_node_id") is None),
        "non_root_nodes_count": sum(1 for node in nodes if node.get("parent_node_id") is not None),
        "vector_chunks_count": len(chunks),
        "vector_chunks_with_node_id": sum(1 for chunk in chunks if chunk.get("node_id")),
        "tree_signals": report["tree_signals"],
        "selected_hotspots": [
            {
                "node_id": hotspot.node_id,
                "heading_path": node_by_id.get(hotspot.node_id, {}).get("heading_path"),
                "score": hotspot.score,
                "reason": hotspot.reason,
                "support_count": hotspot.support_count,
                "dispersion": hotspot.dispersion,
                "entropy": hotspot.entropy,
                "child_count": len(children_by_parent.get(str(hotspot.node_id), [])),
            }
            for hotspot in hotspots
        ],
        "node_diagnostics": diagnostic_stats,
        "root_cause": "Docling ingestion produced spans but no usable heading_path hierarchy. TreeGenerator therefore built only root-level '(root)' nodes with no child hierarchy. Hotspot selection can only choose root nodes; traversal has no child nodes to drill into, and the baseline semantic path returned no final hits for the query set.",
        "functional_implication": "The real DOCX validates ingestion/vector materialization, but does not validate the Phase 10 parent-hotspot-to-child-evidence behavior because the parsed document lacks a usable hierarchy. A transcript segmentation or heading inference step is required before hotspot traversal can work on this source.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
