"""Tests for deep hybrid retrieval path (Phase 6).

Scope: minimal deep hybrid composition of keyword, vector, and tree primitives.
No reranker, no advanced hit-distribution analysis - just aggregation.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query
from llamaindex_runtime.entrypoints._query import _deduplicate_hits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTextNode:
    def __init__(self, text: str, metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata if metadata is not None else {}


class _FakeNodeWithScore:
    def __init__(self, text: str, score: float, metadata: dict | None = None) -> None:
        self.node = _FakeTextNode(text, metadata)
        self.score = score


def _make_node(
    text: str, score: float, metadata: dict | None = None
) -> _FakeNodeWithScore:
    return _FakeNodeWithScore(text, score, metadata)


def _make_keyword_hit(text: str, score: float = 0.9) -> QueryHit:
    return QueryHit(
        text=text,
        score=score,
        metadata={
            "span_id": uuid.uuid4(),
            "doc_id": uuid.uuid4(),
            "version_id": uuid.uuid4(),
            "page_no": 1,
            "heading_path": "Section 1",
        },
    )


def _make_registry() -> MagicMock:
    reg = MagicMock()
    reg.query_spans_by_keyword.return_value = []
    return reg


# Unit tests -- hybrid mode basic mechanics
# ---------------------------------------------------------------------------


class TestQueryHybridMode:
    """query() with mode='hybrid' composes multiple retrieval paths."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_calls_keyword_and_vector(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Hybrid mode should invoke keyword, vector, and tree retrievers."""
        keyword_hit = _make_keyword_hit("PM2.5 indicator", 1.0)
        vector_node = _make_node("PM2.5 monitoring", 0.85)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = [vector_node]
        mock_tree.return_value = []

        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="PM2.5",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )

        mock_kw.assert_called_once()
        mock_vec.assert_called_once()
        mock_tree.assert_called_once()
        assert result.mode == "hybrid"
        # Should aggregate both keyword and vector hits
        assert len(result.hits) >= 2

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_hybrid_mode_calls_all_four_paths(
        self, mock_tree, mock_vec, mock_kw
    ) -> None:
        """Hybrid mode should compose keyword, vector, and tree paths."""
        keyword_hit = _make_keyword_hit("air quality", 1.0)
        vector_node = _make_node("monitoring data", 0.82)
        tree_node = _make_node("environmental standards", 0.78)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = [vector_node]
        mock_tree.return_value = [tree_node]

        registry = _make_registry()

        result = query(
            source_path="/tmp/test.pdf",
            query_text="air quality monitoring",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )

        mock_kw.assert_called_once()
        mock_vec.assert_called_once()
        mock_tree.assert_called_once()
        assert result.mode == "hybrid"
        # Should aggregate hits from all paths
        assert len(result.hits) >= 3

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_deduplicates_hits_by_text(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Hybrid mode should deduplicate hits with identical text content."""
        # Same text from different paths
        keyword_hit = _make_keyword_hit("PM2.5 standard", 1.0)
        vector_node = _make_node("PM2.5 standard", 0.85)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = [vector_node]
        mock_tree.return_value = []

        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="PM2.5",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )

        # Should deduplicate, keeping best score
        assert len(result.hits) == 1
        assert result.hits[0].text == "PM2.5 standard"
        # Should keep the higher score (keyword 1.0 > vector 0.85)
        assert result.hits[0].score == 1.0

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_keeps_best_score_for_duplicate_text(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """When deduplicating, hybrid mode should preserve the highest score."""
        keyword_hit = _make_keyword_hit("air quality", 0.7)
        vector_node = _make_node("air quality", 0.95)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = [vector_node]
        mock_tree.return_value = []

        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="air quality",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )

        assert len(result.hits) == 1
        # Vector score 0.95 > keyword score 0.7
        assert result.hits[0].score == 0.95

    def test_hybrid_mode_without_registry_raises(self) -> None:
        """Hybrid mode requires registry for keyword path."""
        with pytest.raises(ValueError, match="registry"):
            query(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="hybrid",
                embed_model=MockEmbedding(embed_dim=32),
            )

    def test_hybrid_mode_without_embed_model_raises(self) -> None:
        """Hybrid mode requires embed_model for vector/tree paths."""
        registry = _make_registry()
        with pytest.raises(ValueError, match="embed_model"):
            query(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="hybrid",
                registry=registry,
            )

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_result_is_frozen(self, mock_vec, mock_kw, mock_tree) -> None:
        """QueryResult from hybrid mode must be immutable."""
        mock_kw.return_value = [_make_keyword_hit("text", 0.5)]
        mock_vec.return_value = []
        mock_tree.return_value = []
        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="test",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )
        with pytest.raises(AttributeError):
            result.mode = "vector"  # type: ignore[misc]

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_empty_hits_returns_empty_tuple(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Hybrid mode should handle empty results gracefully."""
        mock_kw.return_value = []
        mock_vec.return_value = []
        mock_tree.return_value = []
        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="nonexistent",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )
        assert result.hits == ()
        assert isinstance(result.hits, tuple)


