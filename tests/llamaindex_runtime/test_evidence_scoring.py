"""Tests for the minimal Evidence scoring helper.

This slice adds pure scoring logic for EvidenceLink groups without widening the
Evidence contract or touching persistence code.
"""
from __future__ import annotations

import uuid

import pytest

from llamaindex_runtime.registry.contracts import EvidenceLink


def _make_link(
    *,
    confidence_score: float | None,
    evidence_id: uuid.UUID | None = None,
) -> EvidenceLink:
    return EvidenceLink(
        evidence_link_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        relation_id=None,
        span_id=uuid.uuid4(),
        source_kind="ner",
        confidence_score=confidence_score,
        evidence_id=evidence_id,
    )


class TestAggregateConfidence:
    def test_empty_list_returns_none(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        assert aggregate_confidence([]) is None

    def test_all_none_scores_return_none(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        links = [
            _make_link(confidence_score=None),
            _make_link(confidence_score=None),
            _make_link(confidence_score=None),
        ]

        assert aggregate_confidence(links) is None

    def test_single_link_returns_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        links = [_make_link(confidence_score=0.85, evidence_id=uuid.uuid4())]

        assert aggregate_confidence(links) == 0.85

    def test_zero_score_is_valid(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.0, evidence_id=evidence_id),
            _make_link(confidence_score=0.5, evidence_id=evidence_id),
        ]

        assert aggregate_confidence(links) == pytest.approx(0.25)

    def test_multiple_links_return_mean_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.9, evidence_id=evidence_id),
            _make_link(confidence_score=0.8, evidence_id=evidence_id),
        ]

        assert aggregate_confidence(links) == pytest.approx(0.8)

    def test_mixed_none_and_valid_scores_ignores_none(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.6, evidence_id=evidence_id),
            _make_link(confidence_score=None, evidence_id=evidence_id),
            _make_link(confidence_score=0.8, evidence_id=evidence_id),
        ]

        assert aggregate_confidence(links) == pytest.approx(0.7)


class TestScoreByEvidenceId:
    def test_empty_returns_empty_dict(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        assert score_by_evidence_id([]) == {}

    def test_single_link_returns_single_evidence_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        evidence_id = uuid.uuid4()
        links = [_make_link(confidence_score=0.9, evidence_id=evidence_id)]

        assert score_by_evidence_id(links) == {evidence_id: 0.9}

    def test_groups_multiple_links_under_same_evidence_id(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.9, evidence_id=evidence_id),
            _make_link(confidence_score=0.8, evidence_id=evidence_id),
        ]

        assert score_by_evidence_id(links) == {evidence_id: pytest.approx(0.8)}

    def test_returns_scores_for_multiple_evidence_ids(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        first_evidence_id = uuid.uuid4()
        second_evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.2, evidence_id=first_evidence_id),
            _make_link(confidence_score=0.4, evidence_id=first_evidence_id),
            _make_link(confidence_score=0.9, evidence_id=second_evidence_id),
        ]

        assert score_by_evidence_id(links) == {
            first_evidence_id: pytest.approx(0.3),
            second_evidence_id: pytest.approx(0.9),
        }

    def test_skips_links_without_evidence_id(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.6, evidence_id=evidence_id),
            _make_link(confidence_score=0.8, evidence_id=None),
        ]

        assert score_by_evidence_id(links) == {evidence_id: pytest.approx(0.6)}

    def test_ignores_groups_with_only_none_scores(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import score_by_evidence_id

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=None, evidence_id=evidence_id),
            _make_link(confidence_score=None, evidence_id=evidence_id),
        ]

        assert score_by_evidence_id(links) == {}


