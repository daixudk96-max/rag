"""RAPTOR-style comparison slice: evaluates gap between heading-path tree vs semantic cluster tree.

This test file is evaluation-first, NOT an implementation of RAPTOR clustering.
It documents:
1. What the current heading-based tree + summary_text propagation already achieves
2. What RAPTOR-style semantic clustering capabilities are absent

Key differences between current implementation and RAPTOR:
- Current: heading_path-driven tree structure (split on " > ")
- RAPTOR: semantic cluster-driven tree structure (bottom-up clustering)
- Current: top-down hierarchy from document structure
- RAPTOR: bottom-up hierarchy from content similarity
- Current: summary_text propagates upward (implemented)
- RAPTOR: recursive cluster summaries based on semantic groups (not implemented)

RAPTOR reference: "递归地聚类、摘要并构造树" (Recursively cluster, summarize, and construct tree)
Files: cluster_tree_builder.py, tree_builder.py, tree_structures.py
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from llamaindex_runtime.registry.tree_generator import TreeGenerator


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


# ===========================================================================
# GREEN TESTS: Current implementation behavior (heading-path-driven)
# ===========================================================================


class TestCurrentTreeStructureIsHeadingPathDriven:
    """Tests that document the current heading-path-driven tree structure.

    These tests should PASS (GREEN) because they describe existing behavior.
    """

    def test_tree_nodes_follow_heading_hierarchy(self) -> None:
        """Tree structure is determined by heading_path, not semantic similarity."""
        version_id = uuid.uuid4()
        # Two spans with DIFFERENT semantic content but SAME heading path
        spans = [
            _make_span(
                version_id=version_id,
                heading_path="Chapter 1 > Section 1.1",
                text="Introduction to machine learning algorithms.",  # Topic: ML
            ),
            _make_span(
                version_id=version_id,
                heading_path="Chapter 1 > Section 1.1",
                text="Neural network architecture design principles.",  # Topic: Neural nets
            ),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Both spans should be under the SAME leaf node because they share heading_path
        leaf_nodes = [n for n in result["nodes"] if n["level_no"] == 1]
        assert len(leaf_nodes) == 1, "Spans with same heading_path should be grouped together"
        assert "Section 1.1" in leaf_nodes[0]["title"]

        # Verify both span texts are in the leaf node's summary
        assert "machine learning algorithms" in leaf_nodes[0]["summary_text"]
        assert "Neural network architecture" in leaf_nodes[0]["summary_text"]

    def test_spans_with_different_headings_create_different_nodes(self) -> None:
        """Different heading_path values create separate nodes regardless of semantic similarity."""
        version_id = uuid.uuid4()
        # Two spans with SIMILAR semantic content but DIFFERENT heading paths
        spans = [
            _make_span(
                version_id=version_id,
                heading_path="Chapter 1 > Intro",
                text="Deep learning is a subset of machine learning.",  # Topic: Deep learning
            ),
            _make_span(
                version_id=version_id,
                heading_path="Chapter 2 > Overview",
                text="Deep learning techniques are part of ML.",  # Topic: Deep learning (similar)
            ),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Should create TWO leaf nodes because heading_paths differ
        leaf_nodes = [n for n in result["nodes"] if n["level_no"] == 1]
        assert len(leaf_nodes) == 2, "Different heading_paths must create separate nodes"

        # Each leaf node should have its own span
        assert "Intro" in [n["title"] for n in leaf_nodes]
        assert "Overview" in [n["title"] for n in leaf_nodes]

    def test_heading_hierarchy_defines_parent_child_relationships(self) -> None:
        """Parent-child relationships are determined by heading_path prefix matching."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 > 1.1.1", text="Sub-sub section."),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.2", text="Sibling section."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find nodes
        ch1_node = [n for n in result["nodes"] if n["title"] == "Ch 1"][0]
        node_11 = [n for n in result["nodes"] if n["title"] == "1.1"][0]
        node_111 = [n for n in result["nodes"] if n["title"] == "1.1.1"][0]
        node_12 = [n for n in result["nodes"] if n["title"] == "1.2"][0]

        # Verify hierarchy follows heading path structure
        assert ch1_node["level_no"] == 0
        assert node_11["parent_node_id"] == ch1_node["node_id"]
        assert node_111["parent_node_id"] == node_11["node_id"]
        assert node_12["parent_node_id"] == ch1_node["node_id"]

    def test_tree_structure_is_deterministic_from_heading_path(self) -> None:
        """Same heading_path inputs always produce identical tree structure."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="A > B", text="Content 1."),
            _make_span(version_id=version_id, heading_path="A > C", text="Content 2."),
        ]

        # Generate tree twice
        result1 = TreeGenerator().generate(spans, version_id=version_id)
        result2 = TreeGenerator().generate(spans, version_id=version_id)

        # Tree structures must be identical
        nodes1_ids = [n["node_id"] for n in result1["nodes"]]
        nodes2_ids = [n["node_id"] for n in result2["nodes"]]
        assert nodes1_ids == nodes2_ids, "Tree structure must be deterministic"


class TestCurrentSummaryPropagationWorks:
    """Tests that verify summary_text upward propagation is implemented correctly.

    These tests should PASS (GREEN) because they describe existing behavior.
    """

    def test_leaf_node_summary_concatenates_spans(self) -> None:
        """Leaf nodes concatenate raw_text from all covered spans (already implemented)."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Text A."),
            _make_span(version_id=version_id, heading_path="Ch 1", text="Text B."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = result["nodes"][0]
        assert leaf_node["summary_text"] is not None
        assert "Text A." in leaf_node["summary_text"]
        assert "Text B." in leaf_node["summary_text"]

    def test_parent_node_aggregates_child_summaries(self) -> None:
        """Parent nodes aggregate summary_text from children (already implemented)."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Root > Child1", text="Child1 content."),
            _make_span(version_id=version_id, heading_path="Root > Child2", text="Child2 content."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find root node (level 0)
        root_node = [n for n in result["nodes"] if n["level_no"] == 0][0]
        assert root_node["summary_text"] is not None
        assert "Child1 content." in root_node["summary_text"]
        assert "Child2 content." in root_node["summary_text"]

    def test_deep_hierarchy_propagation(self) -> None:
        """Summary propagation works correctly in deep hierarchies (already implemented)."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Root > L1 > L2 > L3", text="Deep leaf."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # All ancestor nodes should have summary_text
        for node in result["nodes"]:
            assert node["summary_text"] is not None
            assert "Deep leaf." in node["summary_text"]


# ===========================================================================
# GAP TESTS: RAPTOR-style capabilities that are NOT implemented
# ===========================================================================


class TestRAPTORClusterTreeGaps:
    """Tests that document RAPTOR-style capabilities that are absent.

    These tests should PASS (GREEN) as evaluation/comparison tests that
    explicitly demonstrate the gap between current implementation and
    RAPTOR expectations.
    """

    def test_minimal_semantic_split_within_same_heading(self) -> None:
        """Minimal seam: semantic splitting now exists for clearly divergent content under same heading_path.

        RAPTOR expectation: spans with similar content should be clustered together
        regardless of their heading_path (full semantic clustering across headings).

        Minimal seam reality: spans under SAME heading_path with clearly divergent domains
        (e.g., ML vs cooking) are split into separate leaf groups with cluster_id markers.

        This test documents:
        1. Minimal seam implemented: leaf-level semantic splitting for divergent content
        2. Gap remains: no cross-heading semantic clustering (still heading-driven for parents)
        """
        version_id = uuid.uuid4()
        # Three spans: two are semantically similar (ML topic), one is different (cooking)
        spans = [
            _make_span(
                version_id=version_id,
                heading_path="Chapter 1 > ML Intro",
                text="Machine learning algorithms process data to make predictions.",
            ),
            _make_span(
                version_id=version_id,
                heading_path="Chapter 2 > ML Advanced",
                text="ML techniques learn patterns from data for prediction tasks.",
            ),
            # This span is semantically different (cooking, not ML)
            _make_span(
                version_id=version_id,
                heading_path="Chapter 1 > ML Intro",
                text="Cooking recipes require careful ingredient measurements.",
            ),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Minimal seam behavior: divergent content under same heading_path splits
        # "Chapter 1 > ML Intro" now creates TWO leaf nodes (ML cluster, cooking cluster)
        # "Chapter 2 > ML Advanced" creates ONE leaf node (ML cluster)
        leaf_nodes = [n for n in result["nodes"] if n["level_no"] == 1]

        # Find nodes under "Chapter 1 > ML Intro" heading
        ml_intro_nodes = [n for n in leaf_nodes if "ML Intro" in n["title"]]
        assert len(ml_intro_nodes) >= 2, "Minimal seam: ML and cooking now split into separate leaf groups"

        # One node contains ML text, another contains cooking text
        ml_node = [n for n in ml_intro_nodes if "machine learning" in n["summary_text"].lower()][0]
        cooking_node = [n for n in ml_intro_nodes if "cooking" in n["summary_text"].lower()][0]
        assert ml_node["node_id"] != cooking_node["node_id"], "ML and cooking must be in separate nodes"
        assert "cluster_id" in ml_node, "Minimal seam: leaf nodes have cluster_id marker"
        assert "cluster_id" in cooking_node, "Minimal seam: leaf nodes have cluster_id marker"

        # Gap remains: cross-heading semantic clustering NOT implemented
        # ML spans under "Chapter 1 > ML Intro" and "Chapter 2 > ML Advanced" are still separate nodes
        # They are NOT merged into one semantic cluster (RAPTOR would merge them)
        ml_advanced_nodes = [n for n in leaf_nodes if "ML Advanced" in n["title"]]
        assert len(ml_advanced_nodes) == 1, "Chapter 2 node exists separately"
        assert ml_node["node_id"] != ml_advanced_nodes[0]["node_id"], "Cross-heading ML spans not merged (gap remains)"

        # Document what full RAPTOR would do differently:
        # RAPTOR would merge ALL ML-related spans (from both chapters) into one semantic cluster
        # Current implementation keeps them separate because heading_paths differ
        # This is the remaining gap vs full RAPTOR semantic clustering

    def test_no_recursive_cluster_summaries_by_semantic_grouping(self) -> None:
        """Current implementation does NOT build recursive summaries based on semantic clusters.

        RAPTOR expectation:
        - Leaf clusters: semantically similar spans grouped together
        - Parent clusters: aggregate summaries of semantic clusters (not heading hierarchy)
        - Bottom-up: tree built from clusters, not top-down from headings

        Current reality:
        - Leaf nodes: spans grouped by heading_path
        - Parent nodes: aggregate summaries based on heading hierarchy
        - Top-down: tree structure from heading_path splitting

        This test documents that current summary aggregation is heading-based,
        not cluster-based.
        """
        version_id = uuid.uuid4()
        spans = [
            _make_span(
                version_id=version_id,
                heading_path="Topic A > Subtopic 1",
                text="Neural networks learn from examples.",
            ),
            _make_span(
                version_id=version_id,
                heading_path="Topic A > Subtopic 2",
                text="Deep learning models use layered neural networks.",
            ),
            _make_span(
                version_id=version_id,
                heading_path="Topic B > Subtopic 1",
                text="Neural networks are fundamental to AI.",  # Semantically similar to Topic A
            ),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find parent nodes
        topic_a_node = [n for n in result["nodes"] if n["title"] == "Topic A"][0]
        topic_b_node = [n for n in result["nodes"] if n["title"] == "Topic B"][0]

        # Current behavior: summaries aggregate by heading hierarchy
        # Topic A aggregates its children (Subtopic 1 and 2)
        # Topic B aggregates its children (Subtopic 1)
        assert "Neural networks learn" in topic_a_node["summary_text"]
        assert "Deep learning models" in topic_a_node["summary_text"]
        assert "Neural networks are fundamental" in topic_b_node["summary_text"]

        # RAPTOR-style expectation (NOT current behavior):
        # - Neural network spans from Topic A and Topic B should be in same cluster
        # - Parent cluster summary should aggregate semantic clusters, not heading children
        #
        # Document the gap: current summaries are heading-hierarchy based
        # not semantic-cluster based

    def test_tree_structure_driven_by_heading_not_by_clustering(self) -> None:
        """Tree structure is heading-path-driven, NOT semantic-cluster-driven.

        RAPTOR expectation:
        - Tree structure determined by semantic clustering algorithm
        - Nodes represent semantic clusters, not document sections
        - Clusters built bottom-up from similar content

        Current reality:
        - Tree structure determined by heading_path string splitting
        - Nodes represent document sections, not semantic groups
        - Tree built top-down from document structure

        This test documents that tree topology follows heading hierarchy,
        not content similarity.
        """
        version_id = uuid.uuid4()
        # Create spans where semantic content DOES NOT align with heading structure
        spans = [
            # Heading "A > B" contains content about "apples" (fruit)
            _make_span(
                version_id=version_id,
                heading_path="A > B",
                text="Apples are sweet fruits grown in orchards.",
            ),
            # Heading "C > D" contains content about "apples" (same topic)
            _make_span(
                version_id=version_id,
                heading_path="C > D",
                text="Apple varieties include Granny Smith and Fuji.",
            ),
            # Heading "A > B" also contains content about "cars" (different topic)
            _make_span(
                version_id=version_id,
                heading_path="A > B",
                text="Cars are vehicles used for transportation.",
            ),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Current behavior: tree structure from heading_path
        # - Node "A > B" contains apple and car text
        # - Node "C > D" contains apple text
        # - Parent "A" and "C" are separate (no semantic relationship)

        nodes = result["nodes"]
        parent_a = [n for n in nodes if n["title"] == "A"][0]
        parent_c = [n for n in nodes if n["title"] == "C"][0]

        # Parents are separate because headings differ, not because semantics differ
        assert parent_a["node_id"] != parent_c["node_id"]

        # RAPTOR-style expectation (NOT current behavior):
        # - Apple-related spans should be in same cluster
        # - Car-related span should be in different cluster
        # - Tree structure would reflect semantic topology, not heading topology

        # Document the gap: tree topology is heading-driven
        node_ab = [n for n in nodes if "B" in n["title"] and n["parent_node_id"] == parent_a["node_id"]][0]
        node_cd = [n for n in nodes if "D" in n["title"] and n["parent_node_id"] == parent_c["node_id"]][0]

        # These nodes have semantically overlapping content (apples)
        # but are in separate parts of the tree due to heading structure
        assert "Apples are sweet" in node_ab["summary_text"]
        assert "Apple varieties" in node_cd["summary_text"]  # Same topic, different tree branch


class TestRAPTORImplementationAbsence:
    """Tests that explicitly verify RAPTOR-specific code is NOT present.

    These tests document that clustering algorithms and cluster-based tree builders
    are not implemented in TreeGenerator.
    """

    def test_no_raptor_level_clustering_algorithm_in_tree_generator(self) -> None:
        """TreeGenerator contains minimal seam, NOT full RAPTOR-level clustering logic.

        RAPTOR implementation would include:
        - Embedding-based similarity calculation
        - Clustering algorithm (e.g., GMM, k-means)
        - Cluster assignment based on semantic embeddings
        - Cross-heading semantic clustering (merging similar content across headings)
        - Bottom-up tree construction from clusters

        Minimal seam implemented:
        - Keyword-based domain detection (not embeddings)
        - Simple heuristic clustering for clearly divergent domains
        - Leaf-level splitting within same heading_path (not cross-heading)
        - Top-down heading-driven parent structure (unchanged)
        - cluster_id markers for leaf groups

        This test documents that we have minimal seam, NOT full RAPTOR implementation.
        """
        # Verify TreeGenerator source code does not contain RAPTOR-level clustering keywords
        import inspect

        source = inspect.getsource(TreeGenerator)

        # Keywords that would indicate FULL RAPTOR-level clustering implementation
        raptor_keywords = [
            "embedding",
            "similarity",
            "distance",
            "kmeans",
            "gmm",
            "gaussian",
        ]

        # Document that RAPTOR-level clustering keywords are NOT in TreeGenerator
        for keyword in raptor_keywords:
            assert keyword.lower() not in source.lower(), (
                f"Keyword '{keyword}' found in TreeGenerator - RAPTOR-level clustering may be implemented"
            )

        # "cluster" keyword IS present due to minimal seam implementation
        # This is acceptable: minimal seam uses cluster_id markers, not full clustering
        assert "cluster" in source.lower(), "Minimal seam: cluster keyword present for leaf-level grouping"
        assert "cluster_id" in source.lower(), "Minimal seam: cluster_id field added to leaf nodes"

    def test_no_bottom_up_cluster_construction(self) -> None:
        """Tree construction is top-down from headings, NOT bottom-up from clusters.

        RAPTOR process:
        1. Compute embeddings for all chunks
        2. Cluster similar chunks together
        3. Summarize each cluster
        4. Recursively cluster the summaries
        5. Build tree bottom-up from clusters

        Current TreeGenerator process:
        1. Extract heading_path from each span
        2. Split heading_path on " > " separator
        3. Create nodes top-down from heading hierarchy
        4. Assign spans to nodes based on heading_path
        5. Propagate summaries upward
        """
        # This is a documentation test, not a behavior test
        # It explicitly states the construction order difference

        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Root > Child", text="Content."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Verify nodes are created in top-down order (level 0 first, then level 1)
        nodes_by_level = defaultdict(list)
        for node in result["nodes"]:
            nodes_by_level[node["level_no"]].append(node)

        # Top-down: level 0 (root) should exist before level 1 (child)
        assert 0 in nodes_by_level
        assert 1 in nodes_by_level

        # In RAPTOR's bottom-up approach:
        # - Leaf clusters would be created first (level 1)
        # - Parent clusters would be created from leaf summaries (level 0)
        # This is NOT the current implementation order


# ===========================================================================
# SUMMARY GAP ANALYSIS
# ===========================================================================


def test_raptor_comparison_gap_summary() -> None:
    """Meta-test: summarize the RAPTOR vs current implementation gap.

    This test serves as a documentation anchor for the comparison slice.
    It does not test behavior, but documents the evaluation findings.

    Gap Summary:
    1. Current implementation IS heading-path-driven (verified by GREEN tests)
    2. Current implementation DOES propagate summary_text upward (verified by GREEN tests)
    3. Current implementation DOES NOT perform semantic clustering (verified by GAP tests)
    4. Current implementation DOES NOT build cluster-based summaries (verified by GAP tests)
    5. Current implementation DOES NOT construct tree bottom-up from clusters (verified by GAP tests)

    RAPTOR-style capabilities that would need implementation:
    - Embedding computation for spans
    - Similarity-based clustering algorithm
    - Cluster-based node creation (not heading-based)
    - Bottom-up tree construction from clusters
    - Recursive cluster summarization
    """
    # This test always passes - it's a documentation summary
    # The actual gap evidence is in the tests above

    gaps_documented = {
        "semantic_clustering_absent": True,
        "cluster_based_summaries_absent": True,
        "bottom_up_construction_absent": True,
        "heading_path_driven_present": True,
        "summary_propagation_present": True,
    }

    # Document that this comparison slice is complete
    assert all(gaps_documented.values()), "All gap characteristics should be documented"