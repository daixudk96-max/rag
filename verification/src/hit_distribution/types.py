from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NodeHit:
    node_id: uuid.UUID
    score: float
    level_no: int
    heading_path: str | None


@dataclass(frozen=True)
class AncestorScore:
    ancestor_id: uuid.UUID
    accumulated_score: float
    contributing_leaves_count: int
    level_no: int
    heading_path: str | None


@dataclass(frozen=True)
class ExpansionDecision:
    decision: str
    reason: str
    suggested_node_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(frozen=True)
class HitDistributionResult:
    ancestor_scores: list[AncestorScore]
    cv: float
    entropy: float
    decision: ExpansionDecision
    hit_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
