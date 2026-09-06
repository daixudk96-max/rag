"""Evaluation baseline tests for retrieval stability.

These tests establish formal regression baselines around:
1. Generated fixture document (richer than minimal PDF)
2. Representative queries from validation patterns
3. QueryResult shape validation
4. Retrieval stability (consistent results for same inputs)
5. Hybrid mode shape, hit structure, stability, and path composition

This is the minimal eval slice - does NOT modify core retrieval logic.
"""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.entrypoints import QueryResult, query
from tests.llamaindex_runtime.fixtures.evaluation_fixtures import (
    build_evaluation_pdf,
    make_evaluation_registry,
    REPRESENTATIVE_QUERIES,
)


# ---------------------------------------------------------------------------
# Baseline fixture setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluation_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a richer PDF for evaluation baseline testing."""
    tmp_path = tmp_path_factory.mktemp("eval_fixtures")
    pdf_path = tmp_path / "evaluation_baseline.pdf"

    build_evaluation_pdf(
        pdf_path,
        heading="Evaluation Baseline Document",
        paragraphs=[
            "This is the first paragraph for evaluation baseline testing.",
            "Second paragraph contains searchable content for retrieval.",
            "Third paragraph has test query terms for baseline validation.",
            "Additional sample content ensures minimal document retrieval works.",
        ],
    )

    return pdf_path


@pytest.fixture(scope="module")
def hybrid_registry() -> MagicMock:
    """Create a mock registry for hybrid baseline testing.

    Provides keyword path support via make_evaluation_registry.
    """
    return make_evaluation_registry()


# ---------------------------------------------------------------------------
# Test 1: QueryResult shape stability (must always pass for valid query)
# ---------------------------------------------------------------------------


class TestQueryResultShapeBaseline:
    """QueryResult must maintain stable shape across invocations."""

    def test_vector_mode_returns_valid_shape(self, evaluation_pdf: Path) -> None:
        """Baseline: vector mode returns QueryResult with all required fields."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # Shape validation - these fields must always exist
        assert isinstance(result, QueryResult)
        assert result.mode == "vector"
        assert isinstance(result.hits, tuple)
        assert isinstance(result.source_path, str)
        assert isinstance(result.query, str)
        assert result.query == "test query"
        assert result.source_path == str(evaluation_pdf)

    def test_tree_mode_returns_valid_shape(self, evaluation_pdf: Path) -> None:
        """Baseline: tree mode returns QueryResult with all required fields."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )

        assert isinstance(result, QueryResult)
        assert result.mode == "tree"
        assert isinstance(result.hits, tuple)
        assert result.source_path == str(evaluation_pdf)
        assert result.query == "test query"


# ---------------------------------------------------------------------------
# Test 2: Hit structure stability (QueryHit must have text, score, metadata)
# ---------------------------------------------------------------------------


class TestQueryHitShapeBaseline:
    """Each QueryHit in result.hits must have stable structure."""

    def test_vector_hits_have_required_fields(self, evaluation_pdf: Path) -> None:
        """Baseline: vector hits contain text, score, and metadata."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # If hits exist, validate their structure
        if len(result.hits) > 0:
            hit = result.hits[0]
            assert hasattr(hit, "text")
            assert hasattr(hit, "score")
            assert hasattr(hit, "metadata")
            assert isinstance(hit.text, str)
            assert isinstance(hit.score, (float, type(None)))
            assert isinstance(hit.metadata, (dict, MappingProxyType))

    def test_tree_hits_have_required_fields(self, evaluation_pdf: Path) -> None:
        """Baseline: tree hits contain text, score, and metadata."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )

        if len(result.hits) > 0:
            hit = result.hits[0]
            assert hasattr(hit, "text")
            assert hasattr(hit, "score")
            assert hasattr(hit, "metadata")


# ---------------------------------------------------------------------------
# Test 3: Retrieval stability (same query must return same hit count)
# ---------------------------------------------------------------------------


class TestRetrievalStabilityBaseline:
    """Retrieval must be deterministic for same inputs."""

    def test_vector_retrieval_hit_count_stable(self, evaluation_pdf: Path) -> None:
        """Baseline: vector mode returns consistent hit count across invocations."""
        # First invocation
        result1 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # Second invocation with identical parameters
        result2 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # Baseline: hit count must be identical
        assert len(result1.hits) == len(result2.hits)

    def test_tree_retrieval_hit_count_stable(self, evaluation_pdf: Path) -> None:
        """Baseline: tree mode returns consistent hit count across invocations."""
        result1 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )

        result2 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )

        assert len(result1.hits) == len(result2.hits)


# ---------------------------------------------------------------------------
# Test 4: Representative query baseline (must return results for known queries)
# ---------------------------------------------------------------------------


