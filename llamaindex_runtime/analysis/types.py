"""Data types for hit-distribution analysis and fusion/rerank (Phase 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class AncestorScore:
    """Accumulated score for a heading-path ancestor after rollup."""

    heading_path: str
    accumulated_score: float
    contributing_leaves_count: int
    depth: int


@dataclass(frozen=True)
class DistributionSignals:
    """Statistical signals derived from hit distribution."""

    cv: float
    entropy: float
    max_entropy: float
    hit_count: int
    ancestor_count: int


@dataclass(frozen=True)
class ExpansionDecision:
    """Decision about whether to expand the query based on distribution signals."""

    decision: str
    reason: str
    suggested_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HitDistributionResult:
    """Complete result of hit-distribution analysis over QueryHit tuples."""

    ancestor_scores: tuple[AncestorScore, ...]
    signals: DistributionSignals
    decision: ExpansionDecision
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RerankerConfig:
    """Configuration for the rerank/fusion policy layer."""

    rrf_k: int = 60
    multi_path_bonus: float = 0.1
    min_max_clip: bool = True


@dataclass(frozen=True)
class FusedHit:
    """A QueryHit that has been through the fusion pipeline.

    Extends the QueryHit shape with fusion-specific metadata:
    - source_paths: which retrieval paths contributed to this hit
    - normalized_score: score after per-path normalization
    - rerank_score: final RRF-based score used for ranking
    """

    text: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    source_paths: frozenset[str] = frozenset()
    normalized_score: float = 0.0
    rerank_score: float = 0.0


@dataclass(frozen=True)
class RerankedHit:
    """A hit after the full rerank pipeline, with original and rerank scores."""

    text: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    source_paths: frozenset[str] = frozenset()
    original_score: float = 0.0
    normalized_score: float = 0.0
    rerank_score: float = 0.0
