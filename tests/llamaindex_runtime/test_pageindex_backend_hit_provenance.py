from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter


class TestPageIndexBackendHitProvenance:
    def test_retrieve_tree_hits_resolves_real_chunk_id_from_registry(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Chapter 1",
                "page_no": 5,
                "summary_text": "Chapter 1",
                "parent_node_id": None,
            }
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
        ]

        adapter = PageIndexTreeAdapter()
        hits = adapter.retrieve_tree_hits(
            query_text="chapter",
            version_id=version_id,
            registry=registry,
            limit=5,
        )

        assert len(hits) == 1
        assert hits[0].chunk_id == chunk_id
        assert hits[0].span_ids == [span_id]

    def test_retrieve_tree_hits_skips_nodes_without_chunk_provenance(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "heading_path": "Chapter 1",
                "page_no": 5,
                "summary_text": "Chapter 1",
                "parent_node_id": None,
            }
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PageIndexTreeAdapter()
        hits = adapter.retrieve_tree_hits(
            query_text="chapter",
            version_id=version_id,
            registry=registry,
            limit=5,
        )

        assert hits == []
