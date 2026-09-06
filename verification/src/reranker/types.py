from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RerankedHit:
    span_id: uuid.UUID
    source_paths: frozenset[str]
    original_score: float
    normalized_score: float
    rerank_score: float
    page_no: int | None
    heading_path: str | None
    raw_text: str | None
    node_id: uuid.UUID | None


@dataclass(frozen=True)
class RerankerConfig:
    rrf_k: int = 60
    multi_path_bonus: float = 0.1
    min_max_clip: bool = True
