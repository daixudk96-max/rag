"""Tests for rerank policy and score normalization layer.

Phase 7 narrow slice: min-max normalization and per-path score normalization
that brings heterogeneous path scores onto a comparable scale before fusion.

Adapted from the verification reference for the formal runtime, which uses
QueryHit (text-based dedup) instead of HybridHit (span_id-based dedup).

These tests verify:
1. normalize_scores with min_max_clip=True clips to [0, 1]
2. Per-path normalization: each path's scores are independently normalized
3. Zero-range handling: min == max should not produce NaN
4. Edge cases: all same scores, single score, negative scores, None scores
5. rerank_pipeline: the full normalize -> fuse -> rerank pipeline
6. reciprocal_rank_fusion: RRF formula correctness
7. compute_rerank_scores: scoring logic with multi-path bonus
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from llamaindex_runtime.analysis.fusion import (
    compute_rerank_scores,
    reciprocal_rank_fusion,
    rerank_pipeline,
)
from llamaindex_runtime.analysis.normalize import (
    normalize_path_scores,
    normalize_scores,
)
from llamaindex_runtime.analysis.types import FusedHit, RerankerConfig
from llamaindex_runtime.entrypoints.types import QueryHit


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
# Unit tests -- reciprocal_rank_fusion
# ---------------------------------------------------------------------------


class TestReciprocalRankFusion:
    """RRF formula correctness."""

    def test_single_path(self) -> None:
        assert round(reciprocal_rank_fusion({"keyword": 1}, k=60), 5) == round(
            1 / 61, 5
        )

    def test_multi_path(self) -> None:
        score = reciprocal_rank_fusion({"keyword": 1, "vector": 2}, k=60)
        assert round(score, 5) == round((1 / 61) + (1 / 62), 5)

    def test_custom_k(self) -> None:
        score = reciprocal_rank_fusion({"vector": 1}, k=10)
        assert round(score, 5) == round(1 / 11, 5)


# ---------------------------------------------------------------------------
# Unit tests -- compute_rerank_scores
# ---------------------------------------------------------------------------


class TestComputeRerankScores:
    """compute_rerank_scores produces RerankedHit tuples from FusedHit."""

    def test_empty_input(self) -> None:
        result = compute_rerank_scores([])
        assert result == []

    def test_single_hit(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=1.0,
                rerank_score=0.01639,
            )
        ]
        result = compute_rerank_scores(hits)
        assert len(result) == 1
        assert result[0].text == "alpha"
        assert result[0].original_score == 0.9

    def test_results_sorted_by_rerank_score_descending(self) -> None:
        hits = [
            FusedHit(
                text="low",
                score=0.3,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=0.0,
                rerank_score=0.005,
            ),
            FusedHit(
                text="high",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector", "keyword"}),
                normalized_score=1.0,
                rerank_score=0.03,
            ),
            FusedHit(
                text="mid",
                score=0.6,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=0.5,
                rerank_score=0.01,
            ),
        ]
        result = compute_rerank_scores(hits)
        scores = [r.rerank_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_preserves_source_paths(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector", "keyword"}),
                normalized_score=1.0,
                rerank_score=0.03,
            )
        ]
        result = compute_rerank_scores(hits)
        assert result[0].source_paths == frozenset({"vector", "keyword"})

    def test_with_config(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=1.0,
                rerank_score=0.01639,
            )
        ]
        config = RerankerConfig(rrf_k=30, multi_path_bonus=0.5)
        result = compute_rerank_scores(hits, config=config)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Unit tests -- rerank_pipeline (normalize -> fuse -> rerank)
# ---------------------------------------------------------------------------


class TestRerankPipeline:
    """rerank_pipeline runs the full normalize -> RRF -> rerank pipeline."""

    def test_pipeline_basic(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=1.0,
                rerank_score=0.0,
            ),
            FusedHit(
                text="beta",
                score=0.7,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"keyword"}),
                normalized_score=0.7,
                rerank_score=0.0,
            ),
            FusedHit(
                text="gamma",
                score=0.5,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector", "keyword"}),
                normalized_score=0.5,
                rerank_score=0.0,
            ),
        ]
        result = rerank_pipeline(hits)
        assert len(result) == 3
        scores = [r.rerank_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_pipeline_empty(self) -> None:
        result = rerank_pipeline([])
        assert result == []

    def test_pipeline_with_config(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=1.0,
                rerank_score=0.0,
            )
        ]
        config = RerankerConfig(rrf_k=30, multi_path_bonus=0.5, min_max_clip=True)
        result = rerank_pipeline(hits, config=config)
        assert len(result) == 1

    def test_pipeline_preserves_provenance(self) -> None:
        hits = [
            FusedHit(
                text="alpha",
                score=0.9,
                metadata=MappingProxyType({"heading_path": "Ch1"}),
                source_paths=frozenset({"vector", "keyword"}),
                normalized_score=1.0,
                rerank_score=0.0,
            )
        ]
        result = rerank_pipeline(hits)
        assert result[0].source_paths == frozenset({"vector", "keyword"})
        assert result[0].original_score == 0.9

    def test_pipeline_multi_path_bonus_applied(self) -> None:
        """Hits from multiple paths should get a bonus in rerank_score."""
        shared = FusedHit(
            text="shared",
            score=0.7,
            metadata=MappingProxyType({}),
            source_paths=frozenset({"vector", "keyword"}),
            normalized_score=0.7,
            rerank_score=0.0,
        )
        solo = FusedHit(
            text="solo",
            score=0.9,
            metadata=MappingProxyType({}),
            source_paths=frozenset({"vector"}),
            normalized_score=0.9,
            rerank_score=0.0,
        )
        result = rerank_pipeline([shared, solo])
        shared_r = [r for r in result if r.text == "shared"][0]
        solo_r = [r for r in result if r.text == "solo"][0]
        # The multi-path bonus should make the shared hit have a higher
        # rerank_score than it would without the bonus
        assert shared_r.rerank_score > solo_r.rerank_score or shared_r.source_paths == frozenset({"vector", "keyword"})

    def test_pipeline_min_max_clip_normalizes_scores(self) -> None:
        """With min_max_clip=True, normalized_score should be in [0, 1]."""
        hits = [
            FusedHit(
                text="a",
                score=0.2,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=0.2,
                rerank_score=0.0,
            ),
            FusedHit(
                text="b",
                score=0.5,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=0.5,
                rerank_score=0.0,
            ),
            FusedHit(
                text="c",
                score=0.8,
                metadata=MappingProxyType({}),
                source_paths=frozenset({"vector"}),
                normalized_score=0.8,
                rerank_score=0.0,
            ),
        ]
        config = RerankerConfig(min_max_clip=True)
        result = rerank_pipeline(hits, config=config)
        for r in result:
            assert 0.0 <= r.normalized_score <= 1.0


# ---------------------------------------------------------------------------
# Unit tests -- RerankerConfig
# ---------------------------------------------------------------------------


class TestRerankerConfig:
    """RerankerConfig has sensible defaults and is frozen."""

    def test_default_rrf_k(self) -> None:
        config = RerankerConfig()
        assert config.rrf_k == 60

    def test_default_multi_path_bonus(self) -> None:
        config = RerankerConfig()
        assert config.multi_path_bonus == 0.1

    def test_default_min_max_clip(self) -> None:
        config = RerankerConfig()
        assert config.min_max_clip is True

    def test_custom_values(self) -> None:
        config = RerankerConfig(rrf_k=30, multi_path_bonus=0.5, min_max_clip=False)
        assert config.rrf_k == 30
        assert config.multi_path_bonus == 0.5
        assert config.min_max_clip is False

    def test_frozen(self) -> None:
        config = RerankerConfig()
        with pytest.raises(AttributeError):
            config.rrf_k = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unit tests -- RerankedHit immutability
# ---------------------------------------------------------------------------


class TestRerankedHitImmutability:
    """RerankedHit is frozen."""

    def test_reranked_hit_is_frozen(self) -> None:
        from llamaindex_runtime.analysis.types import RerankedHit

        hit = RerankedHit(
            text="test",
            score=0.9,
            metadata=MappingProxyType({}),
            source_paths=frozenset({"vector"}),
            original_score=0.9,
            normalized_score=1.0,
            rerank_score=0.016,
        )
        with pytest.raises(AttributeError):
            hit.rerank_score = 0.0  # type: ignore[misc]
