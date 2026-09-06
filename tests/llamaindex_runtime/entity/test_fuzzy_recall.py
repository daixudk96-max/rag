"""Tests for Phase 17 Wave 4b fuzzy merge suggestions."""

from __future__ import annotations

import ast
import dataclasses
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from llamaindex_runtime.entity.fuzzy_recall import (
    DEFAULT_SUGGESTION_THRESHOLD,
    FuzzySuggestion,
    SuggestionReason,
    suggest_merges,
)
from llamaindex_runtime.entity.identity import (
    EntityIdentity,
    MergeOutcome,
    make_identity_id,
    plan_merge,
)
from llamaindex_runtime.entity.normalization import normalize_mention_text

_IMPL = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "entity"
    / "fuzzy_recall.py"
)

_ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "difflib",
    "enum",
    "typing",
    "llamaindex_runtime.entity.identity",
}

_BANNED_SUBSTRINGS = (
    "rapidfuzz",
    "datetime",
    "paddle",
    "torch",
    "transformers",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "__import__",
    "importlib",
)


_USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"


def _uscc(base17: str) -> str:
    total = 0
    for index, ch in enumerate(base17):
        total += (3**index) % 31 * _USCC_CHARSET.index(ch)
    return base17 + _USCC_CHARSET[(31 - total % 31) % 31]


USCC_A = _uscc("91350100M000100YX")
USCC_B = _uscc("92450100M000100AB")


def _ident(
    name: str, etype: str = "Organization", spans: tuple[str, ...] = ("s-1",)
) -> EntityIdentity:
    normalized = normalize_mention_text(name)
    return EntityIdentity(
        identity_id=make_identity_id(normalized, etype),
        normalized_name=normalized,
        entity_type=etype,
        member_span_ids=spans,
    )


def test_default_threshold_value() -> None:
    assert DEFAULT_SUGGESTION_THRESHOLD == 0.87
    assert type(DEFAULT_SUGGESTION_THRESHOLD) is float


class TestThresholdValidation:
    def test_bool_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], threshold=True)

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], threshold=float("nan"))

    def test_inf_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], threshold=float("inf"))

    def test_out_of_range_rejected(self) -> None:
        for bad in (1.5, -0.1):
            with pytest.raises(ValueError):
                suggest_merges(_ident("acme"), [], threshold=bad)

    def test_non_numeric_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], threshold="0.9")

    def test_int_bounds_accepted(self) -> None:
        assert suggest_merges(_ident("acme"), [], threshold=0) == ()
        assert suggest_merges(_ident("acme"), [], threshold=1) == ()

    def test_overflow_threshold_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], threshold=10**400)


class TestInputValidation:
    def test_non_identity_target_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges("not-an-identity", [])

    def test_string_universe_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), "abc")

    def test_generator_universe_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), (x for x in [1]))

    def test_bytes_universe_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), b"abc")

    def test_non_identity_entry_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [_ident("beta", spans=("s-2",)), "junk"])

    def test_non_callable_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            suggest_merges(_ident("acme"), [], ratio_fn="ratio")


def _high_ratio(left: str, right: str) -> float:
    return 0.99


class TestMergeGate:

    def test_self_excluded(self) -> None:
        target = _ident("acme robotics")
        assert (
            suggest_merges(target, [target], threshold=0.0, ratio_fn=_high_ratio) == ()
        )

    def test_same_name_pair_excluded_resolution_domain(self) -> None:
        target = _ident("huawei", spans=("s-1",))
        other = _ident("huawei", spans=("s-2",))
        decision = plan_merge(target, other)
        assert decision.outcome is MergeOutcome.MERGED
        assert (
            suggest_merges(target, [other], threshold=0.0, ratio_fn=_high_ratio) == ()
        )

    def test_type_mismatch_veto_excluded(self) -> None:
        target = _ident("huawei", "Organization")
        product = _ident("huawei digital energy", "Product")
        decision = plan_merge(target, product)
        assert decision.outcome is MergeOutcome.BLOCKED_VETO
        assert (
            suggest_merges(target, [product], threshold=0.0, ratio_fn=_high_ratio) == ()
        )

    def test_uscc_conflict_veto_excluded(self) -> None:
        target = _ident("acme " + USCC_A)
        rival = _ident("beta " + USCC_B)
        decision = plan_merge(target, rival)
        assert decision.outcome is MergeOutcome.BLOCKED_VETO
        assert (
            suggest_merges(target, [rival], threshold=0.0, ratio_fn=_high_ratio) == ()
        )

    def test_uscc_exact_match_excluded_resolution_domain(self) -> None:
        target = _ident("acme " + USCC_A)
        branch = _ident("acme ltd " + USCC_A)
        decision = plan_merge(target, branch)
        assert decision.outcome is MergeOutcome.MERGED
        assert (
            suggest_merges(target, [branch], threshold=0.0, ratio_fn=_high_ratio) == ()
        )

    def test_deferred_pair_suggested(self) -> None:
        target = _ident("acme robotics")
        near = _ident("acme robotix", spans=("s-2",))
        got = suggest_merges(
            target, [near], threshold=0.5, ratio_fn=lambda left, right: 0.9
        )
        assert len(got) == 1
        assert got[0].candidate_identity_id == near.identity_id
        assert got[0].target_identity_id == target.identity_id
        assert got[0].reason is SuggestionReason.NAME_SIMILARITY


