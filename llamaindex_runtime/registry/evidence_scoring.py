from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from llamaindex_runtime.registry.contracts import EvidenceLink


@dataclass(frozen=True)
class RankedEvidenceScore:
    evidence_id: UUID
    score: float
    support_count: int


@dataclass(frozen=True)
class EvidenceScoringPolicy:
    source_weights: dict[str, float] = field(default_factory=dict)
    support_bonus_per_additional_link: float = 0.0
    max_score: float = 1.0

    def __post_init__(self) -> None:
        if self.max_score <= 0.0:
            raise ValueError("max_score must be positive")
        if self.support_bonus_per_additional_link < 0.0:
            raise ValueError("support_bonus_per_additional_link must be non-negative")
        for source_kind, weight in self.source_weights.items():
            if weight < 0.0:
                raise ValueError(f"source_weights[{source_kind}] must be non-negative")


def _group_links_by_evidence_id(links: Sequence[EvidenceLink]) -> dict[UUID, list[EvidenceLink]]:
    grouped: dict[UUID, list[EvidenceLink]] = {}
    for link in links:
        if link.evidence_id is None:
            continue
        grouped.setdefault(link.evidence_id, []).append(link)
    return grouped


def aggregate_confidence(
    links: Sequence[EvidenceLink],
    policy: EvidenceScoringPolicy | None = None,
) -> float | None:
    scored_links = [link for link in links if link.confidence_score is not None]
    if not scored_links:
        return None

    active_policy = policy or EvidenceScoringPolicy()
    total_weight = 0.0
    weighted_score = 0.0
    for link in scored_links:
        weight = active_policy.source_weights.get(link.source_kind, 1.0)
        total_weight += weight
        weighted_score += link.confidence_score * weight

    if total_weight == 0.0:
        return None

    score = weighted_score / total_weight
    support_bonus = max(0, len(scored_links) - 1) * active_policy.support_bonus_per_additional_link
    return min(active_policy.max_score, score + support_bonus)


def score_by_evidence_id(
    links: Sequence[EvidenceLink],
    policy: EvidenceScoringPolicy | None = None,
) -> dict[UUID, float]:
    scores: dict[UUID, float] = {}
    for evidence_id, evidence_links in _group_links_by_evidence_id(links).items():
        score = aggregate_confidence(evidence_links, policy=policy)
        if score is not None:
            scores[evidence_id] = score
    return scores


def rank_evidence_by_score(
    links: Sequence[EvidenceLink],
    policy: EvidenceScoringPolicy | None = None,
) -> list[RankedEvidenceScore]:
    ranked: list[RankedEvidenceScore] = []
    for evidence_id, evidence_links in _group_links_by_evidence_id(links).items():
        score = aggregate_confidence(evidence_links, policy=policy)
        if score is None:
            continue
        ranked.append(
            RankedEvidenceScore(
                evidence_id=evidence_id,
                score=score,
                support_count=len(evidence_links),
            )
        )

    return sorted(
        ranked,
        key=lambda item: (-item.score, -item.support_count, str(item.evidence_id)),
    )
