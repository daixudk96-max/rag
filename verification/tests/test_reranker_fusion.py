from __future__ import annotations

import uuid

from hybrid_path.types import HybridHit
from reranker.fusion import reciprocal_rank_fusion, compute_rerank_scores
from reranker.reranker import rerank_hits


def test_rrf_single_path() -> None:
    assert round(reciprocal_rank_fusion({"keyword": 1}, k=60), 5) == round(1 / 61, 5)


def test_rrf_multi_path() -> None:
    score = reciprocal_rank_fusion({"keyword": 1, "vector": 2}, k=60)
    assert round(score, 5) == round((1 / 61) + (1 / 62), 5)


def test_rerank_hits_preserves_provenance() -> None:
    hit1 = HybridHit(span_id=uuid.uuid4(), source_paths=frozenset({"keyword"}), best_score=1.0, page_no=1, heading_path="A", raw_text="x", node_id=None)
    hit2 = HybridHit(span_id=uuid.uuid4(), source_paths=frozenset({"keyword", "vector"}), best_score=1.0, page_no=2, heading_path="B", raw_text="y", node_id=None)
    reranked = rerank_hits([hit1, hit2])
    assert reranked[0].span_id == hit2.span_id
    assert reranked[0].raw_text == "y"


def test_compute_rerank_scores_empty() -> None:
    assert compute_rerank_scores([]) == []
