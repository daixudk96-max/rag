from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree.semantic_distribution import (
    PersistedTreeSemanticDistributionAdapter,
    RecursiveTreeTraversalRunner,
    SemanticDistributionRegistry,
)


class TestHIROTraversalIntegration:
    def test_traversal_calls_evaluate_children_when_node_has_children(self) -> None:
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child_a = uuid.uuid4()
        child_b = uuid.uuid4()
        root_span = uuid.uuid4()
        child_span_a = uuid.uuid4()
        child_span_b = uuid.uuid4()
        root_chunk = uuid.uuid4()
        child_chunk_a = uuid.uuid4()
        child_chunk_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "parent_node_id": None, "level_no": 0},
            {"node_id": child_a, "parent_node_id": root_id, "level_no": 1},
            {"node_id": child_b, "parent_node_id": root_id, "level_no": 1},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": root_id, "span_id": root_span, "ordinal_no": 0},
            {"node_id": child_a, "span_id": child_span_a, "ordinal_no": 0},
            {"node_id": child_b, "span_id": child_span_b, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": root_chunk, "node_id": root_id, "embedding": [1.0, 1.0]},
            {"chunk_id": child_chunk_a, "node_id": child_a, "embedding": [2.0, 2.0]},
            {"chunk_id": child_chunk_b, "node_id": child_b, "embedding": [9.0, 9.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": root_chunk, "span_id": root_span, "ordinal_no": 0},
            {"chunk_id": child_chunk_a, "span_id": child_span_a, "ordinal_no": 0},
            {"chunk_id": child_chunk_b, "span_id": child_span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id
        # Phase 14: Add node-level embeddings query (required by analyze_tree_semantic_distribution)
        registry.query_node_embeddings_by_version.return_value = [
            {"node_id": root_id, "embedding": [1.0, 1.0]},
            {"node_id": child_a, "embedding": [2.0, 2.0]},
            {"node_id": child_b, "embedding": [9.0, 9.0]},
        ]

        adapter = PersistedTreeSemanticDistributionAdapter()
        runner = RecursiveTreeTraversalRunner()

        class PolicyWithEvaluateChildren:
            def __init__(self) -> None:
                self.called = False

            def decide_branch_action(self, *, node_stats, tree_signals):
                return "drill_down" if node_stats["node_id"] == root_id else "keep_parent"

            def evaluate_children(self, *, child_stats, tree_signals):
                self.called = True
                return {
                    "decision": "drill_down",
                    "selected_child_id": child_b,
                    "child_decisions": {
                        child_a: "prune",
                        child_b: "drill_down",
                    },
                }

        policy = PolicyWithEvaluateChildren()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[10.0, 10.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert policy.called is True
        assert hits
        assert all(hit.node_id == child_b for hit in hits)
