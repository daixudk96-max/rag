---
phase: 16-raw-corpus-entity-layer
plan: 06
subsystem: entity
tags: [label-map, raner-adapter, fast-tokenizer, offset, provenance, fail-closed, tdd]
type: tdd
wave: 2
macro_wave: W2
depends_on: [16-02, 16-05]
requires:
  - phase: 16-02
    provides: Frozen CorpusSpanInput/MentionCandidate with full-provenance and conditional nullable model provenance.
  - phase: 16-05
    provides: Frozen Segment + deterministic token-aware segmentation (segment_id, exact code-point boundaries, segmentation_version).
provides:
  - Versioned immutable RaNER label map: exactly six raw labels (PER/LOC/CORP/GRP/CW/PROD) mapped deterministically to canonical types with raw_label always preserved; CORP/GRP both map to Organization while remaining distinct raw keys; unknown/invalid raw labels fail closed with typed versioned LabelMapError.
  - ModelScope RaNER adapter that forces the fast-tokenizer offset path, projects local code-point half-open offsets onto parent coordinates, drops the uncalibrated `prob`, and emits full-provenance MentionCandidates with confidence=None / confidence_kind="unavailable"; never calls a generative LLM and never recovers coordinates by substring search.
affects: [16-07, 16-08, 16-10]  # downstream phases consume label_map_digest + candidate provenance contract
requirements: [R-OKF-04, R-OKF-06]

tech-stack:
  added: []
  patterns:
    - "Injected fake model/tokenizer seam: adapter consumes callable model + callable fast tokenizer; never imports/downloads/loads a real model."
    - "Fast-tokenizer offset mapping is authoritative and consumed in input order: strictly start-ordered, non-overlapping; never reordered or recovered (no .sort(), no str.find/index)."
    - "Python code-point zero-based half-open local-to-parent projection: parent_start = segment.start + local_start; mention text slices back exactly from parent.normalized_text."
    - "Full frozen provenance on every candidate; digests validated as exactly-64-lowercase-hex; runtime_compatibility_id may be None."

key-files:
  created:
    - tests/llamaindex_runtime/entity/test_label_map.py
    - tests/llamaindex_runtime/entity/test_raner_adapter.py
    - llamaindex_runtime/entity/label_map.py
    - llamaindex_runtime/entity/raner_adapter.py
  modified: []  # no entity/__init__.py modification; new modules are NOT exported through the facade
  summary:
    - .planning/phases/16-raw-corpus-entity-layer/16-06-SUMMARY.md

key-decisions:
  - "Label map is immutable (MappingProxyType over an inline literal) and versioned (RAINER_LABEL_MAP_VERSION); CORP/GRP share canonical Organization but preserve distinct raw labels so provenance is never collapsed."
  - "Offset mapping is validated in authoritative input order and fails closed on unordered/duplicated/overlapping input; it is never sorted (a sorted mapping would silently mask a non-authoritative tokenizer)."
  - "RaNERAdapter(parent) holds one immutable parent for its lifetime (private _parent seam); extract_segment has frozen names/order and is keyword-only except the single positional segment."
  - "Official ModelScope output is parsed as a Mapping with an 'output' sequence; prob is dropped unconditionally; confidence=None / confidence_kind='unavailable'; candidate order retained; entity_type equals canonical label (free-form TEXT, no enum)."

patterns-established:
  - "Private validators _validate_offsets/_validate_offset_coverage/_validate_mention_shape/_validate_segment/_validate_mention isolate offset validity, coverage, model-output shape, segment-parent consistency, and per-mention coordinate/span checks."
  - "Fail-closed everywhere: slow tokenizer (is_fast False) rejected before invocation; missing offset_mapping; malformed/out-of-range/zero-length/overlapping/unordered offsets; partial/truncated coverage of non-whitespace code points; non-token-aligned mention coordinates; span mismatch; malformed output; non-callable model/tokenizer."

requirements-completed: [R-OKF-04, R-OKF-06]

duration: "multi-round TDD + coordinator review/hardening, all recorded below"
completed: 2026-08-07
---

