---
phase: 16-raw-corpus-entity-layer
plan: 08
subsystem: entity
tags: [dictionary-exact, frontmatter-declared, supplementary-source, d3-priority, d1-canonical-attach, immutable-resolution, tdd, fail-closed]
type: tdd
wave: 2
macro_wave: W3
depends_on: [16-02, 16-03]
requires:
  - phase: 16-02
    provides: Frozen CorpusSpanInput/MentionCandidate with full provenance and conditional nullable model provenance.
  - phase: 16-03
    provides: Deterministic merger structural winner order (_rank_key / _PRIORITY), reused verbatim for same-kind resolution tie-breaks.
provides:
  - Dictionary-exact and OKF frontmatter-declared supplementary candidate loaders with exact attribution and full provenance; supplements never replace the RaNER model.
  - Pure immutable D3/D1 resolution engine: one winning candidate per frozen occurrence, exact-only canonical/alias attach, everything else pending.
affects: [16-09, 16-10]  # resolution decisions feed later materialization; Wave 2 closes at 16-12
requirements: [R-OKF-06]

tech-stack:
  added: []
  patterns:
    - "Plain source envelopes (no public DTOs): extractor_id exactly 'supplementary' plus non-empty extractor_version/schema_version/segmentation_version and a 64-lowercase-hex label_map_digest; normalization_version inherited from CorpusSpanInput."
    - "Explicit zero-based half-open Python Unicode code-point span-local coordinates with exact slice-back validation; coordinates are NEVER recovered by find/index/search; frontmatter declarations come only from the mentions list (title/aliases never scanned)."
    - "confidence == 1.0 is an exact/declaration marker, never a calibrated probability; all model provenance None for non-model sources."
    - "Resolution is a pure immutable function: one frozen PRIORITY_ORDER, numeric confidence never compared, same-kind winner reuses merger._rank_key, occurrence identity excludes segment_id, one immutable authority index per resolve call, fail-closed defensive DTO construction."

key-files:
  created:
    - llamaindex_runtime/entity/dictionary_loader.py
    - llamaindex_runtime/entity/frontmatter_supplement.py
    - llamaindex_runtime/entity/resolution.py
    - tests/llamaindex_runtime/entity/test_supplementary_sources.py
    - tests/llamaindex_runtime/entity/test_resolution.py
  modified:
    - llamaindex_runtime/entity/__init__.py  # additive facade exports for the three new modules
  summary:
    - .planning/phases/16-raw-corpus-entity-layer/16-08-SUMMARY.md

key-decisions:
  - "D3 priority frozen as frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable; 'unavailable' is never treated as low confidence and is dropped only on an actual occurrence conflict."
  - "Same-kind tie-break reuses the merger structural fingerprint (SHA-256 digest + canonical payload); numeric confidence is opaque data inside that fingerprint and never compared as a magnitude."
  - "Occurrence identity is (input_kind, input_id, input_revision, char_start, char_end, mention_text); segment_id is provenance only and excluded."
  - "D1 attaches only on an exact case-sensitive mention_text match to an existing canonical_name+entity_type OR an exact case-sensitive alias to a matching-type entity; canonical_label is never used for alias matching; competition/type-mismatch/case-only/unknown targets stay pending; nothing is created or persisted."
  - "Per-occurrence authority re-scan replaced by one immutable authority index built once per resolve call (review MEDIUM remediation)."

requirements-completed: [R-OKF-06]

duration: "multi-round TDD + coordinator review/hardening, all recorded below"
completed: 2026-08-07
---

# Phase 16: Plan 08 Summary

**Dictionary/Frontmatter Supplementary Sources + D3/D1 Resolution（local/static implementation COMPLETE；Phase 16 仍 OPEN/EXECUTING，Wave 2 未完成）**

## 状态边界（Status Boundaries）

