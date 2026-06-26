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

    def test_dispatch_calls_traverse_hotspot_with_children_when_hotspot_equals_start(self) -> None:
        """When hotspot_node_id == start_node_id, traversal uses dedicated hotspot handler."""
        # Setup: create a hotspot node that will trigger dispatch
        hotspot_node_id = uuid.uuid4()

        # Mock registry and adapter
        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": hotspot_node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = MagicMock()
        adapter.analyze_tree_semantic_distribution.return_value = {
            "node_stats": [],
            "tree_signals": {},
        }

        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,
            entropy_threshold=0.5,
            min_support_threshold=1,
        )

        runner = RecursiveTreeTraversalRunner()

        # Patch the method on the class before instantiation
        import unittest.mock
        with unittest.mock.patch.object(
            RecursiveTreeTraversalRunner,
            '_traverse_hotspot_with_children',
            return_value=[]
        ) as mock_hotspot_handler:
            # Call traverse_tree_for_query with hotspot_node_id == start_node_id
            runner.traverse_tree_for_query(
                version_id=uuid.uuid4(),
                query_embedding=[0.1, 0.2, 0.3],
                registry=registry,
                policy=policy,
                adapter=adapter,
                start_node_id=hotspot_node_id,
                hotspot_node_id=hotspot_node_id,
            )

            # Verify dispatch to _traverse_hotspot_with_children
            mock_hotspot_handler.assert_called_once()
            call_kwargs = mock_hotspot_handler.call_args.kwargs
            assert call_kwargs["hotspot_node"]["node_id"] == hotspot_node_id


class TestHotspotWithChildren:
    """P13-02: Hotspot with evidence-bearing children returns waypoint + evidence hits."""

    def test_returns_waypoint_plus_evidence_hits(self) -> None:
        """Hotspot traversal returns waypoint (MISSING_CHUNK_ID) + real child evidence."""
        # Setup: hotspot node with 2 children that have evidence chunks
        hotspot_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()
        chunk1_id = uuid.uuid4()
        chunk2_id = uuid.uuid4()
        span1_id = uuid.uuid4()
        span2_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()

        hotspot_node = {"node_id": hotspot_id, "parent_node_id": None}
        child1_node = {"node_id": child1_id, "parent_node_id": hotspot_id}
        child2_node = {"node_id": child2_id, "parent_node_id": hotspot_id}

        node_by_id = {
            hotspot_id: hotspot_node,
            child1_id: child1_node,
            child2_id: child2_node,
        }

        child1_stats = {
            "node_id": child1_id,
            "prototype_embedding": [0.1, 0.2, 0.3],
            "chunk_ids": [chunk1_id],
            "entropy": 0.3,
        }
        child2_stats = {
            "node_id": child2_id,
            "prototype_embedding": [0.4, 0.5, 0.6],
            "chunk_ids": [chunk2_id],
            "entropy": 0.4,
        }

        node_stats_list = [child1_stats, child2_stats]
        chunk_to_span_ids = {chunk1_id: [span1_id], chunk2_id: [span2_id]}

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node=hotspot_node,
            version_id=version_id,
            query_embedding=[0.5, 0.5, 0.5],
            node_stats_list=node_stats_list,
            node_by_id=node_by_id,
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=doc_id,
            chunk_to_span_ids=chunk_to_span_ids,
            max_depth=10,
        )

        # Verify: 1 waypoint + 2 evidence hits
        assert len(hits) == 3

        # First hit is waypoint
        waypoint = hits[0]
        assert waypoint.chunk_id == MISSING_CHUNK_ID
        assert waypoint.drill_depth == 0
        assert waypoint.node_id == hotspot_id

        # Remaining hits are evidence with real chunk_ids
        evidence_hits = hits[1:]
        for hit in evidence_hits:
            assert hit.chunk_id != MISSING_CHUNK_ID
            assert hit.drill_depth == 1


