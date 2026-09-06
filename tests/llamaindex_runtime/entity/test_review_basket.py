"""Tests for llamaindex_runtime.entity.review_basket (Phase 17 Wave 5a)."""

from __future__ import annotations

import ast
import json
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from llamaindex_runtime.entity import review_basket as review_basket_module
from llamaindex_runtime.entity.contracts import MentionCandidate
from llamaindex_runtime.entity.fuzzy_recall import (
    DEFAULT_SUGGESTION_THRESHOLD,
    FuzzySuggestion,
    SuggestionReason,
)
from llamaindex_runtime.entity.identity import (
    ENTITY_IDENTITY_NAMESPACE,
    EntityIdentity,
    make_identity_id,
    plan_merge,
)
from llamaindex_runtime.entity.normalization import (
    USCC_CHARSET,
    normalize_mention_text,
)
from llamaindex_runtime.entity.review_basket import (
    BasketItem,
    BasketItemKind,
    BasketItemStatus,
    EvidenceRef,
    ReviewBasket,
    TriageExit,
    TriageVerdict,
    basket_evidence_summary,
    build_review_basket,
    make_item_id,
    triage_mention,
)

_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "entity"
    / "review_basket.py"
)

_S1 = "11111111-1111-4111-8111-111111111111"
_S2 = "22222222-2222-4222-8222-222222222222"
_S3 = "33333333-3333-4333-8333-333333333333"

_BASE17_A = "91350100M000100YX"
_BASE17_B = "92450100M000100AB"


def _construct(base17: str) -> str:
    charset = USCC_CHARSET
    total = 0
    for index in range(17):
        total = (total + charset.index(base17[index]) * pow(3, index, 31)) % 31
    check = 31 - total
    if check == 31:
        check = 0
    return base17 + charset[check]


_USCC_A = _construct(_BASE17_A)
_USCC_B = _construct(_BASE17_B)


def _candidate(
    normalized_text: str,
    entity_type: str,
    span_id: str,
    *,
    char_start: int = 0,
    char_end: int | None = None,
    source: str = "rule",
) -> MentionCandidate:
    end = len(normalized_text) if char_end is None else char_end
    mention_text = normalized_text[char_start:end]
    return MentionCandidate(
        input_id=span_id,
        input_kind="corpus_span",
        input_revision="rev-1",
        normalized_text=normalized_text,
        span_id=span_id,
        segment_id=None,
        char_start=char_start,
        char_end=end,
        mention_text=mention_text,
        raw_label=mention_text,
        canonical_label=mention_text,
        entity_type=entity_type,
        confidence=None,
        confidence_kind="unavailable",
        source=source,
        extractor_id="w5a-basket-fixture",
        extractor_version="1.0.0",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        schema_version="1.0.0",
        normalization_version="1.0.0",
        segmentation_version="1.0.0",
        label_map_digest="0" * 64,
        runtime_compatibility_id=None,
        document_id="00000000-0000-4000-8000-000000000001",
        version_id="00000000-0000-4000-8000-000000000002",
        document_revision="rev-1",
        projection={"sidecar": "fixture"},
    )


def _query_candidate(mention_text: str, entity_type: str) -> MentionCandidate:
    return MentionCandidate(
        input_id="44444444-4444-4444-8444-444444444444",
        input_kind="query_text",
        input_revision="rev-q",
        normalized_text=mention_text,
        span_id=None,
        segment_id=None,
        char_start=0,
        char_end=len(mention_text),
        mention_text=mention_text,
        raw_label=mention_text,
        canonical_label=mention_text,
        entity_type=entity_type,
        confidence=None,
        confidence_kind="unavailable",
        source="rule",
        extractor_id="w5a-basket-fixture",
        extractor_version="1.0.0",
        model_id=None,
        model_revision=None,
        artifact_digest=None,
        schema_version="1.0.0",
        normalization_version="1.0.0",
        segmentation_version="1.0.0",
        label_map_digest="0" * 64,
        runtime_compatibility_id=None,
    )


