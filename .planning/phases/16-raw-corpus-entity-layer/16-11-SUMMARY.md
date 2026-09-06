---
phase: 16-raw-corpus-entity-layer
plan: 11
type: execute
wave: 4
macro_wave: W3
depends_on: [16-01, 16-09, 16-10, 16-07]
requirements: [R-OKF-01, R-OKF-04, R-OKF-06]
files_modified:
  - scripts/rebuild_from_okf_e2b.py
  - tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_cli.py
  - tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_default_seams.py
summary:
  - .planning/phases/16-raw-corpus-entity-layer/16-11-SUMMARY.md
key-decisions:
  - "Plan 16-11 is COMPLETE only for its local/static/pure/injected scope; scheduler Wave 4 static closeout (Task #191) is complete. Phase 16 remains OPEN/EXECUTING; this is a Wave closeout, NOT Phase 16 closure."
  - "Plan 16-11 does NOT wire/load a real RaNER model. Real ModelScope mirror / RaNER smoke / runtime measurement / full-corpus gates belong to later separately authorized work."
  - "Exactly one targeted post-fix Sonnet code review of the corrective delta: APPROVE, 0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW. Earlier broad review/security analysis motivated the corrective work; exact earlier counts are not fabricated and no repeated broad review is claimed."
  - "Frozen CLI test hash 59b458ecc5734586ef3a3638c4fe7b7999d31e7bcc42f99f4eb67d1cbff28ed7 unchanged; runner and corrective-test hashes recorded in this summary."
requirements-progress: [R-OKF-01, R-OKF-04, R-OKF-06]
duration: "frozen initial RED (29 collected; 4 passed / 25 failed) + corrective TDD (two test-authoring mistakes corrected; intended RED 5 failed / 43 passed) + implementation (explicit injection, exceptional-path connection close, CLI redaction) + coordinator final verification + exactly one targeted post-fix review (APPROVE 0/0/0/0)"
completed: 2026-08-08
---

# Phase 16: Plan 11 Summary

**16-11 local/static/pure/injected scope COMPLETE（scheduler Wave 4 static closeout，Task #191）；Phase 16 仍 OPEN / EXECUTING；真实 RaNER/ModelScope/DB/live gate 未执行、未授权**

## 状态边界（Status Boundaries）

- **16-11 local/static/pure/injected scope COMPLETE**：`scripts/rebuild_from_okf_e2b.py`、frozen CLI RED test（`test_rebuild_from_okf_e2b_cli.py`）与 corrective test（`test_rebuild_from_okf_e2b_default_seams.py`）已按 frozen contract 实现并通过 TDD / corrective TDD / coverage / Black / Ruff / py_compile / final verification。本计划当前授权仅覆盖静态/纯/注入范围；**scheduler Wave 4 static closeout（Task #191）已关闭**。
- **Phase 16 仍 OPEN / EXECUTING**；本文件仅为 16-11 静态收尾，**不宣称 Phase 16 closure、C1 closure、production readiness、quality/Level、live acceptance 或 R-OKF-09 live-tested**。
- **无真实 RaNER 模型加载/接线**：Plan 16-11 不 wire/load 真实 RaNER model。真实 ModelScope mirror / RaNER smoke / runtime measurement / full-corpus gates 属后续单独授权工作。
- **所有五个 live gates 仍未执行**：gates 1-4 `blocked_not_executed`；C2 gate 5 `skipped_not_entered`。
- **16-13 Task 2 真实 RaNER smoke 仍未执行**：`runtime_compatibility_id=None`；无 `raner_smoke_evidence.md` / `raner_resource_report.json`。
- **无 PostgreSQL、Docker、ModelScope、network、RaNER inference、WSL measurement、C2、commit 或 push 发生于 Plan 16-11**。
- **无凭据/URI 值写入 planning artifacts**：未读取/打印/记录/持久化任何 credential value、connection URI 或 target value；变量名仅以守卫约束文字出现。
- **早先 DB/Docker/C14 授权不适用于本计划，亦不前置到后续 gates**；`D4` 冻结至 Phase 19；Phase 20 仍需单独 pilot 授权 + human G6 Go/No-Go。
- **未提交、不宣称 clean worktree**：三个新 task 文件（runner + 两份测试）保持 uncommitted/untracked；本 `16-11-SUMMARY.md` 自身同样 uncommitted/untracked；仓库存在大量 pre-existing 不相关 dirty/untracked 状态，**不得**将 whole-worktree 变更归因于本计划。

## 计划身份（Plan Identity）

