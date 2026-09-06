"""Tests for llamaindex_runtime.entity.relation_review (Phase 17 Wave 5b)."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from llamaindex_runtime.entity.review_basket import (
    BasketItemKind,
    BasketItemStatus,
    EvidenceRef,
)
from llamaindex_runtime.entity.relation_review import (
    KeywordEvidenceReviewer,
    RelationBasket,
    RelationClaim,
    RelationReviewExit,
    RelationReviewItem,
    RelationReviewOutcome,
    RelationReviewResult,
    ReviewerEngine,
    make_relation_item_id,
    relation_evidence_summary,
    review_relation_claims,
)

_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "entity"
    / "relation_review.py"
)

_S1 = "11111111-1111-4111-8111-111111111111"
_S2 = "22222222-2222-4222-8222-222222222222"

_GOLDEN_ITEM_ID = "aa6dbb06-be8a-58d7-a0d2-57f547e72ec1"


def _ref(
    source: str = "doc-1",
    quote: str = "华为的总部在杭州。",
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        quote=quote,
        char_start=char_start,
        char_end=char_end,
    )


def _claim(
    *,
    subject: object = "华为",
    predicate: object = "总部位于",
    object: object = "杭州",
    subject_span_id: object = _S1,
    object_span_id: object = _S2,
    evidence: object = None,
) -> RelationClaim:
    if evidence is None:
        evidence = (_ref(),)
    return RelationClaim(
        subject=cast(str, subject),
        predicate=cast(str, predicate),
        object=cast(str, object),
        subject_span_id=cast(str, subject_span_id),
        object_span_id=cast(str, object_span_id),
        evidence=cast(tuple[EvidenceRef, ...], evidence),
    )


def _golden_claim() -> RelationClaim:
    return RelationClaim(
        subject="华为",
        predicate="总部位于",
        object="杭州",
        subject_span_id=_S1,
        object_span_id=_S2,
        evidence=(EvidenceRef(source="doc-1", quote="华为的总部在杭州。"),),
    )


def _review_item(
    *,
    claim: object = None,
    exit: object = RelationReviewExit.UNCERTAIN,
    reviewer_id: object = "keyword-evidence-v1",
    reason: object = "manual review required",
    status: object = BasketItemStatus.PENDING,
    adjudicated_by: object = None,
    kind: object = BasketItemKind.RELATION_CLAIM,
) -> RelationReviewItem:
    if claim is None:
        claim = _golden_claim()
    return RelationReviewItem(
        item_id=make_relation_item_id(cast(RelationClaim, claim)),
        claim=cast(RelationClaim, claim),
        exit=cast(RelationReviewExit, exit),
        reviewer_id=cast(str, reviewer_id),
        reason=cast(str, reason),
        status=cast(BasketItemStatus, status),
        adjudicated_by=(
            cast(str, adjudicated_by) if adjudicated_by is not None else None
        ),
        kind=cast(BasketItemKind, kind),
    )


class _ListKeyMapping(Mapping[object, object]):
    def __iter__(self) -> Iterator[object]:
        yield "source"
        yield [1, 2]

    def __len__(self) -> int:
        return 2

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)


class TestGoldenItemId:
    def test_golden_payload_hashes_to_pinned_id(self) -> None:
        assert make_relation_item_id(_golden_claim()) == _GOLDEN_ITEM_ID

    def test_golden_item_constructs(self) -> None:
        item = _review_item()
        assert item.item_id == _GOLDEN_ITEM_ID


class TestRelationClaimValidation:
    def test_minimal_ok(self) -> None:
        claim = _claim()
        assert claim.subject == "华为"
        assert claim.predicate == "总部位于"
        assert claim.object == "杭州"
        assert claim.subject_span_id == _S1
        assert claim.object_span_id == _S2
        assert len(claim.evidence) == 1
        assert claim.evidence[0].source == "doc-1"

    @pytest.mark.parametrize(
        "field",
        ["subject", "predicate", "object", "subject_span_id", "object_span_id"],
    )
    def test_blank_field_rejected(self, field: str) -> None:
        blank: dict[str, str] = {
            "subject": "",
            "predicate": " ",
            "object": "\t",
            "subject_span_id": "  ",
            "object_span_id": " \n ",
        }
        with pytest.raises(ValueError):
            if field == "subject":
                _claim(subject=blank[field])
            elif field == "predicate":
                _claim(predicate=blank[field])
            elif field == "object":
                _claim(object=blank[field])
            elif field == "subject_span_id":
                _claim(subject_span_id=blank[field])
            else:
                _claim(object_span_id=blank[field])

    @pytest.mark.parametrize(
        "field",
        ["subject", "predicate", "object", "subject_span_id", "object_span_id"],
    )
    def test_non_str_field_rejected(self, field: str) -> None:
        with pytest.raises(ValueError):
            if field == "subject":
                _claim(subject=42)
            elif field == "predicate":
                _claim(predicate=["总部位于"])
            elif field == "object":
                _claim(object=None)
            elif field == "subject_span_id":
                _claim(subject_span_id=True)
            else:
                _claim(object_span_id=7.5)

    def test_equal_span_ids_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(subject_span_id=_S1, object_span_id=_S1)

    def test_empty_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(evidence=())

    def test_non_tuple_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(evidence=[_ref()])

    def test_non_ref_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(evidence=(42,))

    def test_bool_span_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(subject_span_id=True, object_span_id=_S2)

    def test_list_span_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(subject_span_id=[_S1], object_span_id=_S2)

    def test_zero_width_subject_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(subject="\u200b")

    def test_zero_width_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _claim(object="\u200c")

    def test_repr_redacts_names(self) -> None:
        claim = _claim(subject="秘密切题", object="机密对象")
        text = repr(claim)
        assert "秘密切题" not in text
        assert "机密对象" not in text
        assert "<redacted:" in text
        assert "总部位于" in text

    def test_repr_shows_evidence_count(self) -> None:
        text = repr(_claim())
        assert "1 refs" in text


class TestRelationClaimRoundTrip:
    def test_round_trip(self) -> None:
        claim = _claim(
            subject=" 华为 ",
            predicate="总部位于",
            object="杭州",
            evidence=(_ref(source="doc-9", quote="引文内容"),),
        )
        restored = RelationClaim.from_dict(claim.to_dict())
        assert restored == claim

    def test_from_dict_missing_key(self) -> None:
        payload = _claim().to_dict()
        del payload["predicate"]
        with pytest.raises(ValueError):
            RelationClaim.from_dict(payload)

    def test_from_dict_unknown_key(self) -> None:
        payload = _claim().to_dict()
        payload["extra"] = 1
        with pytest.raises(ValueError):
            RelationClaim.from_dict(payload)

    def test_from_dict_non_str_key(self) -> None:
        payload = _claim().to_dict()
        mixed: dict[object, object] = {123: "x"}
        mixed.update(payload)
        with pytest.raises(ValueError):
            RelationClaim.from_dict(mixed)

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationClaim.from_dict(_ListKeyMapping())

    def test_from_dict_non_mapping(self) -> None:
        with pytest.raises(ValueError):
            RelationClaim.from_dict("not-a-mapping")

    def test_from_dict_bad_field_type(self) -> None:
        payload = _claim().to_dict()
        payload["subject"] = 7
        with pytest.raises(ValueError):
            RelationClaim.from_dict(payload)

    def test_from_dict_bad_evidence(self) -> None:
        payload = _claim().to_dict()
        payload["evidence"] = ["not-a-ref"]
        with pytest.raises(ValueError):
            RelationClaim.from_dict(payload)

    def test_from_dict_tampered_evidence_ref(self) -> None:
        payload = _claim().to_dict()
        evidence = payload["evidence"]
        assert isinstance(evidence, list)
        entry = evidence[0]
        assert isinstance(entry, dict)
        entry["source"] = 99
        with pytest.raises(ValueError):
            RelationClaim.from_dict(payload)


class TestRelationReviewResult:
    def test_minimal_ok(self) -> None:
        result = RelationReviewResult(RelationReviewExit.SUPPORTED, "r-1", "looks good")
        assert result.exit is RelationReviewExit.SUPPORTED
        assert result.reviewer_id == "r-1"
        assert result.reason == "looks good"

    def test_blank_reason_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult(RelationReviewExit.SUPPORTED, "r-1", "  ")

    def test_blank_reviewer_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult(RelationReviewExit.SUPPORTED, "", "reason")

    def test_raw_str_exit_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult(cast(RelationReviewExit, "supported"), "r-1", "reason")

    def test_round_trip(self) -> None:
        result = RelationReviewResult(RelationReviewExit.UNCERTAIN, "r-1", "partial")
        restored = RelationReviewResult.from_dict(result.to_dict())
        assert restored == result

    def test_from_dict_bad_exit(self) -> None:
        payload = {
            "exit": "bogus",
            "reviewer_id": "r-1",
            "reason": "reason",
        }
        with pytest.raises(ValueError):
            RelationReviewResult.from_dict(payload)

    def test_from_dict_missing_key(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult.from_dict({"exit": "supported", "reviewer_id": "r-1"})

    def test_from_dict_unknown_key(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult.from_dict(
                {"exit": "supported", "reviewer_id": "r-1", "reason": "x", "extra": 1}
            )

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewResult.from_dict(_ListKeyMapping())


class TestKeywordEvidenceReviewer:
    def test_supported_both_present(self) -> None:
        result = KeywordEvidenceReviewer().review_claim(_golden_claim())
        assert result.exit is RelationReviewExit.SUPPORTED
        assert result.reviewer_id == "keyword-evidence-v1"

    def test_unsupported_neither_present(self) -> None:
        claim = _claim(subject="苹果", object="深圳")
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.UNSUPPORTED
        assert result.reviewer_id == "keyword-evidence-v1"

    def test_uncertain_subject_only(self) -> None:
        claim = _claim(subject="华为", object="深圳")
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.UNCERTAIN
        assert result.reviewer_id == "keyword-evidence-v1"

    def test_uncertain_object_only(self) -> None:
        claim = _claim(subject="苹果", object="杭州")
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.UNCERTAIN

    def test_normalization_case_variant(self) -> None:
        claim = _claim(
            subject="HUAWEI",
            evidence=(_ref(quote="HUAWEI 的总部在杭州。"),),
        )
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.SUPPORTED

    def test_normalization_space_variant(self) -> None:
        claim = _claim(
            subject=" 华 为 ",
            evidence=(_ref(quote="华 为 的总部在杭州。"),),
        )
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.SUPPORTED

    def test_normalization_zero_width_variant(self) -> None:
        claim = _claim(subject="华\u200b为")
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.SUPPORTED

    def test_zero_width_quote_not_supported(self) -> None:
        claim = _claim(evidence=(_ref(quote="\u200b\u200b"),))
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.UNSUPPORTED

    def test_boundary_subject_equals_object(self) -> None:
        claim = _claim(subject="华为", object="华为")
        result = KeywordEvidenceReviewer().review_claim(claim)
        assert result.exit is RelationReviewExit.SUPPORTED

    def test_reviewer_id_property(self) -> None:
        engine = KeywordEvidenceReviewer()
        assert engine.reviewer_id == "keyword-evidence-v1"


class TestEngineFailureClosed:
    def test_engine_exception_no_message_leak(self) -> None:
        class Broken(KeywordEvidenceReviewer):
            def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
                raise RuntimeError("TOP SECRET SENSITIVE LEAK")

        outcome = review_relation_claims([_golden_claim()], Broken())
        assert len(outcome.pending) == 1
        item = outcome.pending[0]
        assert item.exit is RelationReviewExit.UNCERTAIN
        assert item.reviewer_id == "fail-closed"
        assert item.reason == "reviewer engine raised RuntimeError"
        assert "TOP SECRET" not in item.reason
        assert "SENSITIVE" not in item.reason
        assert "LEAK" not in item.reason

    def test_reviewer_id_mismatch_fail_closed(self) -> None:
        class Mismatched(KeywordEvidenceReviewer):
            @property
            def reviewer_id(self) -> str:
                return "other-reviewer"

            def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
                return RelationReviewResult(
                    RelationReviewExit.SUPPORTED,
                    "keyword-evidence-v1",
                    "stamped with a foreign reviewer id",
                )

        outcome = review_relation_claims([_golden_claim()], Mismatched())
        item = outcome.pending[0]
        assert item.reviewer_id == "fail-closed"
        assert item.reason == "reviewer result rejected"

    def test_non_result_return_fail_closed(self) -> None:
        class NotResult(KeywordEvidenceReviewer):
            def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
                return cast(RelationReviewResult, "not-a-result")

        outcome = review_relation_claims([_golden_claim()], NotResult())
        item = outcome.pending[0]
        assert item.reviewer_id == "fail-closed"
        assert item.reason == "reviewer result rejected"

    def test_raw_str_exit_engine_fail_closed(self) -> None:
        class RawExit(KeywordEvidenceReviewer):
            def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
                return RelationReviewResult(
                    cast(RelationReviewExit, "supported"),
                    "keyword-evidence-v1",
                    "ok",
                )

        outcome = review_relation_claims([_golden_claim()], RawExit())
        item = outcome.pending[0]
        assert item.reviewer_id == "fail-closed"
        assert item.reason == "reviewer engine raised ValueError"

    def test_fail_closed_item_is_pending_uncertain(self) -> None:
        outcome = review_relation_claims([_golden_claim()], _RaisingEngine("boom"))
        assert len(outcome.pending) == 1
        assert outcome.pending[0].status is BasketItemStatus.PENDING
        assert outcome.pending[0].exit is RelationReviewExit.UNCERTAIN

    def test_reviewer_id_property_raise_fail_closed(self) -> None:
        class ExplodingId(KeywordEvidenceReviewer):
            @property
            def reviewer_id(self) -> str:
                raise RuntimeError("id probe exploded")

        outcome = review_relation_claims([_golden_claim()], ExplodingId())
        assert len(outcome.pending) == 1
        item = outcome.pending[0]
        assert item.exit is RelationReviewExit.UNCERTAIN
        assert item.reviewer_id == "fail-closed"
        assert "RuntimeError" in item.reason
        assert "exploded" not in item.reason

    def test_plain_object_engine_rejected(self) -> None:
        with pytest.raises(ValueError):
            review_relation_claims([_golden_claim()], cast(ReviewerEngine, object()))


class _RaisingEngine:
    def __init__(self, message: str = "boom") -> None:
        self._message = message

    @property
    def reviewer_id(self) -> str:
        return "keyword-evidence-v1"

    def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
        raise ValueError(self._message)


class TestReviewRelationClaims:
    def test_empty_claims(self) -> None:
        outcome = review_relation_claims([], KeywordEvidenceReviewer())
        assert outcome.supported == ()
        assert outcome.rejected == ()
        assert outcome.basket.items == ()

    def test_claims_str_rejected(self) -> None:
        with pytest.raises(ValueError):
            review_relation_claims("abc", KeywordEvidenceReviewer())

    def test_claims_bytes_rejected(self) -> None:
        with pytest.raises(ValueError):
            review_relation_claims(b"abc", KeywordEvidenceReviewer())

    def test_claims_generator_rejected(self) -> None:
        def gen() -> Iterator[RelationClaim]:
            yield _golden_claim()

        with pytest.raises(ValueError):
            review_relation_claims(cast(Sequence, gen()), KeywordEvidenceReviewer())

    def test_non_claim_element_rejected(self) -> None:
        with pytest.raises(ValueError):
            review_relation_claims([42], KeywordEvidenceReviewer())

    def test_duplicate_claim_rejected(self) -> None:
        dup = _golden_claim()
        with pytest.raises(ValueError):
            review_relation_claims([dup, dup], KeywordEvidenceReviewer())

    def test_duplicate_via_equivalent_rejected(self) -> None:
        dup = _golden_claim()
        twin = _golden_claim()
        with pytest.raises(ValueError):
            review_relation_claims([dup, twin], KeywordEvidenceReviewer())

    def test_bad_engine_no_reviewer_id(self) -> None:
        class NoReview:
            pass

        with pytest.raises(ValueError):
            review_relation_claims([_golden_claim()], cast(ReviewerEngine, NoReview()))

    def test_bad_engine_blank_reviewer_id(self) -> None:
        class BlankId:
            reviewer_id = "  "
            review_claim = KeywordEvidenceReviewer().review_claim

        with pytest.raises(ValueError):
            review_relation_claims([_golden_claim()], cast(ReviewerEngine, BlankId()))

    def test_bad_engine_no_callable(self) -> None:
        class NoCall:
            reviewer_id = "some-id"
            review_claim = None

        with pytest.raises(ValueError):
            review_relation_claims([_golden_claim()], cast(ReviewerEngine, NoCall()))

    def test_supported_routed_to_bucket(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        assert len(outcome.supported) == 1
        assert outcome.supported[0].status is BasketItemStatus.ACCEPTED
        assert outcome.supported[0].adjudicated_by is None

    def test_unsupported_routed_to_bucket(self) -> None:
        claim = _claim(subject="苹果", object="深圳")
        outcome = review_relation_claims([claim], KeywordEvidenceReviewer())
        assert len(outcome.rejected) == 1
        assert outcome.rejected[0].status is BasketItemStatus.REJECTED
        assert outcome.rejected[0].adjudicated_by is None

    def test_uncertain_routed_to_pending(self) -> None:
        claim = _claim(subject="华为", object="深圳")
        outcome = review_relation_claims([claim], KeywordEvidenceReviewer())
        assert len(outcome.pending) == 1
        assert outcome.pending[0].status is BasketItemStatus.PENDING
        assert outcome.pending[0].adjudicated_by is None

    def test_ordering_preserved_per_bucket(self) -> None:
        c1 = _claim(subject="华为", object="杭州")  # SUPPORTED
        c2 = _claim(
            subject="苹果",
            object="深圳",
            subject_span_id="33333333-3333-4333-8333-333333333333",
            object_span_id="44444444-4444-4444-8444-444444444444",
        )  # UNSUPPORTED
        c3 = _claim(
            subject="华为",
            object="深圳",
            subject_span_id="55555555-5555-4555-8555-555555555555",
            object_span_id="66666666-6666-4666-8666-666666666666",
        )  # UNCERTAIN
        outcome = review_relation_claims([c1, c2, c3], KeywordEvidenceReviewer())
        assert [item.item_id for item in outcome.supported] == [
            make_relation_item_id(c1)
        ]
        assert [item.item_id for item in outcome.rejected] == [
            make_relation_item_id(c2)
        ]
        assert [item.item_id for item in outcome.pending] == [make_relation_item_id(c3)]

    def test_deterministic_across_runs(self) -> None:
        c1 = _claim(subject="华为", object="杭州")
        c2 = _claim(
            subject="苹果",
            object="深圳",
            subject_span_id="33333333-3333-4333-8333-333333333333",
            object_span_id="44444444-4444-4444-8444-444444444444",
        )
        first = review_relation_claims([c1, c2], KeywordEvidenceReviewer())
        second = review_relation_claims([c1, c2], KeywordEvidenceReviewer())
        assert first.to_dict() == second.to_dict()


class TestRelationReviewItem:
    def test_minimal_pending_ok(self) -> None:
        item = _review_item()
        assert item.item_id == _GOLDEN_ITEM_ID
        assert item.kind is BasketItemKind.RELATION_CLAIM
        assert item.status is BasketItemStatus.PENDING
        assert item.adjudicated_by is None

    def test_tampered_item_id_rejected(self) -> None:
        claim = _golden_claim()
        with pytest.raises(ValueError):
            RelationReviewItem(
                item_id="00000000-0000-4000-8000-000000000000",
                claim=claim,
                exit=RelationReviewExit.UNCERTAIN,
                reviewer_id="r-1",
                reason="reason",
            )

    def test_bad_kind_rejected(self) -> None:
        claim = _golden_claim()
        with pytest.raises(ValueError):
            RelationReviewItem(
                item_id=make_relation_item_id(claim),
                claim=claim,
                exit=RelationReviewExit.UNCERTAIN,
                reviewer_id="r-1",
                reason="reason",
                kind=BasketItemKind.MERGE_SUGGESTION,
            )

    def test_bad_exit_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(exit="uncertain")  # type: ignore[arg-type]

    def test_blank_reviewer_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(reviewer_id="  ")

    def test_blank_reason_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(reason="")

    def test_bad_status_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(status="pending")  # type: ignore[arg-type]

    def test_pending_with_adjudicator_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(adjudicated_by="human-1")

    def test_pending_with_supported_exit_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(exit=RelationReviewExit.SUPPORTED)

    def test_accepted_uncertain_no_adjudicator_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(
                exit=RelationReviewExit.UNCERTAIN,
                status=BasketItemStatus.ACCEPTED,
            )

    def test_rejected_uncertain_no_adjudicator_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(
                exit=RelationReviewExit.UNCERTAIN,
                status=BasketItemStatus.REJECTED,
            )

    def test_machine_supported_must_be_accepted(self) -> None:
        with pytest.raises(ValueError):
            _review_item(
                exit=RelationReviewExit.SUPPORTED,
                status=BasketItemStatus.REJECTED,
            )

    def test_machine_unsupported_must_be_rejected(self) -> None:
        with pytest.raises(ValueError):
            _review_item(
                exit=RelationReviewExit.UNSUPPORTED,
                status=BasketItemStatus.ACCEPTED,
            )

    def test_machine_supported_adjudicated_ok(self) -> None:
        item = _review_item(
            exit=RelationReviewExit.SUPPORTED,
            status=BasketItemStatus.ACCEPTED,
            adjudicated_by="human-1",
        )
        assert item.adjudicated_by == "human-1"

    def test_machine_unsupported_adjudicated_ok(self) -> None:
        item = _review_item(
            exit=RelationReviewExit.UNSUPPORTED,
            status=BasketItemStatus.REJECTED,
            adjudicated_by="human-1",
        )
        assert item.adjudicated_by == "human-1"

    def test_repr_redacts_claim_names(self) -> None:
        item = _review_item(claim=_claim(subject="绝密实体A", object="绝密实体B"))
        text = repr(item)
        assert "绝密实体A" not in text
        assert "绝密实体B" not in text
        assert "<redacted:" in text

    def test_repr_redacts_engine_reason(self) -> None:
        class LeakEngine(KeywordEvidenceReviewer):
            @property
            def reviewer_id(self) -> str:
                return "leak-engine-v1"

            def review_claim(self, claim: RelationClaim) -> RelationReviewResult:
                return RelationReviewResult(
                    RelationReviewExit.UNCERTAIN,
                    "leak-engine-v1",
                    "quote said: " + claim.evidence[0].quote,
                )

        outcome = review_relation_claims([_golden_claim()], LeakEngine())
        item = outcome.pending[0]
        assert "<redacted:" in repr(item)
        assert "华为的总部在杭州" not in repr(item)
        result = RelationReviewResult(
            RelationReviewExit.UNCERTAIN,
            "leak-engine-v1",
            "quote said: 华为的总部在杭州",
        )
        assert "<redacted:" in repr(result)
        assert "华为的总部在杭州" not in repr(result)

    def test_round_trip_pending(self) -> None:
        item = _review_item()
        restored = RelationReviewItem.from_dict(item.to_dict())
        assert restored == item

    def test_round_trip_adjudicated(self) -> None:
        item = _review_item(
            exit=RelationReviewExit.UNCERTAIN,
            status=BasketItemStatus.ACCEPTED,
            adjudicated_by="human-1",
        )
        restored = RelationReviewItem.from_dict(item.to_dict())
        assert restored == item

    def test_from_dict_missing_key(self) -> None:
        payload = _review_item().to_dict()
        del payload["claim"]
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)

    def test_from_dict_unknown_key(self) -> None:
        payload = _review_item().to_dict()
        payload["extra"] = 1
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(_ListKeyMapping())

    def test_from_dict_non_mapping(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict("nope")

    def test_from_dict_bad_exit_value(self) -> None:
        payload = _review_item().to_dict()
        payload["exit"] = "bogus"
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)

    def test_from_dict_bad_kind_value(self) -> None:
        payload = _review_item().to_dict()
        payload["kind"] = "merge_suggestion"
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)

    def test_from_dict_bad_status_value(self) -> None:
        payload = _review_item().to_dict()
        payload["status"] = "bogus"
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)

    def test_from_dict_null_adjudicator_ok(self) -> None:
        payload = _review_item().to_dict()
        payload["adjudicated_by"] = None
        restored = RelationReviewItem.from_dict(payload)
        assert restored.adjudicated_by is None

    def test_from_dict_nested_claim_tamper(self) -> None:
        payload = _review_item().to_dict()
        claim = payload["claim"]
        assert isinstance(claim, dict)
        claim["subject"] = 9
        with pytest.raises(ValueError):
            RelationReviewItem.from_dict(payload)


class TestRelationBasket:
    def test_empty_default(self) -> None:
        basket = RelationBasket()
        assert basket.items == ()
        assert basket.pending_count == 0
        assert basket.accepted_count == 0
        assert basket.rejected_count == 0

    def test_count_properties(self) -> None:
        pending = _review_item()
        accepted = _review_item(
            claim=_claim(
                subject_span_id="33333333-3333-4333-8333-333333333333",
                object_span_id="44444444-4444-4444-8444-444444444444",
            ),
            exit=RelationReviewExit.UNCERTAIN,
            status=BasketItemStatus.ACCEPTED,
            adjudicated_by="h-1",
        )
        basket = RelationBasket(items=(pending, accepted))
        assert basket.pending_count == 1
        assert basket.accepted_count == 1
        assert basket.rejected_count == 0

    def test_non_item_element_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket(
                items=cast("tuple[RelationReviewItem, ...]", (_review_item(), 42))
            )

    def test_duplicate_item_id_rejected(self) -> None:
        item = _review_item()
        twin = _review_item(claim=item.claim)
        with pytest.raises(ValueError):
            RelationBasket(items=(item, twin))

    def test_from_dict_duplicate_items_rejected(self) -> None:
        payload = _review_item().to_dict()
        with pytest.raises(ValueError):
            RelationBasket.from_dict({"items": [payload, payload]})

    def test_accept_flow(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        updated = basket.adjudicate(
            item.item_id, BasketItemStatus.ACCEPTED, adjudicated_by="human-1"
        )
        assert updated.pending_count == 0
        assert updated.accepted_count == 1
        assert updated.items[0].adjudicated_by == "human-1"

    def test_reject_flow(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        updated = basket.adjudicate(
            item.item_id, BasketItemStatus.REJECTED, adjudicated_by="human-1"
        )
        assert updated.rejected_count == 1
        assert updated.items[0].adjudicated_by == "human-1"

    def test_immutability_of_original(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        updated = basket.adjudicate(
            item.item_id, BasketItemStatus.ACCEPTED, adjudicated_by="human-1"
        )
        assert basket.items[0].status is BasketItemStatus.PENDING
        assert updated.items[0].status is BasketItemStatus.ACCEPTED

    def test_unknown_id_rejected(self) -> None:
        basket = RelationBasket(items=(_review_item(),))
        with pytest.raises(ValueError):
            basket.adjudicate(
                "unknown-id", BasketItemStatus.ACCEPTED, adjudicated_by="h-1"
            )

    def test_blank_item_id_rejected(self) -> None:
        basket = RelationBasket(items=(_review_item(),))
        with pytest.raises(ValueError):
            basket.adjudicate(" ", BasketItemStatus.ACCEPTED, adjudicated_by="x")

    def test_duplicate_adjudication_rejected(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        updated = basket.adjudicate(
            item.item_id, BasketItemStatus.ACCEPTED, adjudicated_by="h-1"
        )
        with pytest.raises(ValueError):
            updated.adjudicate(
                item.item_id, BasketItemStatus.REJECTED, adjudicated_by="h-1"
            )

    def test_pending_verdict_rejected(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        with pytest.raises(ValueError):
            basket.adjudicate(
                item.item_id, BasketItemStatus.PENDING, adjudicated_by="h-1"
            )

    def test_empty_adjudicated_by_rejected(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        with pytest.raises(ValueError):
            basket.adjudicate(
                item.item_id,
                BasketItemStatus.ACCEPTED,
                adjudicated_by=" ",
            )

    def test_non_str_verdict_rejected(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        with pytest.raises(ValueError):
            basket.adjudicate(
                item.item_id,
                cast(BasketItemStatus, "accepted"),
                adjudicated_by="h-1",
            )

    def test_to_dict_round_trip(self) -> None:
        item = _review_item()
        basket = RelationBasket(items=(item,))
        data = basket.to_dict()
        assert set(data) == {"items"}
        restored = RelationBasket.from_dict(data)
        assert restored == basket

    def test_from_dict_missing_items(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket.from_dict({})

    def test_from_dict_unknown_key(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket.from_dict({"items": [], "extra": 1})

    def test_from_dict_bad_items_type(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket.from_dict({"items": "not-a-list"})

    def test_from_dict_non_mapping_element(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket.from_dict({"items": [42]})

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            RelationBasket.from_dict(_ListKeyMapping())


class TestRelationReviewOutcome:
    def test_counts(self) -> None:
        supported = _review_item(
            exit=RelationReviewExit.SUPPORTED,
            status=BasketItemStatus.ACCEPTED,
        )
        rejected = _review_item(
            exit=RelationReviewExit.UNSUPPORTED,
            status=BasketItemStatus.REJECTED,
        )
        pending = _review_item()
        outcome = RelationReviewOutcome(
            supported=(supported,),
            rejected=(rejected,),
            basket=RelationBasket(items=(pending,)),
        )
        assert outcome.supported_count == 1
        assert outcome.rejected_count == 1
        assert outcome.pending_count == 1

    def test_to_dict_shape(self) -> None:
        supported = _review_item(
            exit=RelationReviewExit.SUPPORTED,
            status=BasketItemStatus.ACCEPTED,
        )
        outcome = RelationReviewOutcome(
            supported=(supported,),
            rejected=(),
            basket=RelationBasket(),
        )
        data = outcome.to_dict()
        assert set(data) == {"supported", "rejected", "basket"}

    def test_supported_must_be_tuple(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewOutcome(
                supported=cast("tuple[RelationReviewItem, ...]", [_review_item()]),
                rejected=(),
                basket=RelationBasket(),
            )

    def test_rejected_must_be_tuple(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewOutcome(
                supported=(),
                rejected=cast("tuple[RelationReviewItem, ...]", [_review_item()]),
                basket=RelationBasket(),
            )

    def test_basket_must_be_relation_basket(self) -> None:
        with pytest.raises(ValueError):
            RelationReviewOutcome(
                supported=(),
                rejected=(),
                basket=cast(RelationBasket, {"items": ()}),
            )

    def test_pending_excludes_adjudicated(self) -> None:
        item = _review_item()
        flipped = RelationBasket(items=(item,)).adjudicate(
            item.item_id, BasketItemStatus.ACCEPTED, adjudicated_by="h-1"
        )
        outcome = RelationReviewOutcome(supported=(), rejected=(), basket=flipped)
        assert outcome.pending == ()
        assert outcome.pending_count == 0
        assert outcome.pending_count == len(outcome.pending)


class TestEvidenceSummary:
    def test_valid_single_line_json(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        text = relation_evidence_summary(outcome)
        parsed = json.loads(text)
        assert isinstance(parsed, dict)

    def test_keys_exactly(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        parsed = json.loads(relation_evidence_summary(outcome))
        assert set(parsed) == {
            "items",
            "pending_count",
            "rejected_count",
            "supported_count",
        }

    def test_item_keys_exactly(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        parsed = json.loads(relation_evidence_summary(outcome))
        item = parsed["items"][0]
        assert set(item) == {"item_id", "exit", "reviewer_id", "status"}

    def test_no_free_text_anywhere(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        text = relation_evidence_summary(outcome)
        assert "总部位于" not in text
        assert "华为" not in text
        assert "杭州" not in text
        assert "的总部在杭州" not in text
        assert "doc-1" not in text

    def test_deterministic(self) -> None:
        outcome = review_relation_claims([_golden_claim()], KeywordEvidenceReviewer())
        first = relation_evidence_summary(outcome)
        second = relation_evidence_summary(outcome)
        assert first == second

    def test_items_sorted_by_item_id(self) -> None:
        c_late = _claim(subject="华为", object="杭州")
        c_early = _claim(
            subject="苹果",
            object="深圳",
            subject_span_id="33333333-3333-4333-8333-333333333333",
            object_span_id="44444444-4444-4444-8444-444444444444",
        )
        outcome = review_relation_claims([c_late, c_early], KeywordEvidenceReviewer())
        ids = [
            entry["item_id"]
            for entry in json.loads(relation_evidence_summary(outcome))["items"]
        ]
        assert ids == sorted(ids)
        assert set(ids) == {
            make_relation_item_id(c_late),
            make_relation_item_id(c_early),
        }


class TestPurity:
    def test_module_imports_whitelisted(self) -> None:
        assert _SOURCE.exists()
        source = _SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {
            "__future__",
            "collections.abc",
            "dataclasses",
            "enum",
            "json",
            "uuid",
            "typing",
            "llamaindex_runtime.entity.contracts",
            "llamaindex_runtime.entity.identity",
            "llamaindex_runtime.entity.normalization",
            "llamaindex_runtime.entity.review_basket",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in allowed
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0
                assert node.module in allowed
        assert "__import__" not in source
        assert "importlib" not in source
        assert "eval(" not in source
        assert "exec(" not in source

    def test_no_io_or_clock_calls(self) -> None:
        source = _SOURCE.read_text(encoding="utf-8")
        for token in ("open(", "datetime", "time.time", "requests", "socket"):
            assert token not in source
