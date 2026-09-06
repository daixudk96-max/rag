from __future__ import annotations

import uuid

import pytest

from hit_distribution.analyzer import analyze_hit_distribution
from hit_distribution.decision import decide_expansion
from hit_distribution.types import NodeHit


def test_empty_hits_raise() -> None:
    with pytest.raises(ValueError):
        analyze_hit_distribution([], {}, {}, {})


def test_single_node_hit() -> None:
    n1 = uuid.uuid4()
    hits = [NodeHit(node_id=n1, score=1.0, level_no=1, heading_path="A")]
    result = analyze_hit_distribution(hits, {n1: None}, {n1: 1}, {n1: "A"})
    assert result.hit_count == 1
    assert result.cv == 0.0
    assert result.entropy == 0.0


def test_two_siblings_roll_up_parent() -> None:
    p = uuid.uuid4(); n1 = uuid.uuid4(); n2 = uuid.uuid4()
    hits = [NodeHit(node_id=n1, score=1.0, level_no=2, heading_path="A > B"), NodeHit(node_id=n2, score=2.0, level_no=2, heading_path="A > C")]
    result = analyze_hit_distribution(hits, {n1: p, n2: p, p: None}, {n1: 2, n2: 2, p: 1}, {n1: "A > B", n2: "A > C", p: "A"})
    assert any(a.ancestor_id == p and a.accumulated_score == 3.0 for a in result.ancestor_scores)


def test_decide_expansion_high_concentration() -> None:
    decision = decide_expansion(cv=1.2, entropy=0.0, ancestor_scores=[])
    assert decision.decision == "high_concentration"


def test_decide_expansion_high_dispersion() -> None:
    decision = decide_expansion(cv=0.2, entropy=1.5, ancestor_scores=[])
    assert decision.decision == "high_dispersion"


def test_decide_expansion_moderate() -> None:
    decision = decide_expansion(cv=0.7, entropy=0.5, ancestor_scores=[])
    assert decision.decision == "moderate"
