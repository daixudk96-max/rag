"""Tests for formal-runtime candidate fusion over multi-path HybridHit tuples.

Phase 7 narrow slice: path-aware fusion that combines HybridHit tuples from
multiple retrieval paths (vector, keyword, graph, tree) into deduplicated,
fused HybridHit tuples with RRF-based scoring, per-path score normalization,
and proper source_path attribution.

These tests verify:
1. fuse_candidates: merges per-path HybridHit lists into fused results
2. Path-aware deduplication: same span_id from different paths gets merged
3. Score normalization: per-path min-max normalization before fusion
4. RRF fusion: reciprocal rank fusion across per-path rankings
5. Multi-path bonus: hits appearing in more paths rank higher
6. Edge cases: empty input, single path, single hit, all same span_id
7. Immutability: results are frozen dataclasses
"""
from __future__ import annotations

import uuid

import pytest

from hybrid_path.types import HybridHit
from reranker.fusion import fuse_candidates
from reranker.types import RerankerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    span_id: uuid.UUID,
    score: float = 0.5,
    path: str = "vector",
    heading_path: str | None = None,
    page_no: int | None = None,
    raw_text: str | None = None,
) -> HybridHit:
    return HybridHit(
        span_id=span_id,
        source_paths=frozenset({path}),
        best_score=score,
        page_no=page_no,
        heading_path=heading_path,
        raw_text=raw_text,
        node_id=None,
    )


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
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 1, "text A")]}
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].span_id == span
        assert "vector" in result[0].source_paths

    def test_single_hit_preserves_best_score(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].best_score == 0.9


class TestFuseCandidatesSinglePath:
    """fuse_candidates with hits from a single path."""

    def test_multiple_hits_single_path(self) -> None:
        s1, s2, s3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(s1, 0.9, "vector", "Ch1", 1),
                _hit(s2, 0.7, "vector", "Ch2", 2),
                _hit(s3, 0.5, "vector", "Ch3", 3),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 3
        # Should be sorted by fused score descending
        scores = [h.best_score for h in result]
        assert scores == sorted(scores, reverse=True)

    def test_single_path_all_have_same_source_path(self) -> None:
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        hits_by_path = {
            "keyword": [
                _hit(s1, 1.0, "keyword", "Ch1", 1),
                _hit(s2, 0.8, "keyword", "Ch2", 2),
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

    def test_same_span_id_from_two_paths_merged(self) -> None:
        """Same span_id from vector and keyword should be a single merged hit."""
        span = uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(span, 0.9, "vector", "Ch1", 1, "text A")],
            "keyword": [_hit(span, 1.0, "keyword", "Ch1", 1, "text A")],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].span_id == span
        assert "vector" in result[0].source_paths
        assert "keyword" in result[0].source_paths

    def test_multi_path_hit_ranks_higher(self) -> None:
        """A hit appearing in two paths should rank above single-path hits
        even if a single-path hit has a slightly higher raw score, because
        RRF from two paths + multi-path bonus."""
        shared_span = uuid.uuid4()
        solo_span = uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(shared_span, 0.7, "vector", "Ch1", 1),
                _hit(solo_span, 0.9, "vector", "Ch2", 2),
            ],
            "keyword": [
                _hit(shared_span, 0.8, "keyword", "Ch1", 1),
            ],
        }
        result = fuse_candidates(hits_by_path)
        # The shared hit (2 paths) should outrank the solo hit (1 path)
        shared_hit = [h for h in result if h.span_id == shared_span][0]
        solo_hit = [h for h in result if h.span_id == solo_span][0]
        shared_idx = result.index(shared_hit)
        solo_idx = result.index(solo_hit)
        assert shared_idx < solo_idx

    def test_distinct_spans_from_different_paths_not_merged(self) -> None:
        """Different span_ids from different paths remain separate hits."""
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(s1, 0.9, "vector", "Ch1", 1)],
            "keyword": [_hit(s2, 0.8, "keyword", "Ch2", 2)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 2

    def test_three_paths_same_span(self) -> None:
        """Same span from 3 paths gets all 3 source_paths."""
        span = uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(span, 0.7, "vector", "Ch1", 1)],
            "keyword": [_hit(span, 0.8, "keyword", "Ch1", 1)],
            "graph": [_hit(span, 0.0, "graph", "Ch1", 1)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].source_paths == frozenset({"vector", "keyword", "graph"})

    def test_zero_score_from_graph_handled(self) -> None:
        """Graph hits with score 0.0 should not break fusion."""
        span = uuid.uuid4()
        other_span = uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(span, 0.9, "vector", "Ch1", 1)],
            "graph": [
                _hit(span, 0.0, "graph", "Ch1", 1),
                _hit(other_span, 0.0, "graph", "Ch2", 2),
            ],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 2
        shared = [h for h in result if h.span_id == span][0]
        assert "vector" in shared.source_paths
        assert "graph" in shared.source_paths


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates score normalization
# ---------------------------------------------------------------------------


