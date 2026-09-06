from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HybridHit:
    span_id: uuid.UUID
    source_paths: frozenset[str]
    best_score: float
    page_no: int | None
    heading_path: str | None
    raw_text: str | None
    node_id: uuid.UUID | None


@dataclass(frozen=True)
class PathContribution:
    path_name: str
    hit_count: int
    available: bool


@dataclass(frozen=True)
class HybridQueryResult:
    query: str
    paths_used: list[PathContribution]
    total_hits: int
    decision: str
    expanded_count: int
    evidence: list[dict[str, Any]] = field(default_factory=list)
