from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.tree.semantic_distribution import QueryHit


class TestTreeRuntimeTraversalIntegration:
    def test_backend_retrieval_uses_traversal_runner_when_embeddings_available(self) -> None:
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
                with patch("llamaindex_runtime.tree.runtime.BaselineTreeBranchDecisionPolicy") as policy_cls:
                    runner = runner_cls.return_value
                    runner.traverse_tree_for_query.return_value = traversal_hits

                    hits = retrieve_tree_hits_from_pdf(
                        "/tmp/test.pdf",
                        query="prompt stitching",
                        embed_model=MockEmbedding(embed_dim=32),
                        similarity_top_k=3,
                        registry=mock_registry,
                        version_id=version_id,
                        backend_type="embedding",
                    )

        runner.traverse_tree_for_query.assert_called_once()
        adapter_cls.assert_called_once()
        policy_cls.assert_called_once()
        assert len(hits) == 1
        assert hits[0]["node_id"] == node_id
        assert hits[0]["span_ids"] == [span_id]
        assert hits[0]["score"] == 0.91

    def test_backend_retrieval_falls_back_to_tree_scoring_without_embeddings(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()

        mock_registry = MagicMock()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Section > Prompt",
                "summary_text": "This section explains how prompt stitching works.",
                "page_start": 2,
                "page_end": 2,
            }
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]

        with patch("llamaindex_runtime.tree.runtime.RecursiveTreeTraversalRunner") as runner_cls:
            hits = retrieve_tree_hits_from_pdf(
                "/tmp/test.pdf",
                query="prompt stitching",
                embed_model=None,
                similarity_top_k=3,
                registry=mock_registry,
                version_id=version_id,
                backend_type="embedding",
            )

        runner_cls.assert_not_called()
        assert len(hits) == 1
        assert hits[0]["node_id"] == node_id
        assert hits[0]["span_ids"] == [span_id]
        assert hits[0]["score"] > 0.0
        # Phase 11: Cluster selector adds hotspot/navigation metadata fields
        assert "hotspot_node_id" in hits[0]
        assert "navigation_path" in hits[0]
        assert "drill_depth" in hits[0]
        assert "backend_source" in hits[0]
        assert "retrieval_path" in hits[0]

    def test_runtime_maps_query_hits_back_to_backend_hit_shape(self) -> None:
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
                "summary_text": "Prompt stitching summary",
                "title": "Prompt",
                "page_start": 2,
                "page_end": 2,
                "parent_node_id": None,
            }
        ]
        mock_registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]

        traversal_hits = [
            QueryHit(
                doc_id=uuid.uuid4(),
                version_id=version_id,
                span_id=span_id,
                chunk_id=chunk_id,
                node_id=node_id,
                similarity_score=0.77,
            )
        ]

        with patch("llamaindex_runtime.tree.runtime.RecursiveTreeTraversalRunner") as runner_cls:
            with patch("llamaindex_runtime.tree.runtime.PersistedTreeSemanticDistributionAdapter"):
                with patch("llamaindex_runtime.tree.runtime.BaselineTreeBranchDecisionPolicy"):
                    runner_cls.return_value.traverse_tree_for_query.return_value = traversal_hits

                    hits = retrieve_tree_hits_from_pdf(
                        "/tmp/test.pdf",
                        query="prompt stitching",
                        embed_model=MockEmbedding(embed_dim=32),
                        similarity_top_k=3,
                        registry=mock_registry,
                        version_id=version_id,
                        backend_type="embedding",
                    )

        assert hits == [
            {
                "node_id": node_id,
                "chunk_id": chunk_id,
                "chunk_id_missing": False,
                "score": 0.77,
                "text_preview": "Prompt stitching summary",
                "heading_path": "Section > Prompt",
                "span_ids": [span_id],
                "hotspot_node_id": None,
                "navigation_node_ids": [],
                "navigation_path": [],
                "drill_depth": 0,
                "backend_source": "tree_semantic",
                "retrieval_path": "semantic_traversal",
            }
        ]
