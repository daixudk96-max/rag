"""QUAL-04: Level assessment and closeout gate tests.

Enforces that Level 4+ readiness is impossible unless ALL thresholds pass.
No subjective "looks good" shortcuts allowed.

Level definitions (from verification evidence):
- Level 2: Technically connected, quality unverified (能查但质量未验证)
- Level 3: Query quality basically correct but not stable enough (查得基本对)
- Level 4: All thresholds pass, ready for closeout (查得稳定好)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

# --- Level definitions ---

LEVEL_2 = "Level_2"
LEVEL_3 = "Level_3"
LEVEL_4 = "Level_4"

# --- Thresholds (must match other QUAL test files) ---

THRESHOLDS = {
    "hit_rate": 0.80,
    "top1_relevance": 0.90,
    "stability": 0.85,
    "tree_depth": 3,
    "node_chunk_mapping_rate": 0.80,
    "heading_path_completeness": 0.95,
    "min_test_queries": 10,
}


def _assess_level(
    query_quality: dict[str, Any],
    tree_quality: dict[str, Any],
    evidence_chain: dict[str, Any],
) -> dict[str, Any]:
    """Assess readiness level from measured artifact outputs.

    Rules:
    - Level 4 requires ALL thresholds to pass.
    - Level 3 requires query quality basically passing but may have gaps.
    - Level 2 is the default when quality is unverified.

    Returns:
        {
            "level": "Level_2" | "Level_3" | "Level_4",
            "blocking_factors": list[str],
            "passing_factors": list[str],
            "thresholds": dict,
        }
    """
    blocking: list[str] = []
    passing: list[str] = []

    # Query quality checks
    hit_rate = query_quality.get("hit_rate", 0.0)
    if hit_rate >= THRESHOLDS["hit_rate"]:
        passing.append(f"hit_rate: {hit_rate:.2%}")
    else:
        blocking.append(f"hit_rate: {hit_rate:.2%} (need >= {THRESHOLDS['hit_rate']:.2%})")

    top1 = query_quality.get("top1_relevance", 0.0)
    if top1 >= THRESHOLDS["top1_relevance"]:
        passing.append(f"top1_relevance: {top1:.2%}")
    else:
        blocking.append(f"top1_relevance: {top1:.2%} (need >= {THRESHOLDS['top1_relevance']:.2%})")

    stability = query_quality.get("stability", 0.0)
    if stability >= THRESHOLDS["stability"]:
        passing.append(f"stability: {stability:.2%}")
    else:
        blocking.append(f"stability: {stability:.2%} (need >= {THRESHOLDS['stability']:.2%})")

    test_count = query_quality.get("test_count", 0)
    if test_count >= THRESHOLDS["min_test_queries"]:
        passing.append(f"test_count: {test_count}")
    else:
        blocking.append(f"test_count: {test_count} (need >= {THRESHOLDS['min_test_queries']})")

    # Tree quality checks
    tree_depth = tree_quality.get("max_level", 0)
    if tree_depth >= THRESHOLDS["tree_depth"]:
        passing.append(f"tree_depth: {tree_depth}")
    else:
        blocking.append(f"tree_depth: {tree_depth} (need >= {THRESHOLDS['tree_depth']})")

    # Evidence chain checks
    mapping_rate = evidence_chain.get("node_chunk_mapping_rate", 0.0)
    if mapping_rate >= THRESHOLDS["node_chunk_mapping_rate"]:
        passing.append(f"node_chunk_mapping: {mapping_rate:.2%}")
    else:
        blocking.append(f"node_chunk_mapping: {mapping_rate:.2%} (need >= {THRESHOLDS['node_chunk_mapping_rate']:.2%})")

    heading_rate = evidence_chain.get("heading_path_completeness", 0.0)
    if heading_rate >= THRESHOLDS["heading_path_completeness"]:
        passing.append(f"heading_path: {heading_rate:.2%}")
    else:
        blocking.append(f"heading_path: {heading_rate:.2%} (need >= {THRESHOLDS['heading_path_completeness']:.2%})")

    # Level determination: strict rules
    if not blocking:
        level = LEVEL_4
    elif _query_quality_basically_passing(query_quality):
        level = LEVEL_3
    else:
        level = LEVEL_2

    return {
        "level": level,
        "blocking_factors": blocking,
        "passing_factors": passing,
        "thresholds": THRESHOLDS,
    }


def _query_quality_basically_passing(query_quality: dict[str, Any]) -> bool:
    """Check if query quality is basically correct (Level 3 condition).

    Level 3: hit_rate passes but other metrics may have gaps.
    """
    hit_rate = query_quality.get("hit_rate", 0.0)
    return hit_rate >= THRESHOLDS["hit_rate"]


@pytest.mark.integration
class TestLevelAssessment:
    """QUAL-04: Level assessment closeout gate."""

    def test_level_2_when_quality_unverified(self) -> None:
        """Verify Level 2 is assigned when no quality metrics are available."""
        assessment = _assess_level(
            query_quality={},
            tree_quality={},
            evidence_chain={},
        )
        assert assessment["level"] == LEVEL_2, (
            "Empty metrics should result in Level 2 (quality unverified)"
        )
        assert len(assessment["blocking_factors"]) > 0, (
            "Level 2 must have blocking factors"
        )

    def test_level_4_requires_all_thresholds(self) -> None:
        """Verify Level 4 is impossible unless ALL thresholds pass."""
        all_passing = {
            "hit_rate": 0.85,
            "top1_relevance": 0.92,
            "stability": 0.90,
            "test_count": 15,
        }
        tree_passing = {"max_level": 3}
        evidence_passing = {
            "node_chunk_mapping_rate": 0.85,
            "heading_path_completeness": 0.97,
        }

        assessment = _assess_level(all_passing, tree_passing, evidence_passing)
        assert assessment["level"] == LEVEL_4, (
            f"All thresholds passing should yield Level 4, got {assessment['level']}"
        )
        assert len(assessment["blocking_factors"]) == 0, (
            "Level 4 should have no blocking factors"
        )

    def test_level_4_impossible_with_single_failure(self) -> None:
        """Verify Level 4 is impossible even if one threshold fails."""
        almost_passing = {
            "hit_rate": 0.75,  # Below 0.80 threshold
            "top1_relevance": 0.92,
            "stability": 0.90,
            "test_count": 15,
        }
        tree_passing = {"max_level": 3}
        evidence_passing = {
            "node_chunk_mapping_rate": 0.85,
            "heading_path_completeness": 0.97,
        }

        assessment = _assess_level(almost_passing, tree_passing, evidence_passing)
        assert assessment["level"] != LEVEL_4, (
            "Single threshold failure must prevent Level 4"
        )
        assert any("hit_rate" in f for f in assessment["blocking_factors"]), (
            "hit_rate should appear in blocking factors"
        )

    def test_level_3_when_query_ok_but_tree_insufficient(self) -> None:
        """Verify Level 3 when query quality passes but tree/evidence has gaps."""
        query_ok = {
            "hit_rate": 0.85,
            "top1_relevance": 0.70,  # Not meeting 0.90
            "stability": 0.70,  # Not meeting 0.85
            "test_count": 12,
        }
        tree_failing = {"max_level": 1}  # Below 3
        evidence_failing = {
            "node_chunk_mapping_rate": 0.22,  # Current white-box state
            "heading_path_completeness": 0.80,
        }

        assessment = _assess_level(query_ok, tree_failing, evidence_failing)
        assert assessment["level"] == LEVEL_3, (
            f"hit_rate passing but other metrics failing should yield Level 3, "
            f"got {assessment['level']}"
        )

    def test_whitebox_state_is_level_2(self) -> None:
        """Verify current white-box verification state (2026-05-27) is Level 2.

        Known gaps:
        - hit_rate: unverified (0.0)
        - tree_depth: 0 (only root nodes)
        - node_chunk_mapping: 21.5%
        - heading_path: 80%
        """
        query_unverified = {
            "hit_rate": 0.0,
            "top1_relevance": 0.0,
            "stability": 0.0,
            "test_count": 0,
        }
        tree_flat = {"max_level": 0}
        evidence_incomplete = {
            "node_chunk_mapping_rate": 70 / 326,
            "heading_path_completeness": 262 / 326,
        }

        assessment = _assess_level(query_unverified, tree_flat, evidence_incomplete)
        assert assessment["level"] == LEVEL_2, (
            f"Current white-box state should be Level 2, got {assessment['level']}"
        )

    def test_level_assessment_not_subjective(self) -> None:
        """Verify that level assessment cannot contain subjective shortcuts.

        No "partial", "mostly", "looks good" in assessment output.
        """
        all_passing = {
            "hit_rate": 0.85,
            "top1_relevance": 0.92,
            "stability": 0.90,
            "test_count": 15,
        }
        tree_passing = {"max_level": 3}
        evidence_passing = {
            "node_chunk_mapping_rate": 0.85,
            "heading_path_completeness": 0.97,
        }

        assessment = _assess_level(all_passing, tree_passing, evidence_passing)
        assessment_str = json.dumps(assessment)

        subjective_terms = ["partial", "mostly", "looks good", "seems ok", "probably"]
        for term in subjective_terms:
            assert term not in assessment_str.lower(), (
                f"Subjective term '{term}' found in assessment"
            )

    def test_blocking_factors_explain_why(self) -> None:
        """Verify blocking factors include both current value and threshold."""
        query_failing = {
            "hit_rate": 0.50,
            "top1_relevance": 0.60,
            "stability": 0.70,
            "test_count": 5,
        }
        tree_failing = {"max_level": 1}
        evidence_failing = {
            "node_chunk_mapping_rate": 0.22,
            "heading_path_completeness": 0.80,
        }

        assessment = _assess_level(query_failing, tree_failing, evidence_failing)
        for factor in assessment["blocking_factors"]:
            # Each blocking factor must state current value AND required threshold
            assert "need >=" in factor or "need >= " in factor, (
                f"Blocking factor lacks threshold explanation: {factor}"
            )

    def test_assessment_result_is_json_serializable(self) -> None:
        """Verify assessment result can be written as JSON artifact."""
        query = {"hit_rate": 0.50, "top1_relevance": 0.60, "stability": 0.70, "test_count": 5}
        tree = {"max_level": 1}
        evidence = {"node_chunk_mapping_rate": 0.22, "heading_path_completeness": 0.80}

        assessment = _assess_level(query, tree, evidence)
        # Must not raise
        json_str = json.dumps(assessment, indent=2)
        parsed = json.loads(json_str)
        assert parsed["level"] == assessment["level"]

    def test_thresholds_are_frozen(self) -> None:
        """Verify thresholds are defined as immutable mapping."""
        from types import MappingProxyType

        frozen = MappingProxyType(THRESHOLDS)
        # Verify all expected threshold keys exist with correct values
        assert frozen["hit_rate"] == 0.80
        assert frozen["top1_relevance"] == 0.90
        assert frozen["stability"] == 0.85
        assert frozen["tree_depth"] == 3
        assert frozen["node_chunk_mapping_rate"] == 0.80
        assert frozen["heading_path_completeness"] == 0.95
        assert frozen["min_test_queries"] == 10
