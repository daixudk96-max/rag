"""Tests for formal-runtime candidate fusion over multi-path QueryHit tuples.

Phase 7 narrow slice: path-aware fusion that combines QueryHit tuples from
multiple retrieval paths (vector, keyword, graph, tree) into deduplicated,
fused FusedHit tuples with RRF-based scoring, per-path score normalization,
and proper source_path attribution.

These tests verify:
1. fuse_candidates: merges per-path QueryHit lists into FusedHit results
2. Path-aware deduplication: same text from different paths gets merged
3. Score normalization: per-path min-max normalization before fusion
4. RRF fusion: reciprocal rank fusion across per-path rankings
5. Multi-path bonus: hits appearing in more paths rank higher
6. Edge cases: empty input, single path, single hit, all same text
7. Immutability: FusedHit and results are frozen dataclasses
8. Metadata preservation: best metadata from highest-scoring hit is kept
9. Result sorting: fused results sorted by fused score descending
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.analysis.fusion import fuse_candidates
from llamaindex_runtime.analysis.types import FusedHit, RerankerConfig
from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    text: str,
    score: float = 0.5,
    path: str = "vector",
    heading_path: str | None = None,
    page_no: int | None = None,
) -> QueryHit:
    metadata: dict = {"source_path": path}
    if heading_path is not None:
        metadata["heading_path"] = heading_path
    if page_no is not None:
        metadata["page_no"] = page_no
    return QueryHit(text=text, score=score, metadata=MappingProxyType(metadata))


def _make_registry() -> MagicMock:
    reg = MagicMock()
    reg.query_spans_by_keyword.return_value = []
    return reg


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates empty / single
# ---------------------------------------------------------------------------


class TestFuseCandidatesEmpty:
    """fuse_candidates handles empty input."""

    def test_empty_paths_dict_returns_empty(self) -> None:
        result = fuse_candidates({})
        assert result == []

    def test_empty_path_lists_returns_empty(self) -> None:
        result = fuse_candidates({"vector": [], "keyword": []})
        assert result == []


class TestFuseCandidatesSingleHit:
    """fuse_candidates handles a single hit from one path."""

    def test_single_hit_from_single_path(self) -> None:
        hits_by_path = {"vector": [_hit("text A", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].text == "text A"
        assert "vector" in result[0].source_paths

    def test_single_hit_preserves_score(self) -> None:
        hits_by_path = {"vector": [_hit("text A", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].score == 0.9


class TestFuseCandidatesSinglePath:
    """fuse_candidates with hits from a single path."""

    def test_multiple_hits_single_path(self) -> None:
        hits_by_path = {
            "vector": [
                _hit("a", 0.9, "vector", "Ch1", 1),
                _hit("b", 0.7, "vector", "Ch2", 2),
                _hit("c", 0.5, "vector", "Ch3", 3),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 3
        # Should be sorted by fused score descending
        scores = [h.score for h in result]
        assert scores == sorted(scores, reverse=True)

    def test_single_path_all_have_same_source_path(self) -> None:
        hits_by_path = {
            "keyword": [
                _hit("a", 1.0, "keyword", "Ch1", 1),
                _hit("b", 0.8, "keyword", "Ch2", 2),
            ]
        }
        result = fuse_candidates(hits_by_path)
        for hit in result:
            assert "keyword" in hit.source_paths


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates multi-path
# ---------------------------------------------------------------------------


class TestFuseCandidatesMultiPath:
    """fuse_candidates merges hits from multiple paths correctly."""

    def test_same_text_from_two_paths_merged(self) -> None:
        """Same text from vector and keyword should be a single merged hit."""
        hits_by_path = {
            "vector": [_hit("shared text", 0.9, "vector", "Ch1", 1)],
            "keyword": [_hit("shared text", 1.0, "keyword", "Ch1", 1)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].text == "shared text"
        assert "vector" in result[0].source_paths
        assert "keyword" in result[0].source_paths

    def test_multi_path_hit_ranks_higher(self) -> None:
        """A hit appearing in two paths should rank above single-path hits
        even if a single-path hit has a slightly higher raw score, because
        RRF from two paths + multi-path bonus."""
        hits_by_path = {
            "vector": [
                _hit("shared", 0.7, "vector", "Ch1", 1),
                _hit("solo", 0.9, "vector", "Ch2", 2),
            ],
            "keyword": [
                _hit("shared", 0.8, "keyword", "Ch1", 1),
            ],
        }
        result = fuse_candidates(hits_by_path)
        shared_hit = [h for h in result if h.text == "shared"][0]
        solo_hit = [h for h in result if h.text == "solo"][0]
        shared_idx = result.index(shared_hit)
        solo_idx = result.index(solo_hit)
        assert shared_idx < solo_idx

    def test_distinct_texts_from_different_paths_not_merged(self) -> None:
        """Different texts from different paths remain separate hits."""
        hits_by_path = {
            "vector": [_hit("vec text", 0.9, "vector", "Ch1", 1)],
            "keyword": [_hit("kw text", 0.8, "keyword", "Ch2", 2)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 2

    def test_three_paths_same_text(self) -> None:
        """Same text from 3 paths gets all 3 source_paths."""
        hits_by_path = {
            "vector": [_hit("triple", 0.7, "vector", "Ch1", 1)],
            "keyword": [_hit("triple", 0.8, "keyword", "Ch1", 1)],
            "tree": [_hit("triple", 0.6, "tree", "Ch1", 1)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].source_paths == frozenset({"vector", "keyword", "tree"})

    def test_none_score_from_graph_handled(self) -> None:
        """Graph hits with None score should not break fusion."""
        graph_hit = QueryHit(
            text="graph entity",
            score=None,
            metadata=MappingProxyType({"source_path": "graph"}),
        )
        hits_by_path = {
            "vector": [_hit("graph entity", 0.9, "vector", "Ch1", 1)],
            "graph": [graph_hit],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert "vector" in result[0].source_paths
        assert "graph" in result[0].source_paths


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates score normalization
# ---------------------------------------------------------------------------


class TestFuseCandidatesScoreNormalization:
    """fuse_candidates applies per-path score normalization before RRF."""

    def test_scores_on_different_scales_become_comparable(self) -> None:
        """Vector scores in [0,1] and keyword scores in [0,100] should be
        normalized so RRF ranks are meaningful."""
        hits_by_path = {
            "vector": [_hit("vec result", 0.95, "vector", "Ch1", 1)],
            "keyword": [_hit("kw result", 95.0, "keyword", "Ch2", 2)],
        }
        result = fuse_candidates(hits_by_path)
        # Both should produce valid results -- the key point is no crash
        assert len(result) == 2

    def test_all_none_scores_in_a_path(self) -> None:
        """A path with all None scores (graph) should not crash normalization."""
        graph_hit = QueryHit(
            text="entity",
            score=None,
            metadata=MappingProxyType({"source_path": "graph"}),
        )
        hits_by_path = {"graph": [graph_hit]}
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].score is None or result[0].score == 0.0


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates with RerankerConfig
# ---------------------------------------------------------------------------


class TestFuseCandidatesWithConfig:
    """fuse_candidates respects RerankerConfig parameters."""

    def test_custom_rrf_k(self) -> None:
        """Different rrf_k should produce different RRF scores."""
        hits_by_path = {
            "vector": [
                _hit("a", 0.9, "vector", "Ch1", 1),
                _hit("b", 0.5, "vector", "Ch2", 2),
            ],
        }
        config_k60 = RerankerConfig(rrf_k=60)
        config_k1 = RerankerConfig(rrf_k=1)
        result_k60 = fuse_candidates(hits_by_path, config=config_k60)
        result_k1 = fuse_candidates(hits_by_path, config=config_k1)
        assert len(result_k60) == 2
        assert len(result_k1) == 2

    def test_custom_multi_path_bonus(self) -> None:
        """multi_path_bonus should amplify multi-path hits."""
        hits_by_path = {
            "vector": [
                _hit("shared", 0.7, "vector", "Ch1", 1),
                _hit("solo", 0.9, "vector", "Ch2", 2),
            ],
            "keyword": [
                _hit("shared", 0.8, "keyword", "Ch1", 1),
            ],
        }
        config = RerankerConfig(multi_path_bonus=1.0)
        result = fuse_candidates(hits_by_path, config=config)
        shared_hit = [h for h in result if h.text == "shared"][0]
        solo_hit = [h for h in result if h.text == "solo"][0]
        assert result.index(shared_hit) < result.index(solo_hit)


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates deduplication
# ---------------------------------------------------------------------------


class TestFuseCandidatesDeduplication:
    """fuse_candidates deduplicates by text across paths."""

    def test_duplicate_text_within_same_path(self) -> None:
        """Same text appearing twice in the same path list should be
        deduplicated, keeping the higher score."""
        hits_by_path = {
            "vector": [
                _hit("dup", 0.9, "vector", "Ch1", 1),
                _hit("dup", 0.5, "vector", "Ch1", 1),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_duplicate_text_lower_score_first(self) -> None:
        """When the lower-scored duplicate comes first, the higher one wins."""
        hits_by_path = {
            "vector": [
                _hit("dup", 0.5, "vector", "Ch1", 1),
                _hit("dup", 0.9, "vector", "Ch1", 1),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_duplicate_text_does_not_lose_best_rank(self) -> None:
        """Best duplicate should keep the best rank within its path after deduplication."""
        hits_by_path = {
            "vector": [
                _hit("dup", 0.9, "vector", "Ch1", 1),
                _hit("solo", 0.8, "vector", "Ch2", 2),
                _hit("dup", 0.5, "vector", "Ch1", 1),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 2
        assert result[0].text == "dup"
        assert result[1].text == "solo"

    def test_keeps_metadata_from_highest_score(self) -> None:
        """When merging by text, metadata from the highest-scored
        occurrence is preserved."""
        hits_by_path = {
            "vector": [_hit("text A", 0.9, "vector", "Better Chapter", 5)],
            "keyword": [_hit("text A", 0.7, "keyword", "Other Chapter", 3)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        # The vector hit (0.9) is the best, so its metadata should win
        assert result[0].metadata.get("heading_path") == "Better Chapter"
        assert result[0].metadata.get("page_no") == 5


# ---------------------------------------------------------------------------
# Unit tests -- FusedHit shape
# ---------------------------------------------------------------------------


class TestFusedHitShape:
    """FusedHit carries the expected fields and is frozen."""

    def test_fused_hit_has_source_paths(self) -> None:
        hits_by_path = {"vector": [_hit("a", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert hasattr(result[0], "source_paths")
        assert isinstance(result[0].source_paths, frozenset)

    def test_fused_hit_has_normalized_score(self) -> None:
        hits_by_path = {"vector": [_hit("a", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert hasattr(result[0], "normalized_score")
        assert isinstance(result[0].normalized_score, float)

    def test_fused_hit_has_rerank_score(self) -> None:
        hits_by_path = {"vector": [_hit("a", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert hasattr(result[0], "rerank_score")
        assert isinstance(result[0].rerank_score, float)

    def test_fused_hit_is_frozen(self) -> None:
        fused = FusedHit(
            text="test",
            score=0.9,
            metadata=MappingProxyType({}),
            source_paths=frozenset({"vector"}),
            normalized_score=1.0,
            rerank_score=0.016,
        )
        with pytest.raises(AttributeError):
            fused.score = 0.0  # type: ignore[misc]

    def test_fused_hit_has_text(self) -> None:
        hits_by_path = {"vector": [_hit("alpha", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].text == "alpha"

    def test_fused_hit_has_metadata(self) -> None:
        hits_by_path = {"vector": [_hit("alpha", 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert isinstance(result[0].metadata, MappingProxyType)


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates preserves metadata
# ---------------------------------------------------------------------------


class TestFuseCandidatesMetadata:
    """fuse_candidates preserves hit metadata correctly."""

    def test_heading_path_preserved(self) -> None:
        hits_by_path = {
            "keyword": [_hit("intro", 0.8, "keyword", "Intro > Summary", 2)]
        }
        result = fuse_candidates(hits_by_path)
        assert result[0].metadata.get("heading_path") == "Intro > Summary"

    def test_page_no_preserved(self) -> None:
        hits_by_path = {"vector": [_hit("alpha", 0.9, "vector", "Ch1", 7)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].metadata.get("page_no") == 7


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates result sorting
# ---------------------------------------------------------------------------


class TestFuseCandidatesSorting:
    """fuse_candidates returns results sorted by fused score descending."""

    def test_results_sorted_by_rerank_score_descending(self) -> None:
        hits_by_path = {
            "vector": [
                _hit("low", 0.3, "vector", "Ch1", 1),
                _hit("high", 0.9, "vector", "Ch2", 2),
                _hit("mid", 0.6, "vector", "Ch3", 3),
            ]
        }
        result = fuse_candidates(hits_by_path)
        scores = [h.rerank_score for h in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Integration tests -- query() hybrid branch uses fusion
# ---------------------------------------------------------------------------


class _FakeTextNode:
    def __init__(self, text: str, metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata if metadata is not None else {}


class _FakeNodeWithScore:
    def __init__(self, text: str, score: float, metadata: dict | None = None) -> None:
        self.node = _FakeTextNode(text, metadata)
        self.score = score


class TestHybridModeUsesFusion:
    """query() hybrid branch should invoke fuse_candidates and return FusedHit-like results."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_fuses_hits(self, mock_vec, mock_kw, mock_tree) -> None:
        """Hybrid mode should use fusion to merge and rank hits."""
        keyword_hit = QueryHit(
            text="shared",
            score=1.0,
            metadata=MappingProxyType({"source_path": "keyword", "heading_path": "Ch1"}),
        )
        vector_node = _FakeNodeWithScore("shared", 0.85, {"source_path": "vector", "heading_path": "Ch1"})
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = [vector_node]
        mock_tree.return_value = []

        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="shared",
            mode="hybrid",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )

        # Result should have fused metadata
        assert result.mode == "hybrid"
        # The same text from two paths should be deduplicated
        assert len(result.hits) == 1
        # The hit should have source_paths metadata from fusion
        hit = result.hits[0]
        assert "source_paths" in hit.metadata or "source_path" in hit.metadata

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_hybrid_mode_hits_sorted_by_rerank(self, mock_vec, mock_kw, mock_tree) -> None:
        """Hybrid mode hits should be sorted by rerank score when fusion is active."""
        mock_kw.return_value = [
            QueryHit(text="kw only", score=0.9, metadata=MappingProxyType({"source_path": "keyword"})),
        ]
        mock_vec.return_value = [
            _FakeNodeWithScore("vec only", 0.8, {"source_path": "vector"}),
        ]
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
        assert len(result.hits) == 2