class TestRepresentativeQueryBaseline:
    """System must return results for representative queries."""

    @pytest.mark.parametrize("query_text", REPRESENTATIVE_QUERIES)
    def test_vector_mode_returns_hits_for_representative_queries(
        self, evaluation_pdf: Path, query_text: str
    ) -> None:
        """Baseline: vector mode returns at least 1 hit for representative queries."""
        result = query(
            source_path=evaluation_pdf,
            query_text=query_text,
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # Baseline expectation: should return at least one hit
        # This establishes that the system can retrieve from the fixture document
        assert len(result.hits) >= 1

    @pytest.mark.parametrize("query_text", REPRESENTATIVE_QUERIES)
    def test_tree_mode_returns_hits_for_representative_queries(
        self, evaluation_pdf: Path, query_text: str
    ) -> None:
        """Baseline: tree mode returns at least 1 hit for representative queries."""
        result = query(
            source_path=evaluation_pdf,
            query_text=query_text,
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )

        # Baseline: tree retrieval should work on fixture document
        assert len(result.hits) >= 1


# ---------------------------------------------------------------------------
# Test 5: Score ordering baseline (hits should be ordered by score)
# ---------------------------------------------------------------------------


class TestScoreOrderingBaseline:
    """Hits should be ordered by score (descending)."""

    def test_vector_hits_ordered_by_score(self, evaluation_pdf: Path) -> None:
        """Baseline: vector hits returned in descending score order."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=5,
        )

        if len(result.hits) >= 2:
            # Baseline: scores should be non-increasing
            scores = [h.score for h in result.hits if h.score is not None]
            if len(scores) >= 2:
                assert scores[0] >= scores[1]

    def test_tree_hits_ordered_by_score(self, evaluation_pdf: Path) -> None:
        """Baseline: tree hits returned in descending score order."""
        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=5,
        )

        if len(result.hits) >= 2:
            scores = [h.score for h in result.hits if h.score is not None]
            if len(scores) >= 2:
                assert scores[0] >= scores[1]


# ---------------------------------------------------------------------------
# Test 6: Hybrid mode baseline (P6 regression coverage)
# ---------------------------------------------------------------------------


class TestHybridModeBaseline:
    """Hybrid retrieval baseline for P6 regression coverage.

    Hybrid mode composes keyword, vector, and tree paths (graph optional).
    These tests establish stability baselines without modifying core retrieval.
    Uses evaluation_fixtures.make_evaluation_registry for keyword path support.
    """

    def test_hybrid_mode_returns_valid_shape(self, evaluation_pdf: Path) -> None:
        """Baseline: hybrid mode returns QueryResult with all required fields."""
        registry = make_evaluation_registry()

        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Shape validation - hybrid must return same shape as vector/tree
        assert isinstance(result, QueryResult)
        assert result.mode == "hybrid"
        assert isinstance(result.hits, tuple)
        assert isinstance(result.source_path, str)
        assert isinstance(result.query, str)
        assert result.query == "test query"
        assert result.source_path == str(evaluation_pdf)

    def test_hybrid_hits_have_required_fields(self, evaluation_pdf: Path) -> None:
        """Baseline: hybrid hits contain text, score, metadata, and source_paths."""
        registry = make_evaluation_registry()

        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Hybrid must return hits (vector path alone should guarantee this)
        assert len(result.hits) > 0, "Hybrid mode must return at least vector hits"

        # All hits must have required fields plus hybrid-specific source_paths
        for hit in result.hits:
            assert hasattr(hit, "text")
            assert hasattr(hit, "score")
            assert hasattr(hit, "metadata")
            assert isinstance(hit.text, str)
            assert isinstance(hit.score, (float, type(None)))
            assert isinstance(hit.metadata, (dict, MappingProxyType))
            # Hybrid-specific contract: each hit must carry source_paths metadata
            assert "source_paths" in hit.metadata, (
                "Hybrid hits must carry source_paths metadata "
                "indicating which retrieval path(s) produced the hit"
            )

    def test_hybrid_retrieval_hit_count_stable(self, evaluation_pdf: Path) -> None:
        """Baseline: hybrid mode returns consistent hit count across invocations."""
        registry = make_evaluation_registry()

        # First invocation
        result1 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Second invocation with identical parameters
        result2 = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Baseline: hit count must be identical for deterministic hybrid retrieval
        assert len(result1.hits) == len(result2.hits)

    @pytest.mark.parametrize("query_text", REPRESENTATIVE_QUERIES)
    def test_hybrid_mode_returns_hits_for_representative_queries(
        self, evaluation_pdf: Path, query_text: str
    ) -> None:
        """Baseline: hybrid mode returns at least 1 hit for representative queries."""
        registry = make_evaluation_registry()

        result = query(
            source_path=evaluation_pdf,
            query_text=query_text,
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Hybrid composes vector and tree, so should return at least vector hits
        assert len(result.hits) >= 1

    def test_hybrid_mode_composes_multiple_paths(
        self, evaluation_pdf: Path
    ) -> None:
        """Baseline: hybrid mode must show evidence of multi-path composition.

        Hybrid hits must carry source_paths indicating at least two distinct
        retrieval paths (vector + tree, or keyword + vector, etc.) contributed
        results. This is the core contract that distinguishes hybrid from
        single-mode retrieval.
        """
        registry = make_evaluation_registry()

        result = query(
            source_path=evaluation_pdf,
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            similarity_top_k=3,
            registry=registry,
        )

        # Collect all distinct source_paths across all hits
        all_source_paths: set[str] = set()
        for hit in result.hits:
            sp = hit.metadata.get("source_paths", ())
            all_source_paths.update(sp)

        # Hybrid must compose at least 2 distinct paths (vector + tree minimum)
        assert len(all_source_paths) >= 2, (
            f"Hybrid mode must compose at least 2 retrieval paths, "
            f"but only found: {all_source_paths}"
        )