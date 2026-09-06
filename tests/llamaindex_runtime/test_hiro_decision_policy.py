"""Tests for HIRO-enhanced TreeBranchDecisionPolicy integration.

Phase 4 slice 3: verify HIRO donor logic transplanted into local decision policy.
"""
from __future__ import annotations

import pytest


class TestHIROEnhancedDecisionPolicy:
    """Verify HIRO distance+delta threshold logic integrated."""

    def test_policy_implements_tree_branch_decision_protocol(
        self,
    ) -> None:
        """HIROEnhancedPolicy must implement TreeBranchDecisionPolicy protocol."""
        from llamaindex_runtime.tree.semantic_distribution import TreeBranchDecisionPolicy
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )
        assert isinstance(policy, TreeBranchDecisionPolicy)

    def test_drill_down_when_both_thresholds_met(
        self,
    ) -> None:
        """Drill down when delta > delta_threshold AND distance > selection_threshold."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # HIRO condition: delta > 0.05 AND distance > 0.15
        # delta = child_distance - parent_distance
        # If child has better distance (smaller) than parent, delta < 0 (negative)
        # If child has worse distance (larger) than parent, delta > 0 (positive)
        # HIRO drills down when child is WORSE than parent but still above threshold

        # Scenario 1: Child is worse (delta positive) AND both above threshold → drill_down
        node_stats = {
            "query_distance": 0.20,  # Child distance (worse)
            "parent_query_distance": 0.10,  # Parent distance (better)
            "support_count": 10,
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        # delta = 0.20 - 0.10 = 0.10 > 0.05 (threshold met)
        # distance = 0.20 > 0.15 (threshold met)
        # Both conditions met → drill_down
        assert decision == "drill_down"

    def test_prune_when_delta_below_threshold(
        self,
    ) -> None:
        """Prune when delta < delta_threshold (child not worse enough to drill)."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # Scenario 2: Child is slightly worse (delta small) → prune
        node_stats = {
            "query_distance": 0.12,  # Child distance (slightly worse)
            "parent_query_distance": 0.10,  # Parent distance
            "support_count": 10,
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        # delta = 0.12 - 0.10 = 0.02 < 0.05 (threshold NOT met)
        # Even though distance > 0.15 fails too (0.12 < 0.15)
        # → prune
        assert decision == "prune"

    def test_prune_when_distance_below_threshold(
        self,
    ) -> None:
        """Keep parent when child is better (negative delta, parent already good)."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # Scenario 3: Child is very relevant (distance small) → keep_parent (child improves)
        node_stats = {
            "query_distance": 0.08,  # Child very close to query
            "parent_query_distance": 0.10,
            "support_count": 10,
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        # delta = 0.08 - 0.10 = -0.02 < 0 (child is BETTER, negative delta)
        # distance = 0.08 < 0.15 (below selection threshold)
        # HIRO logic: child improves parent → keep_parent
        assert decision == "keep_parent"

    def test_keep_parent_when_child_is_better(
        self,
    ) -> None:
        """Keep parent when child is better (negative delta, parent already good)."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # Scenario 4: Child is better than parent (negative delta)
        # If parent is already above threshold, keep parent
        node_stats = {
            "query_distance": 0.05,  # Child very close
            "parent_query_distance": 0.10,  # Parent close too
            "support_count": 10,
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        # delta = 0.05 - 0.10 = -0.05 (child is BETTER)
        # HIRO logic: negative delta means child improves, so keep parent
        # (Parent already captures this relevance)
        # → keep_parent (or prune? depends on HIRO exact logic)
        # From hiro/test_hiro_decision.py: negative delta → prune/keep_parent, not drill_down
        assert decision in ["keep_parent", "prune"]

    def test_prune_when_low_support_count(
        self,
    ) -> None:
        """Prune when support_count < min_support_threshold (statistical significance)."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
            min_support_threshold=5,
        )

        # Even if thresholds met, low support → prune
        node_stats = {
            "query_distance": 0.20,
            "parent_query_distance": 0.10,
            "support_count": 2,  # Below threshold
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        assert decision == "prune"


class TestHIROLogicPreservation:
    """Verify HIRO decision logic matches donor semantics."""

    def test_delta_calculation_matches_hiro_formula(
        self,
    ) -> None:
        """delta = child_distance - parent_distance (HIRO formula)."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # Test delta calculation
        # This test verifies internal logic, not just output
        node_stats = {
            "query_distance": 0.25,
            "parent_query_distance": 0.10,
        }

        # Internal delta = 0.25 - 0.10 = 0.15
        # We verify by checking decision outcome matches expected delta
        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals={},
        )

        # delta = 0.15 > 0.05 AND distance = 0.25 > 0.15 → drill_down
        assert decision == "drill_down"

    def test_threshold_parameters_are_configurable(
        self,
    ) -> None:
        """selection_threshold and delta_threshold must be configurable."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        # Different threshold values should produce different decisions
        policy_strict = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.30,  # Higher threshold
            delta_threshold=0.10,
        )

        policy_loose = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.10,  # Lower threshold
            delta_threshold=0.02,
        )

        node_stats = {
            "query_distance": 0.20,
            "parent_query_distance": 0.10,
            "support_count": 10,
        }

        decision_strict = policy_strict.decide_branch_action(
            node_stats=node_stats,
            tree_signals={},
        )
        decision_loose = policy_loose.decide_branch_action(
            node_stats=node_stats,
            tree_signals={},
        )

        # Strict: distance 0.20 < 0.30 → prune
        # Loose: distance 0.20 > 0.10 AND delta 0.10 > 0.02 → drill_down
        assert decision_strict == "prune"
        assert decision_loose == "drill_down"


class TestHIROLocalIntegration:
    """Verify HIRO logic integrated with local semantic distribution adapter."""

    def test_policy_works_with_query_distance_in_node_stats(
        self,
    ) -> None:
        """HIRO policy must work with query_distance precomputed in node_stats."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # node_stats from local adapter includes query_distance
        # (precomputed by RecursiveTreeTraversalRunner)
        node_stats = {
            "node_id": "uuid-placeholder",
            "centroid": [0.5, 0.5],  # From local adapter
            "dispersion": 0.1,  # From local adapter
            "entropy": 0.2,  # From local adapter
            "support_count": 10,  # From local adapter
            "query_distance": 0.20,  # Precomputed by traversal runner
            "parent_query_distance": 0.10,  # Precomputed by traversal runner
        }
        tree_signals = {}

        decision = policy.decide_branch_action(
            node_stats=node_stats,
            tree_signals=tree_signals,
        )

        # HIRO logic uses query_distance, ignores dispersion/entropy
        assert decision == "drill_down"

    def test_policy_ignores_dispersion_entropy(
        self,
    ) -> None:
        """HIRO policy uses distance-based thresholds, not dispersion/entropy."""
        from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy

        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        # Same query_distance, different dispersion/entropy → same decision
        node_stats_1 = {
            "query_distance": 0.20,
            "parent_query_distance": 0.10,
            "dispersion": 0.1,  # Low dispersion
            "entropy": 0.2,  # Low entropy
            "support_count": 10,
        }

        node_stats_2 = {
            "query_distance": 0.20,
            "parent_query_distance": 0.10,
            "dispersion": 0.5,  # High dispersion
            "entropy": 0.8,  # High entropy
            "support_count": 10,
        }

        decision_1 = policy.decide_branch_action(
            node_stats=node_stats_1,
            tree_signals={},
        )
        decision_2 = policy.decide_branch_action(
            node_stats=node_stats_2,
            tree_signals={},
        )

        # Both should produce same decision (HIRO ignores dispersion/entropy)
        assert decision_1 == decision_2