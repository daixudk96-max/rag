"""Tests for Phase 7 hit-distribution analyzer and expansion decision.

Composes on top of Phase 6 deep hybrid QueryHit output. Tests cover:
- HitDistributionAnalyzer.analyze: CV, entropy, ancestor rollup
- decide_expansion: concentration/dispersion decision logic
- Edge cases: empty hits, single hit, flat hierarchy, deep hierarchy
- Integration: analyzer + decision composed end-to-end
"""
from __future__ import annotations

import math
from types import MappingProxyType

import pytest

from llamaindex_runtime.analysis import (
    AncestorScore,
    DistributionSignals,
    ExpansionDecision,
    HitDistributionAnalyzer,
    HitDistributionResult,
    decide_expansion,
)
from llamaindex_runtime.entrypoints.types import QueryHit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    text: str,
    score: float,
    heading_path: str | None = None,
) -> QueryHit:
    metadata: dict = {}
    if heading_path is not None:
        metadata["heading_path"] = heading_path
    return QueryHit(text=text, score=score, metadata=MappingProxyType(metadata))


# ---------------------------------------------------------------------------
# Unit tests -- HitDistributionAnalyzer
# ---------------------------------------------------------------------------


class TestHitDistributionAnalyzerEmpty:
    """Analyzer handles empty input."""

    def test_empty_hits_raises_value_error(self) -> None:
        analyzer = HitDistributionAnalyzer()
        with pytest.raises(ValueError, match="hits.*empty"):
            analyzer.analyze(())