# Unit tests -- QueryResult.mode type extended
# ---------------------------------------------------------------------------


class TestQueryResultModeTypeExtended:
    """QueryResult.mode now includes 'hybrid'."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_is_valid_result_mode(self, mock_vec, mock_kw, mock_tree) -> None:
        """'hybrid' should be a valid mode in QueryResult."""
        mock_kw.return_value = [_make_keyword_hit("text", 0.5)]
        mock_vec.return_value = []
        mock_tree.return_value = []
        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="test",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )
        assert result.mode == "hybrid"

    def test_hybrid_result_can_be_constructed_directly(self) -> None:
        """QueryResult should accept 'hybrid' as mode."""
        result = QueryResult(
            mode="hybrid",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test",
        )
        assert result.mode == "hybrid"


# ---------------------------------------------------------------------------
# Unit tests -- _deduplicate_hits edge cases
# ---------------------------------------------------------------------------


class TestDeduplicateHits:
    """_deduplicate_hits handles edge cases correctly."""

    def test_empty_input_returns_empty(self) -> None:
        """Empty hit list returns empty."""
        assert _deduplicate_hits([]) == []

    def test_single_hit_returns_unchanged(self) -> None:
        """Single hit passes through unchanged."""
        hit = QueryHit(text="unique", score=0.9, metadata={})
        result = _deduplicate_hits([hit])
        assert len(result) == 1
        assert result[0] is hit

    def test_all_distinct_texts_preserved(self) -> None:
        """Distinct texts are all preserved."""
        hits = [
            QueryHit(text="alpha", score=0.8, metadata={}),
            QueryHit(text="beta", score=0.7, metadata={}),
            QueryHit(text="gamma", score=0.6, metadata={}),
        ]
        result = _deduplicate_hits(hits)
        assert len(result) == 3

    def test_duplicate_text_keeps_highest_score(self) -> None:
        """When text duplicates, the hit with the highest score survives."""
        hits = [
            QueryHit(text="same text", score=0.5, metadata={}),
            QueryHit(text="same text", score=0.9, metadata={}),
            QueryHit(text="same text", score=0.3, metadata={}),
        ]
        result = _deduplicate_hits(hits)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_none_score_loses_to_real_score(self) -> None:
        """A None score should lose to any real score for deduplication."""
        hits = [
            QueryHit(text="entity", score=None, metadata={}),
            QueryHit(text="entity", score=0.75, metadata={}),
        ]
        result = _deduplicate_hits(hits)
        assert len(result) == 1
        assert result[0].score == 0.75

    def test_both_none_scores_keeps_first(self) -> None:
        """When both hits have None score for same text, keep the first."""
        hit_a = QueryHit(text="entity", score=None, metadata={"source": "a"})
        hit_b = QueryHit(text="entity", score=None, metadata={"source": "b"})
        result = _deduplicate_hits([hit_a, hit_b])
        assert len(result) == 1
        assert result[0] is hit_a

    def test_real_score_beats_none_score(self) -> None:
        """A hit with a real score should win over None score for same text."""
        hits = [
            QueryHit(text="entity", score=0.6, metadata={}),
            QueryHit(text="entity", score=None, metadata={}),
        ]
        result = _deduplicate_hits(hits)
        assert len(result) == 1
        assert result[0].score == 0.6

    def test_mixed_duplicates_and_distinct(self) -> None:
        """Mix of duplicates and distinct hits deduplicates correctly."""
        hits = [
            QueryHit(text="alpha", score=0.8, metadata={}),
            QueryHit(text="beta", score=0.5, metadata={}),
            QueryHit(text="alpha", score=0.95, metadata={}),
            QueryHit(text="gamma", score=0.7, metadata={}),
            QueryHit(text="beta", score=0.6, metadata={}),
        ]
        result = _deduplicate_hits(hits)
        assert len(result) == 3
        by_text = {h.text: h for h in result}
        assert by_text["alpha"].score == 0.95
        assert by_text["beta"].score == 0.6
        assert by_text["gamma"].score == 0.7