- Plan **16-11**，scheduler **wave 4**，macro **W3**（按 16-11-PLAN.md frontmatter），requirements **R-OKF-01 / R-OKF-04 / R-OKF-06**，depends_on **[16-01, 16-09, 16-10, 16-07]**（均已 COMPLETE）。
- Type：`execute`；Task 1 = 以测试指定 runner CLI 行为；Task 2 = 实现 E2b runner CLI。全部为本地/静态/纯/注入范围；无 live gate task。

## 授权范围（Authorization Scope）

**当前授权仅覆盖**：
- 静态、纯、可注入的 E2b rebuild runner（`scripts/rebuild_from_okf_e2b.py`）；
- frozen CLI RED test（`test_rebuild_from_okf_e2b_cli.py`）；
- corrective default-seams / injection / redaction test（`test_rebuild_from_okf_e2b_default_seams.py`）。

**不覆盖**：真实 RaNER model load/inference、ModelScope mirror access/create/download、DB/PostgreSQL/Docker/network、migration application、runtime measurement、evidence/resource 文件生成、live gate、C2、commit/push。早先 DB/Docker/C14 授权在此不适用。

## 生产实现事实（Production Implementation Facts）

### 1. `scripts/rebuild_from_okf_e2b.py`

- **611 行**，sha256 `ecd01121c4e5cc7d25c032cb1ac89ea7cbabf590ea0fbded9572e67f8ec81390`。
- **静态、纯、可注入**：确定性 bundle admission（raw-only、去重 (doc_id, version_id)、排序）+ canonical scope manifest（schema_version 1 + scopes；SHA-256 manifest）。
- 每篇 document 经注入的 **corpus-input → extractor → desired-state → `E2bMaterializationRepository`** 路由。
- `rebuild_bundle` 暴露 **显式 keyword-only 注入**：`connection_factory`、`repository_factory`、`extractor_factory`、`corpus_input_factory`、`desired_state_factory`（外加可选 `environ`）；默认 extractor / corpus / desired-state builder **保持 fail-closed**（默认执行 model-lazy，且在任何 connection/model 活动前拒绝）。
- `_rebuild_one` **每篇 document 打开一条 fresh primary connection**，将全部 SQL / commit / rollback **委托给 repository**，并在 `finally` 中关闭 primary 且**不 double-close**；**runner 自身从不执行 SQL、从不 commit/rollback**。
- **Fresh failure-audit factory wiring 保留**：repository 以 `failure_audit_connection_factory` 构造，仅在 primary 已 rollback/close 后开 fresh audit connection。
- **Outcome DTO 恰有五个字段**：`outcome`、`manifest_sha256`、`primary_dml_by_table`、`failure_audit_outcome`、`post_rollback_failure_audit_outcome`。**不加、不宣称 `reconciliation_required`**。
- **Allowed primary DML tables 仅**：`entity_mentions`、`okf_e2b_node_link_ownership`、`node_entity_links`；拒绝 `chunk_entity_links` 与 `okf_rebuild_failure_audit`。
- **CLI ValueError 与 psycopg 错误输出固定 redacted message**：从不打印任意 `str(exc)` / URL / credential / bundle / corpus / span；确定性非零退出码（2）。
- **Direct initial gate 用 `RAG_ENTITY_EXTRACTOR`**（严格 `== "raner"`），**不使用 RuntimeSettings.from_env**。
- Connection-support 自 `scripts/_rebuild_database_connection.py` **fresh 加载（不信任 `sys.modules`）**；raw URI 从不位置传给 `psycopg.connect`。
- **不构建/不加载真实 RaNER 模型**：默认 extractor factory 抛 `ValueError("E2b extractor is not configured; no model path is permitted")`。
- **无 canonical entity link 被虚构**：`EntityExtractor.extract()` 仅返回 `MentionCandidate` 并丢弃 `ResolutionDecision.entity_id`；默认 desired-state mapper 因此保持 fail-closed，不发明 entity ID/link。
- **Query hard-zero 与 zero-generative-LLM 边界保持完整**（query input 可以返回纯、不可变、request-scoped `MentionCandidate` 值，但 extractor / query path 不持有或调用任何 durable persistence surface，也不产生 durable mention / merge / alias / link / evidence writes；无生成式 LLM token）。
- `--verify-roundtrip` 为 parser-only / no-DB / no-model 路径，不要求 `RAG_ENTITY_EXTRACTOR` 或 `DATABASE_URL`。

### 2. `tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_cli.py`（frozen RED contract）

- **708 行**，sha256 **`59b458ecc5734586ef3a3638c4fe7b7999d31e7bcc42f99f4eb67d1cbff28ed7`**（authoritative；**do not edit**）。
- Frozen RED：**29 collected cases，`4 passed / 25 failed`，无 collection/syntax 错误**；failures 因 runner 尚不存在；一个无关的已安装 torch/pynvml warning。
- 覆盖 switch gating（fail-closed）、redacted outcome formatting（无 DSN/credential/corpus/span 泄漏）、fresh connection-support loading、injectable pipeline wiring、E2a-shared advisory lock delegation（`okf:e2a:parent:{document_id}:{version_id}`，never `okf:e2b:parent`）。
- **Black 有意不 reformat** 该 frozen 文件。