class TestRankEvidenceByScore:
    def test_empty_returns_empty_list(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import rank_evidence_by_score

        assert rank_evidence_by_score([]) == []

    def test_single_evidence_returns_ranked_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import RankedEvidenceScore, rank_evidence_by_score

        evidence_id = uuid.uuid4()
        links = [_make_link(confidence_score=0.9, evidence_id=evidence_id)]

        assert rank_evidence_by_score(links) == [
            RankedEvidenceScore(evidence_id=evidence_id, score=0.9, support_count=1)
        ]

    def test_multiple_links_same_evidence_aggregate_score_and_support(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import RankedEvidenceScore, rank_evidence_by_score

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.9, evidence_id=evidence_id),
            _make_link(confidence_score=0.8, evidence_id=evidence_id),
        ]

        assert rank_evidence_by_score(links) == [
            RankedEvidenceScore(evidence_id=evidence_id, score=pytest.approx(0.8), support_count=3)
        ]

    def test_multiple_evidence_scores_are_sorted_descending(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import RankedEvidenceScore, rank_evidence_by_score

        high_evidence_id = uuid.uuid4()
        low_evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.3, evidence_id=low_evidence_id),
            _make_link(confidence_score=0.9, evidence_id=high_evidence_id),
        ]

        assert rank_evidence_by_score(links) == [
            RankedEvidenceScore(evidence_id=high_evidence_id, score=0.9, support_count=1),
            RankedEvidenceScore(evidence_id=low_evidence_id, score=0.3, support_count=1),
        ]

    def test_ties_break_by_support_count_then_evidence_id(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import RankedEvidenceScore, rank_evidence_by_score

        first_evidence_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        second_evidence_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        third_evidence_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
        links = [
            _make_link(confidence_score=0.8, evidence_id=second_evidence_id),
            _make_link(confidence_score=0.8, evidence_id=first_evidence_id),
            _make_link(confidence_score=0.8, evidence_id=third_evidence_id),
            _make_link(confidence_score=0.8, evidence_id=third_evidence_id),
        ]

        assert rank_evidence_by_score(links) == [
            RankedEvidenceScore(evidence_id=third_evidence_id, score=0.8, support_count=2),
            RankedEvidenceScore(evidence_id=first_evidence_id, score=0.8, support_count=1),
            RankedEvidenceScore(evidence_id=second_evidence_id, score=0.8, support_count=1),
        ]

    def test_groups_with_only_none_scores_are_excluded(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import RankedEvidenceScore, rank_evidence_by_score

        excluded_evidence_id = uuid.uuid4()
        included_evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=None, evidence_id=excluded_evidence_id),
            _make_link(confidence_score=None, evidence_id=excluded_evidence_id),
            _make_link(confidence_score=0.6, evidence_id=included_evidence_id),
        ]

        assert rank_evidence_by_score(links) == [
            RankedEvidenceScore(evidence_id=included_evidence_id, score=0.6, support_count=1)
        ]


class TestEvidenceScoringPolicy:
    def test_default_policy_preserves_existing_mean_behavior(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy, aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.9, evidence_id=evidence_id),
        ]

        assert aggregate_confidence(links, policy=EvidenceScoringPolicy()) == pytest.approx(0.8)

    def test_negative_source_weight_is_rejected(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy

        with pytest.raises(ValueError, match="source_weights"):
            EvidenceScoringPolicy(source_weights={"ner": -1.0})

    def test_negative_support_bonus_is_rejected(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy

        with pytest.raises(ValueError, match="support_bonus_per_additional_link"):
            EvidenceScoringPolicy(support_bonus_per_additional_link=-0.1)

    def test_non_positive_max_score_is_rejected(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy

        with pytest.raises(ValueError, match="max_score"):
            EvidenceScoringPolicy(max_score=0.0)

    def test_source_kind_weights_change_aggregate_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy, aggregate_confidence

        evidence_id = uuid.uuid4()
        ner_link = _make_link(confidence_score=0.4, evidence_id=evidence_id)
        manual_link = _make_link(confidence_score=0.8, evidence_id=evidence_id)
        object.__setattr__(ner_link, "source_kind", "ner")
        object.__setattr__(manual_link, "source_kind", "manual")

        policy = EvidenceScoringPolicy(source_weights={"ner": 3.0, "manual": 1.0})

        assert aggregate_confidence([ner_link, manual_link], policy=policy) == pytest.approx(0.5)

    def test_support_bonus_boosts_final_score(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy, aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
            _make_link(confidence_score=0.7, evidence_id=evidence_id),
        ]

        policy = EvidenceScoringPolicy(support_bonus_per_additional_link=0.05)

        assert aggregate_confidence(links, policy=policy) == pytest.approx(0.8)

    def test_support_bonus_respects_max_score_cap(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy, aggregate_confidence

        evidence_id = uuid.uuid4()
        links = [
            _make_link(confidence_score=0.95, evidence_id=evidence_id),
            _make_link(confidence_score=0.95, evidence_id=evidence_id),
            _make_link(confidence_score=0.95, evidence_id=evidence_id),
        ]

        policy = EvidenceScoringPolicy(support_bonus_per_additional_link=0.1, max_score=1.0)

        assert aggregate_confidence(links, policy=policy) == pytest.approx(1.0)

    def test_ranking_with_policy_changes_order(self) -> None:
        from llamaindex_runtime.registry.evidence_scoring import EvidenceScoringPolicy, rank_evidence_by_score

        high_manual_evidence_id = uuid.uuid4()
        weighted_ner_evidence_id = uuid.uuid4()

        manual_link = _make_link(confidence_score=0.8, evidence_id=high_manual_evidence_id)
        ner_link_a = _make_link(confidence_score=0.5, evidence_id=weighted_ner_evidence_id)
        ner_link_b = _make_link(confidence_score=0.5, evidence_id=weighted_ner_evidence_id)
        object.__setattr__(manual_link, "source_kind", "manual")
        object.__setattr__(ner_link_a, "source_kind", "ner")
        object.__setattr__(ner_link_b, "source_kind", "ner")

        policy = EvidenceScoringPolicy(
            source_weights={"ner": 2.0, "manual": 1.0},
            support_bonus_per_additional_link=0.35,
        )

        ranked = rank_evidence_by_score([manual_link, ner_link_a, ner_link_b], policy=policy)
        assert ranked[0].evidence_id == weighted_ner_evidence_id
        assert ranked[1].evidence_id == high_manual_evidence_id
