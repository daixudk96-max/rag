from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.tree.semantic_distribution import QueryHit


class TestTreeRuntimeHIROSelection:
    def test_runtime_uses_hiro_policy_when_explicitly_selected(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        mock_registry = MagicMock()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Section > Prompt",
                "summary_text": "This section explains how prompt stitching works.",
                "page_start": 2,
                "page_end": 2,
                "parent_node_id": None,
            }
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        mock_registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
        ]
        mock_registry.query_doc_id_by_version.return_value = uuid.uuid4()

        traversal_hits = [
            QueryHit(
                doc_id=uuid.uuid4(),
                version_id=version_id,
                span_id=span_id,
                chunk_id=chunk_id,
                node_id=node_id,
                similarity_score=0.91,
            )
        ]

        with patch("llamaindex_runtime.tree.runtime.RecursiveTreeTraversalRunner") as runner_cls:
            with patch("llamaindex_runtime.tree.runtime.PersistedTreeSemanticDistributionAdapter") as adapter_cls:
                with patch("llamaindex_runtime.tree.runtime.HIROEnhancedTreeBranchDecisionPolicy") as hiro_cls:
                    with patch("llamaindex_runtime.tree.runtime.BaselineTreeBranchDecisionPolicy") as baseline_cls:
                        runner_cls.return_value.traverse_tree_for_query.return_value = traversal_hits

                        hits = retrieve_tree_hits_from_pdf(
                            "/tmp/test.pdf",
                            query="prompt stitching",
                            embed_model=MockEmbedding(embed_dim=32),
                            similarity_top_k=3,
                            registry=mock_registry,
                            version_id=version_id,
                            decision_policy="hiro",
                            backend_type="embedding",
                        )

        hiro_cls.assert_called_once()
        baseline_cls.assert_not_called()
        runner_cls.return_value.traverse_tree_for_query.assert_called_once()
        assert len(hits) == 1
        assert hits[0]["node_id"] == node_id
        assert hits[0]["span_ids"] == [span_id]

    def test_runtime_uses_baseline_policy_by_default(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        mock_registry = MagicMock()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Section > Prompt",
                "summary_text": "This section explains how prompt stitching works.",
                "page_start": 2,
                "page_end": 2,
                "parent_node_id": None,
            }
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        mock_registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
        ]
        mock_registry.query_doc_id_by_version.return_value = uuid.uuid4()

        traversal_hits = [
            QueryHit(
                doc_id=uuid.uuid4(),
                version_id=version_id,
                span_id=span_id,
                chunk_id=chunk_id,
                node_id=node_id,
                similarity_score=0.91,
            )
        ]

        with patch("llamaindex_runtime.tree.runtime.RecursiveTreeTraversalRunner") as runner_cls:
            with patch("llamaindex_runtime.tree.runtime.PersistedTreeSemanticDistributionAdapter"):
                with patch("llamaindex_runtime.tree.runtime.HIROEnhancedTreeBranchDecisionPolicy") as hiro_cls:
                    with patch("llamaindex_runtime.tree.runtime.BaselineTreeBranchDecisionPolicy") as baseline_cls:
                        runner_cls.return_value.traverse_tree_for_query.return_value = traversal_hits

                        retrieve_tree_hits_from_pdf(
                            "/tmp/test.pdf",
                            query="prompt stitching",
                            embed_model=MockEmbedding(embed_dim=32),
                            similarity_top_k=3,
                            registry=mock_registry,
                            version_id=version_id,
                            backend_type="embedding",
                        )

        baseline_cls.assert_called_once()
        hiro_cls.assert_not_called()
