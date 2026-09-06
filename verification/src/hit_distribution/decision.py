from __future__ import annotations

import math
import uuid

from .types import AncestorScore, ExpansionDecision


def decide_expansion(cv: float, entropy: float, ancestor_scores: list[AncestorScore]) -> ExpansionDecision:
    ranked = sorted(ancestor_scores, key=lambda item: item.accumulated_score, reverse=True)
    if cv > 1.0 and entropy < 0.5:
        return ExpansionDecision(
            decision="high_concentration",
            reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
            suggested_node_ids=[item.ancestor_id for item in ranked[:2]],
        )
    max_entropy = math.log2(len(ranked)) if ranked else 0.0
    if cv < 0.4 or (max_entropy and entropy > 0.8 * max_entropy):
        return ExpansionDecision(
            decision="high_dispersion",
            reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
            suggested_node_ids=[item.ancestor_id for item in ranked],
        )
    return ExpansionDecision(
        decision="moderate",
        reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
        suggested_node_ids=[item.ancestor_id for item in ranked[:1]],
    )
