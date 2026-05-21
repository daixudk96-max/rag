from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from llama_index.core import StorageContext
from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.ingestion.bundle import build_docling_bundle
from llamaindex_runtime.tree.query import TreeRollupQuery
from llamaindex_runtime.tree.scoring import TreeScoring
from llamaindex_runtime.vector import create_vector_index

from .factory import build_tree_nodes, create_auto_merging_retriever
from .hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy
from .semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
)


def _retrieve_tree_hits_from_backend(
    query_text: str,
    *,
    version_id: Any,
    registry: Any,
    limit: int,
    embed_model: BaseEmbedding | None = None,
    decision_policy: str = "baseline",
) -> list[dict[str, Any]]:
    nodes = registry.query_tree_nodes_by_version(version_id)
    if not nodes:
        return []

    span_rows = registry.query_tree_node_spans_by_version(version_id)
    span_ids_by_node: dict[Any, list[Any]] = {}
    for row in span_rows:
        span_ids_by_node.setdefault(row["node_id"], []).append(row["span_id"])

    if embed_model is None:
        return _score_tree_nodes_with_fallback(
            nodes=nodes,
            query_text=query_text,
            span_ids_by_node=span_ids_by_node,
            limit=limit,
        )

    query_embedding = embed_model.get_query_embedding(query_text)
    adapter = PersistedTreeSemanticDistributionAdapter()
    if decision_policy == "hiro":
        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )
    else:
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
    runner = RecursiveTreeTraversalRunner()
    query_hits = runner.traverse_tree_for_query(
        version_id=version_id,
        query_embedding=query_embedding,
        registry=registry,
        policy=policy,
        adapter=adapter,
    )

    node_by_id = {node["node_id"]: node for node in nodes}
    backend_hits = _map_query_hits_to_backend_hits(
        query_hits=query_hits,
        node_by_id=node_by_id,
        span_ids_by_node=span_ids_by_node,
    )
    if not backend_hits:
        return _score_tree_nodes_with_fallback(
            nodes=nodes,
            query_text=query_text,
            span_ids_by_node=span_ids_by_node,
            limit=limit,
        )
    backend_hits.sort(key=lambda item: item["score"], reverse=True)
    return backend_hits[:limit]


def retrieve_tree_hits_from_pdf(
    source_path: str | Path,
    *,
    query: str,
    embed_model: BaseEmbedding | None,
    similarity_top_k: int = 4,
    chunk_sizes: Sequence[int] = (256, 96),
    version_id: Any | None = None,
    registry: Any | None = None,
    decision_policy: str | None = None,  # Phase 8: None = use environment/default
) -> list[Any]:
    # Phase 8: Resolve decision_policy from environment or default
    if decision_policy is None:
        # Check environment variable for Phase 8 default path control
        env_policy = os.environ.get("RAG_TREE_DECISION_POLICY", "baseline")
        decision_policy = env_policy
    if version_id is not None and registry is not None:
        return _retrieve_tree_hits_from_backend(
            query,
            version_id=version_id,
            registry=registry,
            limit=similarity_top_k,
            embed_model=embed_model,
            decision_policy=decision_policy,
        )

    bundle = build_docling_bundle(source_path)
    all_nodes = build_tree_nodes(bundle.markdown_documents, chunk_sizes=list(chunk_sizes))
    leaf_nodes = [node for node in all_nodes if node.metadata.get("level") == 1 or not getattr(node, "child_nodes", None)]
    storage_context = StorageContext.from_defaults()
    storage_context.docstore.add_documents(all_nodes)
    index = create_vector_index(leaf_nodes, embed_model=embed_model, storage_context=storage_context)
    retriever = create_auto_merging_retriever(
        index.as_retriever(similarity_top_k=similarity_top_k),
        storage_context,
        verbose=False,
    )
    return list(retriever.retrieve(query))


def _score_tree_nodes_with_fallback(
    *,
    nodes: list[dict[str, Any]],
    query_text: str,
    span_ids_by_node: dict[Any, list[Any]],
    limit: int,
) -> list[dict[str, Any]]:
    scoring = TreeScoring()
    scored_nodes: list[dict[str, Any]] = []
    for node in nodes:
        score = scoring.score_node(node, query_text)
        if score <= 0.0:
            continue
        scored_nodes.append(
            {
                "node_id": node["node_id"],
                "score": score,
                "text_preview": node.get("summary_text") or node.get("title") or "",
                "heading_path": node.get("heading_path"),
                "span_ids": span_ids_by_node.get(node["node_id"], []),
            }
        )

    scored_nodes.sort(key=lambda item: item["score"], reverse=True)
    return scored_nodes[:limit]


def _map_query_hits_to_backend_hits(
    *,
    query_hits: list[QueryHit],
    node_by_id: dict[Any, dict[str, Any]],
    span_ids_by_node: dict[Any, list[Any]],
) -> list[dict[str, Any]]:
    backend_hits: list[dict[str, Any]] = []
    for hit in query_hits:
        node = node_by_id.get(hit.node_id)
        if node is None:
            continue
        backend_hits.append(
            {
                "node_id": hit.node_id,
                "score": hit.similarity_score,
                "text_preview": node.get("summary_text") or node.get("title") or "",
                "heading_path": node.get("heading_path"),
                "span_ids": [hit.span_id],
            }
        )
    return backend_hits