# Phase 16: Plan 06 Summary

**版本化 RaNER Label Map + Fast-Tokenizer RaNER Adapter（local/static implementation COMPLETE；Phase 16 仍 OPEN/EXECUTING）**

## 状态边界（Status Boundaries）

- **16-06 local/static implementation COMPLETE**：`label_map.py` 与 `raner_adapter.py` 已按 frozen contract 实现并通过 TDD / coverage / review。
- **Phase 16 仍 OPEN/EXECUTING；Wave 2 未完成**。本文件不宣称 16-08/16-12 或 Phase 16 closure，未进入任何后续 wave。
- **只用 injected fake model/tokenizer**：没有真实 ModelScope import/download/load/inference、没有网络、没有 Docker、没有 PostgreSQL/外部 DB、没有 C2、没有 commit/push。
- **`runtime_compatibility_id=None` 合法**（pre-smoke unresolved），但**没有 live smoke 冻结任何真实 compatibility ID**；不宣称任何运行时兼容性已被证明。
- **`entity/__init__.py` 未修改**：两个新模块不被 facade 导出（与 16-07 的 frozen facade 契约一致）。

## Task #186 Wave 2 Closeout（post-plan closeout 状态修正）

- **本 plan 当时**（Task #186 之前）：16-06 local/static implementation COMPLETE，但 scheduler Wave 2 尚未 close；本文件当时只记录 16-06 自身完成，不宣称 16-08/16-12 或 Phase 16 closure。
- **Task #186 后**：scheduler Wave 2 的已授权 local/static/default-blocked 范围（16-06/16-08/16-12）已整体收尾——coordinator fresh combined selector **273 passed in 3.95s**（`test_label_map.py` + `test_raner_adapter.py` + `test_supplementary_sources.py` + `test_resolution.py` + `test_raner_mirror_builder.py`，完整 12-variable env-clean）。这是 **Wave 收尾，不是 Phase 16 closure**。
- Phase 16 仍 **OPEN/EXECUTING**；16-12 production mirror acceptance 仍 **BLOCKED**（真实 gate task 未授权）。本修正只更新状态，不改写本 plan 原始 TDD/coverage/review 证据与结论；Task #186 的最终 COMPLETE 判定由协调器 fresh re-read/verify 决定。

## TDD Evidence

