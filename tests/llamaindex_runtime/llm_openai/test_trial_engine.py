"""TrialEngine adapter tests (fail-closed D2 v2 coverage gate)."""

from __future__ import annotations

import json

import pytest

from llamaindex_runtime.entity.identity import CANONICAL_TYPES
from llamaindex_runtime.llm_openai.client import OpenAICompatClient
from llamaindex_runtime.llm_openai.trial_engine import LlmTrialEngine

from ._helpers import (
    GOOD_ENTITIES,
    GOOD_RELATIONS,
    RELATION_TYPES,
    SAMPLES,
    _ExplodingTransport,
    _QueueTransport,
    _client,
    _trial_engine,
    _trial_payload,
)


class TestLlmTrialEngine:
    def test_full_coverage_is_similar(self) -> None:
        engine, _ = _trial_engine(_trial_payload(GOOD_ENTITIES, GOOD_RELATIONS))
        report = engine.run_trial("batch-1", SAMPLES)
        assert report.coverage_ratio == 1.0
        assert report.homogeneity.value == "similar"
        assert report.batch_id == "batch-1"
        assert report.sample_texts == tuple(SAMPLES)
        assert report.engine_id == "llm-trial-v1"
        assert report.uncovered_items == ()
        assert report.new_type_proposals == ()

    def test_fenced_json_with_surrounding_prose_is_parsed(self) -> None:
        fenced = (
            "前置说明 "
            + "```json"
            + chr(10)
            + json.dumps(
                {"entities": GOOD_ENTITIES, "relations": GOOD_RELATIONS},
                ensure_ascii=False,
            )
            + chr(10)
            + "``` 尾注"
        )
        engine, _ = _trial_engine(fenced)
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == 1.0

    def test_custom_engine_id_is_reported(self) -> None:
        engine, _ = _trial_engine(
            _trial_payload(GOOD_ENTITIES, GOOD_RELATIONS), engine_id="my-engine"
        )
        assert engine.run_trial("b", SAMPLES).engine_id == "my-engine"

    def test_zero_items_never_unlocks_full_coverage(self) -> None:
        engine, _ = _trial_engine(_trial_payload([], []))
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == 0.0
        assert report.homogeneity.value == "heterogeneous"
        assert report.notes == "llm trial: 0/0 in-vocabulary items across 3 sample(s)"
        assert report.uncovered_items == ()
        assert report.new_type_proposals == ()

    def test_unknown_entity_type_uncovered_and_proposed(self) -> None:
        engine, _ = _trial_engine(
            _trial_payload([{"name": "X", "type": "AlienType"}], [])
        )
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == 0.0
        assert report.homogeneity.value == "heterogeneous"
        assert report.uncovered_items == ("entity:AlienType:X",) * len(SAMPLES)
        assert report.new_type_proposals == ("AlienType",)

    def test_unknown_predicate_uncovered(self) -> None:
        engine, _ = _trial_engine(
            _trial_payload([], [{"subject": "a", "predicate": "未知", "object": "b"}])
        )
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == 0.0
        assert report.uncovered_items == ("relation:未知",) * len(SAMPLES)

    def test_known_types_covered(self) -> None:
        assert "Organization" in CANONICAL_TYPES
        engine, _ = _trial_engine(
            _trial_payload(
                [
                    {"name": "李雷", "type": "Person"},
                    {"name": "华为", "type": "Organization"},
                ],
                GOOD_RELATIONS,
            )
        )
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == 1.0

    def test_partial_coverage_heterogeneous(self) -> None:
        first = _trial_payload(
            [{"name": "李雷", "type": "Person"}, {"name": "X", "type": "Alien"}], []
        )
        second = _trial_payload(GOOD_ENTITIES, [])
        third = _trial_payload([], GOOD_RELATIONS)
        contents = [first, second, third]

        transport = _QueueTransport(contents)
        client = OpenAICompatClient(
            model="m", base_url="http://x", api_key="k", transport=transport
        )
        engine = LlmTrialEngine(client=client, relation_types=RELATION_TYPES)
        report = engine.run_trial("b", SAMPLES)
        assert report.coverage_ratio == pytest.approx(3 / 4)
        assert report.homogeneity.value == "heterogeneous"
        assert report.uncovered_items == ("entity:Alien:X",)
        assert report.new_type_proposals == ("Alien",)

    def test_prompt_lists_vocabularies(self) -> None:
        engine, transport = _trial_engine(_trial_payload([], []))
        engine.run_trial("b", SAMPLES)
        prompt = transport.calls[0]["messages"][0]["content"]
        assert "Organization" in prompt
        assert "总部位于" in prompt
        assert "文本一" in prompt

    def test_invalid_json_raises(self) -> None:
        engine, _ = _trial_engine("this is not json")
        with pytest.raises(ValueError, match="JSON object"):
            engine.run_trial("b", SAMPLES)

    @pytest.mark.parametrize(
        "payload",
        [
            {"entities": "x"},
            {"entities": [42]},
            {"entities": [{"name": ""}]},
            {"entities": [{"name": "a", "type": ""}]},
            {"entities": [], "relations": "x"},
            {"entities": [], "relations": [42]},
            {"entities": [], "relations": [{"predicate": ""}]},
        ],
    )
    def test_malformed_payloads_fail_closed(self, payload: object) -> None:
        engine, _ = _trial_engine(json.dumps(payload, ensure_ascii=False))
        with pytest.raises(ValueError):
            engine.run_trial("b", SAMPLES)

    def test_transport_failure_propagates(self) -> None:
        client = OpenAICompatClient(
            model="m",
            base_url="http://x",
            api_key="k",
            transport=_ExplodingTransport(ValueError("boom")),
        )
        engine = LlmTrialEngine(client=client, relation_types=RELATION_TYPES)
        with pytest.raises(ValueError, match="boom"):
            engine.run_trial("b", SAMPLES)

    def test_too_few_samples_rejected(self) -> None:
        engine, transport = _trial_engine(_trial_payload([], []))
        with pytest.raises(ValueError, match="MIN_TRIAL_SAMPLES"):
            engine.run_trial("b", ["只有一条"])
        assert transport.calls == []

    def test_bare_string_samples_rejected(self) -> None:
        engine, _ = _trial_engine(_trial_payload([], []))
        with pytest.raises(ValueError, match="not a bare string"):
            engine.run_trial("b", "abc")

    @pytest.mark.parametrize("bad", [True, 0, 0.0, 1.5, float("nan")])
    def test_rejects_bad_threshold(self, bad: object) -> None:
        client, _ = _client("x")
        with pytest.raises(ValueError, match="coverage_threshold must be"):
            LlmTrialEngine(
                client=client,
                relation_types=RELATION_TYPES,
                coverage_threshold=bad,  # type: ignore[arg-type]
            )

    def test_rejects_bad_relation_types(self) -> None:
        client, _ = _client("x")
        with pytest.raises(ValueError, match="frozenset"):
            LlmTrialEngine(
                client=client, relation_types=["总部位于"]  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="must not be empty"):
            LlmTrialEngine(client=client, relation_types=frozenset())
        with pytest.raises(ValueError, match="non-blank strings"):
            LlmTrialEngine(
                client=client,
                relation_types=frozenset({"ok", 42}),  # type: ignore[arg-type]
            )

    def test_rejects_non_client(self) -> None:
        with pytest.raises(ValueError, match="OpenAICompatClient"):
            LlmTrialEngine(
                client=42,  # type: ignore[arg-type]
                relation_types=RELATION_TYPES,
            )
