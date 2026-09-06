"""Phase 17-W3 deterministic trial-extraction router (pure stdlib, no IO).

Implements the frozen W3 contract (master plan section 14) on top of the
D2 v2 quantitative coverage gate (master plan section 11): every batch
must pass an LLM trial extraction whose report states how well the
legacy schema covers the sampled facts. This module turns such a trial
report into a deterministic extraction-route decision. It never runs an
extractor, never loads a model, never touches the network and never
performs I/O.

Frozen vocabulary and constants:

- BatchHomogeneity: similar | heterogeneous -- batch structure verdict.
- ExtractionRoute: pure_uie | llm_then_uie | llm_primary_uie_assist.
- COVERAGE_THRESHOLD = 0.90: the frozen quantitative coverage gate from
  section 11 (D2 v2); pure UIE is a reward path, never the default path.
- MIN_TRIAL_SAMPLES = 3: the frozen per-batch sample floor from section
  11 ("每批必经, 3~5 篇"); reports built from fewer samples are rejected,
  never downgraded.

Deterministic routing rules (report in -> route out, no classifier):

- homogeneity SIMILAR and coverage_ratio >= threshold -> PURE_UIE.
- homogeneity SIMILAR and coverage_ratio < threshold -> LLM_THEN_UIE.
- homogeneity HETEROGENEOUS -> LLM_PRIMARY_UIE_ASSIST whatever the
  coverage ratio is (coverage never rescues a mixed batch).

来源认证边界: from_dict 仅做形状校验, 不认证报告来源与覆盖率真实性;
调用方只允许喂入 conforming TrialEngine 的产出或经认证通道传输的报告。
engine_id 目前无格式约束, 允许清单/格式约定留待真实试抽引擎接入 wave
再加。

from_dict 校验边界精确措辞: required keys 从不静默填默认 (缺失即拒);
可选键 (uncovered_items/new_type_proposals/notes) 缺失时回退到冻结空
默认 () / ""; 未知键一律拒收 (试抽报告证据必须完整往返, 呼应 §11 试抽
报告强制落盘)。

fail-closed: 上游拿不到试抽报告或报告构造失败时, 调用方不得调用本模块
-- 无试抽报告, 不抽取 (no trial report, no batch extraction).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

__all__ = [
    "COVERAGE_THRESHOLD",
    "MIN_TRIAL_SAMPLES",
    "BatchHomogeneity",
    "ExtractionRoute",
    "RouteDecision",
    "TrialEngine",
    "TrialReport",
    "decide_route",
]

# 主规划 §11 D2 v2 量化覆盖门: 覆盖率 >= COVERAGE_THRESHOLD 且结构相似
# 才允许纯 UIE 全批抽取 (纯 UIE 是奖励路径, 不是默认路径)。
COVERAGE_THRESHOLD: Final[float] = 0.90

# 主规划 §11: "LLM 试抽 (每批必经, 3~5 篇)" -- 每批样本量下限 3 是硬门,
# 少于 3 篇的试抽报告一律拒收 (证据不足不放行)。
MIN_TRIAL_SAMPLES: Final[int] = 3

_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "batch_id",
    "sample_texts",
    "coverage_ratio",
    "homogeneity",
    "engine_id",
)

_OPTIONAL_KEYS: Final[tuple[str, ...]] = (
    "uncovered_items",
    "new_type_proposals",
    "notes",
)

_KNOWN_KEYS: Final[frozenset[str]] = frozenset(_REQUIRED_KEYS + _OPTIONAL_KEYS)


class BatchHomogeneity(StrEnum):
    """Frozen batch-structure verdict vocabulary."""

    SIMILAR = "similar"
    HETEROGENEOUS = "heterogeneous"


class ExtractionRoute(StrEnum):
    """Frozen extraction-route vocabulary (D2 v2, three routes only)."""

    PURE_UIE = "pure_uie"
    LLM_THEN_UIE = "llm_then_uie"
    LLM_PRIMARY_UIE_ASSIST = "llm_primary_uie_assist"


@runtime_checkable
class TrialEngine(Protocol):
    """试抽引擎 seam: 真实引擎 (与 R3 引擎选择解耦) 在后续 wave 接入。

    A conforming engine runs the per-batch LLM trial extraction and
    returns a contract-valid TrialReport. It must fail closed itself:
    when no trial report can be produced the caller must not extract,
    and this module must never be invoked.
    """

    def run_trial(self, batch_id: str, sample_texts: Sequence[str]) -> TrialReport:
        """Run the trial extraction for one batch and report the verdict."""
        ...


@dataclass(frozen=True)
class TrialReport:
    """One trial-extraction report (batch evidence, fail-closed value).

    notes 是有意的第 8 字段扩展 (W3 评审通过, 协调器将在主规划 §14 补记):
    自由文本的评审/工程备注随批次证据一起落盘。
    """

    batch_id: str
    sample_texts: tuple[str, ...]
    coverage_ratio: float
    uncovered_items: tuple[str, ...] = ()
    new_type_proposals: tuple[str, ...] = ()
    homogeneity: BatchHomogeneity = field(kw_only=True)
    engine_id: str = field(kw_only=True)
    notes: str = ""

    def __post_init__(self) -> None:
        """Single point of field validation (from_dict delegates here)."""
        if type(self.batch_id) is not str or not self.batch_id:
            raise ValueError("batch_id must be a non-empty string")
        if (
            not isinstance(self.sample_texts, (list, tuple))
            or not self.sample_texts
            or any(type(text) is not str or not text for text in self.sample_texts)
        ):
            raise ValueError(
                "sample_texts must be a non-empty sequence of non-empty strings"
            )
        object.__setattr__(self, "sample_texts", tuple(self.sample_texts))
        if len(self.sample_texts) < MIN_TRIAL_SAMPLES:
            raise ValueError(
                "sample_texts must have at least "
                f"MIN_TRIAL_SAMPLES={MIN_TRIAL_SAMPLES} samples "
                f"(got {len(self.sample_texts)})"
            )
        if (
            type(self.coverage_ratio) is not float
            or not math.isfinite(self.coverage_ratio)
            or not 0.0 <= self.coverage_ratio <= 1.0
        ):
            raise ValueError("coverage_ratio must be a finite float in [0, 1]")
        if not isinstance(self.homogeneity, BatchHomogeneity):
            raise ValueError(
                "homogeneity must be a BatchHomogeneity member "
                "(plain str is rejected, never coerced)"
            )
        if type(self.engine_id) is not str or not self.engine_id:
            raise ValueError("engine_id must be a non-empty string")
        if type(self.notes) is not str:
            raise ValueError("notes must be a string")
        for name, items in (
            ("uncovered_items", self.uncovered_items),
            ("new_type_proposals", self.new_type_proposals),
        ):
            if not isinstance(items, (list, tuple)) or any(
                type(item) is not str or not item for item in items
            ):
                raise ValueError(f"{name} must be a sequence of non-empty strings")
            object.__setattr__(self, name, tuple(items))

    def to_dict(self) -> dict[str, object]:
        """JSON-safe snapshot; homogeneity is stored as its enum value."""
        return {
            "batch_id": self.batch_id,
            "sample_texts": list(self.sample_texts),
            "coverage_ratio": self.coverage_ratio,
            "uncovered_items": list(self.uncovered_items),
            "new_type_proposals": list(self.new_type_proposals),
            "homogeneity": self.homogeneity.value,
            "engine_id": self.engine_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: object) -> TrialReport:
        """Rebuild a report from a to_dict payload; fails closed.

        Shape validation only: from_dict 仅做形状校验, 不认证报告来源与
        覆盖率真实性; 调用方只允许喂入 conforming TrialEngine 的产出或
        经认证通道传输的报告 (engine_id 格式约束留待真实引擎 wave)。
        Non-mapping payloads are rejected; every missing required key
        and every unknown key is listed in one ValueError (required
        keys 从不静默填默认, 缺失即拒; 未知键拒收 -- 试抽报告证据必须
        完整往返); optional keys (uncovered_items / new_type_proposals /
        notes) fall back to the frozen empty defaults () / "" when
        absent. Field validation is single-sourced in __post_init__ via
        cls(...); homogeneity is the only boundary conversion (enum
        value string -> member). Reads rely on "k in raw" membership and
        raw[key] subscripting only, so a registered Mapping without a
        .get method takes the same fail-closed path.
        """
        if not isinstance(raw, Mapping):
            raise ValueError("trial report payload must be a mapping")
        missing = [key for key in _REQUIRED_KEYS if key not in raw]
        unknown = [key for key in raw if key not in _KNOWN_KEYS]
        if missing or unknown:
            details: list[str] = []
            if missing:
                details.append("missing required keys: " + ", ".join(missing))
            if unknown:
                details.append(
                    "unknown keys: " + ", ".join(str(key) for key in unknown)
                )
            raise ValueError("trial report payload rejected: " + "; ".join(details))
        try:
            homogeneity = BatchHomogeneity(raw["homogeneity"])
        except ValueError:
            raise ValueError(
                "homogeneity must be one of "
                f"{[member.value for member in BatchHomogeneity]}, "
                f"got {raw['homogeneity']!r}"
            ) from None
        return cls(
            batch_id=raw["batch_id"],
            sample_texts=raw["sample_texts"],
            coverage_ratio=raw["coverage_ratio"],
            uncovered_items=(
                raw["uncovered_items"] if "uncovered_items" in raw else ()
            ),
            new_type_proposals=(
                raw["new_type_proposals"] if "new_type_proposals" in raw else ()
            ),
            homogeneity=homogeneity,
            engine_id=raw["engine_id"],
            notes=raw["notes"] if "notes" in raw else "",
        )


@dataclass(frozen=True)
class RouteDecision:
    """Deterministic routing outcome for one trial-extraction report."""

    batch_id: str
    route: ExtractionRoute
    coverage_ratio: float
    threshold: float
    uncovered_items: tuple[str, ...]
    new_type_proposals: tuple[str, ...]
    rationale: str


def decide_route(
    report: TrialReport, *, threshold: float = COVERAGE_THRESHOLD
) -> RouteDecision:
    """Route one trial report; deterministic, no classifier involved.

    report must be a contract-valid TrialReport: duck-typed look-alikes
    are rejected, because only __post_init__-validated evidence may
    drive routing. threshold must be a finite number in (0, 1]: zero,
    negative, above-one, non-finite, bool and unconvertible (overflowing
    integer) thresholds are all rejected with ValueError. SIMILAR
    batches route by the quantitative coverage gate (at/above the
    threshold admits pure UIE, below it requires LLM-then-UIE);
    HETEROGENEOUS batches always route to LLM-primary-UIE-assist --
    coverage never rescues a mixed batch.
    """
    if not isinstance(report, TrialReport):
        raise ValueError("report must be a TrialReport")
    # 有意的不对称 (评审 F-06): coverage_ratio 是落盘证据, 构造时要求
    # 精确 float; threshold 是调用方配置, 接受 int|float (先经 float()
    # 归一); bool 两边一律拒收。
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("threshold must be a finite number in (0, 1]")
    try:
        threshold_value = float(threshold)
    except OverflowError:
        raise ValueError("threshold must be a finite number in (0, 1]") from None
    if not math.isfinite(threshold_value) or not 0.0 < threshold_value <= 1.0:
        raise ValueError("threshold must be a finite number in (0, 1]")
    coverage = report.coverage_ratio
    if report.homogeneity is BatchHomogeneity.HETEROGENEOUS:
        route = ExtractionRoute.LLM_PRIMARY_UIE_ASSIST
        rationale = (
            f"试抽判定本批为异构大杂烩（homogeneity={report.homogeneity.value}），"
            f"覆盖率 {coverage:.3f} 与阈值 {threshold_value:.3f} 均不改变路由，"
            "采用LLM为主、UIE辅助逐篇抽取。"
        )
    elif coverage >= threshold_value:
        route = ExtractionRoute.PURE_UIE
        rationale = (
            f"试抽判定本批结构相似（homogeneity={report.homogeneity.value}），"
            f"覆盖率 {coverage:.3f} 不低于阈值 {threshold_value:.3f}，"
            "允许纯UIE全批抽取。"
        )
    else:
        route = ExtractionRoute.LLM_THEN_UIE
        rationale = (
            f"试抽判定本批结构相似（homogeneity={report.homogeneity.value}），"
            f"但覆盖率 {coverage:.3f} 低于阈值 {threshold_value:.3f}，"
            "先由LLM补全单子（人工确认）后再UIE全批抽取。"
        )
    return RouteDecision(
        batch_id=report.batch_id,
        route=route,
        coverage_ratio=coverage,
        threshold=threshold_value,
        uncovered_items=report.uncovered_items,
        new_type_proposals=report.new_type_proposals,
        rationale=rationale,
    )