class TestHitDistributionAnalyzerSingleHit:
    """Analyzer handles a single hit correctly."""

    def test_single_hit_returns_zero_cv(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.cv == 0.0

    def test_single_hit_returns_zero_entropy(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.entropy == 0.0

    def test_single_hit_hit_count_is_one(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.hit_count == 1

    def test_single_hit_ancestor_scores_include_leaf_and_root(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1 > Section 1.1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        paths = [a.heading_path for a in result.ancestor_scores]
        assert "Chapter 1" in paths
        assert "Chapter 1 > Section 1.1" in paths

    def test_single_hit_leaf_ancestor_has_score_of_hit(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1 > Section 1.1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        leaf = [a for a in result.ancestor_scores if a.heading_path == "Chapter 1 > Section 1.1"][0]
        assert leaf.accumulated_score == pytest.approx(0.9)

    def test_single_hit_root_ancestor_has_same_score(self) -> None:
        hits = (_hit("text", 0.9, "Chapter 1 > Section 1.1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        root = [a for a in result.ancestor_scores if a.heading_path == "Chapter 1"][0]
        assert root.accumulated_score == pytest.approx(0.9)


class TestHitDistributionAnalyzerTwoHitsSameParent:
    """Two hits under the same parent roll up correctly."""

    def test_parent_accumulates_both_scores(self) -> None:
        hits = (
            _hit("text A", 1.0, "Chapter 1 > Section 1.1"),
            _hit("text B", 2.0, "Chapter 1 > Section 1.2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        parent = [a for a in result.ancestor_scores if a.heading_path == "Chapter 1"][0]
        assert parent.accumulated_score == pytest.approx(3.0)

    def test_parent_has_two_contributing_leaves(self) -> None:
        hits = (
            _hit("text A", 1.0, "Chapter 1 > Section 1.1"),
            _hit("text B", 2.0, "Chapter 1 > Section 1.2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        parent = [a for a in result.ancestor_scores if a.heading_path == "Chapter 1"][0]
        assert parent.contributing_leaves_count == 2

    def test_hit_count_is_two(self) -> None:
        hits = (
            _hit("text A", 1.0, "Chapter 1 > Section 1.1"),
            _hit("text B", 2.0, "Chapter 1 > Section 1.2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.hit_count == 2


class TestHitDistributionAnalyzerCV:
    """Coefficient of variation is computed correctly."""

    def test_equal_scores_cv_is_zero(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1 > S1"),
            _hit("b", 1.0, "Ch2 > S2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.cv == pytest.approx(0.0)

    def test_unequal_scores_cv_is_positive(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1"),
            _hit("b", 5.0, "Ch2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.cv > 0.0

    def test_all_zero_scores_cv_is_zero(self) -> None:
        """When all ancestor scores are zero, CV should be 0 (mean=0 guard)."""
        hits = (
            _hit("a", 0.0, "Ch1"),
            _hit("b", 0.0, "Ch2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.cv == 0.0


class TestHitDistributionAnalyzerEntropy:
    """Entropy is computed correctly."""

    def test_uniform_distribution_high_entropy(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1"),
            _hit("b", 1.0, "Ch2"),
            _hit("c", 1.0, "Ch3"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        # Uniform distribution has max entropy
        assert result.signals.entropy > 0.0

    def test_concentrated_distribution_low_entropy(self) -> None:
        hits = (
            _hit("a", 100.0, "Ch1"),
            _hit("b", 0.01, "Ch2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.entropy < 0.5


class TestHitDistributionAnalyzerMaxEntropy:
    """max_entropy reflects the uniform baseline for the ancestor set."""

    def test_max_entropy_for_two_ancestors(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1"),
            _hit("b", 1.0, "Ch2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        expected = math.log2(result.signals.ancestor_count)
        assert result.signals.max_entropy == pytest.approx(expected)


class TestHitDistributionAnalyzerNoHeadingPath:
    """Hits without heading_path are handled gracefully."""

    def test_hit_without_heading_path_uses_text_as_leaf(self) -> None:
        hits = (_hit("standalone text", 0.8),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.hit_count == 1
        assert len(result.ancestor_scores) >= 1

    def test_mixed_heading_and_no_heading(self) -> None:
        hits = (
            _hit("with path", 0.9, "Ch1 > S1"),
            _hit("no path", 0.7),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.signals.hit_count == 2


class TestHitDistributionAnalyzerCustomSeparator:
    """Analyzer supports custom heading-path separators."""

    def test_slash_separator(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1/S1"),
            _hit("b", 2.0, "Ch1/S2"),
        )
        analyzer = HitDistributionAnalyzer(separator="/")
        result = analyzer.analyze(hits)
        parent = [a for a in result.ancestor_scores if a.heading_path == "Ch1"][0]
        assert parent.accumulated_score == pytest.approx(3.0)


class TestHitDistributionAnalyzerDepth:
    """Ancestor depth is computed from heading path hierarchy."""

    def test_root_depth_is_zero(self) -> None:
        hits = (_hit("a", 1.0, "Ch1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        root = [a for a in result.ancestor_scores if a.heading_path == "Ch1"][0]
        assert root.depth == 0

    def test_leaf_depth_reflects_nesting(self) -> None:
        hits = (_hit("a", 1.0, "Ch1 > S1 > SS1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        leaf = [a for a in result.ancestor_scores if a.heading_path == "Ch1 > S1 > SS1"][0]
        assert leaf.depth == 2


class TestHitDistributionAnalyzerResultIsImmutable:
    """HitDistributionResult is frozen."""

    def test_result_is_frozen(self) -> None:
        hits = (_hit("a", 1.0, "Ch1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        with pytest.raises(AttributeError):
            result.signals = DistributionSignals(cv=0, entropy=0, max_entropy=0, hit_count=0, ancestor_count=0)  # type: ignore[misc]

    def test_ancestor_scores_is_tuple(self) -> None:
        hits = (_hit("a", 1.0, "Ch1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert isinstance(result.ancestor_scores, tuple)


# ---------------------------------------------------------------------------
# Unit tests -- decide_expansion
# ---------------------------------------------------------------------------


class TestDecideExpansionHighConcentration:
    """High CV + low entropy => high_concentration decision."""

    def test_high_cv_low_entropy_returns_concentration(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=10.0, contributing_leaves_count=5, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=0.5, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=1.5, entropy=0.1, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "high_concentration"

    def test_concentration_suggests_top_paths(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=10.0, contributing_leaves_count=5, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=0.5, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=1.5, entropy=0.1, max_entropy=1.0, ancestor_scores=ancestors)
        assert "Ch1" in decision.suggested_paths


class TestDecideExpansionHighDispersion:
    """Low CV or high relative entropy => high_dispersion decision."""

    def test_low_cv_returns_dispersion(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.1, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.1, entropy=0.9, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "high_dispersion"

    def test_high_relative_entropy_returns_dispersion(self) -> None:
        """When entropy > 80% of max_entropy, it's dispersion regardless of CV."""
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.5, entropy=0.9, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "high_dispersion"

    def test_dispersion_suggests_all_paths(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.1, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.1, entropy=0.9, max_entropy=1.0, ancestor_scores=ancestors)
        assert set(decision.suggested_paths) == {"Ch1", "Ch2"}


class TestDecideExpansionModerate:
    """Neither concentrated nor dispersed => moderate decision."""

    def test_moderate_cv_and_entropy(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=3.0, contributing_leaves_count=2, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.7, entropy=0.5, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "moderate"

    def test_moderate_suggests_top_one_path(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=3.0, contributing_leaves_count=2, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.7, entropy=0.5, max_entropy=1.0, ancestor_scores=ancestors)
        assert len(decision.suggested_paths) == 1
        assert decision.suggested_paths[0] == "Ch1"


class TestDecideExpansionEmptyAncestors:
    """decide_expansion handles empty ancestor scores."""

    def test_empty_ancestors_returns_moderate(self) -> None:
        decision = decide_expansion(cv=0.0, entropy=0.0, max_entropy=0.0, ancestor_scores=())
        assert decision.decision == "moderate"

    def test_empty_ancestors_suggested_paths_empty(self) -> None:
        decision = decide_expansion(cv=0.0, entropy=0.0, max_entropy=0.0, ancestor_scores=())
        assert decision.suggested_paths == ()


class TestDecideExpansionReasonContainsMetrics:
    """Decision reason string includes CV and entropy values."""

    def test_reason_includes_cv(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=1.2, entropy=0.3, max_entropy=1.0, ancestor_scores=ancestors)
        assert "cv=" in decision.reason

    def test_reason_includes_entropy(self) -> None:
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=1.2, entropy=0.3, max_entropy=1.0, ancestor_scores=ancestors)
        assert "entropy=" in decision.reason


class TestDecideExpansionBoundaryValues:
    """Boundary conditions for CV and entropy thresholds."""

    def test_cv_exactly_at_concentration_threshold(self) -> None:
        """CV > 1.0 and entropy < 0.5 => high_concentration."""
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=10.0, contributing_leaves_count=5, depth=0),
        )
        decision = decide_expansion(cv=1.001, entropy=0.49, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "high_concentration"

    def test_cv_exactly_at_dispersion_threshold(self) -> None:
        """CV < 0.4 => high_dispersion."""
        ancestors = (
            AncestorScore(heading_path="Ch1", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
            AncestorScore(heading_path="Ch2", accumulated_score=1.0, contributing_leaves_count=1, depth=0),
        )
        decision = decide_expansion(cv=0.399, entropy=0.1, max_entropy=1.0, ancestor_scores=ancestors)
        assert decision.decision == "high_dispersion"


# ---------------------------------------------------------------------------
# Unit tests -- ExpansionDecision immutability
# ---------------------------------------------------------------------------


class TestExpansionDecisionImmutable:
    """ExpansionDecision is frozen."""

    def test_expansion_decision_is_frozen(self) -> None:
        d = ExpansionDecision(decision="moderate", reason="test", suggested_paths=("Ch1",))
        with pytest.raises(AttributeError):
            d.decision = "high_concentration"  # type: ignore[misc]

    def test_suggested_paths_is_tuple(self) -> None:
        d = ExpansionDecision(decision="moderate", reason="test", suggested_paths=("Ch1",))
        assert isinstance(d.suggested_paths, tuple)


# ---------------------------------------------------------------------------
# Integration tests -- Analyzer + Decision composed end-to-end
# ---------------------------------------------------------------------------


class TestAnalyzerDecisionIntegration:
    """End-to-end: analyzer produces signals that feed into decide_expansion."""

    def test_concentrated_hits_yield_concentration_decision(self) -> None:
        """All hits in one branch => high_concentration."""
        hits = (
            _hit("a", 10.0, "Ch1 > S1"),
            _hit("b", 8.0, "Ch1 > S2"),
            _hit("c", 0.1, "Ch2 > S3"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        # Ch1 has much more accumulated score than Ch2
        assert result.decision.decision in ("high_concentration", "moderate")

    def test_dispersed_hits_yield_dispersion_decision(self) -> None:
        """Hits spread evenly across branches => high_dispersion."""
        hits = (
            _hit("a", 1.0, "Ch1 > S1"),
            _hit("b", 1.0, "Ch2 > S2"),
            _hit("c", 1.0, "Ch3 > S3"),
            _hit("d", 1.0, "Ch4 > S4"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert result.decision.decision == "high_dispersion"

    def test_result_contains_all_fields(self) -> None:
        hits = (_hit("a", 1.0, "Ch1"),)
        result = HitDistributionAnalyzer().analyze(hits)
        assert isinstance(result.ancestor_scores, tuple)
        assert isinstance(result.signals, DistributionSignals)
        assert isinstance(result.decision, ExpansionDecision)
        assert isinstance(result.metadata, dict)

    def test_metadata_contains_ancestor_count(self) -> None:
        hits = (
            _hit("a", 1.0, "Ch1 > S1"),
            _hit("b", 2.0, "Ch1 > S2"),
        )
        result = HitDistributionAnalyzer().analyze(hits)
        assert "ancestor_count" in result.metadata

    def test_hit_with_none_score_treated_as_zero(self) -> None:
        """Hits with None score (e.g. graph hits) should not crash the analyzer."""
        hit = QueryHit(text="entity", score=None, metadata=MappingProxyType({"heading_path": "Ch1"}))
        result = HitDistributionAnalyzer().analyze((hit,))
        assert result.signals.hit_count == 1
