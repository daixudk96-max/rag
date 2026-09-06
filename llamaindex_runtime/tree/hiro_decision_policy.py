"""HIRO-enhanced TreeBranchDecisionPolicy with distance+delta threshold logic.

Transplants HIRO's dual-threshold decision mechanism into local semantic distribution context.

HIRO logic (from donor test_hiro_decision.py):
    delta = child_distance - parent_distance
    should_drill = (delta > delta_threshold) AND (distance > selection_threshold)

Local adaptation:
- distance: query_distance (precomputed by RecursiveTreeTraversalRunner)
- parent_distance: parent_query_distance (precomputed)
- Thresholds configurable via constructor
- Preserves TreeBranchDecisionPolicy protocol
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HIROEnhancedTreeBranchDecisionPolicy:
    """Distance-based decision policy using HIRO's dual-threshold logic.

    This transplants HIRO's decision skeleton:
    - Delta threshold: measures improvement/degradation relative to parent
    - Selection threshold: minimum relevance to consider drilling

    Unlike BaselineTreeBranchDecisionPolicy (dispersion/entropy-based),
    this uses query_distance metrics (distance from query vector to node centroid).

    Decision logic:
    1. If support_count < min_support_threshold → prune (statistical significance)
    2. Calculate delta = query_distance - parent_query_distance
    3. If delta > delta_threshold AND query_distance > selection_threshold → drill_down
    4. Otherwise → prune or keep_parent (depending on delta sign)

    Parameters
    ----------
    selection_threshold:
        Minimum query_distance to consider drilling (nodes below this are too close).
    delta_threshold:
        Minimum delta to drill (child must be worse enough than parent).
    min_support_threshold:
        Minimum support_count for statistical significance.
    """

    selection_threshold: float
    delta_threshold: float
    min_support_threshold: int = 1

    def decide_branch_action(
        self,
        *,
        node_stats: dict[str, Any],
        tree_signals: dict[str, Any],
    ) -> str:
        """Decide branch action using HIRO's dual-threshold logic.

        Parameters
        ----------
        node_stats:
            Must contain:
            - query_distance: distance from query to node centroid
            - parent_query_distance: distance from query to parent centroid
            - support_count: number of chunks in node
        tree_signals:
            Tree-level signals (ignored by HIRO logic).

        Returns
        -------
        str
            "drill_down", "keep_parent", or "prune"
        """
        # 1. Check support count (statistical significance)
        support_count = node_stats.get("support_count", 0)
        # If support_count missing, assume sufficient (don't prune on missing data)
        if support_count > 0 and support_count < self.min_support_threshold:
            return "prune"

        if node_stats.get("is_route_node"):
            return "drill_down"

        # 2. Extract distances
        query_distance = node_stats.get("query_distance", 0.0)
        parent_query_distance = node_stats.get("parent_query_distance", 0.0)

        # 3. Calculate delta (HIRO formula)
        delta = query_distance - parent_query_distance

        # 4. Apply HIRO dual-threshold logic
        # HIRO drills down when:
        # - Child is WORSE than parent (delta > delta_threshold, positive)
        # - Child is still RELEVANT (query_distance > selection_threshold)
        meets_selection_threshold = query_distance > self.selection_threshold
        meets_delta_threshold = delta > self.delta_threshold

        if meets_delta_threshold and meets_selection_threshold:
            return "drill_down"

        # 5. If child is BETTER than parent (negative delta)
        # Keep parent (parent already captures this relevance)
        if delta < 0:
            return "keep_parent"

        # 6. Otherwise, prune
        return "prune"

    def evaluate_children(
        self,
        *,
        child_stats: list[dict[str, Any]],
        tree_signals: dict[str, Any],
    ) -> dict[str, Any]:
        """Aggregate per-child HIRO decisions into a recursive selection result."""
        child_decisions: dict[Any, str] = {}
        selected_child_id: Any | None = None
        selected_child_score: float | None = None
        saw_keep_parent = False

        for child in child_stats:
            child_id = child.get("node_id")
            decision = self.decide_branch_action(
                node_stats=child,
                tree_signals=tree_signals,
            )
            child_decisions[child_id] = decision

            if decision == "keep_parent":
                saw_keep_parent = True
                continue
            if decision != "drill_down":
                continue

            query_distance = child.get("query_distance", 0.0)
            if selected_child_score is None or query_distance > selected_child_score:
                selected_child_score = query_distance
                selected_child_id = child_id

        if selected_child_id is not None:
            return {
                "decision": "drill_down",
                "selected_child_id": selected_child_id,
                "child_decisions": child_decisions,
            }
        if saw_keep_parent:
            return {
                "decision": "keep_parent",
                "selected_child_id": None,
                "child_decisions": child_decisions,
            }
        return {
            "decision": "prune",
            "selected_child_id": None,
            "child_decisions": child_decisions,
        }
