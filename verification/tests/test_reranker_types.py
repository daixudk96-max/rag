from __future__ import annotations

import uuid

from reranker.types import RerankedHit, RerankerConfig


def test_reranked_hit_type() -> None:
    hit = RerankedHit(
        span_id=uuid.uuid4(),
        source_paths=frozenset({"keyword"}),
        original_score=1.0,
        normalized_score=1.0,
        rerank_score=1.1,
        page_no=1,
        heading_path="A",
        raw_text="x",
        node_id=None,
    )
    assert hit.rerank_score == 1.1


def test_reranker_config_defaults() -> None:
    cfg = RerankerConfig()
    assert cfg.rrf_k == 60
    assert cfg.multi_path_bonus == 0.1
