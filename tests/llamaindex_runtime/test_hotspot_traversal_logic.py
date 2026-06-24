"""Tests for hotspot traversal logic redesign (Phase 13).

These tests validate:
1. Hotspot traversal dispatch detection (hotspot_node_id == start_node_id)
2. Waypoint hit construction (navigation marker with MISSING_CHUNK_ID)
3. BaselineTreeBranchDecisionPolicy.evaluate_children (HIRO-parity interface)
4. Evidence hit shape from child chunks
5. Edge cases: no children, route-only children
6. Fallback dict chunk_id field

Wave 0 scaffold: all 11 required classes present; Plan 01 tests GREEN,
Plan 02/04 tests skip-marked awaiting their wave.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

# NOTE: HIROEnhancedTreeBranchDecisionPolicy import moved to skip-marked tests
# (P13-11 regression tests are not part of Plan 01 acceptance criteria)
from llamaindex_runtime.tree.runtime import MISSING_CHUNK_ID, _map_query_hits_to_backend_hits
from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    QueryHit,
    RecursiveTreeTraversalRunner,
)


class TestHotspotTraversalDispatch:
    """P13-01: traverse_tree_for_query dispatches to _traverse_hotspot_with_children when hotspot_node_id == start_node_id."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_dispatch_calls_traverse_hotspot_with_children_when_hotspot_equals_start(self) -> None:
        """When hotspot_node_id == start_node_id, traversal uses dedicated hotspot handler."""
        # Plan 02 implements the dispatch gate and _traverse_hotspot_with_children method
        pass


class TestHotspotWithChildren:
    """P13-02: Hotspot with evidence-bearing children returns waypoint + evidence hits."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_returns_waypoint_plus_evidence_hits(self) -> None:
        """Hotspot traversal returns waypoint (MISSING_CHUNK_ID) + real child evidence."""
        pass


class TestWaypointShape:
    """P13-03: Waypoint hit has drill_depth=0, evidence hits have drill_depth=1."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_waypoint_drill_depth_zero(self) -> None:
        """Waypoint hit marks the hotspot at drill_depth=0."""
        pass

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_evidence_hit_drill_depth_one(self) -> None:
        """Evidence hits from direct children have drill_depth=1."""
        pass


class TestEvidenceHitShape:
    """P13-04: Evidence hits carry real chunk_id (not MISSING_CHUNK_ID) from child node_stats."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_evidence_hit_chunk_id_is_real_uuid(self) -> None:
        """Child evidence hits have real chunk_id from node_stats, not MISSING sentinel."""
        pass


class TestHotspotNoChildren:
    """P13-05: Hotspot with no children returns waypoint-only list (not empty)."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_hotspot_no_children_returns_waypoint_only(self) -> None:
        """Hotspot without children returns waypoint hit, prevents backend_hits=[] fallback."""
        pass


