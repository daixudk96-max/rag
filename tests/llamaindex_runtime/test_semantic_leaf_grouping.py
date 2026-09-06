"""Tests for minimal semantic grouping seam at leaf level.

These tests verify:
1. Spans with same heading_path but clearly divergent content can split into separate leaf groups
2. Parent heading nodes remain unchanged
3. Summary propagation still works across grouped leaves
4. When content is semantically close, spans stay in one leaf group

This is a minimal seam test for cluster-tree landing slice.
"""
from __future__ import annotations

import uuid

from llamaindex_runtime.registry.tree_generator import TreeGenerator, _detect_semantic_cluster


def _make_span(
    *,
    span_id: uuid.UUID | None = None,
    version_id: uuid.UUID,
    heading_path: str | None = None,
    page_no: int | None = 1,
    text: str = "sample text",
    offset: int = 0,
) -> dict[str, object]:
    """Create a span dict matching the shape returned by query_spans_by_version."""
    return {
        "span_id": span_id or uuid.uuid4(),
        "version_id": version_id,
        "span_kind": "paragraph",
        "start_offset": offset,
        "end_offset": offset + len(text),
        "page_no": page_no,
        "heading_path": heading_path,
        "raw_text": text,
    }


class TestDetectSemanticClusterUnit:
    """Unit tests for the minimal semantic grouping helper."""

    def test_detects_distinct_domains(self) -> None:
        texts = [
            "Machine learning algorithms for neural networks.",
            "Cooking recipes for pasta and sauce.",
        ]

        clusters = _detect_semantic_cluster(texts)

        assert len(clusters) == 2
        assert clusters[0] != clusters[1]

    def test_unclassified_texts_fall_back_to_default_cluster(self) -> None:
        texts = [
            "General introduction with no special keywords.",
            "Another generic paragraph without domain markers.",
        ]

        clusters = _detect_semantic_cluster(texts)

        assert clusters == [0, 0]

    def test_default_cluster_does_not_alias_named_domain_cluster(self) -> None:
        texts = [
            "Machine learning algorithms for neural networks.",
            "Generic text without any domain keywords.",
        ]

        clusters = _detect_semantic_cluster(texts)

        assert len(clusters) == 2
        assert clusters[0] != clusters[1]

    def test_first_matching_domain_wins(self) -> None:
        texts = [
            "Machine learning for stock market forecasting.",
        ]

        clusters = _detect_semantic_cluster(texts)

        assert clusters == [0]


