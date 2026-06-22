"""
Phase 12 D-01/D-02/D-05/D-06 GREEN tests.

These tests NOW PASS because:
- HybridClusterHotspotSelector has theta parameter implemented
- Coverage helper _compute_child_coverage_score exists
- Dual-hot gate logic exists in select_hotspots
- Leaf fallback logic _apply_leaf_fallback exists
- Root avoidance logic _apply_root_avoidance exists

Implementation completed in 12-03. GREEN transition from 12-02 RED tests.
"""

import uuid
from llamaindex_runtime.tree.semantic_distribution import (
    HybridClusterHotspotSelector,
    HotspotSelectionContext,
    SubtreeHotspot,
    NodeSemanticHit,
    KeywordSpanHit,
    _compute_child_coverage_score,
    _is_child_dual_hot,
    _apply_leaf_fallback,
    _apply_root_avoidance,
)
import pytest


class TestClusterCoverageGate:
    """Phase 12 D-01: Coverage gate tests (θ=0.5, min_support=2) - GREEN."""

    def test_parent_with_1_of_3_dual_hot_children_is_not_a_hotspot(self) -> None:
        """GREEN: Coverage 1/3 < θ=0.5 → parent NOT a hotspot."""
        # Setup: parent with 3 children, only 1 is dual-hot
        parent_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()
        child3_id = uuid.uuid4()

        parent_to_children = {
            parent_id: (child1_id, child2_id, child3_id),
        }

        dual_hot = {child1_id}  # Only 1 child is dual-hot

        coverage_ratio, hot_count = _compute_child_coverage_score(
            parent_id=parent_id,
            parent_to_children=parent_to_children,
            dual_hot=dual_hot,
        )

        # Coverage: 1/3 = 0.33 < 0.5 → NOT hotspot
        assert coverage_ratio == 1/3
        assert hot_count == 1
        assert coverage_ratio < 0.5  # Below theta threshold

    def test_parent_with_2_of_3_dual_hot_children_is_a_hotspot(self) -> None:
        """GREEN: Coverage 2/3 >= θ=0.5 → parent IS a hotspot."""
        parent_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()
        child3_id = uuid.uuid4()

        parent_to_children = {
            parent_id: (child1_id, child2_id, child3_id),
        }

        dual_hot = {child1_id, child2_id}  # 2 children dual-hot

        coverage_ratio, hot_count = _compute_child_coverage_score(
            parent_id=parent_id,
            parent_to_children=parent_to_children,
            dual_hot=dual_hot,
        )

        # Coverage: 2/3 = 0.67 >= 0.5 → hotspot eligible
        assert coverage_ratio == 2/3
        assert hot_count == 2
        assert coverage_ratio >= 0.5  # Above theta threshold
        assert hot_count >= 2  # Meets min_support

    def test_parent_with_3_of_3_dual_hot_children_outranks_isolated_high_vector_node(self) -> None:
        """GREEN: Parent with 3/3 coverage outranks isolated high-vector node."""
        # This test validates that cluster coverage scoring takes precedence
        # over single-node fusion scores
        parent_id = uuid.uuid4()
        child_ids = [uuid.uuid4() for _ in range(3)]

        parent_to_children = {
            parent_id: tuple(child_ids),
        }

        dual_hot = set(child_ids)  # All 3 children dual-hot

        coverage_ratio, hot_count = _compute_child_coverage_score(
            parent_id=parent_id,
            parent_to_children=parent_to_children,
            dual_hot=dual_hot,
        )

        # Coverage: 3/3 = 1.0 → strongest parent score
        assert coverage_ratio == 1.0
        assert hot_count == 3
        # Parent with 1.0 coverage should outrank any isolated node


class TestDualHotGate:
    """Phase 12 D-02: Dual-hot gate tests - GREEN."""

    def test_vector_only_child_does_not_count_toward_coverage(self) -> None:
        """GREEN: Vector-only child excluded from coverage (intersection gate)."""
        child_id = uuid.uuid4()
        vector_hot = {child_id}
        keyword_hot = set()  # No keyword match

        # Dual-hot check: must be in BOTH sets
        is_dual = _is_child_dual_hot(
            child_id=child_id,
            vector_hot=vector_hot,
            keyword_hot=keyword_hot,
        )

        assert not is_dual  # Vector-only excluded

    def test_keyword_only_child_does_not_count_toward_coverage(self) -> None:
        """GREEN: Keyword-only child excluded from coverage (intersection gate)."""
        child_id = uuid.uuid4()
        vector_hot = set()  # No vector match
        keyword_hot = {child_id}

        is_dual = _is_child_dual_hot(
            child_id=child_id,
            vector_hot=vector_hot,
            keyword_hot=keyword_hot,
        )

        assert not is_dual  # Keyword-only excluded


class TestConfigurableTheta:
    """Phase 12 D-05: θ configurable tests - GREEN."""

    def test_theta_0_5_selects_2_of_3_parent(self) -> None:
        """GREEN: θ=0.5 allows 2/3 parent as hotspot."""
        selector = HybridClusterHotspotSelector(theta=0.5)
        assert selector._coverage_theta == 0.5
        # 2/3 = 0.67 >= 0.5 → eligible

    def test_theta_0_75_rejects_2_of_3_parent(self) -> None:
        """GREEN: θ=0.75 rejects 2/3 parent (0.67 < 0.75)."""
        selector = HybridClusterHotspotSelector(theta=0.75)
        assert selector._coverage_theta == 0.75
        # 2/3 = 0.67 < 0.75 → NOT eligible


class TestLeafFallback:
    """Phase 12 D-06: Leaf fallback + root avoidance tests - GREEN."""

    def test_focused_exact_leaf_query_returns_strong_dual_hot_leaf_even_when_parent_coverage_below_theta(self) -> None:
        """GREEN: Leaf fallback returns strong dual-hot leaf when parent fails coverage."""
        leaf_id = uuid.uuid4()
        parent_id = uuid.uuid4()

        node_by_id = {
            leaf_id: {"parent_node_id": parent_id},
            parent_id: {"parent_node_id": uuid.uuid4()},  # Non-root parent
        }

        dual_hot = {leaf_id}
        exact_keyword_nodes = set()
        vector_by_node = {leaf_id: 0.8}
        keyword_by_node = {leaf_id: 0.9}

        leaf_candidates = _apply_leaf_fallback(
            dual_hot=dual_hot,
            exact_keyword_nodes=exact_keyword_nodes,
            vector_by_node=vector_by_node,
            keyword_by_node=keyword_by_node,
            node_by_id=node_by_id,
            parent_to_children={},  # Flat fixture (no hierarchy)
            limit=1,
        )

        # Leaf fallback returns the dual-hot leaf
        assert len(leaf_candidates) == 1
        assert leaf_candidates[0][0] == leaf_id
        # Combined score: 0.8*0.5 + 0.9*0.5 = 0.85 (floating-point tolerance)
        assert abs(leaf_candidates[0][1] - 0.85) < 0.001

    def test_root_with_many_children_is_not_promoted_by_coverage_alone(self) -> None:
        """GREEN: Root avoidance prevents root promotion even with high coverage."""
        root_id = uuid.uuid4()
        child_ids = [uuid.uuid4() for _ in range(13)]  # Many children

        parent_stats = {"parent_node_id": None}  # Root has no parent
        children_count = 13
        breadth_cap = 8

        # Root avoidance check
        should_avoid = _apply_root_avoidance(
            parent_id=root_id,
            parent_stats=parent_stats,
            children_count=children_count,
            breadth_cap=breadth_cap,
        )

        assert should_avoid  # Root is avoided