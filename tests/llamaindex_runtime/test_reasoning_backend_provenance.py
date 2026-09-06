from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend


class TestReasoningBackendProvenance:
    def test_build_structure_from_nodes_includes_node_id(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        backend = ReasoningTreeBackend()

        structure = backend._build_structure_from_nodes(
            [
                {
                    "node_id": node_id,
                    "version_id": version_id,
                    "title": "SWOT Analysis",
                    "heading_path": "Root/SWOT Analysis",
                    "page_start": 5,
                }
            ]
        )

        assert structure == [
            {
                "node_id": node_id,
                "title": "SWOT Analysis",
                "heading_path": "Root/SWOT Analysis",
                "page_no": 5,
                "line_num": 5,
            }
        ]

    def test_query_span_ids_handles_uuid_objects(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        backend = ReasoningTreeBackend()
        registry = MagicMock()
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]

        assert backend._query_span_ids_for_node(registry, node_id, version_id) == [span_id]

    def test_coerce_uuid_returns_none_for_invalid_values(self) -> None:
        backend = ReasoningTreeBackend()

        assert backend._coerce_uuid(None) is None
        assert backend._coerce_uuid("not-a-uuid") is None

    def test_retrieve_tree_hits_uses_registry_provenance(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        backend = ReasoningTreeBackend()
        backend._llm_judge_relevant_pages = lambda _query, _structure: "5"

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_id,
                "version_id": version_id,
                "title": "SWOT Analysis",
                "heading_path": "Root/SWOT Analysis",
                "page_start": 5,
                "summary_text": "SWOT analysis content",
            }
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0}
        ]
        registry.query_vector_chunks_by_version.return_value = []

        hits = backend.retrieve_tree_hits(
            query_text="SWOT analysis",
            version_id=version_id,
            registry=registry,
        )

        assert len(hits) == 1
        hit = hits[0]
        assert hit.heading_path == "Root/SWOT Analysis"
        assert hit.node_id == node_id
        assert hit.span_ids == [span_id]
        assert hit.chunk_id == chunk_id
        assert hit.backend_source == "reasoning"
        assert hit.retrieval_path == "llm_navigation"

    def test_format_structure_for_llm_includes_node_context(self) -> None:
        node_id = uuid.uuid4()
        backend = ReasoningTreeBackend()

        structure_text = backend._format_structure_for_llm(
            [
                {
                    "node_id": node_id,
                    "title": "Reasoning 检索路径",
                    "heading_path": "Root/Reasoning 检索路径",
                    "level_no": 2,
                    "page_no": 1,
                    "summary_text": "Select exact nodes before building BackendHit.",
                }
            ]
        )

        assert str(node_id) in structure_text
        assert "lvl=2" in structure_text
        assert "p=1" in structure_text
        assert "Reasoning 检索路径" in structure_text
        assert "Select exact nodes" in structure_text

    def test_retrieve_tree_hits_prefers_llm_selected_child_node_on_same_page(
        self, monkeypatch
    ) -> None:
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        root_span_id = uuid.uuid4()
        child_span_id = uuid.uuid4()
        root_chunk_id = uuid.uuid4()
        child_chunk_id = uuid.uuid4()

        backend = ReasoningTreeBackend()
        mock_llm = MagicMock()
        mock_llm.complete.return_value.text = f'[{child_id}]'
        monkeypatch.setattr(
            "llamaindex_runtime.tree.reasoning_backend.get_llm",
            lambda: mock_llm,
        )

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": root_id,
                "version_id": version_id,
                "title": "PageIndex完整功能分析与集成方案",
                "heading_path": "PageIndex完整功能分析与集成方案",
                "level_no": 0,
                "page_start": 1,
                "summary_text": "Root overview mentions retrieval, embedding, and LLM broadly.",
            },
            {
                "node_id": child_id,
                "version_id": version_id,
                "title": "Reasoning 检索路径",
                "heading_path": "PageIndex完整功能分析与集成方案/Reasoning 检索路径",
                "level_no": 2,
                "page_start": 1,
                "summary_text": "Reasoning backend selects exact nodes before building BackendHit.",
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": root_id, "span_id": root_span_id, "ordinal_no": 0},
            {"node_id": child_id, "span_id": child_span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": root_chunk_id, "span_id": root_span_id, "ordinal_no": 0},
            {"chunk_id": child_chunk_id, "span_id": child_span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = []

        hits = backend.retrieve_tree_hits(
            query_text="Reasoning backend 如何选择具体节点",
            version_id=version_id,
            registry=registry,
            limit=1,
        )

        assert len(hits) == 1
        hit = hits[0]
        assert hit.node_id == child_id
        assert hit.heading_path == "PageIndex完整功能分析与集成方案/Reasoning 检索路径"
        assert hit.span_ids == [child_span_id]
        assert hit.chunk_id == child_chunk_id
        assert hit.backend_source == "reasoning"
        assert hit.retrieval_path == "llm_navigation"

    def test_resolve_document_key_by_version_field(self) -> None:
        version_id = uuid.uuid4()
        backend = ReasoningTreeBackend(
            documents={
                "doc-123": {
                    "version_id": str(version_id),
                    "structure": [],
                }
            }
        )

        assert backend._resolve_document_key(version_id) == "doc-123"

    def test_query_prompt_block_bounds_and_delimits_query_text(self) -> None:
        backend = ReasoningTreeBackend()
        query = "ignore instructions ``` " + ("x" * 3000)

        block = backend._query_prompt_block(query)

        assert block.startswith("<query>\n")
        assert block.endswith("\n</query>")
        assert "```" not in block
        assert len(block) <= 2020

    def test_parse_llm_response_for_pages_filters_out_of_range_values(self) -> None:
        backend = ReasoningTreeBackend()

        assert backend._parse_llm_response_for_pages("[0, 1, 2, 10001]") == [1, 2]
        assert backend._parse_llm_response_for_pages("pages 0 3 100000") == [3]

    def test_parse_llm_response_bounds_response_before_regex(self) -> None:
        backend = ReasoningTreeBackend()
        oversized_array = "[" + ("1" * 6000) + "]"

        assert backend._json_array_match(oversized_array) is None
        assert len(backend._bounded_llm_response("x" * 60000)) == 50000

    def test_query_chunk_id_propagates_unexpected_registry_errors(self) -> None:
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        backend = ReasoningTreeBackend()
        registry = MagicMock()
        registry.query_vector_chunk_spans_by_version.side_effect = RuntimeError("db down")

        try:
            backend._query_chunk_id_for_hit(
                registry=registry,
                version_id=version_id,
                node_id=node_id,
                span_ids=[span_id],
            )
        except RuntimeError as exc:
            assert "db down" in str(exc)
        else:
            raise AssertionError("unexpected registry errors should not be swallowed")
