from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree import runtime as tree_runtime
from llamaindex_runtime.tree.backend_adapter import BackendHit


class TestPersistedTreeBackend:
    def test_persisted_tree_backend_defaults_to_reasoning_backend(
        self, monkeypatch
    ) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        calls: dict[str, object] = {}

        class FakeReasoningTreeBackend:
            def __init__(self, **kwargs) -> None:
                calls["init"] = kwargs

            def retrieve_tree_hits(
                self, *, query_text, version_id, registry, limit=None
            ):
                calls["retrieve"] = {
                    "query_text": query_text,
                    "version_id": version_id,
                    "registry": registry,
                    "limit": limit,
                }
                return [
                    BackendHit(
                        score=None,
                        text_preview="Reasoned PageIndex content",
                        heading_path="Root/Relevant",
                        page_no=2,
                        span_ids=[span_id],
                        node_id=node_id,
                        chunk_id=chunk_id,
                        entity_id=None,
                        relation_id=None,
                        backend_source="reasoning",
                        retrieval_path="llm_navigation",
                    )
                ]

        monkeypatch.setattr(
            tree_runtime,
            "ReasoningTreeBackend",
            FakeReasoningTreeBackend,
            raising=False,
        )

        mock_registry = MagicMock()
        mock_registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Root/Relevant",
                "summary_text": "Reasoned PageIndex content",
                "page_start": 2,
                "page_end": 2,
            }
        ]

        hits = tree_runtime.retrieve_tree_hits_from_pdf(
            "/tmp/test.pdf",
            query="prompt stitching",
            embed_model=MagicMock(),
            similarity_top_k=3,
            registry=mock_registry,
            version_id=version_id,
        )

        assert calls["retrieve"] == {
            "query_text": "prompt stitching",
            "version_id": version_id,
            "registry": mock_registry,
            "limit": 3,
        }
        assert hits == [
            {
                "node_id": node_id,
                "chunk_id": chunk_id,
                "chunk_id_missing": False,
                "score": None,
                "text_preview": "Reasoned PageIndex content",
                "heading_path": "Root/Relevant",
                "page_no": 2,
                "span_ids": [span_id],
                "backend_source": "reasoning",
                "retrieval_path": "llm_navigation",
            }
        ]

    def test_persisted_tree_backend_scores_summary_text_when_embedding_fallback_explicit(
        self,
    ) -> None:
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

        hits = tree_runtime.retrieve_tree_hits_from_pdf(
            "/tmp/test.pdf",
            query="prompt stitching",
            embed_model=None,
            similarity_top_k=3,
            registry=mock_registry,
            version_id=version_id,
            backend_type="embedding",
        )

        assert len(hits) == 1
        hit = hits[0]
        assert hit["node_id"] == node_id
        assert hit["heading_path"] == "Section > Prompt"
        assert hit["span_ids"] == [span_id]
        assert (
            hit["text_preview"] == "This section explains how prompt stitching works."
        )
        assert hit["score"] > 0.0

    def test_persisted_tree_backend_returns_empty_when_no_nodes_exist(self) -> None:
        version_id = uuid.uuid4()
        mock_registry = MagicMock()
        mock_registry.query_tree_nodes_by_version.return_value = []
        mock_registry.query_tree_node_spans_by_version.return_value = []

        hits = tree_runtime.retrieve_tree_hits_from_pdf(
            "/tmp/test.pdf",
            query="prompt stitching",
            embed_model=MagicMock(),
            similarity_top_k=3,
            registry=mock_registry,
            version_id=version_id,
        )

        assert hits == []

    def test_hybrid_cluster_backend_hits_preserve_hotspot_order(self) -> None:
        """Hybrid backend ranking should keep selector hotspot order before evidence score."""
        from llamaindex_runtime.tree.semantic_distribution import SubtreeHotspot

        exact_hotspot_id = uuid.uuid4()
        broad_hotspot_id = uuid.uuid4()
        exact_hit = {
            "hotspot_node_id": exact_hotspot_id,
            "score": 0.30,
            "heading_path": "Root > Exact heading",
        }
        broad_hit = {
            "hotspot_node_id": broad_hotspot_id,
            "score": 0.95,
            "heading_path": "Root > Broad high-vector heading",
        }
        hotspots = [
            SubtreeHotspot(
                node_id=exact_hotspot_id,
                score=0.90,
                reason="hybrid_fusion",
                support_count=1,
                dispersion=0.0,
                entropy=0.0,
            ),
            SubtreeHotspot(
                node_id=broad_hotspot_id,
                score=0.80,
                reason="hybrid_fusion",
                support_count=1,
                dispersion=0.0,
                entropy=0.0,
            ),
        ]

        ranked = tree_runtime._rank_backend_hits_for_hotspot_strategy(
            backend_hits=[broad_hit, exact_hit],
            hotspot_strategy="hybrid_cluster",
            hotspots=hotspots,
        )

        assert ranked == [exact_hit, broad_hit]

    def test_non_hybrid_backend_hits_still_sort_by_score_descending(self) -> None:
        """Rollback selectors must keep historical score-descending ranking."""
        low_score_hit = {"hotspot_node_id": uuid.uuid4(), "score": 0.30}
        high_score_hit = {"hotspot_node_id": uuid.uuid4(), "score": 0.95}

        ranked = tree_runtime._rank_backend_hits_for_hotspot_strategy(
            backend_hits=[low_score_hit, high_score_hit],
            hotspot_strategy="route_subtree",
            hotspots=[],
        )

        assert ranked == [high_score_hit, low_score_hit]