class TestHotspotRouteOnlyChildren:
    """P13-06: Hotspot children that are all route-only (no chunk_ids) produce waypoint only."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_route_only_children_produce_waypoint_only(self) -> None:
        """When all children lack chunk_ids, only waypoint is returned (evidence_hits=[])."""
        pass


class TestBaselineEvaluateChildren:
    """P13-07: BaselineTreeBranchDecisionPolicy.evaluate_children returns correct dict shape."""

    def test_returns_dict_with_required_keys(self) -> None:
        """evaluate_children returns dict with keys: decision, selected_child_id, child_decisions."""
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,
            entropy_threshold=0.5,
            min_support_threshold=1,
        )
        result = policy.evaluate_children(child_stats=[], tree_signals={})
        assert isinstance(result, dict)
        assert set(result.keys()) == {"decision", "selected_child_id", "child_decisions"}
        assert result["decision"] in {"drill_down", "keep_parent", "prune"}

    def test_empty_child_stats_returns_prune(self) -> None:
        """Empty child_stats list returns prune decision."""
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,
            entropy_threshold=0.5,
            min_support_threshold=1,
        )
        result = policy.evaluate_children(child_stats=[], tree_signals={})
        assert result["decision"] == "prune"
        assert result["selected_child_id"] is None
        assert result["child_decisions"] == {}


class TestBaselineEvaluateChildrenDrillDown:
    """P13-08: Baseline evaluate_children selects child with highest similarity when best decision is drill_down."""

    def test_selects_best_similarity_child_for_drill_down(self) -> None:
        """When best child decision is drill_down, selected_child_id is the child with lowest query_distance."""
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,
            entropy_threshold=0.5,
            min_support_threshold=1,
        )

        child_id_1 = uuid.uuid4()
        child_id_2 = uuid.uuid4()

        # Child 1: high dispersion + high entropy + route → drill_down; query_distance=0.2 (better)
        child_stats_1 = {
            "node_id": child_id_1,
            "dispersion": 0.8,
            "entropy": 0.9,
            "support_count": 2,
            "is_route_node": True,
            "query_distance": 0.2,
        }

        # Child 2: high dispersion + high entropy + route → drill_down; query_distance=0.8 (worse)
        child_stats_2 = {
            "node_id": child_id_2,
            "dispersion": 0.8,
            "entropy": 0.9,
            "support_count": 2,
            "is_route_node": True,
            "query_distance": 0.8,
        }

        tree_signals = {"total_chunks": 10}

        result = policy.evaluate_children(
            child_stats=[child_stats_1, child_stats_2],
            tree_signals=tree_signals,
        )

        assert result["decision"] == "drill_down"
        assert result["selected_child_id"] == child_id_1
        assert child_id_1 in result["child_decisions"]
        assert result["child_decisions"][child_id_1] == "drill_down"


class TestBaselineEvaluateChildrenKeepParent:
    """P13-09: Baseline evaluate_children returns keep_parent when best child decision is keep_parent."""

    def test_returns_keep_parent_when_best_child_keeps_parent(self) -> None:
        """When best child decision is keep_parent, aggregate decision is keep_parent."""
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,
            entropy_threshold=0.5,
            min_support_threshold=1,
        )

        child_id = uuid.uuid4()

        # Child: low dispersion + low entropy + support >= threshold → keep_parent
        child_stats = {
            "node_id": child_id,
            "dispersion": 0.2,
            "entropy": 0.1,
            "support_count": 2,
            "is_route_node": False,
            "query_distance": 0.3,
        }

        tree_signals = {"total_chunks": 10}

        result = policy.evaluate_children(
            child_stats=[child_stats],
            tree_signals=tree_signals,
        )

        assert result["decision"] == "keep_parent"
        assert result["selected_child_id"] is None
        assert child_id in result["child_decisions"]
        assert result["child_decisions"][child_id] == "keep_parent"


class TestPolicyEvaluateChildrenCalledOnChildStats:
    """P13-10: _traverse_hotspot_with_children calls policy.evaluate_children on child stats when available."""

    @pytest.mark.skip(reason="awaiting wave 2 — Plan 02")
    def test_policy_evaluates_children_not_hotspot_parent(self) -> None:
        """Policy.evaluate_children is called with child_stats, not with hotspot parent stats."""
        pass


class TestFallbackDictChunkId:
    """P13-12: Fallback dict now contains chunk_id field (MISSING_CHUNK_ID) when traversal returns empty."""

    @pytest.mark.skip(reason="awaiting wave 3 — Plan 03")
    def test_fallback_dict_has_chunk_id_field(self) -> None:
        """Fallback dict from _score_tree_nodes_with_fallback includes chunk_id=MISSING_CHUNK_ID."""
        pass


# Additional test for _build_waypoint_hit (P13-03 helper, tested in Plan 01)
class TestBuildWaypointHit:
    """Waypoint hit construction helper (module-level function in semantic_distribution.py)."""

    def test_build_waypoint_hit_returns_correct_shape(self) -> None:
        """_build_waypoint_hit returns QueryHit with MISSING_CHUNK_ID, drill_depth=0, similarity=0.0."""
        # Force worktree module load (pytest rootdir points to main repo)
        import sys
        from pathlib import Path

        # Clear all llamaindex_runtime modules from sys.modules
        worktree_root = Path(__file__).parent.parent.parent
        modules_to_clear = [
            name for name in sys.modules
            if name.startswith('llamaindex_runtime')
        ]
        for name in modules_to_clear:
            del sys.modules[name]

        # Add worktree to path and reimport
        sys.path.insert(0, str(worktree_root))

        from llamaindex_runtime.tree.semantic_distribution import _build_waypoint_hit, _MISSING_CHUNK_ID

        node_id = uuid.uuid4()
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        hotspot_node_id = node_id

        node = {"node_id": node_id}
        navigation_node_ids = (node_id,)

        hits = _build_waypoint_hit(
            node=node,
            version_id=version_id,
            doc_id=doc_id,
            chunk_to_span_ids={},
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=navigation_node_ids,
        )

        assert len(hits) == 1
        hit = hits[0]
        assert hit.chunk_id == _MISSING_CHUNK_ID
        assert hit.chunk_id == MISSING_CHUNK_ID  # parity with runtime.MISSING_CHUNK_ID
        assert hit.drill_depth == 0
        assert hit.similarity_score == 0.0
        assert hit.hotspot_node_id == hotspot_node_id
        assert hit.navigation_node_ids == navigation_node_ids
        assert hit.node_id == node_id