### 3. `tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_default_seams.py`（corrective test）

- **774 行**（<= 800），sha256 `fb2de4ab10e535d3473d9d7fb6919bcb916a7bc970b40998e3593bc6a24fee20`。
- 覆盖 `rebuild_bundle` 的 keyword-only 注入 surface（默认值仍为 fail-closed seam builders）、`_rebuild_one` connection lifecycle（primary 在 `finally` 关闭、never double-close、never commit/rollback、runner 无 SQL）、固定 redacted CLI 错误输出（never `str(exc)`、确定性退出码）、connection-factory authorization fail-closed、outcome redaction/formatting fail-closed、default seams fail-closed。
- **Corrective TDD 历史（如实概括）**：初始 authored corrective tests 存在 **两个 test-authoring 错误**；修正后 intended RED 为 **`5 failed / 43 passed`**；实现随后加入 **显式注入、exceptional-path connection close、修复 CLI redaction**。**不得**夸大或虚构中间时间点。

## TDD Evidence

| Stage | Result | Detail |
|---|---|---|
| **Frozen initial RED（仅 CLI test）** | `29 collected, 4 passed / 25 failed` | 无 collection/syntax 错误；failures 因 runner 尚不存在；一个无关 installed torch/pynvml warning |
| **Corrective initial authoring** | 两个 test-authoring 错误 | 在验收前修正（不虚构具体中间时间点） |
| **Corrective intended RED** | `5 failed / 43 passed` | 修正后的预期 RED |
| **GREEN（implementation）** | 显式注入 + exceptional-path connection close + CLI redaction 修复 | corrective 行为落地 |
| **Frozen 后** | hash 不变 | `59b458ec…28ed7` 自 RED 起经 review / final verification 从未改变 |