def _identity(name: str, entity_type: str = "Organization") -> EntityIdentity:
    normalized = normalize_mention_text(name)
    return EntityIdentity(
        identity_id=make_identity_id(normalized, entity_type),
        normalized_name=normalized,
        entity_type=entity_type,
        member_span_ids=(_S1,),
    )


def _ratio(value: float) -> Callable[[str, str], float]:
    def _ratio_fn(left: str, right: str) -> float:
        return value

    return _ratio_fn


def _make_item(
    *,
    item_id: str | None = None,
    span_id: str = _S1,
    target: str = "t-id",
    candidate: str = "c-id",
    name: str = "ghost",
    score: float = 0.9,
    decision_id: str = "d-id",
    evidence: tuple[EvidenceRef, ...] | None = None,
    status: BasketItemStatus = BasketItemStatus.PENDING,
    adjudicated_by: str | None = None,
    kind: BasketItemKind = BasketItemKind.MERGE_SUGGESTION,
) -> BasketItem:
    if item_id is None:
        item_id = make_item_id(span_id, target, candidate)
    if evidence is None:
        evidence = (EvidenceRef(source="rule", quote="q"),)
    return BasketItem(
        item_id=item_id,
        span_id=span_id,
        target_identity_id=target,
        candidate_identity_id=candidate,
        candidate_normalized_name=name,
        score=score,
        reason=SuggestionReason.NAME_SIMILARITY,
        decision_id=decision_id,
        evidence=evidence,
        kind=kind,
        status=status,
        adjudicated_by=adjudicated_by,
    )


class _ListKeyMapping(Mapping[object, object]):
    def __iter__(self) -> Iterator[object]:
        yield "source"
        yield [1, 2]

    def __len__(self) -> int:
        return 2

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)