class TestWaypointShape:
    """P13-03: Waypoint hit has drill_depth=0, evidence hits have drill_depth=1."""

    def test_waypoint_drill_depth_zero(self) -> None:
        """Waypoint hit marks the hotspot at drill_depth=0."""
        hotspot_id = uuid.uuid4()
        runner = RecursiveTreeTraversalRunner()

        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[],
            node_by_id={hotspot_id: {"node_id": hotspot_id, "parent_node_id": None}},
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={},
            max_depth=10,
        )

        # Hotspot with no children returns waypoint only
        assert len(hits) == 1
        assert hits[0].drill_depth == 0

    def test_evidence_hit_drill_depth_one(self) -> None:
        """Evidence hits from direct children have drill_depth=1."""
        hotspot_id = uuid.uuid4()
        child_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[
                {
                    "node_id": child_id,
                    "prototype_embedding": [0.1, 0.2],
                    "chunk_ids": [chunk_id],
                }
            ],
            node_by_id={
                hotspot_id: {"node_id": hotspot_id, "parent_node_id": None},
                child_id: {"node_id": child_id, "parent_node_id": hotspot_id},
            },
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={chunk_id: [uuid.uuid4()]},
            max_depth=10,
        )

        # Verify evidence hit has drill_depth=1
        evidence_hit = hits[1]
        assert evidence_hit.drill_depth == 1


class TestEvidenceHitShape:
    """P13-04: Evidence hits carry real chunk_id (not MISSING_CHUNK_ID) from child node_stats."""

    def test_evidence_hit_chunk_id_is_real_uuid(self) -> None:
        """Child evidence hits have real chunk_id from node_stats, not MISSING sentinel."""
        hotspot_id = uuid.uuid4()
        child_id = uuid.uuid4()
        chunk_id = uuid.uuid4()  # Real chunk ID

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[
                {
                    "node_id": child_id,
                    "prototype_embedding": [0.1, 0.2],
                    "chunk_ids": [chunk_id],
                }
            ],
            node_by_id={
                hotspot_id: {"node_id": hotspot_id, "parent_node_id": None},
                child_id: {"node_id": child_id, "parent_node_id": hotspot_id},
            },
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={chunk_id: [uuid.uuid4()]},
            max_depth=10,
        )

        # Verify evidence hit chunk_id matches the real chunk_id from stats
        evidence_hit = hits[1]
        assert evidence_hit.chunk_id == chunk_id
        assert evidence_hit.chunk_id != MISSING_CHUNK_ID


class TestHotspotNoChildren:
    """P13-05: Hotspot with no children returns waypoint-only list unless it has direct evidence."""

    def test_leaf_hotspot_with_direct_chunks_returns_waypoint_plus_own_evidence(self) -> None:
        """Q18 regression: leaf fallback hotspot should map to real chunks.

        Real validation selected a hybrid_cluster ``leaf_fallback`` hotspot with
        direct chunks and no children. Waypoint-only output was skipped by backend
        mapping and triggered zero-chunk fallback hits, so direct leaf evidence
        must be returned with the waypoint.
        """
        hotspot_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        span_id = uuid.uuid4()

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[
                {
                    "node_id": hotspot_id,
                    "prototype_embedding": [0.5, 0.5],
                    "chunk_ids": [chunk_id],
                }
            ],
            node_by_id={hotspot_id: {"node_id": hotspot_id, "parent_node_id": None}},
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={chunk_id: [span_id]},
            max_depth=10,
        )

        assert len(hits) == 2
        assert hits[0].chunk_id == MISSING_CHUNK_ID
        assert hits[0].drill_depth == 0
        assert hits[1].chunk_id == chunk_id
        assert hits[1].node_id == hotspot_id
        assert hits[1].drill_depth == 0

    def test_hotspot_no_children_returns_waypoint_only(self) -> None:
        """Hotspot without children returns waypoint hit, prevents backend_hits=[] fallback."""
        hotspot_id = uuid.uuid4()

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[],
            node_by_id={hotspot_id: {"node_id": hotspot_id, "parent_node_id": None}},
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={},
            max_depth=10,
        )

        # Returns waypoint only (not empty list)
        assert len(hits) == 1
        assert hits[0].chunk_id == MISSING_CHUNK_ID
        assert hits[0].node_id == hotspot_id