class TestSemanticLeafGrouping:
    """Minimal semantic grouping seam: divergent content splits leaf nodes."""

    def test_same_heading_divergent_content_splits_into_separate_leaves(self) -> None:
        """Spans with same heading_path but clearly different content must split into separate leaf groups."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Machine learning algorithms for neural networks."),
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Cooking recipes for Italian pasta dishes."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Should create multiple leaf nodes for same heading_path
        leaf_nodes = [n for n in result["nodes"] if n["heading_path"] == "Chapter 1" and n["level_no"] == 0]
        assert len(leaf_nodes) >= 2, "Divergent content under same heading must split into multiple leaf groups"

        # Each leaf should have different summary_text
        summaries = [n["summary_text"] for n in leaf_nodes if n["summary_text"]]
        assert len(summaries) >= 2, "Each leaf group must have its own summary"

        # One leaf should contain ML text, another cooking text
        ml_leaf = any("machine learning" in s.lower() for s in summaries)
        cooking_leaf = any("cooking" in s.lower() for s in summaries)
        assert ml_leaf, "One leaf must contain machine learning content"
        assert cooking_leaf, "One leaf must contain cooking content"

    def test_parent_heading_nodes_remain_unchanged(self) -> None:
        """Parent heading nodes must remain unchanged when leaves split."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="Machine learning intro."),
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="Cooking recipes."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Parent nodes (Chapter 1, Section A parent) should still exist
        parent_nodes = [n for n in result["nodes"] if n["level_no"] == 0]
        assert len(parent_nodes) == 1, "Parent Chapter 1 node must exist"

        # Section A should have multiple leaf children
        section_a_nodes = [n for n in result["nodes"] if n["heading_path"] == "Chapter 1 > Section A"]
        assert len(section_a_nodes) >= 2, "Section A must have multiple leaf groups due to divergent content"

    def test_summary_propagation_works_across_grouped_leaves(self) -> None:
        """Summary propagation must aggregate from all leaf groups under same parent."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="ML algorithms."),
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="Cooking recipes."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find parent node (Chapter 1)
        parent_node = [n for n in result["nodes"] if n["level_no"] == 0][0]

        # Parent summary must aggregate from both leaf groups
        assert parent_node["summary_text"] is not None, "Parent must have summary_text"
        assert "ml algorithms" in parent_node["summary_text"].lower(), "Parent must contain ML content"
        assert "cooking recipes" in parent_node["summary_text"].lower(), "Parent must contain cooking content"

    def test_close_content_stays_in_one_leaf(self) -> None:
        """Spans with semantically close content must stay in one leaf group."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Neural network architectures."),
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Deep learning models."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Should create single leaf node for semantically close content
        leaf_nodes = [n for n in result["nodes"] if n["heading_path"] == "Chapter 1" and n["level_no"] == 0]
        assert len(leaf_nodes) == 1, "Close semantic content must stay in single leaf"

        # Leaf must contain both texts
        leaf = leaf_nodes[0]
        assert "neural network" in leaf["summary_text"].lower(), "Leaf must contain neural network text"
        assert "deep learning" in leaf["summary_text"].lower(), "Leaf must contain deep learning text"

    def test_node_spans_link_to_correct_leaf_groups(self) -> None:
        """Node-span links must point to correct leaf group after semantic split."""
        version_id = uuid.uuid4()
        span_ml = uuid.uuid4()
        span_cooking = uuid.uuid4()

        spans = [
            _make_span(span_id=span_ml, version_id=version_id, heading_path="Chapter 1", text="Machine learning algorithms."),
            _make_span(span_id=span_cooking, version_id=version_id, heading_path="Chapter 1", text="Cooking recipes."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find node_spans links
        ml_link = [ns for ns in result["node_spans"] if ns["span_id"] == span_ml]
        cooking_link = [ns for ns in result["node_spans"] if ns["span_id"] == span_cooking]

        assert len(ml_link) == 1, "ML span must have exactly one node_span link"
        assert len(cooking_link) == 1, "Cooking span must have exactly one node_span link"

        # They should link to different nodes
        ml_node_id = ml_link[0]["node_id"]
        cooking_node_id = cooking_link[0]["node_id"]
        assert ml_node_id != cooking_node_id, "Divergent spans must link to different leaf nodes"

    def test_cluster_id_field_added_to_leaf_nodes(self) -> None:
        """Leaf nodes must have cluster_id field to identify semantic group."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Machine learning."),
            _make_span(version_id=version_id, heading_path="Chapter 1", text="Cooking."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_nodes = [n for n in result["nodes"] if n["level_no"] == 0]
        assert len(leaf_nodes) >= 2, "Multiple leaves expected"

        # Each leaf should have a cluster_id field
        for leaf in leaf_nodes:
            assert "cluster_id" in leaf, "Leaf node must have cluster_id field"

        # Different leaves should have different cluster_ids
        cluster_ids = [leaf["cluster_id"] for leaf in leaf_nodes]
        assert len(set(cluster_ids)) >= 2, "Different leaf groups must have different cluster_ids"

    def test_parent_nodes_no_cluster_id(self) -> None:
        """Parent nodes must not have cluster_id field."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="ML."),
            _make_span(version_id=version_id, heading_path="Chapter 1 > Section A", text="Cooking."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Parent nodes should not have cluster_id
        parent_nodes = [n for n in result["nodes"] if n["level_no"] < max(m["level_no"] for m in result["nodes"])]
        for parent in parent_nodes:
            assert "cluster_id" not in parent or parent["cluster_id"] is None, "Parent nodes must not have cluster_id"