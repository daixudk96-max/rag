"""Phase 7: Hit-distribution analysis, fusion, and rerank over structured QueryHit tuples.

Composes on top of Phase 6 deep hybrid output. Provides:
- HitDistributionAnalyzer: computes CV, entropy, and ancestor-score rollup
- decide_expansion: returns concentration/dispersion decision from signals
- fuse_candidates: path-aware fusion of multi-path QueryHit tuples
- rerank_pipeline: full normalize -> RRF -> rerank pipeline
"""
from __future__ import annotations

from .analyzer import HitDistributionAnalyzer
from .decision import decide_expansion
from .fusion import compute_rerank_scores, fuse_candidates, reciprocal_rank_fusion, rerank_pipeline
from .normalize import normalize_path_scores, normalize_scores
from .types import (
    AncestorScore,
    DistributionSignals,
    ExpansionDecision,
    FusedHit,
    HitDistributionResult,
    RerankedHit,
    RerankerConfig,
)

__all__ = [
    "AncestorScore",
    "DistributionSignals",
    "ExpansionDecision",
    "FusedHit",
    "HitDistributionAnalyzer",
    "HitDistributionResult",
    "RerankedHit",
    "RerankerConfig",
    "compute_rerank_scores",
    "decide_expansion",
    "fuse_candidates",
    "normalize_path_scores",
    "normalize_scores",
    "reciprocal_rank_fusion",
    "rerank_pipeline",
]
