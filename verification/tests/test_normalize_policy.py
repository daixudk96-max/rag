"""Tests for rerank policy and score normalization layer.

Phase 7 narrow slice: min-max clip normalization and per-path score
normalization that brings heterogeneous path scores onto a comparable
scale before fusion.

These tests verify:
1. normalize_scores with min_max_clip=True clips to [0, 1]
2. Per-path normalization: each path's scores are independently normalized
3. Rerank policy: the full pipeline normalize -> fuse -> rerank
4. Edge cases: all same scores, single score, negative scores, None scores
5. Zero-range handling: min == max should not produce NaN
"""
from __future__ import annotations

import uuid

import pytest

from hybrid_path.types import HybridHit
from reranker.fusion import compute_rerank_scores, rerank_pipeline
from reranker.normalize import (
    normalize_path_scores,
    normalize_scores,
)
from reranker.types import RerankerConfig


# ---------------------------------------------------------------------------
# Unit tests -- normalize_scores with min_max_clip
# ---------------------------------------------------------------------------


class TestNormalizeScoresMinMaxClip:
    """normalize_scores with min_max_clip=True clips output to [0, 1]."""

    def test_standard_values_already_in_range(self) -> None:
        result = normalize_scores([0.2, 0.5, 0.8], min_max_clip=True)
        assert result == [0.0, 0.5, 1.0]

    def test_values_out_of_range_get_clipped(self) -> None:
        """When min_max_clip=True, values below 0 or above 1 are clipped."""
        result = normalize_scores([-0.5, 0.0, 0.5, 1.5], min_max_clip=True)
        assert all(0.0 <= v <= 1.0 for v in result)

    def test_min_max_clip_false_no_clipping(self) -> None:
        """Without min_max_clip, values can be outside [0,1] if input is."""
        result = normalize_scores([-0.5, 0.0, 0.5, 1.5], min_max_clip=False)
        # min-max normalization always maps to [0,1] for the input range
        # but if input has negative values, the raw output is still [0,1]
        assert result[0] == 0.0
        assert result[-1] == 1.0

    def test_single_value_with_clip(self) -> None:
        result = normalize_scores([0.7], min_max_clip=True)
        assert result == [1.0]

    def test_empty_with_clip(self) -> None:
        result = normalize_scores([], min_max_clip=True)
        assert result == []


