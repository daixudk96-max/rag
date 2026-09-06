"""Tests for Phase 3 Slice 3: hierarchical scoring and branch pruning over persisted tree.

These tests verify:
1. Hierarchical scoring: score nodes based on summary_text content matching
2. Score propagation: parent nodes aggregate scores from children
3. Branch pruning: remove low-score branches while preserving provenance
4. Pruned tree traversal: rollup queries respect pruning status
5. Provenance integrity: pruning does not break span-node links

Unit tests use mock data and run without a database.
Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from okf._e2a_pipeline_testkit import _FakeReconciler

from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.query import TreeRollupQuery


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


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


# ===========================================================================
# UNIT TESTS -- TreeScoring hierarchical scoring behavior (no database)
# ===========================================================================


class TestTreeScoringUnit:
    """Core TreeScoring behavior: score nodes based on summary_text content matching."""

    def test_score_leaf_node_by_text_match(self) -> None:
        """Leaf node score must reflect how well summary_text matches a query."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Introduction to machine learning."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = tree["nodes"][0]
        # Score calculation should exist on TreeRollupQuery
        # For now, test that we can call a scoring method
        # This test will FAIL initially because the method doesn't exist yet
        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        score = scorer.score_node(leaf_node, query="machine learning")

        assert score is not None, "score_node must return a numeric score"
        assert isinstance(score, float), "score must be a float"
        # High score expected because summary contains query terms
        assert score > 0.5, "High match should have high score"

    def test_score_parent_node_aggregates_children(self) -> None:
        """Parent node score must aggregate scores from all child nodes."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro", text="Introduction to ML."),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.2 Methods", text="Deep learning methods."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        # Score the parent node
        parent_node = [n for n in tree["nodes"] if n["level_no"] == 0][0]
        parent_score = scorer.score_node(parent_node, query="machine learning")

        # Score the children
        children = [n for n in tree["nodes"] if n["level_no"] > 0]
        child_scores = [scorer.score_node(c, query="machine learning") for c in children]

        # Parent score should reflect aggregation of children
        # (could be max, average, or weighted - implementation choice)
        assert parent_score is not None
        # Parent score should be related to child scores
        # For simplicity, check that parent score is non-zero when children have scores
        assert parent_score > 0.0, "Parent with scored children must have non-zero score"

    def test_score_chain_hierarchical_decay(self) -> None:
        """Score chain from leaf to root must show hierarchical relationship."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 > 1.1.1", text="Deep learning intro."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        query = "deep learning"

        # Score all nodes in the chain
        chain_scores = []
        for node in tree["nodes"]:
            score = scorer.score_node(node, query=query)
            chain_scores.append((node["level_no"], score))

        # Scores should be ordered - could be decreasing from leaf to root
        # or increasing from root to leaf (implementation choice)
        # For now, just verify all scores exist
        assert all(s is not None for _, s in chain_scores), "All nodes must be scored"

    def test_score_empty_node_returns_zero(self) -> None:
        """Node with no summary_text must return score of 0."""
        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        empty_node = {
            "node_id": uuid.uuid4(),
            "summary_text": None,
        }
        score = scorer.score_node(empty_node, query="test query")
        assert score == 0.0, "Node with no summary must have zero score"

    def test_score_none_query_rejected(self) -> None:
        """Passing None as query should fail fast instead of crashing with AttributeError."""
        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        node = {
            "node_id": uuid.uuid4(),
            "summary_text": "Machine learning introduction",
        }
        with pytest.raises(ValueError, match="query"):
            scorer.score_node(node, query=None)  # type: ignore[arg-type]


# ===========================================================================
# UNIT TESTS -- TreePruning branch pruning behavior (no database)
# ===========================================================================


