"""Phase 17-W3 contract tests for the trial-extraction router (TDD, round 2).

Pins llamaindex_runtime/extraction/trial.py against the frozen W3
contract (master plan section 14) implementing the D2 v2 quantitative
coverage gate (master plan section 11), plus the round-2 review fixes:
minimum-sample hard gate, unknown-key rejection, Mapping boundary
robustness, total threshold validation, report type gate and AST-level
import purity. No model is loaded, no network is touched and no
filesystem I/O happens beyond reading the two module sources for the
purity pins:

- COVERAGE_THRESHOLD is the frozen 0.90 quantitative gate and
  MIN_TRIAL_SAMPLES the frozen 3-sample floor from section 11; pure UIE
  is a reward path, never the default path.
- TrialReport is fail-closed on construction (bad coverage numbers,
  empty ids, undersized samples, non-member homogeneity) and round-trips
  strictly through to_dict/from_dict: unknown keys are rejected,
  required keys are never silently defaulted, optional keys fall back
  to the frozen empty defaults.
- decide_route is deterministic: SIMILAR at/above the threshold routes
  PURE_UIE, SIMILAR below routes LLM_THEN_UIE, HETEROGENEOUS always
  routes LLM_PRIMARY_UIE_ASSIST -- coverage never rescues a mixed
  batch; every invalid threshold and non-TrialReport input is rejected
  with ValueError.
- TrialEngine is the seam protocol; the real engine arrives in a later
  wave. A fake engine here proves the seam type-checks and feeds the
  router.
- Module purity: both extraction modules import exactly the whitelisted
  stdlib roots and never name a heavy NLP framework.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from llamaindex_runtime.extraction import trial as trial_module
from llamaindex_runtime.extraction.trial import (
    COVERAGE_THRESHOLD,
    BatchHomogeneity,
    ExtractionRoute,
    RouteDecision,
    TrialEngine,
    TrialReport,
    decide_route,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTRACTION_DIR = _REPO_ROOT / "llamaindex_runtime" / "extraction"
_TRIAL_SOURCE = (_EXTRACTION_DIR / "trial.py").read_text(encoding="utf-8")
_INIT_SOURCE = (_EXTRACTION_DIR / "__init__.py").read_text(encoding="utf-8")

_REQUIRED_KEYS = (
    "batch_id",
    "sample_texts",
    "coverage_ratio",
    "homogeneity",
    "engine_id",
)

_ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "math",
    "collections.abc",
    "dataclasses",
    "enum",
    "typing",
}


def _report(**overrides: Any) -> TrialReport:
    """Valid baseline TrialReport (3 samples per the section 11 floor)."""
    kwargs: dict[str, Any] = {
        "batch_id": "batch-2026-09-01-001",
        "sample_texts": (
            "样本一：李雷在北京使用华为Mate60。",
            "样本二：韩梅梅发布了新产品。",
            "样本三：韩梅梅在北京发布了新产品。",
        ),
        "coverage_ratio": 0.95,
        "homogeneity": BatchHomogeneity.SIMILAR,
        "engine_id": "fake-trial-engine-v1",
    }
    kwargs.update(overrides)
    return TrialReport(**kwargs)


class TestCoverageThresholdGate:
    """0.90 边界: == 阈值 → PURE_UIE; 阈值-0.001 → LLM_THEN_UIE."""

    def test_coverage_threshold_is_frozen_default(self) -> None:
        assert COVERAGE_THRESHOLD == 0.90
        assert type(COVERAGE_THRESHOLD) is float

    def test_similar_coverage_equal_threshold_routes_pure_uie(self) -> None:
        report = _report(coverage_ratio=COVERAGE_THRESHOLD)
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.PURE_UIE
        assert decision.coverage_ratio == COVERAGE_THRESHOLD
        assert decision.threshold == COVERAGE_THRESHOLD

    def test_similar_coverage_just_below_threshold_routes_llm_then_uie(
        self,
    ) -> None:
        report = _report(coverage_ratio=COVERAGE_THRESHOLD - 0.001)
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.LLM_THEN_UIE

    def test_similar_full_coverage_routes_pure_uie(self) -> None:
        decision = decide_route(_report(coverage_ratio=1.0))
        assert decision.route is ExtractionRoute.PURE_UIE

    def test_similar_zero_coverage_routes_llm_then_uie(self) -> None:
        decision = decide_route(_report(coverage_ratio=0.0))
        assert decision.route is ExtractionRoute.LLM_THEN_UIE


class TestHeterogeneousGate:
    """大杂烩批: 覆盖率救不了 (§11: 大杂烩 → LLM 为主 UIE 辅助)."""

    def test_heterogeneous_full_coverage_still_routes_llm_primary(self) -> None:
        report = _report(
            homogeneity=BatchHomogeneity.HETEROGENEOUS,
            coverage_ratio=1.0,
        )
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.LLM_PRIMARY_UIE_ASSIST

    def test_heterogeneous_low_coverage_routes_llm_primary(self) -> None:
        report = _report(
            homogeneity=BatchHomogeneity.HETEROGENEOUS,
            coverage_ratio=0.4,
        )
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.LLM_PRIMARY_UIE_ASSIST


class TestCustomThreshold:
    def test_lower_threshold_admits_pure_uie(self) -> None:
        decision = decide_route(_report(coverage_ratio=0.6), threshold=0.5)
        assert decision.route is ExtractionRoute.PURE_UIE
        assert decision.threshold == 0.5

    def test_lower_threshold_boundary_exact(self) -> None:
        at = decide_route(_report(coverage_ratio=0.5), threshold=0.5)
        below = decide_route(_report(coverage_ratio=0.4999), threshold=0.5)
        assert at.route is ExtractionRoute.PURE_UIE
        assert below.route is ExtractionRoute.LLM_THEN_UIE

    def test_threshold_one_admits_only_full_coverage(self) -> None:
        full = decide_route(_report(coverage_ratio=1.0), threshold=1.0)
        almost = decide_route(_report(coverage_ratio=0.999), threshold=1.0)
        assert full.route is ExtractionRoute.PURE_UIE
        assert almost.route is ExtractionRoute.LLM_THEN_UIE


class TestThresholdValidation:
    @pytest.mark.parametrize(
        "bad_threshold",
        [
            pytest.param(0.0, id="zero"),
            pytest.param(-0.1, id="negative"),
            pytest.param(1.01, id="above-one"),
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="inf"),
            pytest.param(float("-inf"), id="negative-inf"),
            pytest.param(10**400, id="huge-int"),
            pytest.param(True, id="bool-true"),
            pytest.param(False, id="bool-false"),
        ],
    )
    def test_decide_route_rejects_invalid_threshold(self, bad_threshold: float) -> None:
        with pytest.raises(ValueError, match="threshold"):
            decide_route(_report(), threshold=bad_threshold)


class TestTrialReportFailClosed:
    """拒收矩阵: 违反 → ValueError 且消息含字段名."""

    def test_rejects_nan_coverage(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            _report(coverage_ratio=float("nan"))

    def test_rejects_infinite_coverage(self) -> None:
        for bad in (float("inf"), float("-inf")):
            with pytest.raises(ValueError, match="coverage_ratio"):
                _report(coverage_ratio=bad)

    def test_rejects_negative_coverage(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            _report(coverage_ratio=-0.0001)

    def test_rejects_coverage_above_one(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            _report(coverage_ratio=1.0001)

    def test_rejects_non_float_coverage(self) -> None:
        # 契约钉死: coverage_ratio 必须是 float, int 一律拒收.
        with pytest.raises(ValueError, match="coverage_ratio"):
            _report(coverage_ratio=1)

    def test_rejects_bool_coverage(self) -> None:
        # 钉死: bool 是 int 子类, True/False 一律拒收 (构造路径).
        for bad in (True, False):
            with pytest.raises(ValueError, match="coverage_ratio"):
                _report(coverage_ratio=bad)

    def test_rejects_empty_batch_id(self) -> None:
        with pytest.raises(ValueError, match="batch_id"):
            _report(batch_id="")

    def test_rejects_non_string_batch_id(self) -> None:
        with pytest.raises(ValueError, match="batch_id"):
            _report(batch_id=7)

    def test_rejects_empty_sample_texts(self) -> None:
        with pytest.raises(ValueError, match="sample_texts"):
            _report(sample_texts=())

    def test_rejects_sample_texts_with_empty_string(self) -> None:
        with pytest.raises(ValueError, match="sample_texts"):
            _report(sample_texts=("有内容一", "有内容二", "有内容三", ""))

    def test_rejects_non_string_sample_item(self) -> None:
        with pytest.raises(ValueError, match="sample_texts"):
            _report(sample_texts=("有内容一", "有内容二", "有内容三", 3))

    def test_rejects_empty_engine_id(self) -> None:
        with pytest.raises(ValueError, match="engine_id"):
            _report(engine_id="")

    def test_rejects_plain_str_homogeneity(self) -> None:
        # 契约钉死: 只收 BatchHomogeneity 成员, 裸 str 拒收不转换.
        with pytest.raises(ValueError, match="homogeneity"):
            _report(homogeneity="similar")

    def test_rejects_unknown_homogeneity_str(self) -> None:
        with pytest.raises(ValueError, match="homogeneity"):
            _report(homogeneity="bogus")


class TestMinimumSampleGate:
    """§11: 每批必经 LLM 试抽 3~5 篇 — 样本量下限 3 是硬门 (评审加固)."""

    def test_min_trial_samples_constant_is_frozen_three(self) -> None:
        assert trial_module.MIN_TRIAL_SAMPLES == 3
        assert type(trial_module.MIN_TRIAL_SAMPLES) is int

    def test_report_rejects_two_samples(self) -> None:
        with pytest.raises(ValueError, match="MIN_TRIAL_SAMPLES"):
            _report(sample_texts=("样本一", "样本二"))

    def test_report_rejects_one_sample(self) -> None:
        with pytest.raises(ValueError, match="MIN_TRIAL_SAMPLES"):
            _report(sample_texts=("样本一",))

    def test_report_accepts_exactly_three_samples(self) -> None:
        report = _report(sample_texts=("样本一", "样本二", "样本三"))
        assert len(report.sample_texts) == 3

    def test_message_reports_actual_sample_count(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            _report(sample_texts=("样本一", "样本二"))
        message = str(excinfo.value)
        assert "MIN_TRIAL_SAMPLES" in message
        assert "2" in message

    def test_from_dict_rejects_two_samples(self) -> None:
        payload = _report().to_dict()
        payload["sample_texts"] = ["样本一", "样本二"]
        with pytest.raises(ValueError, match="MIN_TRIAL_SAMPLES"):
            TrialReport.from_dict(payload)


class TestTrialReportSerialization:
    def test_from_dict_rejects_non_mapping(self) -> None:
        for bad in ([1, 2], "not-a-mapping", None, 42):
            with pytest.raises(ValueError, match="mapping"):
                TrialReport.from_dict(bad)

    @pytest.mark.parametrize("required_key", _REQUIRED_KEYS)
    def test_from_dict_missing_required_key_reports_key_name(
        self, required_key: str
    ) -> None:
        payload = _report().to_dict()
        del payload[required_key]
        with pytest.raises(ValueError) as excinfo:
            TrialReport.from_dict(payload)
        assert required_key in str(excinfo.value)

    def test_from_dict_missing_multiple_keys_lists_all(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            TrialReport.from_dict({"notes": "只有可选键"})
        message = str(excinfo.value)
        for key in _REQUIRED_KEYS:
            assert key in message

    def test_from_dict_rejects_single_unknown_key(self) -> None:
        payload = _report().to_dict()
        payload["sneaky_extra"] = 1
        with pytest.raises(ValueError, match="unknown"):
            TrialReport.from_dict(payload)

    def test_from_dict_unknown_key_message_names_the_key(self) -> None:
        payload = _report().to_dict()
        payload["sneaky_extra"] = 1
        with pytest.raises(ValueError) as excinfo:
            TrialReport.from_dict(payload)
        assert "sneaky_extra" in str(excinfo.value)

    def test_from_dict_rejects_multiple_unknown_keys(self) -> None:
        payload = _report().to_dict()
        payload["extra_a"] = 1
        payload["extra_b"] = 2
        with pytest.raises(ValueError) as excinfo:
            TrialReport.from_dict(payload)
        message = str(excinfo.value)
        assert "extra_a" in message
        assert "extra_b" in message

    def test_from_dict_mixed_missing_and_unknown_lists_both(self) -> None:
        payload = _report().to_dict()
        del payload["batch_id"]
        del payload["engine_id"]
        payload["extra_a"] = 1
        with pytest.raises(ValueError) as excinfo:
            TrialReport.from_dict(payload)
        message = str(excinfo.value)
        assert "batch_id" in message
        assert "engine_id" in message
        assert "extra_a" in message

    def test_from_dict_rejects_invalid_homogeneity_value(self) -> None:
        payload = _report().to_dict()
        payload["homogeneity"] = "bogus"
        with pytest.raises(ValueError, match="homogeneity"):
            TrialReport.from_dict(payload)

    def test_from_dict_accepts_enum_value_string(self) -> None:
        payload = _report().to_dict()
        assert payload["homogeneity"] == "similar"
        report = TrialReport.from_dict(payload)
        assert report.homogeneity is BatchHomogeneity.SIMILAR

    def test_from_dict_rejects_bad_coverage_value(self) -> None:
        payload = _report().to_dict()
        payload["coverage_ratio"] = 1.5
        with pytest.raises(ValueError, match="coverage_ratio"):
            TrialReport.from_dict(payload)

    def test_from_dict_rejects_bool_and_int_coverage(self) -> None:
        # 钉死: JSON 通道来的 int/bool 覆盖率一律拒收 (必须精确 float).
        for bad in (True, False, 1):
            payload = _report().to_dict()
            payload["coverage_ratio"] = bad
            with pytest.raises(ValueError, match="coverage_ratio"):
                TrialReport.from_dict(payload)

    def test_from_dict_rejects_bad_engine_id_value(self) -> None:
        payload = _report().to_dict()
        payload["engine_id"] = ""
        with pytest.raises(ValueError, match="engine_id"):
            TrialReport.from_dict(payload)

    def test_round_trip_preserves_all_fields(self) -> None:
        original = TrialReport(
            batch_id="batch-2026-09-01-002",
            sample_texts=("样本甲", "样本乙", "样本丙"),
            coverage_ratio=0.72,
            uncovered_items=("未覆盖: 新品发布日期", "未覆盖: 涉案金额"),
            new_type_proposals=("发布事件",),
            homogeneity=BatchHomogeneity.HETEROGENEOUS,
            engine_id="engine-x",
            notes="分歧两条待人工复核",
        )
        restored = TrialReport.from_dict(original.to_dict())
        assert restored == original
        assert restored.to_dict() == original.to_dict()

    def test_round_trip_through_json_with_default_optionals(self) -> None:
        original = _report()
        restored = TrialReport.from_dict(json.loads(json.dumps(original.to_dict())))
        assert restored == original
        assert restored.uncovered_items == ()
        assert restored.new_type_proposals == ()
        assert restored.notes == ""

    def test_from_dict_defaults_optionals_when_absent(self) -> None:
        payload = {
            key: value
            for key, value in _report().to_dict().items()
            if key in _REQUIRED_KEYS
        }
        report = TrialReport.from_dict(payload)
        assert report.uncovered_items == ()
        assert report.new_type_proposals == ()
        assert report.notes == ""

    def test_to_dict_is_json_safe_and_stores_enum_value(self) -> None:
        payload = _report(homogeneity=BatchHomogeneity.HETEROGENEOUS).to_dict()
        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["homogeneity"] == "heterogeneous"
        assert decoded["sample_texts"] == [
            "样本一：李雷在北京使用华为Mate60。",
            "样本二：韩梅梅发布了新产品。",
            "样本三：韩梅梅在北京发布了新产品。",
        ]
        assert decoded["coverage_ratio"] == 0.95


class TestMappingBoundary:
    """Mapping 入口只依赖 k in raw / raw[k]: 缺 .get 的注册 Mapping 不炸."""

    @staticmethod
    def _bare_dict(data: dict[str, object]) -> object:
        class BareDict:
            def __getitem__(self, key: str) -> object:
                return data[key]

            def __iter__(self) -> Iterator[str]:
                return iter(data)

            def __len__(self) -> int:
                return len(data)

        Mapping.register(BareDict)
        return BareDict()

    def test_from_dict_accepts_mapping_without_get(self) -> None:
        bare = self._bare_dict(dict(_report().to_dict()))
        assert isinstance(bare, Mapping)
        assert not hasattr(bare, "get")
        assert TrialReport.from_dict(bare) == _report()

    def test_missing_keys_is_valueerror_not_attributeerror(self) -> None:
        bare = self._bare_dict({"notes": "缺全部必填键"})
        with pytest.raises(ValueError, match="missing required keys"):
            TrialReport.from_dict(bare)

    def test_unknown_key_is_valueerror_not_attributeerror(self) -> None:
        full = dict(_report().to_dict())
        full["sneaky_extra"] = 1
        bare = self._bare_dict(full)
        with pytest.raises(ValueError, match="unknown"):
            TrialReport.from_dict(bare)


class TestPassthrough:
    def test_uncovered_and_proposals_pass_through_on_pure_uie(self) -> None:
        report = _report(
            coverage_ratio=0.95,
            uncovered_items=("未覆盖: 新品发布日期",),
            new_type_proposals=("发布事件",),
        )
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.PURE_UIE
        assert decision.uncovered_items == report.uncovered_items
        assert decision.new_type_proposals == report.new_type_proposals

    def test_uncovered_and_proposals_pass_through_on_llm_then_uie(self) -> None:
        report = _report(
            coverage_ratio=0.7,
            uncovered_items=("未覆盖: 公司注册资本", "未覆盖: 涉案金额"),
            new_type_proposals=("资本变动",),
        )
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.LLM_THEN_UIE
        assert decision.uncovered_items == report.uncovered_items
        assert decision.new_type_proposals == report.new_type_proposals

    def test_uncovered_and_proposals_pass_through_on_heterogeneous(self) -> None:
        report = _report(
            homogeneity=BatchHomogeneity.HETEROGENEOUS,
            coverage_ratio=1.0,
            uncovered_items=("未覆盖: 天气类事实",),
            new_type_proposals=("气象事件",),
        )
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.LLM_PRIMARY_UIE_ASSIST
        assert decision.uncovered_items == report.uncovered_items
        assert decision.new_type_proposals == report.new_type_proposals


class TestRationale:
    def test_rationale_nonempty_numeric_and_homogeneity_all_routes(self) -> None:
        cases = [
            (_report(coverage_ratio=0.95), ExtractionRoute.PURE_UIE),
            (_report(coverage_ratio=0.7), ExtractionRoute.LLM_THEN_UIE),
            (
                _report(
                    homogeneity=BatchHomogeneity.HETEROGENEOUS,
                    coverage_ratio=0.95,
                ),
                ExtractionRoute.LLM_PRIMARY_UIE_ASSIST,
            ),
        ]
        for report, route in cases:
            decision = decide_route(report)
            assert decision.rationale
            assert f"{report.coverage_ratio:.3f}" in decision.rationale
            assert f"{COVERAGE_THRESHOLD:.3f}" in decision.rationale
            assert report.homogeneity.value in decision.rationale
            assert decision.route is route

    def test_default_threshold_rationale_contains_09_text(self) -> None:
        decision = decide_route(_report(coverage_ratio=0.9))
        assert "0.9" in decision.rationale


class TestRouteDecisionShape:
    def test_decision_frozen_and_field_complete(self) -> None:
        decision = decide_route(_report(coverage_ratio=0.8))
        assert isinstance(decision, RouteDecision)
        assert decision.batch_id == "batch-2026-09-01-001"
        assert decision.coverage_ratio == 0.8
        assert decision.threshold == COVERAGE_THRESHOLD
        assert decision.uncovered_items == ()
        assert decision.new_type_proposals == ()
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.route = ExtractionRoute.PURE_UIE  # type: ignore[misc]

    def test_decide_route_rejects_duck_typed_report(self) -> None:
        @dataclasses.dataclass(frozen=True)
        class DuckReport:
            batch_id: str = "batch-duck"
            sample_texts: tuple[str, ...] = ("样本1", "样本2", "样本3")
            coverage_ratio: float = 0.95
            uncovered_items: tuple[str, ...] = ()
            new_type_proposals: tuple[str, ...] = ()
            homogeneity: BatchHomogeneity = BatchHomogeneity.SIMILAR
            engine_id: str = "duck-engine"
            notes: str = ""

        # 字段齐全但未经 __post_init__ 校验的裸 dataclass 必须被拒收.
        with pytest.raises(ValueError, match="TrialReport"):
            decide_route(DuckReport())  # type: ignore[arg-type]


class TestTrialEngineSeam:
    """TrialEngine 是 seam; 真实引擎在后续 wave 接入."""

    def test_fake_engine_satisfies_protocol_and_feeds_router(self) -> None:
        class FakeEngine:
            def run_trial(
                self, batch_id: str, sample_texts: Sequence[str]
            ) -> TrialReport:
                return TrialReport(
                    batch_id=batch_id,
                    sample_texts=tuple(sample_texts),
                    coverage_ratio=0.93,
                    homogeneity=BatchHomogeneity.SIMILAR,
                    engine_id="fake-trial-engine-v1",
                )

        assert isinstance(FakeEngine(), TrialEngine)
        engine: TrialEngine = FakeEngine()
        report = engine.run_trial("batch-seam-001", ("样本1", "样本2", "样本3"))
        assert isinstance(report, TrialReport)
        decision = decide_route(report)
        assert decision.route is ExtractionRoute.PURE_UIE
        assert decision.batch_id == "batch-seam-001"


class TestModulePurity:
    @staticmethod
    def _import_roots(source: str) -> set[str]:
        roots: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # 包内相对导入 (from .trial import ...)
                if node.module:
                    roots.add(node.module)
        return roots

    def test_import_roots_exactly_match_stdlib_whitelist(self) -> None:
        trial_roots = self._import_roots(_TRIAL_SOURCE)
        init_roots = self._import_roots(_INIT_SOURCE)
        assert trial_roots | init_roots == _ALLOWED_IMPORT_ROOTS
        assert trial_roots <= _ALLOWED_IMPORT_ROOTS
        assert init_roots <= _ALLOWED_IMPORT_ROOTS

    def test_sources_have_no_heavy_framework_substrings(self) -> None:
        for source in (_TRIAL_SOURCE, _INIT_SOURCE):
            for banned in ("paddle", "torch", "transformers"):
                assert banned not in source


class TestPackageSurface:
    def test_package_exports_frozen_public_api(self) -> None:
        import llamaindex_runtime.extraction as extraction_pkg

        assert set(extraction_pkg.__all__) == {
            "COVERAGE_THRESHOLD",
            "MIN_TRIAL_SAMPLES",
            "BatchHomogeneity",
            "ExtractionRoute",
            "RouteDecision",
            "TrialEngine",
            "TrialReport",
            "decide_route",
        }
        for name in extraction_pkg.__all__:
            assert getattr(extraction_pkg, name) is not None
        assert extraction_pkg.COVERAGE_THRESHOLD == 0.90
        assert extraction_pkg.MIN_TRIAL_SAMPLES == 3
        assert extraction_pkg.TrialReport is TrialReport
        assert extraction_pkg.decide_route is decide_route