class TestDeduplication:
    def test_duplicate_universe_entry_suggested_once(self) -> None:
        target = _ident("acme robotics")
        near = _ident("acme robotix", spans=("s-2",))
        got = suggest_merges(
            target, [near, near], threshold=0.5, ratio_fn=lambda left, right: 0.9
        )
        assert len(got) == 1

    def test_duplicate_identity_id_suggested_once(self) -> None:
        target = _ident("acme robotics")
        first = _ident("acme robotix", spans=("s-2",))
        second = _ident("acme robotix", spans=("s-3",))
        assert first.identity_id == second.identity_id
        got = suggest_merges(
            target, [first, second], threshold=0.5, ratio_fn=lambda left, right: 0.9
        )
        assert len(got) == 1


class TestScoring:
    def test_score_equal_to_threshold_included(self) -> None:
        target = _ident("aaa")
        candidate = _ident("bbb", spans=("s-2",))
        got = suggest_merges(
            target, [candidate], threshold=0.87, ratio_fn=lambda left, right: 0.87
        )
        assert len(got) == 1

    def test_score_below_threshold_excluded(self) -> None:
        target = _ident("aaa")
        candidate = _ident("bbb", spans=("s-2",))
        got = suggest_merges(
            target, [candidate], threshold=0.87, ratio_fn=lambda left, right: 0.86
        )
        assert got == ()

    def test_sorted_by_score_then_name(self) -> None:
        target = _ident("target")
        c_aaa = _ident("aaa", spans=("s-a",))
        c_bbb = _ident("bbb", spans=("s-b",))
        c_zzz = _ident("zzz", spans=("s-z",))
        scores = {"aaa": 0.90, "bbb": 0.90, "zzz": 0.95}

        def ratio_fn(left: str, right: str) -> float:
            return scores[right]

        got = suggest_merges(
            target, [c_bbb, c_zzz, c_aaa], threshold=0.5, ratio_fn=ratio_fn
        )
        assert [item.candidate_normalized_name for item in got] == [
            "zzz",
            "aaa",
            "bbb",
        ]

    def test_deterministic_repeat(self) -> None:
        target = _ident("acme robotics")
        universe = [
            _ident("acme robotix", spans=("s-2",)),
            _ident("acme robotik", spans=("s-3",)),
        ]
        first = suggest_merges(
            target, universe, threshold=0.5, ratio_fn=lambda left, right: 0.9
        )
        second = suggest_merges(
            target, universe, threshold=0.5, ratio_fn=lambda left, right: 0.9
        )
        assert first == second

    def test_overflow_ratio_rejected(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        with pytest.raises(ValueError):
            suggest_merges(target, [candidate], ratio_fn=lambda left, right: 10**400)

    def test_nan_ratio_rejected(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        with pytest.raises(ValueError):
            suggest_merges(
                target, [candidate], ratio_fn=lambda left, right: float("nan")
            )

    def test_inf_ratio_rejected(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        with pytest.raises(ValueError):
            suggest_merges(
                target, [candidate], ratio_fn=lambda left, right: float("inf")
            )

    def test_bool_ratio_rejected(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        with pytest.raises(ValueError):
            suggest_merges(target, [candidate], ratio_fn=lambda left, right: True)

    def test_zero_score_at_zero_threshold_included(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        got = suggest_merges(
            target, [candidate], threshold=0.0, ratio_fn=lambda left, right: 0.0
        )
        assert len(got) == 1

    def test_one_score_at_one_threshold_included(self) -> None:
        target = _ident("acme robotics")
        candidate = _ident("acme robotix", spans=("s-2",))
        got = suggest_merges(
            target, [candidate], threshold=1.0, ratio_fn=lambda left, right: 1.0
        )
        assert len(got) == 1


class TestRealDifflib:
    def test_near_identical_names_suggested_with_difflib_score(self) -> None:
        target = _ident("huawei technologies")
        candidate = _ident("huawei technolgies", spans=("s-2",))
        got = suggest_merges(target, [candidate])
        expected = SequenceMatcher(
            None, "huawei technologies", "huawei technolgies"
        ).ratio()
        assert len(got) == 1
        assert got[0].score == expected
        assert got[0].score >= DEFAULT_SUGGESTION_THRESHOLD

    def test_chinese_company_pair_suggested(self) -> None:
        target = _ident("华为技术有限公司")
        candidate = _ident("华为技术有限责任公司", spans=("s-2",))
        got = suggest_merges(target, [candidate])
        expected = SequenceMatcher(
            None, "华为技术有限公司", "华为技术有限责任公司"
        ).ratio()
        assert len(got) == 1
        assert got[0].score == expected
        assert got[0].score >= DEFAULT_SUGGESTION_THRESHOLD

    def test_distant_names_not_suggested(self) -> None:
        target = _ident("huawei technologies")
        candidate = _ident("beijing byd auto industry", spans=("s-2",))
        assert suggest_merges(target, [candidate]) == ()


class TestFuzzySuggestion:
    def _suggestion(self) -> FuzzySuggestion:
        return FuzzySuggestion(
            target_identity_id=make_identity_id("aaa", "Organization"),
            candidate_identity_id=make_identity_id("bbb", "Organization"),
            candidate_normalized_name="bbb",
            score=0.9,
            reason=SuggestionReason.NAME_SIMILARITY,
        )

    def test_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            self._suggestion().score = 0.1

    def test_round_trip(self) -> None:
        original = self._suggestion()
        assert FuzzySuggestion.from_dict(original.to_dict()) == original

    def test_same_ids_rejected(self) -> None:
        same = make_identity_id("aaa", "Organization")
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id=same,
                candidate_identity_id=same,
                candidate_normalized_name="aaa",
                score=0.5,
                reason=SuggestionReason.NAME_SIMILARITY,
            )

    def test_score_out_of_range_rejected(self) -> None:
        for bad in (1.5, -0.1, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                FuzzySuggestion(
                    target_identity_id=make_identity_id("aaa", "Organization"),
                    candidate_identity_id=make_identity_id("bbb", "Organization"),
                    candidate_normalized_name="bbb",
                    score=bad,
                    reason=SuggestionReason.NAME_SIMILARITY,
                )

    def test_bare_string_reason_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id=make_identity_id("aaa", "Organization"),
                candidate_identity_id=make_identity_id("bbb", "Organization"),
                candidate_normalized_name="bbb",
                score=0.5,
                reason="name_similarity",
            )

    def test_missing_key_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload.pop("score")
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_unknown_key_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["extra"] = 1
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_non_string_keys_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload[1] = "x"
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_non_mapping_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(["nope"])

    def test_bool_score_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id=make_identity_id("aaa", "Organization"),
                candidate_identity_id=make_identity_id("bbb", "Organization"),
                candidate_normalized_name="bbb",
                score=True,
                reason=SuggestionReason.NAME_SIMILARITY,
            )

    def test_empty_target_identity_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id="",
                candidate_identity_id=make_identity_id("bbb", "Organization"),
                candidate_normalized_name="bbb",
                score=0.5,
                reason=SuggestionReason.NAME_SIMILARITY,
            )

    def test_empty_candidate_identity_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id=make_identity_id("aaa", "Organization"),
                candidate_identity_id="",
                candidate_normalized_name="bbb",
                score=0.5,
                reason=SuggestionReason.NAME_SIMILARITY,
            )

    def test_empty_candidate_normalized_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            FuzzySuggestion(
                target_identity_id=make_identity_id("aaa", "Organization"),
                candidate_identity_id=make_identity_id("bbb", "Organization"),
                candidate_normalized_name="",
                score=0.5,
                reason=SuggestionReason.NAME_SIMILARITY,
            )

    def test_from_dict_unknown_reason_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["reason"] = "bogus"
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_from_dict_non_string_reason_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["reason"] = 123
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_from_dict_string_score_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["score"] = "0.5"
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_from_dict_nan_score_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["score"] = float("nan")
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)

    def test_from_dict_inf_score_rejected(self) -> None:
        payload = self._suggestion().to_dict()
        payload["score"] = float("inf")
        with pytest.raises(ValueError):
            FuzzySuggestion.from_dict(payload)


class TestPurity:
    def test_import_allowlist(self) -> None:
        tree = ast.parse(_IMPL.read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add(node.module)
        assert found <= _ALLOWED_IMPORTS

    def test_no_banned_dependencies(self) -> None:
        text = _IMPL.read_text(encoding="utf-8")
        for token in _BANNED_SUBSTRINGS:
            assert token not in text, token