- **16-08 local/static implementation COMPLETE**：`dictionary_loader.py`、`frontmatter_supplement.py`、`resolution.py` 已按 frozen contract 实现并通过 TDD / coverage / review。
- **Phase 16 仍 OPEN/EXECUTING；Wave 2 未完成（直至 16-12）**。本文件仅为 16-08 local/static completion；**不进入任何后续 plan、live gate 或 C2**，亦不宣称 Phase 16 closure。
- **无真实模型/网络/持久化**：没有 ModelScope import/download/load/inference、没有网络、没有 Docker、没有 PostgreSQL/外部 DB、没有 C2、没有 live gates、没有 commit/push。
- **无凭据**：未读取/打印/记录/持久化任何 credential value 或 connection value（变量名仅以守卫约束文字出现在 canonical selector 中）。
- **未提交**：16-08 全部生产/测试/`__init__.py` 文件保持 uncommitted（commit/push 未授权）；本文件不宣称 git cleanliness。
- **C1 未满足**：dictionary/frontmatter-only 补充管线不能单独满足 C1 acceptance；Plan 16-08 完成不是 Phase 16 closure。

## Task #186 Wave 2 Closeout（post-plan closeout 状态修正）

- **本 plan 当时**（Task #186 之前）：16-08 local/static implementation COMPLETE，但 scheduler Wave 2 尚未 close（直至 16-12）；本文件当时只记录 16-08 自身完成，不宣称 16-12 或 Phase 16 closure。
- **Task #186 后**：scheduler Wave 2 的已授权 local/static/default-blocked 范围（16-06/16-08/16-12）已整体收尾——coordinator fresh combined selector **273 passed in 3.95s**（`test_label_map.py` + `test_raner_adapter.py` + `test_supplementary_sources.py` + `test_resolution.py` + `test_raner_mirror_builder.py`，完整 12-variable env-clean）。这是 **Wave 收尾，不是 Phase 16 closure**。
- Phase 16 仍 **OPEN/EXECUTING**；16-12 production mirror acceptance 仍 **BLOCKED**（真实 gate task 未授权）。本修正只更新状态，不改写本 plan 原始 TDD/coverage/review 证据与结论；Task #186 的最终 COMPLETE 判定由协调器 fresh re-read/verify 决定。

## TDD Evidence

