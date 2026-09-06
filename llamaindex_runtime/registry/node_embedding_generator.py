#!/usr/bin/env python3
"""
Node Embedding Generator
========================

Compute prototype embeddings for tree nodes (centroid of their chunks' embeddings).

Phase 2 Task 2.1补齐：为 HybridClusterHotspotSelector 提供节点语义表示。
"""

from __future__ import annotations

from uuid import UUID
from typing import Any, Sequence
import numpy as np

from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding


class NodeEmbeddingGenerator:
    """Generate prototype embeddings for tree nodes.

    Prototype embedding = centroid (average vector) of all chunks belonging to the node.

    Workflow:
    1. Extract chunks for each node (from spans mapping)
    2. Compute embeddings for each chunk
    3. Compute centroid embedding for each node
    4. Return list of node_embeddings ready for write_node_embeddings()
    """

    def __init__(
        self,
        *,
        embedding_model: str = "all-MiniLM-L6-v2",
        embed_dim: int = 384,
    ) -> None:
        self._embedding_model = embedding_model
        self._embed_dim = embed_dim
        self._embedder = SentenceTransformersEmbedding(model_name=embedding_model)

    def generate_node_embeddings(
        self,
        *,
        nodes: Sequence[dict[str, Any]],
        spans: Sequence[dict[str, Any]],
        node_spans_mappings: Sequence[dict[str, Any]],
        chunk_embeddings_cache: dict[UUID, list[float]] | None = None,
    ) -> list[dict[str, Any]]:
        """Compute prototype embeddings for each node.

        Args:
            nodes: List of tree nodes (from TreeGenerator.generate_tree)
            spans: List of canonical spans (from registry.query_spans_by_version)
            node_spans_mappings: List of node_id → span_id mappings (from TreeGenerator)
            chunk_embeddings_cache: Optional precomputed chunk embeddings (speed optimization)

        Returns:
            List of node_embeddings dicts with keys:
            - node_id: UUID
            - embedding_model: str
            - embedding_vector: list[float] (centroid)
        """
        if not nodes:
            return []

        # Build span_id → span_text mapping
        span_by_id: dict[UUID, dict[str, Any]] = {}
        for span in spans:
            span_id = UUID(span["span_id"]) if isinstance(span["span_id"], str) else span["span_id"]
            span_by_id[span_id] = span

        # Build node_id → span_ids mapping
        node_to_spans: dict[UUID, list[UUID]] = {}
        for mapping in node_spans_mappings:
            node_id = UUID(mapping["node_id"]) if isinstance(mapping["node_id"], str) else mapping["node_id"]
            span_id = UUID(mapping["span_id"]) if isinstance(mapping["span_id"], str) else mapping["span_id"]

            if node_id not in node_to_spans:
                node_to_spans[node_id] = []
            node_to_spans[node_id].append(span_id)

        # Compute prototype embedding for each node
        node_embeddings: list[dict[str, Any]] = []

        for node in nodes:
            node_id = UUID(node["node_id"]) if isinstance(node["node_id"], str) else node["node_id"]
            node_span_ids = node_to_spans.get(node_id, [])

            if not node_span_ids:
                # Node has no spans (pure route node) — skip (no prototype embedding)
                continue

            # Extract span texts for this node
            span_texts: list[str] = []
            for span_id in node_span_ids:
                span_info = span_by_id.get(span_id)
                if span_info and span_info.get("raw_text"):
                    span_texts.append(span_info["raw_text"])

            if not span_texts:
                # Node's spans have no text content — skip
                continue

            # Compute embeddings for each span/chunk
            chunk_embeddings: list[list[float]] = []

            for span_text in span_texts:
                # Use cache if available (avoid recomputation)
                # Note: chunk_embeddings_cache key should be chunk_id, not span_id
                # For now, we recompute (simple approach)
                embedding = self._embedder._get_text_embedding(span_text)
                if len(embedding) == self._embed_dim:
                    chunk_embeddings.append(embedding)

            if not chunk_embeddings:
                # No valid embeddings — skip
                continue

            # Compute centroid (average vector)
            centroid_embedding = np.mean(chunk_embeddings, axis=0).tolist()

            # Validate dimension
            if len(centroid_embedding) != self._embed_dim:
                # Dimension mismatch — skip (should not happen)
                continue

            node_embeddings.append({
                "node_id": node_id,
                "embedding_model": self._embedding_model,
                "embedding_vector": centroid_embedding,
            })

        return node_embeddings