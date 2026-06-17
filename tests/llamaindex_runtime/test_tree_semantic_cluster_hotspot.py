"""Tests for Phase 11 cluster-hotspot selector behavior.

These tests validate the level-agnostic, post-hoc cluster-based hotspot
tracking algorithm that replaces Phase 10 route-node bonus scoring.

Core semantic shift:
  Old: hotspot_node_id = node preselected as route/hotspot with bonus scoring
  New: hotspot_node_id = post-hoc inferred shared region where hits clustered

Implementation target: ClusterHotspotSelector
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

# NOTE: ClusterHotspotSelector does not exist yet.
# This import will fail in RED phase, which is expected behavior.
from llamaindex_runtime.tree.semantic_distribution import (
    ClusterHotspotSelector,
)


class TestClusterHotspotSelector:
    """Level-agnostic cluster hotspot selector tests (Phase 11 TDD RED)."""

    def test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus(
        self,
    ) -> None:
        """D-01: All eligible nodes compete equally by cosine similarity.

        Route-like parent nodes must not receive bonuses solely because
        they are parents or have no direct chunks. Selection must be
        post-hoc from observed semantic hit distribution, not pre-ranked
        by route-node role.

        This test validates that a route-like parent with lower similarity
        is not selected over a child evidence node with higher similarity.
        """
        # Setup: Route-like parent and evidence child with different similarities
        version_id = uuid.uuid4()
        route_parent_id = uuid.uuid4()
        evidence_child_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        # Mock registry with tree hierarchy
        registry = MagicMock()

        # Parent: route-like (no direct chunks, subtree has chunks)
        # Similarity: 0.60 (lower than child)
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": route_parent_id,
                "heading_path": "Chapter 1",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": evidence_child_id,
                "heading_path": "Chapter 1 > Evidence",
                "level_no": 1,
                "parent_node_id": route_parent_id,
            },
        ]

        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": evidence_child_id, "span_id": span_id, "ordinal_no": 0},
        ]

        # Child has direct chunks; parent has none
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "node_id": evidence_child_id,
                "embedding": [1.0, 0.0],  # Matches query direction
            },
        ]

        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        # Build node_stats manually to reflect route-node/evidence split
        # This simulates PersistedTreeSemanticDistributionAdapter output
        node_stats = [
            {
                "node_id": route_parent_id,
                "heading_path": "Chapter 1",
                "span_ids": [],  # Parent has no direct spans
                "chunk_ids": [],  # Parent has no direct chunks
                "subtree_chunk_ids": [chunk_id],  # Subtree has evidence
                "centroid": [0.6, 0.0],  # Aggregated centroid
                "prototype_embedding": [0.6, 0.0],
                "dispersion": 0.5,
                "entropy": 0.8,
                "support_count": 1,
                "direct_support_count": 0,
                "is_route_node": True,  # Route node flag from Phase 10
            },
            {
                "node_id": evidence_child_id,
                "heading_path": "Chapter 1 > Evidence",
                "span_ids": [span_id],
                "chunk_ids": [chunk_id],
                "subtree_chunk_ids": [chunk_id],
                "centroid": [1.0, 0.0],
                "prototype_embedding": [1.0, 0.0],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,  # Evidence node
            },
        ]

        tree_signals = {
            "node_count": 2,
            "analyzed_node_count": 2,
            "skipped_chunk_count": 0,
            "embedding_dimension": 2,
        }

        # Query embedding matches child direction (higher similarity)
        query_embedding = [1.0, 0.0]

        # Execute selector
        selector = ClusterHotspotSelector()
        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=3,  # Request 3 hits to validate candidate breadth
        )

        # Assertions for D-01 and D-03

        # D-01: Route parent must not win solely because is_route_node=True
        # Child similarity is 1.0; parent similarity is 0.6
        # If route bonus were applied, parent might unfairly win
        assert hotspots, "Selector should return at least one hotspot"
        assert hotspots[0].node_id == evidence_child_id, (
            "Evidence child with higher similarity should win over "
            "route parent with lower similarity. No route-node bonus allowed."
        )

        # D-03: Candidate breadth validation
        # Selector must inspect broader candidate set than final limit
        # For limit=3, candidate_top_n should be max(3 * 4, 20) = 20
        # We cannot directly observe candidate_top_n from output,
        # but we can validate the selector does not prematurely prune
        # at limit=3 when broader inspection is required.
        #
        # In this fixture with only 2 nodes, selector should still
        # process both nodes (not prune parent before child comparison).
        # The fact that child wins proves parent was considered and rejected.
        # This indirectly validates broader candidate inspection.

        # Additional contract validation
        assert hasattr(selector, "select_hotspots"), (
            "Selector must implement select_hotspots method"
        )

        # Verify no route-node bonus field exists in selector
        # (would indicate transplanted Phase 10 logic)
        assert not hasattr(selector, "_ROUTE_NODE_BONUS"), (
            "ClusterHotspotSelector must not have _ROUTE_NODE_BONUS field"
        )
        assert not hasattr(selector, "_DEPTH_BONUS_PER_LEVEL"), (
            "ClusterHotspotSelector must not have _DEPTH_BONUS_PER_LEVEL field"
        )
        assert not hasattr(selector, "_SUPPORT_BONUS_PER_CHUNK"), (
            "ClusterHotspotSelector must not have _SUPPORT_BONUS_PER_CHUNK field"
        )

    def test_cluster_hotspot_selector_selects_densest_shared_ancestor(
        self,
    ) -> None:
        """D-02: Hotspot is densest shared ancestor, not highest single hit.

        When semantic hits cluster under ancestor A with strong combined
        density, but one isolated hit under B has highest single score,
        the selector should choose A as the hotspot region.

        Cluster scoring formula (Phase 11 design):
          cluster_score = max_score * 0.40
                        + avg_score * 0.30
                        + normalized_support_count * 0.20
                        + density * 0.10
        """
        # Setup: Tree with two competing subtrees
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        node_a_id = uuid.uuid4()
        node_a1_id = uuid.uuid4()
        node_a2_id = uuid.uuid4()
        node_a3_id = uuid.uuid4()
        node_b_id = uuid.uuid4()
        node_b1_id = uuid.uuid4()

        span_a1 = uuid.uuid4()
        span_a2 = uuid.uuid4()
        span_a3 = uuid.uuid4()
        span_b1 = uuid.uuid4()
        chunk_a1 = uuid.uuid4()
        chunk_a2 = uuid.uuid4()
        chunk_a3 = uuid.uuid4()
        chunk_b1 = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "heading_path": "Root", "level_no": 0, "parent_node_id": None},
            {"node_id": node_a_id, "heading_path": "Root > A", "level_no": 1, "parent_node_id": root_id},
            {"node_id": node_a1_id, "heading_path": "Root > A > A1", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_a2_id, "heading_path": "Root > A > A2", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_a3_id, "heading_path": "Root > A > A3", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_b_id, "heading_path": "Root > B", "level_no": 1, "parent_node_id": root_id},
            {"node_id": node_b1_id, "heading_path": "Root > B > B1", "level_no": 2, "parent_node_id": node_b_id},
        ]

        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a1_id, "span_id": span_a1, "ordinal_no": 0},
            {"node_id": node_a2_id, "span_id": span_a2, "ordinal_no": 0},
            {"node_id": node_a3_id, "span_id": span_a3, "ordinal_no": 0},
            {"node_id": node_b1_id, "span_id": span_b1, "ordinal_no": 0},
        ]

        # A subtree: three hits with similarities 0.85, 0.80, 0.70 (cluster)
        # B subtree: one hit with similarity 0.90 (highest single)
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a1, "node_id": node_a1_id, "embedding": [0.85, 0.15]},
            {"chunk_id": chunk_a2, "node_id": node_a2_id, "embedding": [0.80, 0.20]},
            {"chunk_id": chunk_a3, "node_id": node_a3_id, "embedding": [0.70, 0.30]},
            {"chunk_id": chunk_b1, "node_id": node_b1_id, "embedding": [0.90, 0.10]},  # Highest single
        ]

        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a1, "span_id": span_a1, "ordinal_no": 0},
            {"chunk_id": chunk_a2, "span_id": span_a2, "ordinal_no": 0},
            {"chunk_id": chunk_a3, "span_id": span_a3, "ordinal_no": 0},
            {"chunk_id": chunk_b1, "span_id": span_b1, "ordinal_no": 0},
        ]

        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        # Build node_stats simulating adapter output
        # A subtree has combined density; B1 has highest single hit
        node_stats = [
            {
                "node_id": node_a1_id,
                "heading_path": "Root > A > A1",
                "span_ids": [span_a1],
                "chunk_ids": [chunk_a1],
                "subtree_chunk_ids": [chunk_a1],
                "centroid": [0.85, 0.15],
                "prototype_embedding": [0.85, 0.15],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_a2_id,
                "heading_path": "Root > A > A2",
                "span_ids": [span_a2],
                "chunk_ids": [chunk_a2],
                "subtree_chunk_ids": [chunk_a2],
                "centroid": [0.80, 0.20],
                "prototype_embedding": [0.80, 0.20],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_a3_id,
                "heading_path": "Root > A > A3",
                "span_ids": [span_a3],
                "chunk_ids": [chunk_a3],
                "subtree_chunk_ids": [chunk_a3],
                "centroid": [0.70, 0.30],
                "prototype_embedding": [0.70, 0.30],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_b1_id,
                "heading_path": "Root > B > B1",
                "span_ids": [span_b1],
                "chunk_ids": [chunk_b1],
                "subtree_chunk_ids": [chunk_b1],
                "centroid": [0.90, 0.10],  # Highest similarity
                "prototype_embedding": [0.90, 0.10],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
        ]

        tree_signals = {
            "node_count": 7,
            "analyzed_node_count": 4,
            "skipped_chunk_count": 0,
            "embedding_dimension": 2,
        }

        # Query: balanced direction to see cluster competition
        query_embedding = [0.80, 0.20]

        selector = ClusterHotspotSelector()
        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=3,
        )

        # D-02 assertion: Cluster A wins over isolated B1
        # Expected cluster scores (approximate):
        #   A cluster: max=0.85, avg≈0.78, support=3, density=1.0
        #     score ≈ 0.85*0.40 + 0.78*0.30 + 0.15*0.20 + 1.0*0.10 ≈ 0.66
        #   B cluster: max=0.90, avg=0.90, support=1, density=1.0
        #     score ≈ 0.90*0.40 + 0.90*0.30 + 0.05*0.20 + 1.0*0.10 ≈ 0.68
        #
        # With root penalty for root ancestor and tie-breaking,
        # selector should prefer local ancestor A over root.
        assert hotspots, "Selector should return hotspots"

        # Validate hotspot selection logic
        # In this case, A subtree has stronger cluster density
        # than B's single highest hit
        selected_node_id = hotspots[0].node_id

        # Expected: selected hotspot is within A subtree or ancestor A
        a_subtree_ids = {node_a_id, node_a1_id, node_a2_id, node_a3_id}
        assert selected_node_id in a_subtree_ids, (
            f"Densest cluster under A should win over isolated B1 hit. "
            f"Expected hotspot in A subtree ({a_subtree_ids}), got {selected_node_id}"
        )

    def test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists(
        self,
    ) -> None:
        """D-04: Root must not be selected when meaningful local cluster exists.

        Root ancestor accumulates all hits, but local ancestor should win
        when it contains most relevant cluster. This prevents root-bias
        where hotspot becomes too broad to be useful.

        Root penalty logic: Root should be penalized or excluded unless
        no better local candidate exists.
        """
        # Setup: Same tree as densest ancestor test
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        node_a_id = uuid.uuid4()
        node_a1_id = uuid.uuid4()
        node_a2_id = uuid.uuid4()
        node_a3_id = uuid.uuid4()
        node_b_id = uuid.uuid4()
        node_b1_id = uuid.uuid4()

        span_a1 = uuid.uuid4()
        span_a2 = uuid.uuid4()
        span_a3 = uuid.uuid4()
        span_b1 = uuid.uuid4()
        chunk_a1 = uuid.uuid4()
        chunk_a2 = uuid.uuid4()
        chunk_a3 = uuid.uuid4()
        chunk_b1 = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "heading_path": "Root", "level_no": 0, "parent_node_id": None},
            {"node_id": node_a_id, "heading_path": "Root > A", "level_no": 1, "parent_node_id": root_id},
            {"node_id": node_a1_id, "heading_path": "Root > A > A1", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_a2_id, "heading_path": "Root > A > A2", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_a3_id, "heading_path": "Root > A > A3", "level_no": 2, "parent_node_id": node_a_id},
            {"node_id": node_b_id, "heading_path": "Root > B", "level_no": 1, "parent_node_id": root_id},
            {"node_id": node_b1_id, "heading_path": "Root > B > B1", "level_no": 2, "parent_node_id": node_b_id},
        ]

        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a1_id, "span_id": span_a1, "ordinal_no": 0},
            {"node_id": node_a2_id, "span_id": span_a2, "ordinal_no": 0},
            {"node_id": node_a3_id, "span_id": span_a3, "ordinal_no": 0},
            {"node_id": node_b1_id, "span_id": span_b1, "ordinal_no": 0},
        ]

        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a1, "node_id": node_a1_id, "embedding": [0.85, 0.15]},
            {"chunk_id": chunk_a2, "node_id": node_a2_id, "embedding": [0.80, 0.20]},
            {"chunk_id": chunk_a3, "node_id": node_a3_id, "embedding": [0.70, 0.30]},
            {"chunk_id": chunk_b1, "node_id": node_b1_id, "embedding": [0.90, 0.10]},
        ]

        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a1, "span_id": span_a1, "ordinal_no": 0},
            {"chunk_id": chunk_a2, "span_id": span_a2, "ordinal_no": 0},
            {"chunk_id": chunk_a3, "span_id": span_a3, "ordinal_no": 0},
            {"chunk_id": chunk_b1, "span_id": span_b1, "ordinal_no": 0},
        ]

        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        # Node stats (same as densest ancestor test)
        node_stats = [
            {
                "node_id": node_a1_id,
                "heading_path": "Root > A > A1",
                "span_ids": [span_a1],
                "chunk_ids": [chunk_a1],
                "subtree_chunk_ids": [chunk_a1],
                "centroid": [0.85, 0.15],
                "prototype_embedding": [0.85, 0.15],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_a2_id,
                "heading_path": "Root > A > A2",
                "span_ids": [span_a2],
                "chunk_ids": [chunk_a2],
                "subtree_chunk_ids": [chunk_a2],
                "centroid": [0.80, 0.20],
                "prototype_embedding": [0.80, 0.20],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_a3_id,
                "heading_path": "Root > A > A3",
                "span_ids": [span_a3],
                "chunk_ids": [chunk_a3],
                "subtree_chunk_ids": [chunk_a3],
                "centroid": [0.70, 0.30],
                "prototype_embedding": [0.70, 0.30],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": node_b1_id,
                "heading_path": "Root > B > B1",
                "span_ids": [span_b1],
                "chunk_ids": [chunk_b1],
                "subtree_chunk_ids": [chunk_b1],
                "centroid": [0.90, 0.10],
                "prototype_embedding": [0.90, 0.10],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
        ]

        tree_signals = {
            "node_count": 7,
            "analyzed_node_count": 4,
            "skipped_chunk_count": 0,
            "embedding_dimension": 2,
        }

        query_embedding = [0.80, 0.20]

        selector = ClusterHotspotSelector()
        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=3,
        )

        # D-04 assertion: Root must not be selected
        assert hotspots, "Selector should return hotspots"
        assert hotspots[0].node_id != root_id, (
            "Root should not be selected as hotspot when local cluster A exists. "
            "Local ancestor should win due to root penalty logic."
        )

        # Validate hotspot is in meaningful local region
        a_subtree_ids = {node_a_id, node_a1_id, node_a2_id, node_a3_id}
        b_subtree_ids = {node_b_id, node_b1_id}
        local_ids = a_subtree_ids | b_subtree_ids

        assert hotspots[0].node_id in local_ids, (
            f"Hotspot should be local ancestor (A or B subtree), not root. "
            f"Got {hotspots[0].node_id}"
        )

    def test_short_exact_heading_node_survives_long_related_text(
        self,
    ) -> None:
        """D-05: Short exact heading node should not be hidden by long related text.

        When query matches a short heading exactly, but a longer related
        section has higher embedding similarity due to token count,
        the cluster selector should preserve the exact match in returned hits.

        This validates that cluster density scoring and local ancestor
        selection do not accidentally suppress exact matches.
        """
        # Setup: Short exact heading vs long related text
        version_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        exact_heading_node_id = uuid.uuid4()
        long_related_node_id = uuid.uuid4()

        span_exact = uuid.uuid4()
        span_long = uuid.uuid4()
        chunk_exact = uuid.uuid4()
        chunk_long = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": parent_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": exact_heading_node_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > AI产品经理核心DNA",
                "level_no": 1,
                "parent_node_id": parent_id,
            },
            {
                "node_id": long_related_node_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > AI产品经理的思考方向",
                "level_no": 1,
                "parent_node_id": parent_id,
            },
        ]

        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": exact_heading_node_id, "span_id": span_exact, "ordinal_no": 0},
            {"node_id": long_related_node_id, "span_id": span_long, "ordinal_no": 0},
        ]

        # Short exact node: "数据驱动 / 非确定性 / 持续性"
        # Embedding may have lower similarity due to short text
        # Long related node: "AI产品经理的思考方向 / 数据飞轮 / 用户行为..."
        # Embedding may have higher similarity due to rich context
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_exact,
                "node_id": exact_heading_node_id,
                "embedding": [0.70, 0.30],  # Short text, moderate similarity
            },
            {
                "chunk_id": chunk_long,
                "node_id": long_related_node_id,
                "embedding": [0.85, 0.15],  # Long context, higher similarity
            },
        ]

        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_exact, "span_id": span_exact, "ordinal_no": 0},
            {"chunk_id": chunk_long, "span_id": span_long, "ordinal_no": 0},
        ]

        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        # Node stats
        node_stats = [
            {
                "node_id": exact_heading_node_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > AI产品经理核心DNA",
                "span_ids": [span_exact],
                "chunk_ids": [chunk_exact],
                "subtree_chunk_ids": [chunk_exact],
                "centroid": [0.70, 0.30],
                "prototype_embedding": [0.70, 0.30],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": long_related_node_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > AI产品经理的思考方向",
                "span_ids": [span_long],
                "chunk_ids": [chunk_long],
                "subtree_chunk_ids": [chunk_long],
                "centroid": [0.85, 0.15],
                "prototype_embedding": [0.85, 0.15],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
        ]

        tree_signals = {
            "node_count": 3,
            "analyzed_node_count": 2,
            "skipped_chunk_count": 0,
            "embedding_dimension": 2,
        }

        # Query: matches exact heading keywords
        query_embedding = [0.75, 0.25]

        selector = ClusterHotspotSelector()
        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=3,
        )

        # D-05 assertion: Exact heading node should appear in returned hits
        assert hotspots, "Selector should return hotspots"

        # Check if exact heading node is in returned hits
        returned_node_ids = {hit.node_id for hit in hotspots}
        assert exact_heading_node_id in returned_node_ids, (
            "Short exact heading node should survive in returned hits. "
            "Long related text should not suppress exact match."
        )

        # Validate hotspot is local parent or exact node itself
        # (not unrelated region)
        hotspot_node_id = hotspots[0].node_id
        allowed_hotspot_ids = {parent_id, exact_heading_node_id}
        assert hotspot_node_id in allowed_hotspot_ids, (
            f"Hotspot should be local parent or exact heading node. "
            f"Got {hotspot_node_id}, expected one of {allowed_hotspot_ids}"
        )

    def test_p6_ai_product_manager_core_dna_routes_to_product_characteristics(
        self,
    ) -> None:
        """D-07: p6 regression test for AI产品经理核心DNA query.

        Query: "AI产品经理的核心DNA是什么？"

        Must return evidence containing:
          - 数据驱动
          - 非确定性
          - 持续性

        Primary hotspot must be:
          - 00:31 - 产品特性对比
          - OR AI产品经理核心DNA itself

        Must NOT select unrelated regions as primary hotspot:
          - 05:40 - 抖音案例
          - 04:40 - 数据工作重要性
          - 06:29 - 特斯拉案例
        """
        # Setup: p6 corpus tree with multiple sections
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        product_characteristics_id = uuid.uuid4()
        dna_heading_id = uuid.uuid4()
        douyin_case_id = uuid.uuid4()
        data_importance_id = uuid.uuid4()
        tesla_case_id = uuid.uuid4()

        span_dna = uuid.uuid4()
        span_product = uuid.uuid4()
        span_douyin = uuid.uuid4()
        span_data = uuid.uuid4()
        span_tesla = uuid.uuid4()

        chunk_dna = uuid.uuid4()
        chunk_product = uuid.uuid4()
        chunk_douyin = uuid.uuid4()
        chunk_data = uuid.uuid4()
        chunk_tesla = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": root_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": product_characteristics_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比",
                "level_no": 1,
                "parent_node_id": root_id,
            },
            {
                "node_id": dna_heading_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA",
                "level_no": 2,
                "parent_node_id": product_characteristics_id,
            },
            {
                "node_id": douyin_case_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例",
                "level_no": 1,
                "parent_node_id": root_id,
            },
            {
                "node_id": data_importance_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 04:40 - 数据工作重要性",
                "level_no": 1,
                "parent_node_id": root_id,
            },
            {
                "node_id": tesla_case_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 06:29 - 特斯拉案例",
                "level_no": 1,
                "parent_node_id": root_id,
            },
        ]

        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": dna_heading_id, "span_id": span_dna, "ordinal_no": 0},
            {"node_id": product_characteristics_id, "span_id": span_product, "ordinal_no": 0},
            {"node_id": douyin_case_id, "span_id": span_douyin, "ordinal_no": 0},
            {"node_id": data_importance_id, "span_id": span_data, "ordinal_no": 0},
            {"node_id": tesla_case_id, "span_id": span_tesla, "ordinal_no": 0},
        ]

        # DNA evidence: contains 数据驱动, 非确定性, 持续性
        # Product characteristics: broader context
        # Other cases: unrelated or tangentially related
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_dna,
                "node_id": dna_heading_id,
                "embedding": [0.90, 0.10],  # High similarity to DNA query
            },
            {
                "chunk_id": chunk_product,
                "node_id": product_characteristics_id,
                "embedding": [0.85, 0.15],  # Related context
            },
            {
                "chunk_id": chunk_douyin,
                "node_id": douyin_case_id,
                "embedding": [0.60, 0.40],  # Lower similarity
            },
            {
                "chunk_id": chunk_data,
                "node_id": data_importance_id,
                "embedding": [0.65, 0.35],  # Moderate similarity
            },
            {
                "chunk_id": chunk_tesla,
                "node_id": tesla_case_id,
                "embedding": [0.55, 0.45],  # Lower similarity
            },
        ]

        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_dna, "span_id": span_dna, "ordinal_no": 0},
            {"chunk_id": chunk_product, "span_id": span_product, "ordinal_no": 0},
            {"chunk_id": chunk_douyin, "span_id": span_douyin, "ordinal_no": 0},
            {"chunk_id": chunk_data, "span_id": span_data, "ordinal_no": 0},
            {"chunk_id": chunk_tesla, "span_id": span_tesla, "ordinal_no": 0},
        ]

        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        # Node stats
        node_stats = [
            {
                "node_id": dna_heading_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA",
                "span_ids": [span_dna],
                "chunk_ids": [chunk_dna],
                "subtree_chunk_ids": [chunk_dna],
                "centroid": [0.90, 0.10],
                "prototype_embedding": [0.90, 0.10],
                "dispersion": 0.05,
                "entropy": 0.2,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": product_characteristics_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比",
                "span_ids": [span_product],
                "chunk_ids": [chunk_product],
                "subtree_chunk_ids": [chunk_product, chunk_dna],  # Parent aggregates child
                "centroid": [0.875, 0.125],  # Average of product + DNA
                "prototype_embedding": [0.875, 0.125],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 2,
                "direct_support_count": 1,
                "is_route_node": True,  # Parent with subtree evidence
            },
            {
                "node_id": douyin_case_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例",
                "span_ids": [span_douyin],
                "chunk_ids": [chunk_douyin],
                "subtree_chunk_ids": [chunk_douyin],
                "centroid": [0.60, 0.40],
                "prototype_embedding": [0.60, 0.40],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": data_importance_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 04:40 - 数据工作重要性",
                "span_ids": [span_data],
                "chunk_ids": [chunk_data],
                "subtree_chunk_ids": [chunk_data],
                "centroid": [0.65, 0.35],
                "prototype_embedding": [0.65, 0.35],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
            {
                "node_id": tesla_case_id,
                "heading_path": "AI产品经理项目实战与深度思考架构分析 > 06:29 - 特斯拉案例",
                "span_ids": [span_tesla],
                "chunk_ids": [chunk_tesla],
                "subtree_chunk_ids": [chunk_tesla],
                "centroid": [0.55, 0.45],
                "prototype_embedding": [0.55, 0.45],
                "dispersion": 0.1,
                "entropy": 0.3,
                "support_count": 1,
                "direct_support_count": 1,
                "is_route_node": False,
            },
        ]

        tree_signals = {
            "node_count": 6,
            "analyzed_node_count": 5,
            "skipped_chunk_count": 0,
            "embedding_dimension": 2,
        }

        # Query: "AI产品经理的核心DNA是什么？"
        query_embedding = [0.88, 0.12]

        selector = ClusterHotspotSelector()
        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=3,
        )

        # D-07 assertions

        # 1. Primary hotspot must be allowed region
        allowed_hotspot_ids = {product_characteristics_id, dna_heading_id}
        rejected_hotspot_ids = {douyin_case_id, data_importance_id, tesla_case_id}

        assert hotspots, "Selector should return hotspots"
        hotspot_node_id = hotspots[0].node_id

        assert hotspot_node_id in allowed_hotspot_ids, (
            f"Primary hotspot must be '00:31 - 产品特性对比' or 'AI产品经理核心DNA'. "
            f"Got {hotspot_node_id}, which is in rejected regions: {rejected_hotspot_ids}"
        )

        assert hotspot_node_id not in rejected_hotspot_ids, (
            f"Primary hotspot must not be unrelated region "
            f"(抖音案例, 数据工作重要性, 特斯拉案例). Got {hotspot_node_id}"
        )

        # 2. Returned hits must include DNA evidence node
        returned_node_ids = {hit.node_id for hit in hotspots}
        assert dna_heading_id in returned_node_ids, (
            "Returned hits must contain 'AI产品经理核心DNA' node "
            "with evidence: 数据驱动, 非确定性, 持续性"
        )

        # 3. Check for expected evidence strings in hit metadata
        # (This would require text_preview field, which depends on
        # EvidenceContentResolver. For now, we validate node selection.)
        # Full evidence validation happens in Phase 11 validation runner.


# NOTE: This file is in RED phase.
# All tests will fail because ClusterHotspotSelector does not exist yet.
# Expected failure mode: ImportError or AttributeError.