Selector（逻辑 selector：相同两个 test paths、`-q`、完整 env guards；launcher 在 `pytest` 与 `python -m pytest` 间变化，语义等价）：

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_label_map.py tests/llamaindex_runtime/entity/test_raner_adapter.py -q
```

> **launcher 说明**：上述为 plan 的 canonical selector（launcher `pytest`）；协调器 fresh runs 使用 `python -m pytest`，除 launcher 外 test paths、`-q` 与完整 env guards 均与 canonical 语义等价（各 run 并非逐字命令相同）。

| Stage | Result | Detail |
|---|---|---|
| **RED** | exit 2，2 collection errors | production `label_map.py`/`raner_adapter.py` 均不存在。**两个 collection error 因 adapter test import order 都首先报告 `ModuleNotFoundError: llamaindex_runtime.entity.label_map`**——不得伪称分别看到了两个 missing modules；这是同一根因在 collection 阶段的两份报告。协调器独立复验：**2 errors in 0.99s**。 |
| **GREEN（初始实现）** | `83 passed in 1.82s` | 同一 focused selector 首次通过（Sonnet 记录）。协调器 fresh verify：**`83 passed in 1.93s`**。 |
| **REFACTOR** | `83 passed in 1.43s` | coordinator source review 在 REFACTOR 前发现 `_validate_offsets()` 使用 `.sort()` 会把 `[(1,2),(0,1)]` 静默变为有序；隔离 probe 真实输出 `[(0,1),(1,2)]`。Sonnet 删除排序并按 authoritative input order fail closed，同时提取小 helper/收窄注解（immutability remediation 见下）。协调器 fresh：**`83 passed in 1.44s`**；最终 unordered probe 抛 **`RaNEROffsetError: offset mapping must be ordered by start`**。 |
| **测试断言冻结** | 不变 | **两份测试在首次 GREEN 后未修改**；GREEN→REFACTOR 之间未改动任何断言。 |

## 最终验证（Final Verification）

- **Full entity + coverage（最终代码后）**：`322 passed, 1 skipped in 5.41s`。
- **唯一 skip 与 16-06 无关**：Windows 不支持 FIFO，skip 来自 offline mirror 测试（16-07），与 16-06 无关联。
- **Coverage**：
  - `label_map`：**100%**（11 stmts, 0 miss）。
  - `raner_adapter`：**94%**（137 stmts, 8 miss）——**不宣称 adapter 100% 覆盖**。
  - combined：**95%**（148 stmts, 8 miss）。
- **Focused tests 覆盖的 source/import/behavior guards**：no heavy import（modelscope/torch/transformers/tokenizers/sentencepiece/jieba 均不 import）、no generative LLM（无 openai/anthropic/llm client/FunctionAgent/get_llm 引用）、no find/index substring coordinate recovery、fast tokenizer exact kwargs（`return_offsets_mapping=True`、`add_special_tokens=False`、`truncation=False`）、malformed/partial/truncated offsets fail closed、Unicode code-point projection（astral + combining）、`prob` dropped、model 每非空 segment 恰好调用一次、full provenance 逐字段断言。

## 实现 Contract

- **六标签不可变版本化 label map**：`RAINER_RAW_TO_CANONICAL` 精确为 `PER→Person`、`LOC→Location`、`CORP→Organization`、`GRP→Organization`、`CW→CreativeWork`、`PROD→Product`；`RAINER_LABEL_MAP_VERSION = "e2b-raner-label-map-v1"`。CORP/GRP 均映射到 Organization 但保持 distinct raw label（provenance 不 collapse）。未知/非法 raw label（含大小写不匹配、空白未归一、空串、None、非 str）抛 typed 且携带版本的 `LabelMapError(ValueError)`。`RAINER_RAW_TO_CANONICAL` 为 `MappingProxyType`，immutability 由测试与 coordinator probe 双重 pin。
- **`RaNERAdapter(parent: CorpusSpanInput)`**：private parent seam（`self._parent`），构造时拒绝非 `CorpusSpanInput`；`extract_segment(segment, *, model, tokenizer, model_id, model_revision, artifact_digest, label_map_digest, runtime_compatibility_id, extractor_id, extractor_version, schema_version, normalization_version, segmentation_version)` —— 名字/顺序/全部 keyword-only 被 `inspect.signature` 冻结；`segment` 是唯一 positional 参数。
- **Offset 处理**：tokenizer 以 frozen kwargs 调用一次；`offset_mapping` 可为 attribute 或 mapping key；mapping 按 authoritative input order 校验（strictly start-ordered、non-overlapping、int-not-bool、in-range、start < end），**永不 reorder、永不 substring recovery**；非 whitespace code point 全覆盖校验（partial/truncated/empty-on-non-whitespace fail closed）；slow tokenizer（`is_fast is False`）在调用前拒绝。
- **坐标投影**：Python code-point zero-based half-open；`parent_start = segment.start + local_start`、`parent_end = segment.start + local_end`；`mention_text` 从 `parent.normalized_text[parent_start:parent_end]` 精确 slice-back（含 astral/combining、重复 mention 文本）。
- **官方输出解析**：接受 `Mapping` 形状 `{"output": [...]}`；`prob` 无条件丢弃；`confidence=None`、`confidence_kind="unavailable"`、`source="model"`；candidate 顺序保留；`entity_type = canonical_label`（free-form TEXT，非 enum）；每个 candidate 携带 full parent/model/version/digest provenance（extractor_id/version、model_id/revision、artifact_digest、schema/normalization/segmentation version、label_map_digest、runtime_compatibility_id、document/version/revision/projection）。

## 审核与 Hardening

- **唯一稳定 delta Sonnet review**：**0 CRITICAL, 0 HIGH**，verdict **APPROVE WITH NOTES**。
- **MEDIUM（forward-integration note，不改当前冻结行为）**：`LabelMapError` 必须**原样传播**（不捕获、不包装）；未来 16-10 per-input handler 需同时 catch `RaNERAdapterError` 与 `LabelMapError`（或在 separately planned scope 下引入共享 base）。**明确不是当前 16-06 defect**。
- **LOW（digest note）**：adapter 对 `label_map_digest` 仅验证 64 位 lowercase hex 并按 frozen injected-provenance contract 透传；**不声称**本 plan 内它绑定实际 map content——未来 composition/loader authority 需负责合法 digest。
- **LOW（mutable backing finding）**：协调器隔离进程复现 `_RAW_TO_CANONICAL` 可经公开 proxy 修改；Sonnet 改为 **`MappingProxyType({...literal...})`**（inline literal，不留模块级可变 backing），最终 probe **`IMMUTABILITY_PROBE: PASS`**。
- **对该 remediation delta 做限定 review**：**0 CRITICAL / 0 HIGH / 0 MEDIUM，APPROVE**；仅有 optional LOW：永久测试未 pin `not hasattr(module, "_RAW_TO_CANONICAL")`。由于 **GREEN→REFACTOR 冻结要求禁止改测试断言**，本 plan 保留协调器 probe 作为证据，**不在收口后改测试**。
- **Real ModelScope token-end semantics**：仍需未来 separately authorized smoke 验证；**不得写为 current defect/pass**。

## Deviations / Decisions / Limitations

- **Deviations**：无实现/契约 deviation。实现严格遵循 16-06-PLAN 的 frozen verify selector 与 must_haves；verification launcher 在 `pytest` 与 `python -m pytest` 间的非语义变化不改变 selector 的 test targets/options/env guards。
- **Decisions**：`MappingProxyType` inline literal（消除可修改 backing）；删除 `.sort()`（authoritative order，fail closed）；`entity_type` 采用 canonical label（free-form TEXT）；两新模块不进入 facade。
- **Limitations**：无 live smoke（未下载模型、未 load、未 inference）；`runtime_compatibility_id` 未冻结；adapter coverage 94%（8 miss，不宣称 100%）；`label_map_digest` 的结构绑定由未来 loader/composition 负责；真实 ModelScope token-end 语义需另行授权验证。

## 文件清单（Files Created）

- `llamaindex_runtime/entity/label_map.py`（new production）——版本化 label map。
- `llamaindex_runtime/entity/raner_adapter.py`（new production）——fast-tokenizer RaNER adapter。
- `tests/llamaindex_runtime/entity/test_label_map.py`（new RED test）。
- `tests/llamaindex_runtime/entity/test_raner_adapter.py`（new RED test）。
- **`entity/__init__.py` 未修改**；本 SUMMARY 为唯一新建文档。

## Boundary Compliance

- 无 heavy import：module 仅 stdlib + `.contracts`/`.segmenter`/`.label_map`；source guard + in-process + fresh-subprocess 测试断言 modelscope/torch/jieba/sentencepiece 不进入 `sys.modules`。
- 无 substring recovery：source guard 拒绝 `str.find`/`.find(`/`str.index`/`.index(`/`split_max_length`。
- 无 generative LLM：source guard 拒绝 openai/anthropic/llm client/FunctionAgent/get_llm。
- 无 DB/Docker/PostgreSQL/network/model download/live gate/C2/commit/push；每条 Bash 命令经 `rtk env -u ...` 在进程内清空全部敏感与授权守卫变量；未读取/打印/持久化任何 credential value 或 connection URI（仅以变量名作为守卫约束文字出现）。
- 测试断言冻结：RED 后仅实现层演进，两份测试未改动。

## Next Integration Notes

- 16-07（offline mirror loader）与 16-08 可消费本 plan 的 `label_map_digest` 约定与 candidate provenance 契约。
- 16-10 per-input handler 需同时处理 `RaNERAdapterError` 与 `LabelMapError`（见 MEDIUM note）。
- 真实 RaNER smoke（冻结 `runtime_compatibility_id`、验证 token-end 语义）为 separately authorized gate，不属于本 plan。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 06*
*Completed: 2026-08-07*
