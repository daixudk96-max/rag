from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict

from .decision import decide_expansion
from .types import AncestorScore, HitDistributionResult, NodeHit


def analyze_hit_distribution(
    hits: list[NodeHit],
    tree_parent_map: dict[uuid.UUID, uuid.UUID | None],
    tree_level_map: dict[uuid.UUID, int],
    tree_heading_map: dict[uuid.UUID, str | None],
) -> HitDistributionResult:
    if not hits:
        raise ValueError("hits cannot be empty")

    score_map: dict[uuid.UUID, float] = defaultdict(float)
    leaf_count: dict[uuid.UUID, int] = defaultdict(int)

    for hit in hits:
        current: uuid.UUID | None = hit.node_id
        while current is not None:
            score_map[current] += hit.score
            leaf_count[current] += 1
            current = tree_parent_map.get(current)

    ancestor_scores = [
        AncestorScore(
            ancestor_id=node_id,
            accumulated_score=score,
            contributing_leaves_count=leaf_count[node_id],
            level_no=tree_level_map.get(node_id, 0),
            heading_path=tree_heading_map.get(node_id),
        )
        for node_id, score in score_map.items()
    ]
    values = [item.accumulated_score for item in ancestor_scores]
    mean = sum(values) / len(values) if values else 0.0
    cv = statistics.stdev(values) / mean if len(values) > 1 and mean != 0 else 0.0
    total = sum(values)
    entropy = 0.0
    if total > 0:
        for value in values:
            p = value / total
            if p > 0:
                entropy -= p * math.log2(p)

    decision = decide_expansion(cv, entropy, ancestor_scores)
    return HitDistributionResult(
        ancestor_scores=ancestor_scores,
        cv=cv,
        entropy=entropy,
        decision=decision,
        hit_count=len(hits),
        metadata={"ancestor_count": len(ancestor_scores)},
    )