Selector（focused，完整 12-variable env-clean guards；canonical 形式为外层 `rtk env -u …` + 嵌套 `rtk proxy pytest … -q`，变量名仅以守卫约束文字出现）：

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED rtk proxy pytest tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_cli.py tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_default_seams.py -q
```

## 最新 coordinator final verification（LAST edit 之后 fresh run）

- **Focused frozen + corrective selector**：`81 passed, 1 warning in 47.61s`；warning 为无关的已安装 torch/pynvml deprecation。
- **Branch-aware coverage run**：`81 passed, 1 warning in 84.82s`；`scripts/rebuild_from_okf_e2b.py` = **289 statements, 2 missed, 84 branches, 1 partial, 99% displayed coverage**；missing lines 610-611（`__main__` guard）由 subprocess test **行为性覆盖**。**远超 80% 门槛**。
- **隔离 fresh-process 全纯 entity suite**：`651 passed, 1 skipped in 7.27s`；skip 为既有 Windows FIFO skip，**与 16-11 无关**。
- **Black**：`2 files would be left unchanged`（runner + corrective test；frozen test 有意不 reformat）。
- **Ruff**：runner + 两份测试全部检查通过。
- **py_compile**：runner + 两份测试 success。
- **Frozen hash 不变**（`59b458ec…28ed7`）。
- **Corrective test = 774 lines（<= 800）**。
- **Coverage artifacts 已清理**。
- **Scoped status 恰含三个 intended untracked Plan 16-11 文件**；仓库存在大量 pre-existing 不相关 dirty/untracked 状态，**不得**宣称 clean worktree 或把 whole-worktree 变更归因于本计划。

## 审核（Review Boundaries）

- **恰一次** targeted post-fix Sonnet code review of the corrective delta：**APPROVE，0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW**。
- 早期 broad review / security analysis **促成了 corrective 工作**；本 summary **不虚构早期精确 counts**，且**不宣称重复 broad reviews**（无 second broad review）。

## Known LOW Parity Notes（recorded / unfixed / non-blocking）

如实记录，**不作已修复或 blocker 声明**：

1. **无 `OKF_BUNDLE_ROOT` fallback parity**：E2b runner 不读取/回退 `OKF_BUNDLE_ROOT`，直接以 `--bundle` 为输入（与 E2a 的 bundle-root fallback 不一致）。
2. **无 E2a fixture-scope guard parity**：E2b `--verify-roundtrip` 不复制 E2a 的 fixture-scope guard。
3. **无 `.strip()` normalization parity**：`_require_raner_extractor` 对 `RAG_ENTITY_EXTRACTOR` 严格比较，不做 `.strip()` 规范化。
4. **无 combined `--verify-roundtrip --rebuild` scope guard parity**：CLI 允许二者组合，未复制 E2a 的互斥/作用域 guard。

## Frozen Plan Conflict Resolution / Deviations

- **corrective test 为计划 files_modified 之外新增**：16-11-PLAN.md 仅列出 runner + CLI test；corrective TDD 新增 `test_rebuild_from_okf_e2b_default_seams.py` 以覆盖注入 surface / connection lifecycle / redaction / fail-closed branches。这是交付的第三个 intended file，随 corrective delta 记录。
- **默认 extractor / desired-state mapper 有意 fail-closed**：本 runner 不 load 真实 RaNER；无 canonical entity link 被虚构。
- **`post_rollback_failure_audit_outcome` 字段在 outcome 中始终为 `None`**：redact seam 拒绝第二 audit channel 的非 None 值；DTO 保持五字段，无 `reconciliation_required`。
- **`runtime_compatibility_id` 不变（None）**：本计划无 smoke、无 runtime measurement、无 freeze。

## Safety / Boundary Facts

- 无真实 RaNER model load/inference、model/mirror access/create/download、heavy import、ModelScope、WSL/resource measurement、evidence generation、DB/PostgreSQL/Docker/network、migration application、live gate、C2、commit 或 push。
- 无 credential/URI/target value 被读取、打印、记录或持久化。
- **早先 DB/Docker/C14 授权不适用**；`D4` 冻结至 Phase 19；Phase 20 需单独 pilot 授权 + human G6 Go/No-Go。
- 仓库存在大量 pre-existing 不相关 dirty/untracked 状态；**不宣称 repo cleanliness**。三个新 task 文件为 untracked，本 SUMMARY 自身同样 uncommitted/untracked。
- **Authoritative coordinator final verification commands**（如上方 focused selector）均使用完整 12-variable env-clean guard + `rtk`；**不对全部历史子代理命令作 blanket claim**。

## 文件清单（Files Created）

- `scripts/rebuild_from_okf_e2b.py`（created，611 lines，sha256 `ecd01121c4e5cc7d25c032cb1ac89ea7cbabf590ea0fbded9572e67f8ec81390`）。
- `tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_cli.py`（created/frozen during RED，708 lines，sha256 `59b458ecc5734586ef3a3638c4fe7b7999d31e7bcc42f99f4eb67d1cbff28ed7`；**do not edit**）。
- `tests/llamaindex_runtime/okf/test_rebuild_from_okf_e2b_default_seams.py`（created/corrective，774 lines，sha256 `fb2de4ab10e535d3473d9d7fb6919bcb916a7bc970b40998e3593bc6a24fee20`）。
- 本 `16-11-SUMMARY.md` 为唯一新建文档。全部文件保持 uncommitted；仓库存在 pre-existing 不相关 dirty/untracked 状态，不宣称 git cleanliness。

## Next Integration Notes / Routing

- **下一 scheduler 层为 Wave 5 = exactly plan 16-14**（gate 1 migration runner）。已核查 `16-14-PLAN.md`：其 `depends_on` **[16-04]** 已满足（16-04 COMPLETE static；live migration application 仍 `blocked_not_executed`），故**在 plan-dependency 层面 dependency-ready**；但 **16-14 本计划的 Task 2 为 blocking decision gate（future gate 1）且仍 `blocked_not_executed`**，其 gate-runner test surface（`test_e2b_migration_gate_runner.py`）尚不存在，且 **16-14 未由本 Plan 16-11 continuation 授权**。**不得**假设其 dependency-ready 即已授权；no later-wave / live-gate authorization is implied。
- 五 live gates 不变：gates 1-4 `blocked_not_executed`；C2 gate 5 `skipped_not_entered`。
- **Task #191 / Plan 16-11 administrative Wave 4 static closeout 已 complete**（coordinator 已独立读取核对本 closeout artifacts）；task tracker 由 coordinator 在文档核验后更新，**本 summary 不自行变更 tracker**。
- Phase 16 仍 OPEN/EXECUTING；本文件为 Wave 4 static closeout 文档，供 coordinator 核查。

## 结论（Conclusion）

- **16-11 local/static/pure/injected scope COMPLETE**：静态、纯、可注入 E2b rebuild runner + frozen CLI RED test + corrective test 均已按 frozen contract 实现并通过 TDD / corrective TDD / coverage / Black / Ruff / py_compile / final verification；**scheduler Wave 4 static closeout（Task #191）完成**。
- **Phase 16 仍 OPEN / EXECUTING**；不宣称 live readiness、C1 live-model closure、production readiness、quality/Level 或 R-OKF-09 live-tested。
- 下一 scheduler 层 Wave 5 = exactly plan 16-14，未授权；no later-wave/live-gate authorization implied。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 11*
*Completed: 2026-08-08*
