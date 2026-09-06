from __future__ import annotations

from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy


class TestHIRORecursiveEvaluationSkeleton:
    def test_policy_exposes_recursive_evaluate_children_entrypoint(self) -> None:
        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        assert hasattr(policy, "evaluate_children")
        assert callable(policy.evaluate_children)

    def test_evaluate_children_returns_best_child_and_aggregate_decision(self) -> None:
        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        child_stats = [
            {
                "node_id": "child-a",
                "query_distance": 0.12,
                "parent_query_distance": 0.10,
                "support_count": 10,
            },
            {
                "node_id": "child-b",
                "query_distance": 0.22,
                "parent_query_distance": 0.10,
                "support_count": 10,
            },
        ]

        result = policy.evaluate_children(
            child_stats=child_stats,
            tree_signals={},
        )

        assert result["selected_child_id"] == "child-b"
        assert result["decision"] == "drill_down"
        assert result["child_decisions"]["child-a"] == "prune"
        assert result["child_decisions"]["child-b"] == "drill_down"

    def test_evaluate_children_keeps_parent_when_no_child_qualifies(self) -> None:
        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
        )

        child_stats = [
            {
                "node_id": "child-a",
                "query_distance": 0.08,
                "parent_query_distance": 0.10,
                "support_count": 10,
            },
            {
                "node_id": "child-b",
                "query_distance": 0.11,
                "parent_query_distance": 0.10,
                "support_count": 10,
            },
        ]

        result = policy.evaluate_children(
            child_stats=child_stats,
            tree_signals={},
        )

        assert result["selected_child_id"] is None
        assert result["decision"] == "keep_parent"

    def test_evaluate_children_prunes_low_support_children_before_selection(self) -> None:
        policy = HIROEnhancedTreeBranchDecisionPolicy(
            selection_threshold=0.15,
            delta_threshold=0.05,
            min_support_threshold=5,
        )

        child_stats = [
            {
                "node_id": "child-a",
                "query_distance": 0.30,
                "parent_query_distance": 0.10,
                "support_count": 2,
            },
            {
                "node_id": "child-b",
                "query_distance": 0.20,
                "parent_query_distance": 0.10,
                "support_count": 10,
            },
        ]

        result = policy.evaluate_children(
            child_stats=child_stats,
            tree_signals={},
        )

        assert result["selected_child_id"] == "child-b"
        assert result["child_decisions"]["child-a"] == "prune"
        assert result["child_decisions"]["child-b"] == "drill_down"
