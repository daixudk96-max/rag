"""Tests for llamaindex_runtime.entity.identity (Phase 17 Wave 4a)."""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from llamaindex_runtime.entity.contracts import MentionCandidate
from llamaindex_runtime.entity.identity import (
    CANONICAL_TYPES,
    EntityIdentity,
    EntityMergeEvent,
    MergeDecision,
    MergeOutcome,
    VetoKind,
    make_decision_id,
    make_event_id,
    make_identity_id,
    plan_merge,
    record_merge_event,
    resolve_identities,
)
from llamaindex_runtime.entity.normalization import (
    USCC_CHARSET,
    normalize_mention_text,
)

_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "entity"
    / "identity.py"
)

_S1 = "11111111-1111-4111-8111-111111111111"
_S2 = "22222222-2222-4222-8222-222222222222"

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


def _candidate(mention_text: str, entity_type: str, span_id: str) -> MentionCandidate:
    # ADAPT-ONLY ZONE: make this single constructor call match the real
    # MentionCandidate signature in llamaindex_runtime/entity/contracts.py.
    # Every assertion in this file must stay untouched.
    return MentionCandidate(
        input_id=span_id,
        input_kind="corpus_span",
        input_revision="rev-1",
        normalized_text=mention_text,
        span_id=span_id,
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
        extractor_id="w4a-identity-fixture",
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
    # Valid query_text candidate per contracts.py (span_id/None, no projection).
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
        extractor_id="w4a-identity-fixture",
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


def _identity(
    name: str, entity_type: str, spans: tuple[str, ...] = (_S1,)
) -> EntityIdentity:
    normalized = normalize_mention_text(name)
    return EntityIdentity(
        identity_id=make_identity_id(normalized, entity_type),
        normalized_name=normalized,
        entity_type=entity_type,
        member_span_ids=tuple(sorted(set(spans))),
    )


def _named(name: str) -> EntityIdentity:
    return _identity(name, "Organization")


def _uscc_pair() -> tuple[EntityIdentity, EntityIdentity]:
    """Same-USCC different-name pair: MERGED with two distinct identity ids."""
    return _named("acme " + _USCC_A), _named("acme ltd " + _USCC_A)


class TestMakeIdentityId:
    def test_deterministic_for_same_key(self) -> None:
        assert make_identity_id("华为", "Organization") == make_identity_id(
            "华为", "Organization"
        )

    def test_differs_by_name(self) -> None:
        assert make_identity_id("华为", "Organization") != make_identity_id(
            "中兴", "Organization"
        )

    def test_differs_by_type(self) -> None:
        assert make_identity_id("华为", "Organization") != make_identity_id(
            "华为", "Product"
        )

    def test_canonical_types_pinned(self) -> None:
        assert CANONICAL_TYPES == frozenset(
            {"Person", "Location", "Organization", "CreativeWork", "Product"}
        )

    def test_identity_id_is_uuid5(self) -> None:
        parsed = uuid.UUID(make_identity_id("华为", "Organization"))
        assert parsed.version == 5

    def test_golden_uuid_pinned(self) -> None:
        # The default json.dumps encoding of the payload IS the identity
        # contract; changing separators/ensure_ascii would break this.
        assert (
            make_identity_id("华为", "Organization")
            == "6be8cbc7-44ce-5f89-a468-5a883a3fcb75"
        )

    @pytest.mark.parametrize(
        "bad",
        [123, None, ["华为"], ("华为",), ""],
        ids=["int", "none", "list", "tuple", "empty"],
    )
    def test_non_string_name_rejected(self, bad: object) -> None:
        with pytest.raises(ValueError):
            make_identity_id(bad, "Organization")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad", [123, None, ["Organization"], ""], ids=["int", "none", "list", "empty"]
    )
    def test_non_string_type_rejected(self, bad: object) -> None:
        with pytest.raises(ValueError):
            make_identity_id("华为", bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad", [123, None, "", ["x"]], ids=["int", "none", "empty", "list"]
    )
    def test_non_string_decision_input_rejected(self, bad: object) -> None:
        with pytest.raises(ValueError):
            make_decision_id("2191a2a0-0000-4000-8000-000000000001", bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad", [123, None, "", ["d"]], ids=["int", "none", "empty", "list"]
    )
    def test_non_string_event_input_rejected(self, bad: object) -> None:
        with pytest.raises(ValueError):
            make_event_id(bad)  # type: ignore[arg-type]


