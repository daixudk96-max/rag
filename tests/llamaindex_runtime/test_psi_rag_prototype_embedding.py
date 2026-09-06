from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    RecursiveTreeTraversalRunner,
    SemanticDistributionRegistry,
)


class TestPsiRagPrototypeEmbeddingTransplant:
    def test_adapter_exposes_prototype_embedding_in_node_stats(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "heading_path": "Root", "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": node_id, "embedding": [1.0, 3.0]},
            {"chunk_id": chunk_b, "node_id": node_id, "embedding": [3.0, 5.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_id, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_id, "ordinal_no": 1},
        ]

        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        result = adapter.analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )

        assert len(result["node_stats"]) == 1
        node_stats = result["node_stats"][0]
        assert node_stats["prototype_embedding"] == pytest.approx([2.0, 4.0])

    def test_traversal_prefers_prototype_embedding_for_similarity(self) -> None:
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        root_span = uuid.uuid4()
        child_span = uuid.uuid4()
        root_chunk = uuid.uuid4()
        child_chunk = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "parent_node_id": None, "level_no": 0},
            {"node_id": child_id, "parent_node_id": root_id, "level_no": 1},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": root_id, "span_id": root_span, "ordinal_no": 0},
            {"node_id": child_id, "span_id": child_span, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": root_chunk, "node_id": root_id, "embedding": [0.0, 0.0]},
            {"chunk_id": child_chunk, "node_id": child_id, "embedding": [10.0, 10.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": root_chunk, "span_id": root_span, "ordinal_no": 0},
            {"chunk_id": child_chunk, "span_id": child_span, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id

        registry.query_node_embeddings_by_version.return_value = []

        class PrototypeAwarePolicy:
            def decide_branch_action(self, *, node_stats: dict[str, object], tree_signals: dict[str, object]) -> str:
                return "drill_down" if node_stats["node_id"] == root_id else "keep_parent"

        adapter = PersistedTreeSemanticDistributionAdapter()
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[10.0, 10.0],
            registry=registry,
            policy=PrototypeAwarePolicy(),
            adapter=adapter,
        )

        assert hits
        assert all(hit.node_id == child_id for hit in hits)
