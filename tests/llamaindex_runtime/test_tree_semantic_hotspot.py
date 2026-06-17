"""Tests for tree semantic retrieval hotspot behavior.

These tests validate:
1. SubtreeHotspotSelector selects a parent hotspot from descendant evidence
2. RecursiveTreeTraversalRunner supports start_node_id parameter
3. Route-only parent without stats drills to evidence-bearing child
4. Runtime maps hotspot navigation metadata and final evidence-bearing hits

NOTE: These tests validate implemented hotspot navigation behavior.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.runtime import _map_query_hits_to_backend_hits
from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SubtreeHotspotSelector,
)


class TestSubtreeHotspotSelector:
    """Hotspot selector chooses nearest parent route when descendant has evidence."""

    def test_selector_returns_nearest_parent_when_descendant_has_evidence(self) -> None:
        """When evidence is in descendant, hotspot should be the nearest route parent.

        This avoids root-bias while still treating parent nodes as route-only
        hotspot heads instead of final content hits.
        """
        # NOTE: SubtreeHotspotSelector class does not yet exist
        # This test documents expected behavior for future implementation
        version_id = uuid.uuid4()
        parent_node_id = uuid.uuid4()
        child_node_id = uuid.uuid4()
        grandchild_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        # Mock registry with tree hierarchy
        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": parent_node_id,
                "heading_path": "Chapter 1",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_node_id,
                "heading_path": "Chapter 1 > Section 1.1",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
            {
                "node_id": grandchild_node_id,
                "heading_path": "Chapter 1 > Section 1.1 > Detail",
                "level_no": 2,
                "parent_node_id": child_node_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": grandchild_node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "node_id": grandchild_node_id,
                "embedding": [1.0, 2.0],
            },
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        report = PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
            version_id=version_id,
            registry=registry,
        )
        hotspots = SubtreeHotspotSelector().select_hotspots(
            query_embedding=[1.0, 2.0],
            node_stats=report["node_stats"],
            tree_signals=report["tree_signals"],
            limit=1,
        )

        assert hotspots
        assert hotspots[0].node_id == child_node_id

    def test_selector_rejects_query_embedding_dimension_mismatch(self) -> None:
        """Query embedding dimension must match indexed tree embeddings."""
        with pytest.raises(ValueError, match="query embedding dimension"):
            SubtreeHotspotSelector().select_hotspots(
                query_embedding=[1.0],
                node_stats=[
                    {
                        "node_id": uuid.uuid4(),
                        "heading_path": "Chapter",
                        "prototype_embedding": [1.0, 0.0],
                        "centroid": [1.0, 0.0],
                        "support_count": 1,
                    }
                ],
                tree_signals={"embedding_dimension": 2},
                limit=1,
            )


class TestRecursiveTreeTraversalRunnerStartNodeId:
    """Traversal runner supports starting from specific node."""

    def test_start_node_id_limits_traversal_scope(self) -> None:
        """When start_node_id provided, traversal begins from that node.

        This enables hotspot navigation where we drill into a specific
        subtree rather than traversing from root.
        """
        version_id = uuid.uuid4()
        root_node_id = uuid.uuid4()
        target_node_id = uuid.uuid4()
        child_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": root_node_id,
                "heading_path": "Root",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": target_node_id,
                "heading_path": "Target",
                "level_no": 1,
                "parent_node_id": root_node_id,
            },
            {
                "node_id": child_node_id,
                "heading_path": "Target > Child",
                "level_no": 2,
                "parent_node_id": target_node_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": child_node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": child_node_id, "embedding": [1.0, 1.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        query_embedding = [1.0, 1.0]

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
            start_node_id=target_node_id,
            hotspot_node_id=target_node_id,
        )

        assert hits
        assert all(root_node_id not in hit.navigation_node_ids for hit in hits)
        assert {hit.node_id for hit in hits} == {child_node_id}
        assert hits[0].hotspot_node_id == target_node_id


class TestHotspotDrillDownToEvidence:
    """Parent hotspot drills down to evidence-bearing child."""

    def test_parent_with_chunks_and_dispersion_drills_to_children(self) -> None:
        """When parent node HAS chunks AND high dispersion, policy decides drill_down.

        This tests current working behavior where parent has evidence but
        dispersed, triggering descent to more specific children.
        """
        version_id = uuid.uuid4()
        parent_node_id = uuid.uuid4()
        child_a_id = uuid.uuid4()
        child_b_id = uuid.uuid4()
        span_parent = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_parent = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": parent_node_id,
                "heading_path": "Dispersed Parent",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_a_id,
                "heading_path": "Dispersed Parent > Child A",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
            {
                "node_id": child_b_id,
                "heading_path": "Dispersed Parent > Child B",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": parent_node_id, "span_id": span_parent, "ordinal_no": 0},
            {"node_id": child_a_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": child_b_id, "span_id": span_b, "ordinal_no": 0},
        ]
        # Parent HAS dispersed chunks, children also have evidence
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_parent,
                "node_id": parent_node_id,
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_id": chunk_parent,
                "node_id": parent_node_id,
                "embedding": [0.0, 1.0],
            },
            {"chunk_id": chunk_a, "node_id": child_a_id, "embedding": [1.0, 0.0]},
            {"chunk_id": chunk_b, "node_id": child_b_id, "embedding": [0.0, 1.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_parent, "span_id": span_parent, "ordinal_no": 0},
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,  # Low threshold to trigger drill_down
            entropy_threshold=0.3,  # Low threshold for entropy
        )
        runner = RecursiveTreeTraversalRunner()

        query_embedding = [0.5, 0.5]

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Current behavior: parent has chunks + dispersion => drill_down to children
        assert len(hits) >= 1
        assert {hit.node_id for hit in hits}
        # All hits should have valid provenance
        for hit in hits:
            assert hit.chunk_id != uuid.UUID(int=0)
            assert hit.span_id != uuid.UUID(int=0)

    def test_parent_without_stats_drills_to_child_with_evidence(self) -> None:
        """Route-only parent aggregates descendant stats and drills to evidence.

        Parent nodes without direct chunks are semantic waypoints.  Their
        subtree statistics let traversal enter the subtree while final hits
        still come only from evidence-bearing children.
        """
        version_id = uuid.uuid4()
        parent_node_id = uuid.uuid4()
        child_a_id = uuid.uuid4()
        child_b_id = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": parent_node_id,
                "heading_path": "Hotspot Parent",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_a_id,
                "heading_path": "Hotspot Parent > Child A",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
            {
                "node_id": child_b_id,
                "heading_path": "Hotspot Parent > Child B",
                "level_no": 1,
                "parent_node_id": parent_node_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": child_a_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": child_b_id, "span_id": span_b, "ordinal_no": 0},
        ]
        # Parent has NO chunks/evidence, only children have evidence
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": child_a_id, "embedding": [1.0, 0.0]},
            {"chunk_id": chunk_b, "node_id": child_b_id, "embedding": [0.0, 1.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        query_embedding = [0.5, 0.5]

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert len(hits) == 2
        assert {hit.node_id for hit in hits} == {child_a_id, child_b_id}
        assert all(hit.chunk_id != uuid.UUID(int=0) for hit in hits)


class TestRuntimeHotspotMetadataMapping:
    """Runtime maps hotspot navigation metadata to backend hits."""

    def test_runtime_preserves_hotspot_provenance_in_hit_metadata(self) -> None:
        """When hotspot navigation produces QueryHits, runtime should
        preserve navigation metadata (hotspot_node_id, drill_depth) in
        the backend hit output.

        This tests the mapping from QueryHit to backend hit dict with
        hotspot-specific metadata fields.
        """
        version_id = uuid.uuid4()
        hotspot_node_id = uuid.uuid4()
        evidence_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": hotspot_node_id,
                "heading_path": "Hotspot",
                "level_no": 0,
                "parent_node_id": None,
                "summary_text": "Hotspot summary",
            },
            {
                "node_id": evidence_node_id,
                "heading_path": "Hotspot > Evidence",
                "level_no": 1,
                "parent_node_id": hotspot_node_id,
                "summary_text": "Evidence detail",
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": evidence_node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "node_id": evidence_node_id,
                "embedding": [1.0, 1.0],
            },
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        query_hit = QueryHit(
            doc_id=uuid.uuid4(),
            version_id=version_id,
            span_id=span_id,
            chunk_id=chunk_id,
            node_id=evidence_node_id,
            similarity_score=0.85,
            hotspot_node_id=hotspot_node_id,
            navigation_node_ids=(hotspot_node_id, evidence_node_id),
            drill_depth=1,
        )

        mapped_hits = _map_query_hits_to_backend_hits(
            query_hits=[query_hit],
            node_by_id={
                hotspot_node_id: registry.query_tree_nodes_by_version.return_value[0],
                evidence_node_id: registry.query_tree_nodes_by_version.return_value[1],
            },
            span_ids_by_node={evidence_node_id: [span_id]},
        )

        assert len(mapped_hits) == 1
        mapped_hit = mapped_hits[0]
        assert mapped_hit["chunk_id"] == chunk_id
        assert mapped_hit["hotspot_node_id"] == hotspot_node_id
        assert mapped_hit["navigation_node_ids"] == [hotspot_node_id, evidence_node_id]
        assert mapped_hit["navigation_path"] == ["Hotspot", "Hotspot > Evidence"]
        assert mapped_hit["drill_depth"] == 1
        assert mapped_hit["backend_source"] == "tree_semantic"
        assert mapped_hit["retrieval_path"] == "subtree_hotspot_traversal"

    def test_runtime_maps_root_semantic_hits_with_consistent_schema(self) -> None:
        """Root semantic traversal hits should expose the same provenance keys."""
        evidence_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        query_hit = QueryHit(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            span_id=span_id,
            chunk_id=chunk_id,
            node_id=evidence_node_id,
            similarity_score=0.72,
        )

        mapped_hits = _map_query_hits_to_backend_hits(
            query_hits=[query_hit],
            node_by_id={
                evidence_node_id: {
                    "node_id": evidence_node_id,
                    "heading_path": "Evidence",
                    "summary_text": "Evidence summary",
                }
            },
            span_ids_by_node={evidence_node_id: [span_id]},
        )

        assert len(mapped_hits) == 1
        mapped_hit = mapped_hits[0]
        assert mapped_hit["chunk_id"] == chunk_id
        assert mapped_hit["chunk_id_missing"] is False
        assert mapped_hit["hotspot_node_id"] is None
        assert mapped_hit["navigation_node_ids"] == []
        assert mapped_hit["navigation_path"] == []
        assert mapped_hit["drill_depth"] == 0
        assert mapped_hit["backend_source"] == "tree_semantic"
        assert mapped_hit["retrieval_path"] == "semantic_traversal"


class TestEvidenceBearingHitsFinalOutput:
    """Final hits from traversal are evidence-bearing nodes."""

    def test_final_hits_contain_actual_chunk_evidence(self) -> None:
        """EXPECTED BEHAVIOR:
        Traversal should only return hits from nodes with actual chunks,
        not intermediate hotspot nodes that guided navigation.

        CURRENT BEHAVIOR:
        Nodes without chunks are filtered out, so hits always have evidence.
        This works for current behavior but needs enhancement for hotspot
        navigation where parents guide descent to children.
        """
        version_id = uuid.uuid4()
        waypoint_node_id = uuid.uuid4()
        evidence_node_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": waypoint_node_id,
                "heading_path": "Waypoint",
                "level_no": 0,
                "parent_node_id": None,
                "summary_text": "Navigation waypoint (no chunks)",
            },
            {
                "node_id": evidence_node_id,
                "heading_path": "Waypoint > Evidence",
                "level_no": 1,
                "parent_node_id": waypoint_node_id,
                "summary_text": "Evidence node with chunks",
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": evidence_node_id, "span_id": span_id, "ordinal_no": 0},
        ]
        # Waypoint has NO chunks, evidence node has chunks
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "node_id": evidence_node_id,
                "embedding": [2.0, 2.0],
            },
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
        )
        runner = RecursiveTreeTraversalRunner()

        query_embedding = [2.0, 2.0]

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert len(hits) == 1
        assert hits[0].node_id == evidence_node_id
        assert hits[0].chunk_id == chunk_id
        assert hits[0].span_id == span_id


class TestHotspotNavigationIntegration:
    """End-to-end hotspot navigation from parent to evidence."""

    def test_full_hotspot_flow_selects_parent_then_drills(self) -> None:
        """Complete hotspot navigation flow:
        1. Semantic distribution identifies route parent as hotspot from children stats
        2. Policy drills down through route-only parent
        3. Traversal descends to evidence-bearing children
        4. Final hits preserve child evidence provenance
        """
        version_id = uuid.uuid4()
        hotspot_parent_id = uuid.uuid4()
        child_a_id = uuid.uuid4()
        child_b_id = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": hotspot_parent_id,
                "heading_path": "Hotspot Chapter",
                "level_no": 0,
                "parent_node_id": None,
            },
            {
                "node_id": child_a_id,
                "heading_path": "Hotspot Chapter > Evidence A",
                "level_no": 1,
                "parent_node_id": hotspot_parent_id,
            },
            {
                "node_id": child_b_id,
                "heading_path": "Hotspot Chapter > Evidence B",
                "level_no": 1,
                "parent_node_id": hotspot_parent_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": child_a_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": child_b_id, "span_id": span_b, "ordinal_no": 0},
        ]
        # Parent has NO chunks - children have dispersed evidence
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": child_a_id, "embedding": [1.0, 0.0]},
            {"chunk_id": chunk_b, "node_id": child_b_id, "embedding": [0.0, 1.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = uuid.uuid4()

        adapter = PersistedTreeSemanticDistributionAdapter()
        # Policy with thresholds that trigger drill_down for dispersed children
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=0.5,  # Lower threshold to trigger drill_down
            entropy_threshold=0.3,  # Lower threshold for entropy
        )
        runner = RecursiveTreeTraversalRunner()

        query_embedding = [0.5, 0.5]  # Central query matching both children

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        assert len(hits) == 2
        assert {hit.node_id for hit in hits} == {child_a_id, child_b_id}
        assert {hit.chunk_id for hit in hits} == {chunk_a, chunk_b}
        assert all(hit.drill_depth == 1 for hit in hits)

    def test_cyclic_tree_relationship_fails_fast(self) -> None:
        """Corrupt tree cycles should not recurse forever during aggregation."""
        node_a_id = uuid.uuid4()
        node_b_id = uuid.uuid4()
        span_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        registry = MagicMock()
        registry.query_tree_nodes_by_version.return_value = [
            {
                "node_id": node_a_id,
                "heading_path": "A",
                "parent_node_id": node_b_id,
            },
            {
                "node_id": node_b_id,
                "heading_path": "B",
                "parent_node_id": node_a_id,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a_id, "span_id": span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": node_a_id, "embedding": [1.0, 0.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        with pytest.raises(ValueError, match="cycle detected"):
            PersistedTreeSemanticDistributionAdapter().analyze_tree_semantic_distribution(
                version_id=uuid.uuid4(),
                registry=registry,
            )


class TestHotspotSelectorSwitch:
    """Phase 11: Config-driven selector switch validation."""

    def test_hotspot_selector_switch_routes_to_cluster_selector(self) -> None:
        """Verify RAG_TREE_HOTSPOT_SELECTOR=cluster routes to ClusterHotspotSelector."""
        from llamaindex_runtime.tree.semantic_distribution import (
            ClusterHotspotSelector,
            get_hotspot_selector,
        )

        selector = get_hotspot_selector("cluster")
        assert isinstance(selector, ClusterHotspotSelector)
        assert not isinstance(selector, SubtreeHotspotSelector)

    def test_hotspot_selector_switch_routes_to_route_selector(self) -> None:
        """Verify RAG_TREE_HOTSPOT_SELECTOR=route_subtree routes to SubtreeHotspotSelector."""
        from llamaindex_runtime.tree.semantic_distribution import get_hotspot_selector

        selector = get_hotspot_selector("route_subtree")
        assert isinstance(selector, SubtreeHotspotSelector)
        assert not isinstance(selector, ClusterHotspotSelector)

    def test_hotspot_selector_switch_invalid_strategy_raises(self) -> None:
        """Verify invalid strategy raises ValueError."""
        from llamaindex_runtime.tree.semantic_distribution import get_hotspot_selector

        with pytest.raises(ValueError, match="Unknown hotspot selector strategy"):
            get_hotspot_selector("invalid_strategy")
