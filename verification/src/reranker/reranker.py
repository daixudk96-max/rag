from __future__ import annotations

from hybrid_path.types import HybridHit
from .fusion import compute_rerank_scores
from .types import RerankedHit, RerankerConfig


def rerank_hits(hits: list[HybridHit], config: RerankerConfig | None = None) -> list[RerankedHit]:
    return compute_rerank_scores(hits, config=config)
