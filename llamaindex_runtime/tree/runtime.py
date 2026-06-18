from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from llama_index.core import StorageContext
from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.ingestion.bundle import build_docling_bundle
from llamaindex_runtime.tree.scoring import TreeScoring
from llamaindex_runtime.vector import create_vector_index

from .backend_adapter import BackendHit
from .evidence_content_resolver import EvidenceContentResolver
from .factory import build_tree_nodes, create_auto_merging_retriever
from .hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy
from .reasoning_backend import ReasoningTreeBackend
from .semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SubtreeHotspotSelector,
    get_hotspot_selector,
)

logger = logging.getLogger(__name__)


# Reserved sentinel for hits that cannot be resolved to a persisted vector chunk.
MISSING_CHUNK_ID = UUID(int=0)


def _retrieve_tree_hits_from_backend(
    query_text: str,
    *,
    version_id: Any,
    registry: Any,
    limit: int,
    embed_model: BaseEmbedding | None = None,
    decision_policy: str = "baseline",
    backend_type: str = "reasoning",
    hotspot_strategy: str = "route_subtree",  # Phase 11: Selector strategy
) -> list[dict[str, Any]]:
    nodes = registry.query_tree_nodes_by_version(version_id)
    if not nodes:
        return []

    resolved_backend_type = backend_type.lower()
    if resolved_backend_type == "reasoning":
        reasoning_backend = ReasoningTreeBackend()
        reasoning_hits = reasoning_backend.retrieve_tree_hits(
            query_text=query_text,
            version_id=version_id,
            registry=registry,
            limit=limit,
        )
        return [_backend_hit_to_dict(hit) for hit in reasoning_hits]

    if resolved_backend_type not in {"embedding", "legacy", "semantic"}:
        raise ValueError(
            "backend_type must be one of 'reasoning', 'embedding', 'legacy', or 'semantic'"
        )

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
    distribution_report = adapter.analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )
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
    # Phase 11: Config-driven hotspot selector
    import os
    logger.info(f"Using hotspot selector strategy: {hotspot_strategy}")
    hotspot_selector = get_hotspot_selector(hotspot_strategy)
    hotspots = hotspot_selector.select_hotspots(
        query_embedding=query_embedding,
        node_stats=distribution_report["node_stats"],
        tree_signals=distribution_report["tree_signals"],
        limit=max(limit, 1),
    )

    query_hits: list[QueryHit] = []
    if hotspots:
        for hotspot in hotspots:
            query_hits.extend(
                runner.traverse_tree_for_query(
                    version_id=version_id,
                    query_embedding=query_embedding,
                    registry=registry,
                    policy=policy,
                    adapter=adapter,
                    start_node_id=hotspot.node_id,
                    hotspot_node_id=hotspot.node_id,
                )
            )
            if len(query_hits) >= limit:
                break
    else:
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
        registry=registry,
        version_id=version_id,
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
    backend_type: str | None = None,
) -> list[Any]:
    """Retrieve tree hits from persisted backend or local PDF fallback.

    Persisted retrieval (``version_id`` + ``registry``) defaults to
    PageIndex-style reasoning navigation.  Pass ``backend_type="embedding"``
    (or ``"legacy"`` / ``"semantic"``) to force the previous embedding-based
    traversal fallback.

    Environment precedence
    ----------------------
    Explicit ``backend_type`` wins.  When it is ``None``,
    ``RAG_TREE_BACKEND_TYPE`` is read from the environment and defaults to
    ``"reasoning"``.  ``decision_policy`` still controls only the explicit
    embedding fallback and defaults from ``RAG_TREE_DECISION_POLICY``.
    """
    # Phase 8: Resolve decision_policy from environment or default
    if decision_policy is None:
        # Check environment variable for Phase 8 default path control
        env_policy = os.environ.get("RAG_TREE_DECISION_POLICY", "baseline")
        decision_policy = env_policy
    if backend_type is None:
        backend_type = os.environ.get("RAG_TREE_BACKEND_TYPE", "reasoning")
    # Phase 11: Resolve hotspot selector strategy from environment or default
    hotspot_strategy = os.environ.get("RAG_TREE_HOTSPOT_SELECTOR", "route_subtree")
    if version_id is not None and registry is not None:
        return _retrieve_tree_hits_from_backend(
            query,
            version_id=version_id,
            registry=registry,
            limit=similarity_top_k,
            embed_model=embed_model,
            decision_policy=decision_policy,
            backend_type=backend_type,
            hotspot_strategy=hotspot_strategy,
        )

    bundle = build_docling_bundle(source_path)
    all_nodes = build_tree_nodes(
        bundle.markdown_documents, chunk_sizes=list(chunk_sizes)
    )
    leaf_nodes = [
        node
        for node in all_nodes
        if node.metadata.get("level") == 1 or not getattr(node, "child_nodes", None)
    ]
    storage_context = StorageContext.from_defaults()
    storage_context.docstore.add_documents(all_nodes)
    index = create_vector_index(
        leaf_nodes, embed_model=embed_model, storage_context=storage_context
    )
    retriever = create_auto_merging_retriever(
        index.as_retriever(similarity_top_k=similarity_top_k),
        storage_context,
        verbose=False,
    )
    return list(retriever.retrieve(query))