class TestEntityIdentity:
    def test_happy_path_fields(self) -> None:
        identity = _identity("华为", "Organization", (_S2, _S1))
        assert identity.normalized_name == "华为"
        assert identity.entity_type == "Organization"
        assert identity.member_span_ids == (_S1, _S2)

    def test_from_dict_round_trip(self) -> None:
        identity = _identity("华为", "Organization", (_S1, _S2))
        assert EntityIdentity.from_dict(identity.to_dict()) == identity

    def test_from_dict_round_trip_with_provenance(self) -> None:
        identity = EntityIdentity(
            identity_id=make_identity_id("华为", "Organization"),
            normalized_name="华为",
            entity_type="Organization",
            member_span_ids=(_S1,),
            provenance=(("rule", "exact"),),
        )
        assert EntityIdentity.from_dict(identity.to_dict()) == identity

    def test_identity_id_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id="not-the-id",
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=(_S1,),
            )

    def test_non_normalized_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id(" 华为 ", "Organization"),
                normalized_name=" 华为 ",
                entity_type="Organization",
                member_span_ids=(_S1,),
            )

    def test_non_canonical_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "PER"),
                normalized_name="华为",
                entity_type="PER",
                member_span_ids=(_S1,),
            )

    def test_empty_members_rejected(self) -> None:
        with pytest.raises(ValueError):
            _identity("华为", "Organization", spans=())

    def test_unsorted_members_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "Organization"),
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=(_S2, _S1),
            )

    def test_duplicate_members_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "Organization"),
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=(_S1, _S1),
            )

    def test_non_string_member_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "Organization"),
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=(123,),  # type: ignore[arg-type]
            )

    def test_member_span_ids_must_be_tuple(self) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "Organization"),
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=[_S1],  # type: ignore[arg-type]
            )

    def test_from_dict_rejects_non_mapping(self) -> None:
        for bad in ([], "x", None, 42):
            with pytest.raises(ValueError):
                EntityIdentity.from_dict(bad)

    def test_from_dict_rejects_mixed_type_keys(self) -> None:
        raw = _identity("华为", "Organization", (_S1,)).to_dict()
        raw["mystery"] = 1  # type: ignore[assignment]
        raw[("a", "b")] = "poison"  # type: ignore[assignment]
        with pytest.raises(ValueError):
            EntityIdentity.from_dict(raw)

    def test_from_dict_lists_missing_and_unknown(self) -> None:
        raw = {
            "identity_id": make_identity_id("华为", "Organization"),
            "normalized_name": "华为",
            "member_span_ids": [_S1],
            "mystery": 1,
        }
        with pytest.raises(ValueError) as info:
            EntityIdentity.from_dict(raw)
        message = str(info.value)
        assert "entity_type" in message
        assert "mystery" in message

    def test_from_dict_rejects_string_members(self) -> None:
        raw = {
            "identity_id": make_identity_id("华为", "Organization"),
            "normalized_name": "华为",
            "entity_type": "Organization",
            "member_span_ids": "s-1",
        }
        with pytest.raises(ValueError):
            EntityIdentity.from_dict(raw)