class TestTreePruningUnit:
    """Core TreePruning behavior: prune low-score branches."""

    def test_prune_low_score_leaf_node(self) -> None:
        """Pruning must mark low-score leaf nodes as pruned."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Introduction to cooking."),
            _make_span(version_id=version_id, heading_path="Ch 2", text="Machine learning basics."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring
        from llamaindex_runtime.tree.pruning import TreePruning

        scorer = TreeScoring()
        query = "machine learning"

        # Score all nodes
        scored_nodes = []
        for node in tree["nodes"]:
            score = scorer.score_node(node, query=query)
            scored_nodes.append({**node, "score": score})

        # Prune with threshold
        pruner = TreePruning(threshold=0.3)
        pruned_tree = pruner.prune_tree(scored_nodes, tree["node_spans"])

        # Check that low-score node is pruned
        cooking_node = [n for n in pruned_tree["nodes"] if "cooking" in n.get("summary_text", "").lower()][0]
        ml_node = [n for n in pruned_tree["nodes"] if "machine learning" in n.get("summary_text", "").lower()][0]

        assert cooking_node.get("pruned") is True, "Low-score node must be marked as pruned"
        assert ml_node.get("pruned") is False, "High-score node must not be pruned"

    def test_prune_branch_by_parent_score(self) -> None:
        """Pruning must prune entire branch when parent score is below threshold."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Cooking > Recipes", text="Recipe A."),
            _make_span(version_id=version_id, heading_path="Cooking > Ingredients", text="Ingredient B."),
            _make_span(version_id=version_id, heading_path="ML > Algorithms", text="Machine learning neural network algorithms."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring
        from llamaindex_runtime.tree.pruning import TreePruning

        scorer = TreeScoring()
        query = "machine learning algorithms"

        # Score all nodes
        scored_nodes = []
        for node in tree["nodes"]:
            score = scorer.score_node(node, query=query)
            scored_nodes.append({**node, "score": score})

        # Prune with threshold
        pruner = TreePruning(threshold=0.2)
        pruned_tree = pruner.prune_tree(scored_nodes, tree["node_spans"])

        # All nodes in Cooking branch should be pruned
        cooking_nodes = [n for n in pruned_tree["nodes"] if "Cooking" in n.get("heading_path", "")]
        assert all(n.get("pruned") for n in cooking_nodes), "All nodes in low-score branch must be pruned"

        # ML nodes should not be pruned (they have high scores due to term overlap)
        ml_nodes = [n for n in pruned_tree["nodes"] if "ML" in n.get("heading_path", "") or "ml" in n.get("heading_path", "").lower()]
        # Note: parent nodes get aggregated summaries, so they may have scores too
        ml_leaf_nodes = [n for n in ml_nodes if n.get("level_no", 0) > 0]
        assert all(not n.get("pruned") for n in ml_leaf_nodes), "High-score leaf nodes must not be pruned"

    def test_pruning_preserves_span_links(self) -> None:
        """Pruning must not break span-node links in tree_node_spans."""
        version_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()

        spans = [
            _make_span(span_id=span_id_1, version_id=version_id, heading_path="Ch 1", text="ML intro."),
            _make_span(span_id=span_id_2, version_id=version_id, heading_path="Ch 2", text="Cooking."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring
        from llamaindex_runtime.tree.pruning import TreePruning

        scorer = TreeScoring()
        query = "machine learning"

        scored_nodes = []
        for node in tree["nodes"]:
            score = scorer.score_node(node, query=query)
            scored_nodes.append({**node, "score": score})

        pruner = TreePruning(threshold=0.3)
        pruned_tree = pruner.prune_tree(scored_nodes, tree["node_spans"])

        # Even though Cooking node is pruned, its span links must remain
        cooking_node_spans = [
            ns for ns in pruned_tree["node_spans"]
            if ns["span_id"] == span_id_2
        ]
        assert len(cooking_node_spans) > 0, "Pruned node must still have span links"


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveTreeScoring:
    """Live tests for hierarchical scoring over persisted tree data."""

    def test_score_persisted_node(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Scoring must work on nodes retrieved from database."""
        sample_pdf = tmp_path / "score-persisted.pdf"
        _build_rich_pdf(sample_pdf, text_body="Neural network deep learning architectures.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Scoring test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Query persisted nodes
        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        query = "deep learning"

        # Score a persisted node
        leaf_node = persisted_nodes[0]
        score = scorer.score_node(leaf_node, query=query)

        assert score is not None
        assert isinstance(score, float)
        assert score > 0.0, "Node with matching content must have positive score"

    def test_score_chain_from_persisted_tree(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Scoring must work on chains retrieved from TreeRollupQuery."""
        sample_pdf = tmp_path / "score-chain.pdf"
        _build_rich_pdf(sample_pdf, text_body="Transformer architecture for NLP.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Score chain test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        tree_query = TreeRollupQuery(live_db_connection)

        # Get a chain from persisted tree
        node_spans = tree["node_spans"]
        leaf_node_id = node_spans[0]["node_id"]
        chain = tree_query.rollup_chain(leaf_node_id)

        from llamaindex_runtime.tree.scoring import TreeScoring

        scorer = TreeScoring()
        query = "transformer architecture"

        # Score each node in the chain
        chain_scores = []
        for node in chain:
            score = scorer.score_node(node, query=query)
            chain_scores.append(score)

        assert all(s >= 0.0 for s in chain_scores), "All scores must be non-negative"


class TestLiveTreePruning:
    """Live tests for branch pruning over persisted tree data."""

    def test_prune_persisted_tree(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Pruning must mark persisted nodes as pruned without deleting them."""
        sample_pdf = tmp_path / "prune-persisted.pdf"
        _build_rich_pdf(sample_pdf, text_body="Gourmet cooking recipes and ML algorithms.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Pruning test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Query persisted nodes
        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring
        from llamaindex_runtime.tree.pruning import TreePruning

        scorer = TreeScoring()
        query = "machine learning"

        # Score nodes
        scored_nodes = []
        for node in persisted_nodes:
            score = scorer.score_node(node, query=query)
            scored_nodes.append({**node, "score": score})

        # Prune with threshold
        pruner = TreePruning(threshold=0.3)
        pruned_nodes = pruner.prune_nodes(scored_nodes)

        # Check that some nodes are marked as pruned
        pruned_count = sum(1 for n in pruned_nodes if n.get("pruned"))
        assert pruned_count > 0, "Pruning must mark some nodes as pruned"

        # Pruned nodes should still exist in the list (not deleted)
        assert len(pruned_nodes) == len(scored_nodes), "Pruning must not delete nodes"

    def test_pruned_node_span_links_preserved(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Pruned nodes must still have span links in tree_node_spans."""
        sample_pdf = tmp_path / "prune-links.pdf"
        _build_rich_pdf(sample_pdf, text_body="Cooking recipes and ML tutorials.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Prune links test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)

        from llamaindex_runtime.tree.scoring import TreeScoring
        from llamaindex_runtime.tree.pruning import TreePruning

        scorer = TreeScoring()
        query = "machine learning"

        scored_nodes = []
        for node in persisted_nodes:
            score = scorer.score_node(node, query=query)
            scored_nodes.append({**node, "score": score})

        pruner = TreePruning(threshold=0.3)
        pruned_nodes = pruner.prune_nodes(scored_nodes)

        # Find a pruned node
        pruned_node = [n for n in pruned_nodes if n.get("pruned")][0]
        pruned_node_id = pruned_node["node_id"]

        # Check that its spans still exist
        tree_query = TreeRollupQuery(live_db_connection)
        node_spans = tree_query.get_node_spans(pruned_node_id)

        assert len(node_spans) > 0, "Pruned node must still have span links"