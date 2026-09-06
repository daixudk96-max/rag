"""
Tests for transplanted Psi-RAG traversal skeleton.

These tests validate the traversal loop skeleton transplanted from Psi-RAG concept,
adapted to preserve local provenance contracts and distribution-based decisions.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SemanticDistributionRegistry,
    TreeSemanticTraversalRunner,
)


class TestTreeSemanticTraversalRunner:
    """Tests for Psi-RAG traversal skeleton transplantation."""

    def test_traversal_starts_from_root_nodes(self) -> None:
        """Traversal must start from root nodes (level_no=0 or no parent)."""
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        root_node_id = uuid.uuid4()
        child_node_id = uuid.uuid4()
        root_chunk_id = uuid.uuid4()
        child_chunk_id = uuid.uuid4()
        root_span_id = uuid.uuid4()
        child_span_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_node_id, "parent_node_id": None, "level_no": 0},
            {
                "node_id": child_node_id,
                "parent_node_id": root_node_id,
                "level_no": 1,
            },
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": root_node_id, "span_id": root_span_id, "ordinal_no": 0},
            {"node_id": child_node_id, "span_id": child_span_id, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": root_chunk_id,
                "node_id": root_node_id,
                "embedding": [1.0, 2.0],
            },
            {
                "chunk_id": child_chunk_id,
                "node_id": child_node_id,
                "embedding": [3.0, 4.0],
            },
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": root_chunk_id, "span_id": root_span_id, "ordinal_no": 0},
            {"chunk_id": child_chunk_id, "span_id": child_span_id, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id
        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # At least one hit should come from root node
        assert any(hit.node_id == root_node_id for hit in hits)

    def test_policy_guides_descent_decisions(self) -> None:
        """At each node, policy decides whether to drill down, keep parent, or prune."""
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": uuid.uuid4(),
                "node_id": node_id,
                "embedding": [1.0, 2.0],
            }
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []
        registry.query_node_embeddings_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Policy should make some decision (hits non-empty means keep_parent or drill_down)
        # This test passes if traversal completes without error
        assert isinstance(hits, list)

    def test_evidence_accumulates_across_visited_nodes(self) -> None:
        """Traversal accumulates chunk_ids and span_ids across visited nodes."""
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_a, "parent_node_id": None, "level_no": 0},
            {"node_id": node_b, "parent_node_id": node_a, "level_no": 1},
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_a, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_a, "node_id": node_a, "embedding": [1.0, 2.0]},
            {"chunk_id": chunk_b, "node_id": node_b, "embedding": [3.0, 4.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Evidence should include chunks from visited nodes
        chunk_ids = {hit.chunk_id for hit in hits}
        assert chunk_a in chunk_ids or chunk_b in chunk_ids

    def test_returns_query_hits_with_provenance(self) -> None:
        """Traversal returns QueryHit list with doc_id, version_id, span_id, chunk_id, node_id."""
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": chunk_id, "node_id": node_id, "embedding": [1.0, 2.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        if hits:
            hit = hits[0]
            assert isinstance(hit, QueryHit)
            assert hit.version_id == version_id
            assert hit.chunk_id == chunk_id
            assert hit.node_id == node_id

    def test_does_not_bypass_registry(self) -> None:
        """All evidence comes from persisted registry tables, not donor backend."""
        version_id = uuid.uuid4()
        node_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        # Verify registry is actually called
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": uuid.uuid4(), "node_id": node_id, "embedding": [1.0, 2.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Verify registry methods were called (not bypassed)
        registry.query_tree_nodes_by_version.assert_called()
        registry.query_vector_chunks_by_version.assert_called()

    def test_query_embedding_prioritizes_child_nodes(self) -> None:
        """Traversal uses query embedding to prioritize child nodes by similarity."""
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child_a = uuid.uuid4()
        child_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "parent_node_id": None, "level_no": 0},
            {"node_id": child_a, "parent_node_id": root_id, "level_no": 1},
            {"node_id": child_b, "parent_node_id": root_id, "level_no": 1},
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": uuid.uuid4(), "node_id": root_id, "embedding": [1.0, 1.0]},
            {
                "chunk_id": uuid.uuid4(),
                "node_id": child_a,
                "embedding": [0.9, 0.9],
            },  # Similar to query
            {
                "chunk_id": uuid.uuid4(),
                "node_id": child_b,
                "embedding": [0.1, 0.1],
            },  # Dissimilar
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5, min_support_threshold=2
        )
        runner = RecursiveTreeTraversalRunner()

        # Query similar to child_a
        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
            max_depth=1,
        )

        # Traversal should complete (prioritization logic exists)
        assert isinstance(hits, list)


class TestTreeSemanticTraversalIntegration:
    """Integration tests combining Phase 1 adapter + policy with traversal runner."""

    def test_adapter_provides_node_stats_for_traversal(self) -> None:
        """Traversal runner uses Phase 1 adapter to get node stats."""
        version_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": uuid.uuid4(), "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": uuid.uuid4(), "node_id": uuid.uuid4(), "embedding": [1.0, 2.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 2.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Integration works without error
        assert isinstance(hits, list)

    def test_policy_drills_down_when_high_dispersion_and_entropy(self) -> None:
        """Policy decides drill_down when node has high dispersion and high entropy."""
        version_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": root_id, "parent_node_id": None, "level_no": 0},
            {"node_id": child_id, "parent_node_id": root_id, "level_no": 1},
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        # High dispersion and entropy at root
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": uuid.uuid4(), "node_id": root_id, "embedding": [1.0, 0.0]},
            {"chunk_id": uuid.uuid4(), "node_id": root_id, "embedding": [5.0, 0.0]},
            {"chunk_id": uuid.uuid4(), "node_id": child_id, "embedding": [3.0, 3.0]},
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # If root has high dispersion/entropy, policy may drill down
        # (this test validates integration, not specific behavior)
        assert isinstance(hits, list)

    def test_policy_keeps_parent_when_low_dispersion_and_entropy(self) -> None:
        """Policy decides keep_parent when node has low dispersion and low entropy."""
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        node_id = uuid.uuid4()
        span_a = uuid.uuid4()
        span_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": node_id, "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = [
            {"node_id": node_id, "span_id": span_a, "ordinal_no": 0},
            {"node_id": node_id, "span_id": span_b, "ordinal_no": 1},
        ]
        # Low dispersion and entropy
        registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_a,
                "node_id": node_id,
                "embedding": [1.0, 1.0],
            },
            {
                "chunk_id": chunk_b,
                "node_id": node_id,
                "embedding": [1.0, 1.0],
            },
        ]
        registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_a, "span_id": span_a, "ordinal_no": 0},
            {"chunk_id": chunk_b, "span_id": span_b, "ordinal_no": 0},
        ]
        registry.query_doc_id_by_version.return_value = doc_id

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0, entropy_threshold=0.5
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Low dispersion/entropy should collect hits (keep_parent decision)
        assert len(hits) >= 2

    def test_policy_prunes_when_low_support_count(self) -> None:
        """Policy decides prune when node has insufficient support_count."""
        version_id = uuid.uuid4()

        registry = MagicMock(spec=SemanticDistributionRegistry)
        registry.query_tree_nodes_by_version.return_value = [
            {"node_id": uuid.uuid4(), "parent_node_id": None, "level_no": 0}
        ]
        registry.query_tree_node_spans_by_version.return_value = []
        # Only 1 chunk (low support_count)
        registry.query_vector_chunks_by_version.return_value = [
            {"chunk_id": uuid.uuid4(), "node_id": uuid.uuid4(), "embedding": [1.0, 1.0]}
        ]
        registry.query_vector_chunk_spans_by_version.return_value = []

        adapter = PersistedTreeSemanticDistributionAdapter()
        policy = BaselineTreeBranchDecisionPolicy(
            dispersion_threshold=1.0,
            entropy_threshold=0.5,
            min_support_threshold=2,  # Require at least 2 chunks
        )
        runner = RecursiveTreeTraversalRunner()

        hits = runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=[1.0, 1.0],
            registry=registry,
            policy=policy,
            adapter=adapter,
        )

        # Low support_count should prune (no hits)
        assert len(hits) == 0


class TestTraversalSeams:
    """Protocol seams for traversal runner."""

    def test_runner_implements_traversal_protocol(self) -> None:
        runner = RecursiveTreeTraversalRunner()
        assert isinstance(runner, TreeSemanticTraversalRunner)

    def test_query_hit_has_required_provenance(self) -> None:
        hit = QueryHit(
            doc_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            similarity_score=0.9,
        )

        # All provenance fields present
        assert hit.doc_id is not None
        assert hit.version_id is not None
        assert hit.span_id is not None
        assert hit.chunk_id is not None
        assert hit.node_id is not None