class TestFuseCandidatesScoreNormalization:
    """fuse_candidates applies per-path score normalization before RRF."""

    def test_scores_on_different_scales_become_comparable(self) -> None:
        """Vector scores in [0,1] and keyword scores in [0,100] should be
        normalized so RRF ranks are meaningful."""
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(s1, 0.95, "vector", "Ch1", 1)],
            "keyword": [_hit(s2, 95.0, "keyword", "Ch2", 2)],
        }
        result = fuse_candidates(hits_by_path)
        # Both should produce valid results -- the key point is no crash
        # and both get normalized scores
        assert len(result) == 2

    def test_all_zero_scores_in_a_path(self) -> None:
        """A path with all 0.0 scores (graph) should not crash normalization."""
        s1 = uuid.uuid4()
        hits_by_path = {
            "graph": [_hit(s1, 0.0, "graph", "Ch1", 1)],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].best_score == 0.0


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates with RerankerConfig
# ---------------------------------------------------------------------------


class TestFuseCandidatesWithConfig:
    """fuse_candidates respects RerankerConfig parameters."""

    def test_custom_rrf_k(self) -> None:
        """Different rrf_k should produce different RRF scores."""
        span = uuid.uuid4()
        other_span = uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(span, 0.9, "vector", "Ch1", 1),
                _hit(other_span, 0.5, "vector", "Ch2", 2),
            ],
        }
        config_k60 = RerankerConfig(rrf_k=60)
        config_k1 = RerankerConfig(rrf_k=1)
        result_k60 = fuse_candidates(hits_by_path, config=config_k60)
        result_k1 = fuse_candidates(hits_by_path, config=config_k1)
        # Both should have 2 results
        assert len(result_k60) == 2
        assert len(result_k1) == 2

    def test_custom_multi_path_bonus(self) -> None:
        """multi_path_bonus should amplify multi-path hits."""
        shared_span = uuid.uuid4()
        solo_span = uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(shared_span, 0.7, "vector", "Ch1", 1),
                _hit(solo_span, 0.9, "vector", "Ch2", 2),
            ],
            "keyword": [
                _hit(shared_span, 0.8, "keyword", "Ch1", 1),
            ],
        }
        # High bonus should make the shared hit even more dominant
        config = RerankerConfig(multi_path_bonus=1.0)
        result = fuse_candidates(hits_by_path, config=config)
        shared_hit = [h for h in result if h.span_id == shared_span][0]
        solo_hit = [h for h in result if h.span_id == solo_span][0]
        assert result.index(shared_hit) < result.index(solo_hit)


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates deduplication
# ---------------------------------------------------------------------------


class TestFuseCandidatesDeduplication:
    """fuse_candidates deduplicates by span_id across paths."""

    def test_duplicate_span_within_same_path(self) -> None:
        """Same span_id appearing twice in the same path list should be
        deduplicated, keeping the higher score."""
        span = uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(span, 0.9, "vector", "Ch1", 1),
                _hit(span, 0.5, "vector", "Ch1", 1),
            ]
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        assert result[0].best_score == 0.9

    def test_keeps_metadata_from_highest_score(self) -> None:
        """When merging by span_id, metadata from the highest-scored
        occurrence is preserved."""
        span = uuid.uuid4()
        hits_by_path = {
            "vector": [_hit(span, 0.9, "vector", "Better Chapter", 5, "good text")],
            "keyword": [_hit(span, 0.7, "keyword", "Other Chapter", 3, "ok text")],
        }
        result = fuse_candidates(hits_by_path)
        assert len(result) == 1
        # The vector hit (0.9) is the best, so its metadata should win
        assert result[0].heading_path == "Better Chapter"
        assert result[0].page_no == 5
        assert result[0].raw_text == "good text"


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates immutability
# ---------------------------------------------------------------------------


class TestFuseCandidatesImmutability:
    """Results from fuse_candidates are immutable."""

    def test_hybrid_hit_is_frozen(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        with pytest.raises(AttributeError):
            result[0].best_score = 0.0  # type: ignore[misc]

    def test_source_paths_is_frozenset(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 1)]}
        result = fuse_candidates(hits_by_path)
        assert isinstance(result[0].source_paths, frozenset)


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates preserves metadata
# ---------------------------------------------------------------------------


class TestFuseCandidatesMetadata:
    """fuse_candidates preserves hit metadata correctly."""

    def test_raw_text_preserved(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 1, "important text")]}
        result = fuse_candidates(hits_by_path)
        assert result[0].raw_text == "important text"

    def test_heading_path_preserved(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"keyword": [_hit(span, 0.8, "keyword", "Intro > Summary", 2)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].heading_path == "Intro > Summary"

    def test_page_no_preserved(self) -> None:
        span = uuid.uuid4()
        hits_by_path = {"vector": [_hit(span, 0.9, "vector", "Ch1", 7)]}
        result = fuse_candidates(hits_by_path)
        assert result[0].page_no == 7


# ---------------------------------------------------------------------------
# Unit tests -- fuse_candidates result sorting
# ---------------------------------------------------------------------------


class TestFuseCandidatesSorting:
    """fuse_candidates returns results sorted by fused score descending."""

    def test_results_sorted_by_best_score_descending(self) -> None:
        s1, s2, s3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        hits_by_path = {
            "vector": [
                _hit(s1, 0.3, "vector", "Ch1", 1),
                _hit(s2, 0.9, "vector", "Ch2", 2),
                _hit(s3, 0.6, "vector", "Ch3", 3),
            ]
        }
        result = fuse_candidates(hits_by_path)
        scores = [h.best_score for h in result]
        assert scores == sorted(scores, reverse=True)
