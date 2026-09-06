from __future__ import annotations

import uuid

from hybrid_path.types import HybridHit, HybridQueryResult, PathContribution


def test_hybrid_hit_type() -> None:
    hit = HybridHit(span_id=uuid.uuid4(), source_paths=frozenset({"keyword"}), best_score=1.0, page_no=1, heading_path="A", raw_text="x", node_id=None)
    assert hit.best_score == 1.0


def test_hybrid_query_result_type() -> None:
    result = HybridQueryResult(query="q", paths_used=[], total_hits=0, decision="no_hits", expanded_count=0, evidence=[])
    assert result.decision == "no_hits"


def test_path_contribution_type() -> None:
    pc = PathContribution(path_name="graph", hit_count=0, available=False)
    assert pc.available is False