class TestHotspotRouteOnlyChildren:
    """P13-06: Hotspot children that are all route-only (no chunk_ids) produce waypoint only."""

    def test_route_only_children_produce_waypoint_only(self) -> None:
        """When all children lack chunk_ids, only waypoint is returned (evidence_hits=[])."""
        hotspot_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[
                {
                    "node_id": child1_id,
                    "prototype_embedding": [0.1, 0.2],
                    "chunk_ids": [],  # Route-only: no chunks
                },
                {
                    "node_id": child2_id,
                    "prototype_embedding": [0.3, 0.4],
                    "chunk_ids": [],  # Route-only: no chunks
                },
            ],
            node_by_id={
                hotspot_id: {"node_id": hotspot_id, "parent_node_id": None},
                child1_id: {"node_id": child1_id, "parent_node_id": hotspot_id},
                child2_id: {"node_id": child2_id, "parent_node_id": hotspot_id},
            },
            tree_signals={},
            policy=BaselineTreeBranchDecisionPolicy(
                dispersion_threshold=0.5,
                entropy_threshold=0.5,
                min_support_threshold=1,
            ),
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={},
            max_depth=10,
        )

        # Only waypoint returned (no evidence hits)
        assert len(hits) == 1
        assert hits[0].chunk_id == MISSING_CHUNK_ID


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

    def test_policy_evaluates_children_not_hotspot_parent(self) -> None:
        """Policy.evaluate_children is called with child_stats, not with hotspot parent stats."""
        hotspot_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()

        # Create a mock policy with evaluate_children
        mock_policy = MagicMock()
        mock_policy.evaluate_children.return_value = {
            "decision": "prune",
            "selected_child_id": None,
            "child_decisions": {},
        }

        runner = RecursiveTreeTraversalRunner()
        hits = runner._traverse_hotspot_with_children(
            hotspot_node={"node_id": hotspot_id, "parent_node_id": None},
            version_id=uuid.uuid4(),
            query_embedding=[0.5, 0.5],
            node_stats_list=[
                {
                    "node_id": child1_id,
                    "prototype_embedding": [0.1, 0.2],
                    "chunk_ids": [],
                },
                {
                    "node_id": child2_id,
                    "prototype_embedding": [0.3, 0.4],
                    "chunk_ids": [],
                },
            ],
            node_by_id={
                hotspot_id: {"node_id": hotspot_id, "parent_node_id": None},
                child1_id: {"node_id": child1_id, "parent_node_id": hotspot_id},
                child2_id: {"node_id": child2_id, "parent_node_id": hotspot_id},
            },
            tree_signals={},
            policy=mock_policy,
            registry=MagicMock(),
            doc_id=uuid.uuid4(),
            chunk_to_span_ids={},
            max_depth=10,
        )

        # Verify evaluate_children was called
        mock_policy.evaluate_children.assert_called_once()

        # Verify it was called with child_stats, not hotspot parent stats
        call_kwargs = mock_policy.evaluate_children.call_args.kwargs
        child_stats_arg = call_kwargs["child_stats"]

        # child_stats should have child node_ids, not hotspot_id
        child_node_ids = {stats["node_id"] for stats in child_stats_arg}
        assert hotspot_id not in child_node_ids
        assert child1_id in child_node_ids or child2_id in child_node_ids


class TestFallbackDictChunkId:
    """P13-12: Fallback dict now contains chunk_id field (MISSING_CHUNK_ID) when traversal returns empty."""

    def test_fallback_dict_has_chunk_id_field(self) -> None:
        """Fallback dict from _score_tree_nodes_with_fallback includes chunk_id=MISSING_CHUNK_ID."""
        from llamaindex_runtime.tree.runtime import _score_tree_nodes_with_fallback, MISSING_CHUNK_ID
        from llamaindex_runtime.tree.scoring import TreeScoring

        # Create a node that will score positively (contains query_text substring)
        node_id = uuid.uuid4()
        query_text = "machine learning algorithms"
        node = {
            "node_id": node_id,
            "summary_text": "This section covers machine learning algorithms for classification",
            "heading_path": "Chapter 3 > Machine Learning",
        }

        # Call fallback scoring
        scored_nodes = _score_tree_nodes_with_fallback(
            nodes=[node],
            query_text=query_text,
            span_ids_by_node={},
            limit=10,
        )

        # Verify at least one node scored positively
        assert len(scored_nodes) > 0, "Fixture node must score > 0.0 for this test"

        # Verify chunk_id field present and equals MISSING_CHUNK_ID
        first_result = scored_nodes[0]
        assert "chunk_id" in first_result
        assert first_result["chunk_id"] == MISSING_CHUNK_ID


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