def _backend_hit_to_dict(hit: BackendHit) -> dict[str, Any]:
    chunk_id_missing = hit.chunk_id == MISSING_CHUNK_ID
    return {
        "node_id": hit.node_id,
        "chunk_id": hit.chunk_id,
        "chunk_id_missing": chunk_id_missing,
        "score": hit.score,
        "text_preview": hit.text_preview,
        "heading_path": hit.heading_path,
        "page_no": hit.page_no,
        "span_ids": list(hit.span_ids),
        "backend_source": hit.backend_source,
        "retrieval_path": hit.retrieval_path,
    }


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
    registry: Any | None = None,
    version_id: Any | None = None,
) -> list[dict[str, Any]]:
    backend_hits: list[dict[str, Any]] = []
    resolver = EvidenceContentResolver()
    seen_chunks: set[Any] = set()
    for hit in query_hits:
        if hit.chunk_id == MISSING_CHUNK_ID or hit.chunk_id in seen_chunks:
            continue
        node = node_by_id.get(hit.node_id)
        if node is None:
            continue
        span_ids = span_ids_by_node.get(hit.node_id, []) or [hit.span_id]
        fallback_text = node.get("summary_text") or node.get("title") or ""
        text_preview = fallback_text
        if registry is not None and version_id is not None:
            text_preview = resolver.build_text_preview(
                registry=registry,
                version_id=version_id,
                node_id=hit.node_id,
                span_ids=span_ids,
                fallback_text=fallback_text,
                chunk_id=hit.chunk_id,
            )
        # WR-05: Validate navigation completeness before mapping
        missing_nav_ids = [
            node_id for node_id in hit.navigation_node_ids
            if node_id not in node_by_id
        ]
        if missing_nav_ids:
            logger.warning(
                "QueryHit has navigation_node_ids not in node_by_id: %s",
                missing_nav_ids
            )

        navigation_path = [
            node_by_id[node_id].get("heading_path") or node_by_id[node_id].get("title")
            for node_id in hit.navigation_node_ids
            if node_id in node_by_id
        ]
        hit_dict = {
            "node_id": hit.node_id,
            "chunk_id": hit.chunk_id,
            "chunk_id_missing": False,
            "score": hit.similarity_score,
            "text_preview": text_preview,
            "heading_path": node.get("heading_path"),
            "span_ids": list(span_ids),
            "hotspot_node_id": hit.hotspot_node_id,
            "navigation_node_ids": list(hit.navigation_node_ids),
            "navigation_path": navigation_path,
            "drill_depth": hit.drill_depth,
            "backend_source": "tree_semantic",
            "retrieval_path": (
                "subtree_hotspot_traversal"
                if hit.hotspot_node_id is not None
                else "semantic_traversal"
            ),
        }
        backend_hits.append(hit_dict)
        seen_chunks.add(hit.chunk_id)
    return backend_hits