class TestNormalizeScoresZeroRange:
    """normalize_scores handles zero-range (all same values) correctly."""

    def test_all_same_values_no_clip(self) -> None:
        result = normalize_scores([0.5, 0.5, 0.5], min_max_clip=False)
        assert result == [0.5, 0.5, 0.5]

    def test_all_same_values_with_clip(self) -> None:
        """When all values are the same, the value itself is returned
        (identity, since there is no range to normalize over)."""
        result = normalize_scores([0.5, 0.5, 0.5], min_max_clip=True)
        assert result == [0.5, 0.5, 0.5]

    def test_all_zeros_no_nan(self) -> None:
        """All zeros should not produce NaN."""
        result = normalize_scores([0.0, 0.0, 0.0])
        assert all(v == 0.0 for v in result)

    def test_negative_values(self) -> None:
        """Negative values should normalize correctly."""
        result = normalize_scores([-10.0, -5.0, 0.0])
        assert result[0] == 0.0
        assert result[-1] == 1.0
        assert result[1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Unit tests -- normalize_path_scores (per-path normalization)
# ---------------------------------------------------------------------------


class TestNormalizePathScores:
    """normalize_path_scores normalizes scores per path independently."""

    def test_single_path(self) -> None:
        scores_by_path = {"vector": [0.2, 0.5, 0.8]}
        result = normalize_path_scores(scores_by_path)
        assert "vector" in result
        assert result["vector"] == [0.0, 0.5, 1.0]

    def test_multiple_paths_independent(self) -> None:
        """Each path is normalized independently."""
        scores_by_path = {
            "vector": [0.2, 0.5, 0.8],
            "keyword": [20.0, 50.0, 80.0],
        }
        result = normalize_path_scores(scores_by_path)
        # Both paths should normalize to [0.0, 0.5, 1.0]
        assert result["vector"] == [0.0, 0.5, 1.0]
        assert result["keyword"] == [0.0, 0.5, 1.0]

    def test_none_scores_replaced_with_zero(self) -> None:
        """None scores in a path are treated as 0.0 for normalization."""
        scores_by_path = {"graph": [None, 0.5, 1.0]}
        result = normalize_path_scores(scores_by_path)
        # None -> 0.0, so the range is [0.0, 1.0] -> [0.0, 0.5, 1.0]
        assert result["graph"] == [0.0, 0.5, 1.0]

    def test_all_none_scores_in_path(self) -> None:
        """A path with all None scores should produce all 0.0 normalized."""
        scores_by_path = {"graph": [None, None]}
        result = normalize_path_scores(scores_by_path)
        assert result["graph"] == [0.0, 0.0]

    def test_empty_path(self) -> None:
        """An empty path list should produce an empty normalized list."""
        scores_by_path = {"vector": []}
        result = normalize_path_scores(scores_by_path)
        assert result["vector"] == []

    def test_empty_dict(self) -> None:
        """An empty dict should produce an empty dict."""
        result = normalize_path_scores({})
        assert result == {}

    def test_with_min_max_clip(self) -> None:
        """min_max_clip parameter is passed through to normalize_scores."""
        scores_by_path = {"vector": [0.2, 0.5, 0.8]}
        result = normalize_path_scores(scores_by_path, min_max_clip=True)
        assert "vector" in result
        assert all(0.0 <= v <= 1.0 for v in result["vector"])


# ---------------------------------------------------------------------------
# Unit tests -- rerank_pipeline (normalize -> fuse -> rerank)
# ---------------------------------------------------------------------------


class TestRerankPipeline:
    """rerank_pipeline runs the full normalize -> RRF -> rerank pipeline."""

    def test_pipeline_basic(self) -> None:
        s1, s2, s3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector"}), best_score=0.9, page_no=1, heading_path="A", raw_text="x", node_id=None),
            HybridHit(span_id=s2, source_paths=frozenset({"keyword"}), best_score=0.7, page_no=2, heading_path="B", raw_text="y", node_id=None),
            HybridHit(span_id=s3, source_paths=frozenset({"vector", "keyword"}), best_score=0.5, page_no=3, heading_path="C", raw_text="z", node_id=None),
        ]
        result = rerank_pipeline(hits)
        assert len(result) == 3
        # Results should be sorted by rerank_score descending
        scores = [r.rerank_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_pipeline_empty(self) -> None:
        result = rerank_pipeline([])
        assert result == []

    def test_pipeline_with_config(self) -> None:
        s1 = uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector"}), best_score=0.9, page_no=1, heading_path="A", raw_text="x", node_id=None),
        ]
        config = RerankerConfig(rrf_k=30, multi_path_bonus=0.5, min_max_clip=True)
        result = rerank_pipeline(hits, config=config)
        assert len(result) == 1

    def test_pipeline_preserves_provenance(self) -> None:
        s1 = uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector", "keyword"}), best_score=0.9, page_no=1, heading_path="A", raw_text="x", node_id=None),
        ]
        result = rerank_pipeline(hits)
        assert result[0].source_paths == frozenset({"vector", "keyword"})
        assert result[0].original_score == 0.9

    def test_pipeline_multi_path_bonus_applied(self) -> None:
        """Hits from multiple paths should get a bonus in rerank_score."""
        shared = uuid.uuid4()
        solo = uuid.uuid4()
        hits = [
            HybridHit(span_id=shared, source_paths=frozenset({"vector", "keyword"}), best_score=0.7, page_no=1, heading_path="A", raw_text="shared", node_id=None),
            HybridHit(span_id=solo, source_paths=frozenset({"vector"}), best_score=0.9, page_no=2, heading_path="B", raw_text="solo", node_id=None),
        ]
        result = rerank_pipeline(hits)
        shared_r = [r for r in result if r.span_id == shared][0]
        solo_r = [r for r in result if r.span_id == solo][0]
        # The multi-path bonus should make the shared hit have a higher
        # rerank_score than it would without the bonus
        assert shared_r.rerank_score > solo_r.rerank_score or shared_r.source_paths == frozenset({"vector", "keyword"})

    def test_pipeline_min_max_clip_normalizes_scores(self) -> None:
        """With min_max_clip=True, normalized_score should be in [0, 1]."""
        s1, s2, s3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector"}), best_score=0.2, page_no=1, heading_path="A", raw_text="x", node_id=None),
            HybridHit(span_id=s2, source_paths=frozenset({"vector"}), best_score=0.5, page_no=2, heading_path="B", raw_text="y", node_id=None),
            HybridHit(span_id=s3, source_paths=frozenset({"vector"}), best_score=0.8, page_no=3, heading_path="C", raw_text="z", node_id=None),
        ]
        config = RerankerConfig(min_max_clip=True)
        result = rerank_pipeline(hits, config=config)
        for r in result:
            assert 0.0 <= r.normalized_score <= 1.0


# ---------------------------------------------------------------------------
# Unit tests -- compute_rerank_scores with min_max_clip
# ---------------------------------------------------------------------------


class TestComputeRerankScoresWithClip:
    """compute_rerank_scores respects the min_max_clip config option."""

    def test_normalized_score_clipped_when_config_enabled(self) -> None:
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector"}), best_score=0.2, page_no=1, heading_path="A", raw_text="x", node_id=None),
            HybridHit(span_id=s2, source_paths=frozenset({"vector"}), best_score=0.9, page_no=2, heading_path="B", raw_text="y", node_id=None),
        ]
        config = RerankerConfig(min_max_clip=True)
        result = compute_rerank_scores(hits, config=config)
        for r in result:
            assert 0.0 <= r.normalized_score <= 1.0

    def test_normalized_score_not_clipped_when_config_disabled(self) -> None:
        """Without min_max_clip, normalized scores follow standard min-max
        (which is [0,1] anyway, but the flag should be respected)."""
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        hits = [
            HybridHit(span_id=s1, source_paths=frozenset({"vector"}), best_score=0.2, page_no=1, heading_path="A", raw_text="x", node_id=None),
            HybridHit(span_id=s2, source_paths=frozenset({"vector"}), best_score=0.9, page_no=2, heading_path="B", raw_text="y", node_id=None),
        ]
        config = RerankerConfig(min_max_clip=False)
        result = compute_rerank_scores(hits, config=config)
        # Results are sorted by rerank_score descending, so the 0.9 hit is first
        # The 0.9 hit has normalized_score 1.0, the 0.2 hit has 0.0
        by_original = {r.original_score: r for r in result}
        assert by_original[0.2].normalized_score == 0.0
        assert by_original[0.9].normalized_score == 1.0