class TestProvenanceDiscipline:
    @pytest.mark.parametrize(
        "bad",
        [
            ((1, "x"),),
            (("rule", 1),),
            ("ab",),
            [("rule", "x")],
            "ab",
            (("", "x"),),
            (("rule", ""),),
        ],
        ids=[
            "int-first",
            "int-second",
            "str-pair",
            "list-not-tuple",
            "bare-str",
            "empty-first",
            "empty-second",
        ],
    )
    def test_direct_construction_rejects_malformed(self, bad: object) -> None:
        with pytest.raises(ValueError):
            EntityIdentity(
                identity_id=make_identity_id("华为", "Organization"),
                normalized_name="华为",
                entity_type="Organization",
                member_span_ids=(_S1,),
                provenance=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize(
        "bad",
        [
            [[1, "x"]],
            [["rule", 1]],
            ["abc"],
            ["ab"],
            [["a", ""]],
            [["", "b"]],
            "ab",
            (("a", "b"),),
            {("a", "b")},
            [["a", "b", "c"]],
        ],
        ids=[
            "int-first",
            "int-second",
            "str-item",
            "str-pair",
            "empty-second",
            "empty-first",
            "bare-str",
            "tuple-not-list",
            "set",
            "three-items",
        ],
    )
    def test_from_dict_rejects_malformed(self, bad: object) -> None:
        raw = _identity("华为", "Organization", (_S1,)).to_dict()
        raw["provenance"] = bad  # type: ignore[assignment]
        with pytest.raises(ValueError):
            EntityIdentity.from_dict(raw)

    def test_from_dict_accepts_list_of_pairs(self) -> None:
        raw = _identity("华为", "Organization", (_S1,)).to_dict()
        raw["provenance"] = [["rule", "exact"], ["dictionary", "uscc"]]
        identity = EntityIdentity.from_dict(raw)
        assert identity.provenance == (("rule", "exact"), ("dictionary", "uscc"))


class TestResolveIdentities:
    def test_cross_document_same_name_type_merges(self) -> None:
        mentions = [
            _candidate("华为", "Organization", _S1),
            _candidate("华为", "Organization", _S2),
        ]
        identities = resolve_identities(mentions)
        assert len(identities) == 1
        assert identities[0].member_span_ids == (_S1, _S2)

    def test_same_name_different_type_stays_apart(self) -> None:
        identities = resolve_identities(
            [
                _candidate("华为", "Organization", _S1),
                _candidate("华为", "Product", _S2),
            ]
        )
        assert len(identities) == 2

    def test_fullwidth_variant_merges(self) -> None:
        identities = resolve_identities(
            [
                _candidate("ＨＵＡＷＥＩ", "Organization", _S1),
                _candidate("huawei", "Organization", _S2),
            ]
        )
        assert len(identities) == 1
        assert identities[0].normalized_name == "huawei"

    def test_non_canonical_type_fails_closed(self) -> None:
        with pytest.raises(ValueError):
            resolve_identities([_candidate("华为", "PER", _S1)])

    def test_empty_input_yields_empty(self) -> None:
        assert resolve_identities([]) == ()

    def test_order_independent(self) -> None:
        forward = [
            _candidate("华为", "Organization", _S1),
            _candidate("Huawei", "Organization", _S2),
        ]
        assert resolve_identities(list(reversed(forward))) == resolve_identities(
            forward
        )
        # Fullwidth-variant pair must also be order independent (both directions
        # normalize to the same group with sorted, deduplicated members).
        fullwidth = [
            _candidate("ＨＵＡＷＥＩ", "Organization", _S1),
            _candidate("huawei", "Organization", _S2),
        ]
        assert resolve_identities(list(reversed(fullwidth))) == resolve_identities(
            fullwidth
        )

    def test_query_candidate_rejected(self) -> None:
        with pytest.raises(ValueError):
            resolve_identities([_query_candidate("华为", "Organization")])

    def test_span_id_reused_across_groups_rejected(self) -> None:
        with pytest.raises(ValueError):
            resolve_identities(
                [
                    _candidate("华为", "Organization", _S1),
                    _candidate("华为", "Product", _S1),
                ]
            )

    def test_span_id_reused_across_texts_rejected(self) -> None:
        with pytest.raises(ValueError):
            resolve_identities(
                [
                    _candidate("华为", "Organization", _S1),
                    _candidate("中兴", "Organization", _S1),
                ]
            )

    def test_span_id_duplicate_in_same_group_allowed(self) -> None:
        identities = resolve_identities(
            [
                _candidate("华为", "Organization", _S1),
                _candidate("华为", "Organization", _S1),
            ]
        )
        assert len(identities) == 1
        assert identities[0].member_span_ids == (_S1,)

    def test_non_sequence_input_rejected(self) -> None:
        for bad in ("华为", "华为".encode("utf-8"), (c for c in ()), 42):
            with pytest.raises(ValueError):
                resolve_identities(bad)  # type: ignore[arg-type]


class TestPlanMerge:
    def test_type_mismatch_vetoes_even_same_name(self) -> None:
        decision = plan_merge(
            _identity("华为", "Organization"), _identity("华为", "Product")
        )
        assert decision.outcome is MergeOutcome.BLOCKED_VETO
        assert decision.veto_kind is VetoKind.TYPE_MISMATCH

    def test_same_uscc_merges_despite_name_difference(self) -> None:
        decision = plan_merge(_named("acme " + _USCC_A), _named("acme ltd " + _USCC_A))
        assert decision.outcome is MergeOutcome.MERGED
        assert decision.rule_id == "uscc_exact_match"
        assert _USCC_A in " ".join(decision.reasons)

    def test_conflicting_uscc_vetoes(self) -> None:
        decision = plan_merge(_named("alpha " + _USCC_A), _named("beta " + _USCC_B))
        assert decision.outcome is MergeOutcome.BLOCKED_VETO
        assert decision.veto_kind is VetoKind.USCC_CONFLICT
        joined = " ".join(decision.reasons)
        assert _USCC_A in joined and _USCC_B in joined

    def test_no_uscc_same_name_merges(self) -> None:
        decision = plan_merge(_named("华为"), _named("华为"))
        assert decision.outcome is MergeOutcome.MERGED
        assert decision.rule_id == "exact_normalized_name"

    def test_no_uscc_different_names_defers_to_w4b(self) -> None:
        decision = plan_merge(_named("华为"), _named("中兴"))
        assert decision.outcome is MergeOutcome.DEFERRED_REVIEW
        assert decision.veto_kind is VetoKind.NONE
        assert "W4b" in " ".join(decision.reasons)

    def test_one_sided_uscc_different_names_defers(self) -> None:
        decision = plan_merge(_named("acme " + _USCC_A), _named("acme"))
        assert decision.outcome is MergeOutcome.DEFERRED_REVIEW

    def test_non_identity_input_rejected(self) -> None:
        with pytest.raises(ValueError):
            plan_merge("华为", _named("华为"))  # type: ignore[arg-type]


class TestMergeDecisionContract:
    def _merged_pair(self) -> tuple[EntityIdentity, EntityIdentity, MergeDecision]:
        a = _named("华为")
        b = _named("华为")
        return a, b, plan_merge(a, b)

    def test_from_dict_round_trip_and_enum_coercion(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        assert raw["outcome"] == "merged"
        assert MergeDecision.from_dict(raw) == decision

    def test_bare_str_outcome_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=raw["decision_id"],
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome="merged",  # type: ignore[arg-type]
                veto_kind=VetoKind.NONE,
                rule_id=raw["rule_id"],
                reasons=("exact normalized name match",),
            )

    def test_bare_str_veto_kind_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=raw["decision_id"],
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.MERGED,
                veto_kind="none",  # type: ignore[arg-type]
                rule_id=raw["rule_id"],
                reasons=("exact normalized name match",),
            )

    def test_hashable_but_unstr_outcome_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        with pytest.raises(ValueError):
            MergeDecision.from_dict({**raw, "outcome": ["merged"]})

    def test_hashable_but_unstr_veto_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        with pytest.raises(ValueError):
            MergeDecision.from_dict({**raw, "veto_kind": ["none"]})

    def test_blocked_with_none_veto_rejected(self) -> None:
        a = _identity("华为", "Organization")
        b = _identity("华为", "Product")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=make_decision_id(a.identity_id, b.identity_id),
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.BLOCKED_VETO,
                veto_kind=VetoKind.NONE,
                rule_id="type_mismatch_veto",
                reasons=("mismatch",),
            )

    def test_merged_with_concrete_veto_rejected(self) -> None:
        a = _named("华为")
        b = _named("华为")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=make_decision_id(a.identity_id, b.identity_id),
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.MERGED,
                veto_kind=VetoKind.TYPE_MISMATCH,
                rule_id="exact_normalized_name",
                reasons=("exact normalized name match",),
            )

    def test_merged_none_with_wrong_rule_id_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=decision.decision_id,
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.MERGED,
                veto_kind=VetoKind.NONE,
                rule_id="type_mismatch_veto",
                reasons=("exact normalized name match",),
            )

    def test_blocked_type_mismatch_with_wrong_rule_id_rejected(self) -> None:
        a = _identity("华为", "Organization")
        b = _identity("华为", "Product")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=make_decision_id(a.identity_id, b.identity_id),
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.BLOCKED_VETO,
                veto_kind=VetoKind.TYPE_MISMATCH,
                rule_id="uscc_exact_match",
                reasons=("mismatch",),
            )

    def test_deferred_with_concrete_veto_rejected(self) -> None:
        a = _named("华为")
        b = _named("中兴")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=make_decision_id(a.identity_id, b.identity_id),
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.DEFERRED_REVIEW,
                veto_kind=VetoKind.TYPE_MISMATCH,
                rule_id="deferred_fuzzy_recall",
                reasons=("deferred",),
            )

    def test_deferred_none_with_wrong_rule_id_rejected(self) -> None:
        a = _named("华为")
        b = _named("中兴")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id=make_decision_id(a.identity_id, b.identity_id),
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.DEFERRED_REVIEW,
                veto_kind=VetoKind.NONE,
                rule_id="type_mismatch_veto",
                reasons=("deferred",),
            )

    def test_reasons_must_be_tuple(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        for bad in ("exact normalized name match", ["exact normalized name match"]):
            with pytest.raises(ValueError):
                MergeDecision(
                    decision_id=raw["decision_id"],
                    a_identity_id=a.identity_id,
                    b_identity_id=b.identity_id,
                    outcome=MergeOutcome.MERGED,
                    veto_kind=VetoKind.NONE,
                    rule_id=raw["rule_id"],
                    reasons=bad,  # type: ignore[arg-type]
                )

    def test_wrong_decision_id_rejected(self) -> None:
        a = _named("华为")
        b = _named("中兴")
        with pytest.raises(ValueError):
            MergeDecision(
                decision_id="wrong-id",
                a_identity_id=a.identity_id,
                b_identity_id=b.identity_id,
                outcome=MergeOutcome.DEFERRED_REVIEW,
                veto_kind=VetoKind.NONE,
                rule_id="deferred_fuzzy_recall",
                reasons=("deferred",),
            )

    def test_from_dict_unknown_outcome_value_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        raw["outcome"] = "bogus"
        with pytest.raises(ValueError):
            MergeDecision.from_dict(raw)

    def test_from_dict_non_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            MergeDecision.from_dict([])

    def test_from_dict_rejects_mixed_type_keys(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        raw["mystery"] = 1  # type: ignore[assignment]
        raw[("a", "b")] = "poison"  # type: ignore[assignment]
        with pytest.raises(ValueError):
            MergeDecision.from_dict(raw)

    def test_from_dict_reasons_not_list_rejected(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        raw["reasons"] = "exact normalized name match"
        with pytest.raises(ValueError):
            MergeDecision.from_dict(raw)
        raw["reasons"] = ("exact normalized name match",)
        with pytest.raises(ValueError):
            MergeDecision.from_dict(raw)

    def test_from_dict_lists_missing_and_unknown(self) -> None:
        a, b, decision = self._merged_pair()
        raw = decision.to_dict()
        del raw["reasons"]
        raw["mystery"] = 1
        with pytest.raises(ValueError) as info:
            MergeDecision.from_dict(raw)
        message = str(info.value)
        assert "reasons" in message
        assert "mystery" in message


class TestMergeEvent:
    def test_records_merged_decision(self) -> None:
        a, b = _uscc_pair()
        decision = plan_merge(a, b)
        assert decision.outcome is MergeOutcome.MERGED
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        survivor, absorbed = sorted([a.identity_id, b.identity_id])
        assert survivor != absorbed
        assert event.merged_into_id == survivor
        assert event.absorbed_id == absorbed
        assert event.event_id == make_event_id(decision.decision_id)

    def test_event_id_deterministic(self) -> None:
        a, b = _uscc_pair()
        first = record_merge_event(a, b, recorded_by="coordinator-17")
        second = record_merge_event(a, b, recorded_by="coordinator-17")
        assert first == second

    def test_blocked_decision_rejected(self) -> None:
        a = _identity("华为", "Organization")
        b = _identity("华为", "Product")
        with pytest.raises(ValueError):
            record_merge_event(a, b, recorded_by="coordinator-17")

    def test_deferred_decision_rejected(self) -> None:
        with pytest.raises(ValueError):
            record_merge_event(
                _named("华为"), _named("中兴"), recorded_by="coordinator-17"
            )

    def test_self_merge_rejected(self) -> None:
        a = _named("华为")
        b = _named("华为")
        with pytest.raises(ValueError):
            record_merge_event(a, b, recorded_by="coordinator-17")

    def test_non_identity_input_rejected(self) -> None:
        a, b = _uscc_pair()
        with pytest.raises(ValueError):
            record_merge_event("华为", b, recorded_by="coordinator-17")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            record_merge_event(a, "华为", recorded_by="coordinator-17")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            record_merge_event(a, b, recorded_by=None)  # type: ignore[arg-type]

    def test_empty_recorded_by_rejected(self) -> None:
        a, b = _uscc_pair()
        with pytest.raises(ValueError):
            record_merge_event(a, b, recorded_by="   ")

    def test_round_trip(self) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        assert EntityMergeEvent.from_dict(event.to_dict()) == event

    def test_event_id_mismatch_rejected(self) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        raw = event.to_dict()
        raw["event_id"] = "00000000-0000-4000-8000-000000000000"
        with pytest.raises(ValueError):
            EntityMergeEvent(**raw)

    def test_merged_into_equals_absorbed_rejected(self) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        raw = event.to_dict()
        raw["merged_into_id"] = raw["absorbed_id"]
        with pytest.raises(ValueError):
            EntityMergeEvent(**raw)

    @pytest.mark.parametrize(
        "field",
        [
            "event_id",
            "decision_id",
            "merged_into_id",
            "absorbed_id",
            "rule_id",
            "recorded_by",
        ],
    )
    def test_whitespace_field_rejected(self, field: str) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        raw = event.to_dict()
        raw[field] = "   "
        with pytest.raises(ValueError):
            EntityMergeEvent(**raw)

    def test_from_dict_rejects_mixed_type_keys(self) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        raw = event.to_dict()
        raw["mystery"] = 1  # type: ignore[assignment]
        raw[("a", "b")] = "poison"  # type: ignore[assignment]
        with pytest.raises(ValueError):
            EntityMergeEvent.from_dict(raw)

    def test_from_dict_lists_missing_and_unknown(self) -> None:
        a, b = _uscc_pair()
        event = record_merge_event(a, b, recorded_by="coordinator-17")
        raw = event.to_dict()
        del raw["recorded_by"]
        raw["mystery"] = 1
        with pytest.raises(ValueError) as info:
            EntityMergeEvent.from_dict(raw)
        message = str(info.value)
        assert "recorded_by" in message
        assert "mystery" in message


class TestPurityAndDiscipline:
    def test_import_allowlist(self) -> None:
        tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
        allowed = {
            "__future__",
            "json",
            "uuid",
            "collections.abc",
            "dataclasses",
            "enum",
            "typing",
            "llamaindex_runtime.entity.contracts",
            "llamaindex_runtime.entity.label_map",
            "llamaindex_runtime.entity.normalization",
        }
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add("." * node.level + (node.module or ""))
        assert modules, "no imports found"
        assert modules <= allowed

    def test_no_forbidden_substrings(self) -> None:
        text = _SOURCE.read_text(encoding="utf-8").lower()
        for banned in ("datetime", "paddle", "torch", "transformers", "requests"):
            assert banned not in text