Selector（逻辑 selector：相同两个 test paths、`-q`、完整 env guards；launcher 在 `pytest` 与 `python -m pytest` 间变化，语义等价）：

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/entity/test_supplementary_sources.py tests/llamaindex_runtime/entity/test_resolution.py -q
```

> **launcher 说明**：上述为 plan 的 canonical selector（launcher `pytest`）；协调器 fresh runs 使用 `python -m pytest`，除 launcher 外 test paths、`-q` 与完整 env guards 均与 canonical 语义等价（各 run 并非逐字命令相同）。

| Stage | Result | Detail |
|---|---|---|
| **RED** | exit 2，2 collection errors in 0.96s（coordinator fresh） | 三个生产模块均不存在。**Import order 依次暴露 `llamaindex_runtime.entity.dictionary_loader` 与 `llamaindex_runtime.entity.resolution` 两个 missing modules**；`frontmatter_supplement` 未独立出现（collection 提前停止）。不得伪称看到三个独立 missing-module error。 |
| **GREEN attempt 1** | `142 passed, 1 failed`（agent 1.93s；coordinator 1.68s） | 唯一失败来自测试 canonicalization helper 对 dataclasses.Field 对象调用 `getattr`。**在任何完整 GREEN 之前**做机械 harness 修正：`getattr(..., f)` → `getattr(..., f.name)`；业务断言未改动。 |
| **GREEN（首个完整）** | `143 passed in 0.86s`（coordinator fresh） | 同一 focused selector 首次完整通过。**tests 在首次 GREEN 时冻结**。 |
| **REFACTOR / review 修正后** | `143 passed in 0.82s`（coordinator final fresh） | Ruff production lint 通过；**四个生产文件已格式化**。**不宣称 frozen tests 通过 Ruff format check**——测试因 hash 冻结而故意未重新格式化。 |
| **测试断言冻结** | 不变 | **hash 在全部 REFACTOR/hardening runs 中保持一致**（见下）。 |

**Frozen test hashes（首次 GREEN 时冻结，全部 REFACTOR/hardening runs 均不变）：**

- `test_supplementary_sources.py` — **733 行**，sha256 `10db869abf52cd150aa4ab0db372401145748a59c6424f9e5e2317120e3cc4c0`
- `test_resolution.py` — **799 行**，sha256 `2f34199e46683ba5754eaf40eca5a9698e20020169584c10f0802c0908551a36`

## 最终验证（Final Verification）

- **Full entity regression（最终代码后）**：`465 passed, 1 skipped in 3.35s`。
- **唯一 skip 与 16-08 无关**：为 16-07 offline mirror 的 `test_fifo_as_manifest_file_rejected`（Windows 无 FIFO，`os.mkfifo` 不可用），是既有平台 skip。
- **Coverage focused selector（最终代码后）**：`143 passed in 1.88s`：
  - `dictionary_loader`：**95%**（55 stmts, 3 miss）。
  - `frontmatter_supplement`：**95%**（55 stmts, 3 miss）。
  - `resolution`：**92%**（141 stmts, 11 miss）——**不复用早期 pre-hardening 的 96% resolution 数字**。
  - combined：**93%**（251 stmts, 17 miss）。
- **Coordinator ephemeral probes 全部通过**：defensive immutable direct construction（非法 `ResolutionResult` 序列 / `chosen_priority` fail-closed）；exact vs conflicting duplicate entity IDs；`canonical_label` 永不用于 attach；multi-occurrence indexed resolution；frozen hashes。

## 实现 Contract

- **Supplementary source envelope**：显式提供 `extractor_version` / `schema_version` / `segmentation_version` / `label_map_digest`；`extractor_id` 必须精确为 `"supplementary"`（其他值 fail closed）；`normalization_version` 继承自 `CorpusSpanInput`。
- **合法 frozen DTO 解释**：`source="dictionary"` + `confidence_kind="dictionary_exact"`；`source="frontmatter"` + `confidence_kind="frontmatter_declared"`。`confidence == 1.0` 仅为 exact/declaration marker，**永不视为 calibrated probability**；全部 model provenance 为 `None`。
- **坐标纪律**：显式 Unicode code-point zero-based half-open span-local 坐标；从 `normalized_text` 精确 slice-back（`normalized_text[char_start:char_end] == mention_text`）；无 substring search / find / index / title / alias body scan；frontmatter 候选仅来自 `mentions`，且**仅 corpus input 合法**（query input fail closed）。
- **D3 精确顺序**：`frontmatter_declared > dictionary_exact > rule_weight > model_probability > unavailable`；numeric confidence 永不比较；same-kind winner 复用 `merger._rank_key`（SHA-256 digest + canonical payload）；occurrence identity **排除 segment_id**；`unavailable` 仅在真实 occurrence 冲突时才落败。
- **D1 attach**：仅当 exact case-sensitive `mention_text` 与现有 compatible entity 的 `canonical_name` + exact `entity_type` 匹配，或 exact alias 指向同型 entity；`canonical_label` 不参与 alias 匹配；ambiguous / unknown / type-mismatch / case-only 一律 pending（`entity_id=None`）；**不创建 canonical entity / alias、无 DB write、无 model/network call、无 persistence**。
- **ResolutionResult immutable**：`resolved`/`pending` 防御性拷贝为 tuple；`chosen_priority` 为只读 `MappingProxyType`，key 为 frozen 六字段 occurrence tuple，value 直接为 `ConfidenceKind` string；每 call 一个 immutable authority index；conflicting duplicate `entity_id` 记录 fail closed。
- **Facade**：`entity/__init__.py` 新增导出 `dictionary_loader.py`、`frontmatter_supplement.py`、`resolution.py` 的 public symbols（additive）。

## 审核与 Hardening

- **唯一稳定实现 Sonnet review**：**0 CRITICAL / 0 HIGH**；1 MEDIUM（performance）+ 3 LOW。
- **MEDIUM（已修复）**：per-occurrence authority re-scan → **每 resolve call 构建一个 immutable authority index**（`_AuthorityIndex`），消除重复扫描。
- **LOW（已修复）**：direct sequence 与 chosen_priority shape 问题已按 frozen DTO 契约修正。
- **两处 evidence-only test-pinning gaps**：判定 `no_change_needed`——frozen tests 不能改动，且 coordinator probes 已覆盖对应行为。
- **同一 reviewer 复验 outcomes 并返回 APPROVE，无新增 CRITICAL/HIGH**；这不是第二次独立 full review。

## Deviations / Decisions / Limitations

- **Deviations**：无实现/契约 deviation。实现严格遵循 16-08-PLAN 的 frozen verify selector 与 must_haves；verification launcher 在 `pytest` 与 `python -m pytest` 间的非语义变化不改变 selector 的 test targets/options/env guards。
- **Decisions**：三模块经 facade additive 导出；每 call 单一 immutable authority index；`ResolutionResult` 防御性 freeze；frozen tests 不因 Ruff format 重新格式化（hash 冻结优先）。
- **Limitations**：无 live model/network/DB（未下载/load/inference 任何模型）；`runtime_compatibility_id` 保持 `None`（16-08 不涉及 real mirror smoke）；测试 hash 冻结故 tests 未按 Ruff 重新格式化；dictionary/frontmatter-only 不满足 C1 acceptance。

## 文件清单（Files Created / Modified）

- `llamaindex_runtime/entity/dictionary_loader.py`（new production）——dictionary-exact supplementary loader。
- `llamaindex_runtime/entity/frontmatter_supplement.py`（new production）——OKF frontmatter-declared supplement。
- `llamaindex_runtime/entity/resolution.py`（new production）——D3/D1 pure immutable resolution engine。
- `tests/llamaindex_runtime/entity/test_supplementary_sources.py`（new RED test，frozen）。
- `tests/llamaindex_runtime/entity/test_resolution.py`（new RED test，frozen）。
- `llamaindex_runtime/entity/__init__.py`（additive modified）——facade exports。
- 本 SUMMARY 为唯一新建文档。全部文件保持 uncommitted（commit/push 未授权）。

## Boundary Compliance

- 无 heavy import：模块仅 stdlib + `.contracts` / `.merger`；source guard + in-process 断言 modelscope/torch/jieba 不进入 `sys.modules`；import marker guard 拒绝 persistence/network/LLM/adapter/mirror/registry 导入。
- 无 substring recovery：source guard 拒绝 `find`/`index`/`rfind`/`rindex`/`search`；frontmatter title/aliases 永不扫描。
- 无 generative LLM / SQL DML：resolution source guard 拒绝 `execute`/`executemany`/`commit`/`rollback`/`complete`/`acomplete`。
- 无 DB/Docker/PostgreSQL/network/model download/live gate/C2/commit/push；每条 Bash 命令经 `rtk env -u ...` 清空全部敏感与授权守卫变量；未读取/打印/持久化任何 credential value 或 connection URI。
- 测试断言冻结：RED 后存在一次 pre-GREEN 机械 harness 修正（`getattr(..., f)` → `getattr(..., f.name)`，无业务断言改动）；两份测试 hash 在首个完整 GREEN 时记录并冻结，并从 GREEN 起至全部 REFACTOR/hardening/final runs 保持不变。

## Next Integration Notes

- `resolution.py` 的 `ResolutionDecision`/`chosen_priority` 输出供后续 materialization 消费（`mention_id` 属于 16-09 materialization，本 plan 明确不含）。
- **Wave 2 未完成（本 plan 当时叙述）**：Phase 16 仍 OPEN/EXECUTING，直至 16-12 收口；本 plan 不进入任何后续 plan、live gate 或 C2。**Task #186 后**：Wave 2 local/static/default-blocked 范围已收尾（见上方 closeout note）；下一层为 Wave 3（16-09/16-10/16-13），未进入、需独立人类授权。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 08*
*Completed: 2026-08-07*