class TestMakeItemId:
    def test_deterministic(self) -> None:
        assert make_item_id(_S1, "t", "c") == make_item_id(_S1, "t", "c")

    def test_differs_by_span(self) -> None:
        assert make_item_id(_S1, "t", "c") != make_item_id(_S2, "t", "c")

    def test_differs_by_target(self) -> None:
        assert make_item_id(_S1, "t1", "c") != make_item_id(_S1, "t2", "c")

    def test_differs_by_candidate(self) -> None:
        assert make_item_id(_S1, "t", "c1") != make_item_id(_S1, "t", "c2")

    def test_algorithm_pinned(self) -> None:
        expected = str(
            uuid.uuid5(
                ENTITY_IDENTITY_NAMESPACE,
                json.dumps(
                    ["review-item", _S1, "t", "c"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        )
        assert make_item_id(_S1, "t", "c") == expected

    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_rejects_empty_component(self, position: int) -> None:
        args = [_S1, "t", "c"]
        args[position] = ""
        with pytest.raises(ValueError):
            make_item_id(*args)


class TestEvidenceRef:
    def test_minimal_ok(self) -> None:
        ref = EvidenceRef(source="rule", quote="q")
        assert ref.char_start is None and ref.char_end is None

    def test_full_offsets_ok(self) -> None:
        ref = EvidenceRef(source="doc", quote="q", char_start=0, char_end=1)
        assert ref.char_start == 0 and ref.char_end == 1

    def test_equal_offsets_ok(self) -> None:
        EvidenceRef(source="doc", quote="q", char_start=3, char_end=3)

    def test_round_trip(self) -> None:
        ref = EvidenceRef(source="doc", quote="q", char_start=1, char_end=2)
        assert EvidenceRef.from_dict(ref.to_dict()) == ref

    def test_start_gt_end_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_start=5, char_end=4)

    def test_single_offset_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_start=0)
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_end=4)

    def test_bool_offset_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_start=True, char_end=2)
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_start=0, char_end=False)

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="q", char_start=-1, char_end=2)

    def test_empty_fields_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source="  ", quote="q")
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote="")

    def test_non_str_fields_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef(source=cast(str, 123), quote="q")
        with pytest.raises(ValueError):
            EvidenceRef(source="d", quote=cast(str, 123))

    @pytest.mark.parametrize("raw", ["x", 42, None, ["source"]])
    def test_from_dict_non_mapping_rejected(self, raw: object) -> None:
        with pytest.raises(ValueError):
            EvidenceRef.from_dict(raw)

    def test_from_dict_missing_key(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef.from_dict({"source": "d", "quote": "q"})

    def test_from_dict_unknown_key(self) -> None:
        payload = EvidenceRef(source="d", quote="q").to_dict()
        payload["extra"] = 1
        with pytest.raises(ValueError):
            EvidenceRef.from_dict(payload)

    def test_from_dict_non_str_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef.from_dict(
                {
                    123: "x",
                    "source": "d",
                    "quote": "q",
                    "char_start": None,
                    "char_end": None,
                }
            )

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvidenceRef.from_dict(_ListKeyMapping())


class TestTriageVerdict:
    def test_auto_with_suggestions_rejected(self) -> None:
        stale = FuzzySuggestion(
            target_identity_id="t",
            candidate_identity_id="c",
            candidate_normalized_name="ghost",
            score=0.5,
            reason=SuggestionReason.NAME_SIMILARITY,
        )
        with pytest.raises(ValueError):
            TriageVerdict(
                span_id=_S1,
                normalized_name="x",
                entity_type="Organization",
                exit=TriageExit.AUTO,
                matched_identity_id="m",
                suggestions=(stale,),
            )

    def test_review_without_suggestions_rejected(self) -> None:
        with pytest.raises(ValueError):
            TriageVerdict(
                span_id=_S1,
                normalized_name="x",
                entity_type="Organization",
                exit=TriageExit.REVIEW,
            )

    def test_new_with_matched_rejected(self) -> None:
        with pytest.raises(ValueError):
            TriageVerdict(
                span_id=_S1,
                normalized_name="x",
                entity_type="Organization",
                exit=TriageExit.NEW,
                matched_identity_id="m",
            )

    def test_non_enum_exit_rejected(self) -> None:
        with pytest.raises(ValueError):
            TriageVerdict(
                span_id=_S1,
                normalized_name="x",
                entity_type="Organization",
                exit=cast(TriageExit, "auto"),
            )


class TestTriageMention:
    def test_auto_exact_match(self) -> None:
        verdict = triage_mention(
            _candidate("华为", "Organization", _S1), [_identity("华为")]
        )
        assert verdict.exit is TriageExit.AUTO
        assert verdict.matched_identity_id == make_identity_id("华为", "Organization")
        assert verdict.suggestions == ()

    def test_auto_after_normalization(self) -> None:
        verdict = triage_mention(
            _candidate("ＨＵＡＷＥＩ", "Organization", _S1), [_identity("huawei")]
        )
        assert verdict.exit is TriageExit.AUTO

    def test_auto_requires_same_type(self) -> None:
        verdict = triage_mention(_candidate("华为", "Person", _S1), [_identity("华为")])
        assert verdict.exit is TriageExit.NEW
        assert verdict.matched_identity_id is None

    def test_new_when_no_match_and_low_ratio(self) -> None:
        verdict = triage_mention(
            _candidate("zhangsan", "Organization", _S1),
            [_identity("wangxiaoming1")],
        )
        assert verdict.exit is TriageExit.NEW
        assert verdict.suggestions == ()

    def test_review_with_real_difflib(self) -> None:
        universe = [_identity("wangxiaoming1")]
        verdict = triage_mention(
            _candidate("wangxiaoming", "Organization", _S2), universe
        )
        assert verdict.exit is TriageExit.REVIEW
        assert len(verdict.suggestions) == 1
        suggestion = verdict.suggestions[0]
        target = EntityIdentity(
            identity_id=make_identity_id("wangxiaoming", "Organization"),
            normalized_name="wangxiaoming",
            entity_type="Organization",
            member_span_ids=(_S2,),
        )
        expected = plan_merge(target, universe[0])
        fresh = plan_merge(target, universe[0])
        assert fresh.decision_id == expected.decision_id
        assert suggestion.target_identity_id == target.identity_id

    def test_review_via_ratio_seam(self) -> None:
        verdict = triage_mention(
            _candidate("alpha corp", "Organization", _S1),
            [_identity("alpha inc")],
            ratio_fn=_ratio(0.95),
        )
        assert verdict.exit is TriageExit.REVIEW

    def test_threshold_boundary_is_inclusive(self) -> None:
        verdict = triage_mention(
            _candidate("alpha corp", "Organization", _S1),
            [_identity("alpha inc")],
            ratio_fn=_ratio(DEFAULT_SUGGESTION_THRESHOLD),
        )
        assert verdict.exit is TriageExit.REVIEW

    def test_below_threshold_is_new(self) -> None:
        verdict = triage_mention(
            _candidate("alpha corp", "Organization", _S1),
            [_identity("alpha inc")],
            ratio_fn=_ratio(0.5),
        )
        assert verdict.exit is TriageExit.NEW

    def test_uscc_conflict_pair_never_reviewed(self) -> None:
        mention = _candidate("acme co " + _USCC_A, "Organization", _S1)
        universe = [_identity("acme other " + _USCC_B)]
        verdict = triage_mention(mention, universe, ratio_fn=_ratio(1.0))
        assert verdict.exit is TriageExit.NEW

    def test_same_uscc_merged_pair_skipped(self) -> None:
        mention = _candidate("acme " + _USCC_A, "Organization", _S1)
        universe = [_identity("acme ltd " + _USCC_A)]
        verdict = triage_mention(mention, universe, ratio_fn=_ratio(1.0))
        assert verdict.exit is TriageExit.NEW

    def test_cross_type_exact_name_not_auto(self) -> None:
        verdict = triage_mention(
            _candidate("华为", "Person", _S1), [_identity("华为", "Organization")]
        )
        assert verdict.exit is TriageExit.NEW

    def test_stale_merged_suggestion_dropped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mention = _candidate("acme " + _USCC_A, "Organization", _S1)
        universe = [_identity("acme ltd " + _USCC_A)]

        def _fake(
            target: EntityIdentity,
            candidates: Sequence[EntityIdentity],
            *,
            threshold: float,
            ratio_fn: Callable[[str, str], float] | None = None,
        ) -> tuple[FuzzySuggestion, ...]:
            return (
                FuzzySuggestion(
                    target_identity_id=target.identity_id,
                    candidate_identity_id=candidates[0].identity_id,
                    candidate_normalized_name=candidates[0].normalized_name,
                    score=0.99,
                    reason=SuggestionReason.NAME_SIMILARITY,
                ),
            )

        monkeypatch.setattr(review_basket_module, "suggest_merges", _fake)
        verdict = triage_mention(mention, universe, ratio_fn=_ratio(1.0))
        assert verdict.exit is TriageExit.NEW

    def test_suggestion_with_unknown_candidate_dropped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mention = _candidate("alpha corp", "Organization", _S1)

        def _fake(
            target: EntityIdentity,
            candidates: Sequence[EntityIdentity],
            *,
            threshold: float,
            ratio_fn: Callable[[str, str], float] | None = None,
        ) -> tuple[FuzzySuggestion, ...]:
            return (
                FuzzySuggestion(
                    target_identity_id=target.identity_id,
                    candidate_identity_id="no-such-id",
                    candidate_normalized_name="ghost",
                    score=0.99,
                    reason=SuggestionReason.NAME_SIMILARITY,
                ),
            )

        monkeypatch.setattr(review_basket_module, "suggest_merges", _fake)
        verdict = triage_mention(
            mention, [_identity("alpha inc")], ratio_fn=_ratio(1.0)
        )
        assert verdict.exit is TriageExit.NEW

    def test_query_candidate_rejected(self) -> None:
        with pytest.raises(ValueError):
            triage_mention(_query_candidate("华为", "Organization"), [])

    def test_non_canonical_entity_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            triage_mention(_candidate("华为", "COMPANY", _S1), [_identity("华为")])

    def test_duplicate_identity_id_rejected(self) -> None:
        ident = _identity("华为")
        with pytest.raises(ValueError):
            triage_mention(_candidate("华为", "Organization", _S1), [ident, ident])

    def test_non_identity_element_rejected(self) -> None:
        with pytest.raises(ValueError):
            triage_mention(
                _candidate("华为", "Organization", _S1),
                [_identity("华为"), cast(EntityIdentity, "not-an-identity")],
            )

    def test_non_mention_rejected(self) -> None:
        with pytest.raises(ValueError):
            triage_mention(cast(MentionCandidate, "华为"), [])

    def test_bool_threshold_propagates_validation(self) -> None:
        with pytest.raises(ValueError):
            triage_mention(
                _candidate("alpha", "Organization", _S1),
                [_identity("alpha inc")],
                threshold=True,
            )


class TestBuildReviewBasket:
    def test_empty_inputs(self) -> None:
        basket = build_review_basket([], [])
        assert basket.items == ()
        assert basket.pending_count == 0

    def test_mixed_exits_yield_only_review_items(self) -> None:
        mentions = [
            _candidate("华为", "Organization", _S1),
            _candidate("wangxiaoming", "Organization", _S2),
            _candidate("zhangsan", "Organization", _S3),
        ]
        universe = [_identity("华为"), _identity("wangxiaoming1")]
        basket = build_review_basket(mentions, universe)
        assert len(basket.items) == 1
        assert basket.items[0].span_id == _S2

    def test_span_sorted_deterministic_order(self) -> None:
        mentions = [
            _candidate("wangxiaoming", "Organization", _S2),
            _candidate("wangxiaoming", "Organization", _S1),
        ]
        universe = [_identity("wangxiaoming1"), _identity("wangxiaoming2")]
        basket = build_review_basket(mentions, universe)
        assert len(basket.items) == 4
        assert basket.items[0].span_id == _S1
        assert basket.items[2].span_id == _S2
        again = build_review_basket(mentions, universe)
        assert basket.to_dict() == again.to_dict()

    def test_duplicate_span_rejected(self) -> None:
        mentions = [
            _candidate("alpha", "Organization", _S1),
            _candidate("beta", "Organization", _S1),
        ]
        with pytest.raises(ValueError):
            build_review_basket(mentions, [])

    def test_str_input_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_review_basket(cast(Sequence[MentionCandidate], "nope"), [])
        with pytest.raises(ValueError):
            build_review_basket(cast(Sequence[MentionCandidate], b"nope"), [])

    def test_non_candidate_element_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_review_basket(cast(Sequence[MentionCandidate], [42]), [])

    def test_query_candidate_in_build_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_review_basket([_query_candidate("华为", "Organization")], [])

    def test_item_fields_match_plan_merge_and_mention(self) -> None:
        mention = _candidate("wangxiaoming", "Organization", _S2)
        universe = [_identity("wangxiaoming1")]
        basket = build_review_basket([mention], universe)
        item = basket.items[0]
        target = EntityIdentity(
            identity_id=make_identity_id("wangxiaoming", "Organization"),
            normalized_name="wangxiaoming",
            entity_type="Organization",
            member_span_ids=(_S2,),
        )
        expected = plan_merge(target, universe[0])
        assert item.decision_id == expected.decision_id
        assert item.target_identity_id == target.identity_id
        assert item.candidate_identity_id == universe[0].identity_id
        assert item.candidate_normalized_name == "wangxiaoming1"
        assert 0.0 < item.score <= 1.0
        assert item.reason is SuggestionReason.NAME_SIMILARITY
        assert item.kind is BasketItemKind.MERGE_SUGGESTION
        assert item.status is BasketItemStatus.PENDING
        assert item.adjudicated_by is None
        assert item.evidence == (
            EvidenceRef(
                source="rule",
                quote="wangxiaoming",
                char_start=0,
                char_end=12,
            ),
        )

    def test_offsets_come_from_mention_slice(self) -> None:
        mention = _candidate(
            "xx wangxiaoming yy",
            "Organization",
            _S2,
            char_start=3,
            char_end=15,
        )
        basket = build_review_basket([mention], [_identity("wangxiaoming1")])
        ref = basket.items[0].evidence[0]
        assert ref.char_start == 3
        assert ref.char_end == 15
        assert ref.quote == "wangxiaoming"

    def test_item_display_name_uses_real_candidate_identity(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mention = _candidate("alpha corp", "Organization", _S1)
        universe = [_identity("alpha inc")]

        def _fake(
            target: EntityIdentity,
            candidates: Sequence[EntityIdentity],
            *,
            threshold: float,
            ratio_fn: Callable[[str, str], float] | None = None,
        ) -> tuple[FuzzySuggestion, ...]:
            return (
                FuzzySuggestion(
                    target_identity_id=target.identity_id,
                    candidate_identity_id=candidates[0].identity_id,
                    candidate_normalized_name="forged-name-ghost",
                    score=0.99,
                    reason=SuggestionReason.NAME_SIMILARITY,
                ),
            )

        monkeypatch.setattr(review_basket_module, "suggest_merges", _fake)
        basket = build_review_basket([mention], universe, ratio_fn=_ratio(1.0))
        assert len(basket.items) == 1
        assert basket.items[0].candidate_normalized_name == "alpha inc"
        assert basket.items[0].candidate_normalized_name != "forged-name-ghost"

    @pytest.mark.parametrize("bad_identity", ["x", 42])
    def test_empty_mentions_still_validate_identities(
        self, bad_identity: object
    ) -> None:
        with pytest.raises(ValueError):
            build_review_basket([], cast(Sequence[EntityIdentity], [bad_identity]))

    @pytest.mark.parametrize("bad_threshold", [True, float("nan")])
    def test_empty_mentions_still_validate_threshold(
        self, bad_threshold: object
    ) -> None:
        with pytest.raises(ValueError):
            build_review_basket([], [], threshold=cast(float, bad_threshold))


class TestAdjudicate:
    def _basket(self) -> ReviewBasket:
        return build_review_basket(
            [_candidate("wangxiaoming", "Organization", _S2)],
            [_identity("wangxiaoming1")],
        )

    def test_accept_updates_item(self) -> None:
        basket = self._basket()
        item_id = basket.items[0].item_id
        updated = basket.adjudicate(
            item_id, BasketItemStatus.ACCEPTED, adjudicated_by="reviewer"
        )
        assert updated.items[0].status is BasketItemStatus.ACCEPTED
        assert updated.items[0].adjudicated_by == "reviewer"
        assert updated.accepted_count == 1
        assert updated.pending_count == 0
        assert basket.items[0].status is BasketItemStatus.PENDING

    def test_reject_updates_item(self) -> None:
        basket = self._basket()
        updated = basket.adjudicate(
            basket.items[0].item_id,
            BasketItemStatus.REJECTED,
            adjudicated_by="reviewer",
        )
        assert updated.items[0].status is BasketItemStatus.REJECTED
        assert updated.rejected_count == 1

    def test_pending_verdict_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._basket().adjudicate(
                "x", BasketItemStatus.PENDING, adjudicated_by="reviewer"
            )

    def test_plain_str_verdict_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._basket().adjudicate(
                self._basket().items[0].item_id,
                cast(BasketItemStatus, "accepted"),
                adjudicated_by="reviewer",
            )

    def test_unknown_item_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._basket().adjudicate(
                "unknown", BasketItemStatus.ACCEPTED, adjudicated_by="reviewer"
            )

    def test_double_adjudication_rejected(self) -> None:
        basket = self._basket()
        updated = basket.adjudicate(
            basket.items[0].item_id,
            BasketItemStatus.ACCEPTED,
            adjudicated_by="reviewer",
        )
        with pytest.raises(ValueError):
            updated.adjudicate(
                basket.items[0].item_id,
                BasketItemStatus.REJECTED,
                adjudicated_by="reviewer",
            )

    @pytest.mark.parametrize("bad", ["", "   ", 123, None])
    def test_adjudicated_by_validated(self, bad: object) -> None:
        basket = self._basket()
        with pytest.raises(ValueError):
            basket.adjudicate(
                basket.items[0].item_id,
                BasketItemStatus.ACCEPTED,
                adjudicated_by=cast(str, bad),
            )


class TestEvidenceSummary:
    def _basket(self) -> ReviewBasket:
        return build_review_basket(
            [_candidate("wangxiaoming", "Organization", _S2)],
            [_identity("wangxiaoming1")],
        )

    def test_shape_and_counts(self) -> None:
        summary = json.loads(basket_evidence_summary(self._basket()))
        assert set(summary) == {"basket_size", "counts", "items"}
        assert summary["basket_size"] == 1
        assert summary["counts"] == {"pending": 1, "accepted": 0, "rejected": 0}
        item = summary["items"][0]
        assert set(item) == {
            "item_id",
            "span_id",
            "target_identity_id",
            "candidate_identity_id",
            "decision_id",
            "score",
            "reason",
            "status",
        }

    def test_single_line(self) -> None:
        text = basket_evidence_summary(self._basket())
        assert "\n" not in text
        assert "\r" not in text

    def test_redacted(self) -> None:
        text = basket_evidence_summary(self._basket())
        assert "quote" not in text
        assert "wangxiaoming" not in text
        assert "ghost" not in text
        assert "wangxiaoming1" not in text  # candidate display name never leaks

    def test_counts_track_adjudication(self) -> None:
        basket = self._basket()
        updated = basket.adjudicate(
            basket.items[0].item_id,
            BasketItemStatus.REJECTED,
            adjudicated_by="reviewer",
        )
        summary = json.loads(basket_evidence_summary(updated))
        assert summary["counts"] == {"pending": 0, "accepted": 0, "rejected": 1}
        assert summary["items"][0]["status"] == "rejected"

    def test_deterministic(self) -> None:
        assert basket_evidence_summary(self._basket()) == basket_evidence_summary(
            self._basket()
        )

    def test_empty_basket(self) -> None:
        text = basket_evidence_summary(ReviewBasket())
        assert json.loads(text)["basket_size"] == 0
        assert json.loads(text)["items"] == []

    def test_non_basket_rejected(self) -> None:
        with pytest.raises(ValueError):
            basket_evidence_summary(cast(ReviewBasket, "nope"))


class TestRedactedRepr:
    def test_evidence_ref_repr_redacts_quote(self) -> None:
        ref = EvidenceRef(source="doc", quote="secret-quote", char_start=0, char_end=2)
        text = repr(ref)
        assert "secret-quote" not in text
        assert "secret" not in text
        assert "<redacted:12-chars>" in text
        assert "char_start=0" in text and "char_end=2" in text

    def test_basket_item_repr_redacts_name(self) -> None:
        item = _make_item(name="top-secret-name")
        text = repr(item)
        assert "top-secret-name" not in text
        assert "<redacted:" in text
        assert 'quote="q"' not in text
        assert "pending" in text and "0.9" in text

    def test_triage_verdict_repr_redacts_name(self) -> None:
        verdict = TriageVerdict(
            span_id=_S1,
            normalized_name="secret-name",
            entity_type="Organization",
            exit=TriageExit.NEW,
        )
        text = repr(verdict)
        assert "secret-name" not in text
        assert "<redacted:" in text

    def test_review_basket_repr_does_not_leak_item_name(self) -> None:
        basket = ReviewBasket(items=(_make_item(name="secret-item-name"),))
        text = repr(basket)
        assert "secret-item-name" not in text
        assert "<redacted:" in text


class TestBasketItemValidation:
    def test_tampered_item_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(item_id="bogus")

    def test_self_pair_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(target="same", candidate="same")

    @pytest.mark.parametrize(
        "bad",
        [True, False, None, "0.5", float("nan"), float("inf"), -0.1, 1.5],
    )
    def test_score_validated(self, bad: object) -> None:
        with pytest.raises(ValueError):
            _make_item(score=cast(float, bad))

    def test_overflow_score_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(score=10**400)

    def test_empty_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(evidence=())

    def test_non_tuple_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(
                evidence=cast(
                    "tuple[EvidenceRef, ...]", [EvidenceRef(source="d", quote="q")]
                )
            )

    def test_non_ref_evidence_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(evidence=cast("tuple[EvidenceRef, ...]", (42,)))

    def test_raw_reason_rejected(self) -> None:
        with pytest.raises(ValueError):
            BasketItem(
                item_id=make_item_id(_S1, "t", "c"),
                span_id=_S1,
                target_identity_id="t",
                candidate_identity_id="c",
                candidate_normalized_name="ghost",
                score=0.9,
                reason=cast(SuggestionReason, "name_similarity"),
                decision_id="d",
                evidence=(EvidenceRef(source="d", quote="q"),),
            )

    def test_raw_status_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(status=cast(BasketItemStatus, "pending"))

    def test_pending_with_adjudicator_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(adjudicated_by="someone")

    def test_accepted_without_adjudicator_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_item(status=BasketItemStatus.ACCEPTED)

    def test_round_trip_pending(self) -> None:
        item = _make_item()
        assert BasketItem.from_dict(item.to_dict()) == item

    def test_round_trip_adjudicated(self) -> None:
        item = _make_item(status=BasketItemStatus.REJECTED, adjudicated_by="reviewer")
        assert BasketItem.from_dict(item.to_dict()) == item

    def test_from_dict_missing_key(self) -> None:
        payload = _make_item().to_dict()
        del payload["decision_id"]
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_unknown_key(self) -> None:
        payload = _make_item().to_dict()
        payload["extra"] = 1
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_non_str_key(self) -> None:
        payload = _make_item().to_dict()
        mixed: dict[object, object] = {123: "x"}
        mixed.update(payload)
        with pytest.raises(ValueError):
            BasketItem.from_dict(mixed)

    def test_from_dict_bad_reason(self) -> None:
        payload = _make_item().to_dict()
        payload["reason"] = "bogus"
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_bad_kind(self) -> None:
        payload = _make_item().to_dict()
        payload["kind"] = "merge_claim"
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_relation_claim_kind_rejected(self) -> None:
        payload = _make_item().to_dict()
        payload["kind"] = "relation_claim"
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_bad_score(self) -> None:
        payload = _make_item().to_dict()
        payload["score"] = "0.5"
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_bad_evidence_entry(self) -> None:
        payload = _make_item().to_dict()
        payload["evidence"] = [42]
        with pytest.raises(ValueError):
            BasketItem.from_dict(payload)

    def test_from_dict_non_mapping(self) -> None:
        with pytest.raises(ValueError):
            BasketItem.from_dict("nope")

    def test_from_dict_list_key_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            BasketItem.from_dict(_ListKeyMapping())


class TestReviewBasketToDict:
    def test_to_dict_shape(self) -> None:
        basket = build_review_basket(
            [_candidate("wangxiaoming", "Organization", _S2)],
            [_identity("wangxiaoming1")],
        )
        data = basket.to_dict()
        assert set(data) == {"items"}
        items = data["items"]
        assert isinstance(items, list) and len(items) == 1
        restored = BasketItem.from_dict(items[0])
        assert restored == basket.items[0]
        assert restored.item_id == basket.items[0].item_id
        assert (
            restored.candidate_normalized_name
            == basket.items[0].candidate_normalized_name
        )


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
            "llamaindex_runtime.entity.contracts",
            "llamaindex_runtime.entity.fuzzy_recall",
            "llamaindex_runtime.entity.identity",
            "llamaindex_runtime.entity.normalization",
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
