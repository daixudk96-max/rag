"""Expansion decision function based on concentration/dispersion signals."""
from __future__ import annotations

from .types import AncestorScore, ExpansionDecision


def decide_expansion(
    cv: float,
    entropy: float,
    max_entropy: float,
    ancestor_scores: tuple[AncestorScore, ...],
) -> ExpansionDecision:
    """Return an expansion decision based on concentration/dispersion signals.

    Thresholds mirror the verification reference:
    - high_concentration: cv > 1.0 AND entropy < 0.5
    - high_dispersion: cv < 0.4 OR (max_entropy > 0 AND entropy > 0.8 * max_entropy)
    - moderate: everything else
    """
    if not ancestor_scores:
        return ExpansionDecision(
            decision="moderate",
            reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
            suggested_paths=(),
        )

    ranked = sorted(ancestor_scores, key=lambda a: a.accumulated_score, reverse=True)
    ranked_paths = tuple(a.heading_path for a in ranked)

    if cv > 1.0 and entropy < 0.5:
        return ExpansionDecision(
            decision="high_concentration",
            reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
            suggested_paths=ranked_paths[:2],
        )

    if cv < 0.4 or (max_entropy > 0 and entropy > 0.8 * max_entropy):
        return ExpansionDecision(
            decision="high_dispersion",
            reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
            suggested_paths=ranked_paths,
        )

    return ExpansionDecision(
        decision="moderate",
        reason=f"cv={cv:.3f}, entropy={entropy:.3f}",
        suggested_paths=ranked_paths[:1],
    )
