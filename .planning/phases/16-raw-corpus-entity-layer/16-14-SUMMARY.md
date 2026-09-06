---
phase: 16-raw-corpus-entity-layer
plan: 14
type: execute
wave: 5
macro_wave: W4
depends_on: [16-04]
requirements: [R-OKF-01, R-OKF-06]
files_modified:
  - verification/phase16-raw-corpus-entity-layer/run_e2b_migration_gate.py
  - tests/llamaindex_runtime/okf/test_e2b_migration_gate_runner.py
  - tests/llamaindex_runtime/okf/test_e2b_migration_gate_relation_scope.py
  - verification/phase16-raw-corpus-entity-layer/e2b_migration_gate_evidence.md
  # NOTE: e2b_migration_gate_evidence.md was intentionally ABSENT during the
  # historical Wave 5 STATIC closeout (2026-08-08). After the separately
  # authorized live gate (Plan 16-14 Task 2) ran successfully on 2026-08-09, the
  # file EXISTS and was written only by that successful production gate.
summary:
  - .planning/phases/16-raw-corpus-entity-layer/16-14-SUMMARY.md
key-decisions:
  - "Scheduler Wave 5 = exactly Plan 16-14. Task 1 (local/static/default-blocked gate-1 migration runner scope) is COMPLETE (historical Wave 5 STATIC closeout 2026-08-08)."
  - "Plan 16-14 Task 2 (blocking human decision, future gate 1) was NOT authorized during the historical static closeout; after separate human authorization it was EXECUTED once on 2026-08-09 (status=executed, evidence_verified=true, cleanup_ok=true). Task 2 and the full/live Plan 16-14 objective are now COMPLETE."
  - "Ownership UNIQUE probes are anchored twice to okf_e2b_node_link_ownership via conrelid; this corrected a MEDIUM false-pass found after the first review. PostgreSQL constraint names are not generally schema-wide unique; the original rationale was NOT valid."
  - "Evidence markdown e2b_migration_gate_evidence.md is now present (one-line canonical redacted JSON, sha256 af34c997...bf1341), written only by the successful production gate; it was intentionally absent during the historical static closeout."
  - "Wave 5 LIVE closeout is NOT Phase 16/C1 closure; Phase 16 remains OPEN/EXECUTING (nyquist_compliant false)."
  - "Wave 6 = plans 16-15 and 16-16 is the next scheduler layer but is NOT automatically authorized and is NOT claimed dependency-ready; no authorization inheritance. Next routing is Navigator to route the next Phase 16 C1 entry, not premature C2 authorization."
requirements-progress: [R-OKF-01, R-OKF-06]
duration: "multi-round TDD + coordinator verification + one original targeted review (0/0/0/1 LOW but incorrect PostgreSQL premise) + one NARROW post-fix delta review (APPROVE 0/0/0/1 LOW); then authorized live gate 2026-08-09 (Task #208 static harness 63 passed in 3.67s; final broad Sonnet review initially BLOCKED 0/1/1/4 — HIGH=invalid Docker-ID cleanup gap, MEDIUM=parser-derived env-file user/database — TDD correction added 10 RED tests then 63 GREEN; same original reviewer narrow post-fix APPROVE, HIGH/MEDIUM RESOLVED, new CRITICAL/HIGH=0)"
completed: 2026-08-09
---

# Phase 16: Plan 14 Summary

**16-14 Task 1 static/default-blocked scope COMPLETE（历史 Wave 5 STATIC closeout 2026-08-08）；Task 2 live gate EXECUTED / COMPLETE（2026-08-09）；full/live Plan 16-14 objective COMPLETE；Phase 16 仍 OPEN/EXECUTING**

## 状态边界（Status Boundaries）

- **Scheduler Wave 5 = 恰好 Plan 16-14**（gate-1 disposable-PostgreSQL migration runner）。本 closeout 为 **Wave 5 LIVE closeout**：覆盖 Plan 16-14 Task 1 的 local/static/default-blocked 范围（历史，2026-08-08）与 Task 2 的授权 live gate（2026-08-09）。
- **16-14 Task 1 static/default-blocked runner scope COMPLETE（历史 closeout，2026-08-08）**：`run_e2b_migration_gate.py`（authorization-first runner）、frozen RED contract `test_e2b_migration_gate_runner.py`（79 tests，从未改动）与 narrow corrective relation-scope regression `test_e2b_migration_gate_relation_scope.py`（2 tests）已按 frozen contract 实现并通过 TDD / coverage / review / final verification。
- **Plan 16-14 Task 2（blocking 人类决策，gate 1）—— 历史状态 blocked_not_executed，现 EXECUTED / COMPLETE（2026-08-09）**：经独立人类授权，一次 local loopback disposable Docker PostgreSQL container + 恰好一次 production migration-gate 调用执行成功：status=executed，catalog_apply_count=1，idempotence_reapply_count=1，idempotence_ddl_count=0，evidence_verified=true，cleanup_ok=true。**不得再将 Task 2 描述为当前 blocked_not_executed**；blocked_not_executed 仅作为历史默认/static 行为出现。
- **Full/live Plan 16-14 objective 现 COMPLETE**：fresh-schema 全 catalog 应用、020 exactly-once / idempotence live 证明、redacted live evidence 均已取得。
- **Phase 16 仍 OPEN / EXECUTING**（`nyquist_compliant: false`）；本文件为 Wave 5 **LIVE** closeout，**不是 Phase 16/C1 closure**。
- **Live 行为已发生（授权、单次）**：一个 local loopback disposable Docker PostgreSQL container，恰好一次 production migration-gate 调用；无 external DB、无 DATABASE_URL fallback/read/output/persistence、无 C2 entry、无 commit/push。
- **无凭据**：无任何 credential value、connection URI 或 target value 被读取/打印/记录/持久化；evidence 为 canonical redacted JSON。
- **未提交、不宣称 clean worktree**：`run_e2b_migration_gate.py` 与两份 test（frozen + corrective）保持 uncommitted/untracked；本 `16-14-SUMMARY.md` 自身同样 uncommitted/untracked；仓库存在大量 pre-existing 不相关 dirty/untracked 状态。

## 计划身份（Plan Identity）

- Plan **16-14**，scheduler **wave 5**（= scheduler Wave 5，拓扑层），macro **W4**（按 plan frontmatter 如实记录），requirements **R-OKF-01 / R-OKF-06**，depends_on **16-04**。
- Type：`execute`；Task 1 为 auto 实现（single-use migration gate runner，default blocked）；Task 2 为 blocking decision gate（gate 1，单次 disposable-PostgreSQL migration testing 授权）。Task 2 已于 2026-08-09 授权并执行成功。

## 授权范围（Authorization Scope）

**Wave 5 STATIC closeout（2026-08-08，历史）授权覆盖**：
- 静态 / default-blocked migration gate runner（`run_e2b_migration_gate.py`）；
- frozen RED contract（`test_e2b_migration_gate_runner.py`）；
- narrow corrective relation-scope regression（`test_e2b_migration_gate_relation_scope.py`）。

**Wave 5 LIVE closeout（2026-08-09，新增授权）**：人类授权已扩展以允许按需多次独立 outer invocation；实际仅需要并执行了**一次** outer invocation（一个 local loopback disposable Docker PostgreSQL container + 恰好一次 production migration-gate 调用）。无 automatic rerun。

**仍不覆盖**：任何 external DB、DATABASE_URL fallback/read/output/persistence、凭据/raw URI/target value 输出、C2 entry、commit/push。

## 生产实现事实（Production Implementation Facts）

### `verification/phase16-raw-corpus-entity-layer/run_e2b_migration_gate.py`

（以下为历史 Wave 5 STATIC closeout 记录，2026-08-08；live gate 事实见「Live Closeout (2026-08-09)」节。）

- **548 行**，sha256 `2644bf7b0dafc99f486e6ea18a50782e1a01332b945726abf2249b9363f94503`。
- **Authorization-first**：`run_migration_gate` 的第一个动作是 `_require_gate_authorization(environ)`；**未授权路径返回精确 `blocked_not_executed`，且零 target parsing / 零 connection / 零 catalog / 零 inventory / 零 reapply / 零 evidence**（该默认/static 行为现为历史路径）。
- **programmatic keyword-only `target_uri`**：无 environment 或 `DATABASE_URL` fallback；CLI 不接受、不显示任何 target value（`argv` credential route 被显式拒绝）。目标仅经 `scripts/_rebuild_database_connection.parse_disposable_postgresql_target` 解析为 strict loopback disposable target。
- **exact seven-field frozen `GateOutcome`**：`status`、`catalog_tail`、`catalog_apply_count`、`idempotence_reapply_count`、`idempotence_ddl_count`、`inventory`、`evidence_sha256`。
- **exact production default symbol identities preserved**：`FULL_MIGRATION_CATALOG`、`_apply_catalog`、`parse_disposable_postgresql_target`、`runtime_connection_factory`、`EVIDENCE_PATH` 均保留为精确默认符号。
- **two-connection lifecycle**：connection 1 应用 full root catalog（`apply_catalog`）后关闭；connection 2 执行 inventory / snapshot / reapply-020 / snapshot 后关闭（`finally` 无 double-close）；evidence 最后写入。
- **idempotence_ddl_count=0 语义**：zero **EFFECTIVE** structural delta（`before == after` snapshot），**不代表** migration SQL 不发出任何 DDL statement。frozen contract 明确记录这一区分。
- **Inventory**：20 个 provenance columns、6 个 constraints、4 个 indexes、2 个 tables，以及 ledger UNIQUE **有序** `(node_id, entity_id, version_id)` —— 后者从真实 `pg_constraint.conkey WITH ORDINALITY` 提取并按 ordinality 排序。
- **deterministic structural snapshot**：覆盖 relevant columns / constraints / indexes / tables / functions / triggers，显式稳定排序，等值 snapshot 证明 020 reapply 的 effective structural idempotence。
- **Ownership UNIQUE probes 双锚定**：`_inventory_020` 中 existence probe 与 ordered-column lookup 两处均以 `constraint_row.conrelid = 'okf_e2b_node_link_ownership'::regclass` 精确锚定 target relation，且均限定 `contype = 'u'`、`connamespace = current_schema()`。**这是对第一轮 review 后发现的 MEDIUM false-pass 的纠正**：PostgreSQL constraint name 并非 schema-wide unique，同名 imposter constraint 可能满足未锚定的 probe。**不得重复被拒绝的错误 premise**（声称 constraint name schema-wide unique）。
- **Evidence**：deterministic canonical redacted payload（仅 catalog tail + inventory，无 connection string / credential）；`_write_evidence` 仅在校验全部 inventory 后、且仅在 authorized executed path 上被调用；unauthorized path 永不调用。

## TDD / Corrective Evidence（历史 static，2026-08-08）

| Stage | Result | Detail |
|---|---|---|
| **Frozen RED contract** | 79 tests frozen，1028 行，sha256 `474b7d031ae66a72c5ed00c632deeed8a319eead58747417c7e5a816ae672ded`，自冻结后从未改动 | `test_e2b_migration_gate_runner.py`：default blocked path with zero connection；authorized transition matrix 的 static/contracted seam 断言（authorization-first、keyword-only `target_uri`、七字段 outcome、two-connection lifecycle、catalog tail、inventory、reapply、evidence-last）。 |
| **Corrective relation-scope regression** | 86 行，sha256 `da676f84d3cd9103488525877aaf55c687e493bd685fcea7345858da5ad0c616` | `test_e2b_migration_gate_relation_scope.py`：narrow source regression 仅针对 `_inventory_020` 的 ownership UNIQUE relation anchor —— 断言 `conrelid` predicate 恰好出现两次（existence probe + ordered-column probe）、两处均保持 `contype='u'`、`UNNEST(constraint_row.conkey) WITH ORDINALITY` 恰好一次、按 `key_columns.ordinality` 排序。Frozen test 未改动。 |
| **MEDIUM false-pass correction** | 纠正后接受 | 第一轮 review 后，coordinator 独立重开验证发现 ownership UNIQUE probe 未锚定 target relation 的 MEDIUM false-pass（PostgreSQL constraint name 非 schema-wide unique）；Sonnet TDD correction 添加两处 `conrelid` relation anchor，narrow corrective test 固定之。 |

## 最新 coordinator final verification（历史 static post-correction fresh run，2026-08-08）

Fresh exact evidence（canonical 完整 12-variable env-clean guard + 嵌套 `rtk proxy pytest`）：
- **Frozen + relation-scope selector**：**81 passed in 3.01s**（79 frozen + 2 corrective）。
- **静态 migration regressions**：**28 passed, 10 deselected in 2.09s**；integration 显式排除；无 DB connection。
- **Coverage**：**81 passed in 4.20s**；runner `run_e2b_migration_gate.py` **166 statements, 29 missed, 38 branches, 3 partial, 84%**。
- **Black**：`2 files would be left unchanged`（runner + corrective test；frozen test 有意不 reformat）。
- **Ruff**：`No issues found`。
- **py_compile**：success。
- **Hashes 未变**：frozen test hash 与 GREEN 起一致（`474b7d03…`）；runner `2644bf7b…`；corrective `da676f84…`。
- **临时 `.coverage.phase16-14-fix` 已清理**；无 evidence file 生成（历史静态阶段；live evidence 见下）。

## 审核（Review Correction History）

### 历史 static（2026-08-08）
- **第一次 targeted review（原始 Plan 16-14）**：报告 **0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW**，但依赖一个**关于 schema-wide constraint-name uniqueness 的错误 PostgreSQL premise**。**该 rationale 无效，不得宣称其有效**。
- Coordinator 独立重开 verification（不依赖该 review 的结论）；Sonnet TDD correction 添加两处 relation anchors（`conrelid` 双锚定）并新增 narrow corrective test；frozen test 未改动。
- **随后恰好一次 NARROW post-fix delta review（非重复 broad review）**：返回 **APPROVE，0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW**。
- **剩余 1 LOW**：现有 unqualified `::regclass` / `search_path` convention；在 gate 的 disposable single-schema 假设下 non-blocking，且与既有文件用法一致。记录为 unfixed/non-blocking。

### Live gate（2026-08-09，Task #208）
- **最终 broad Sonnet review 初判 BLOCKED**：**0 CRITICAL / 1 HIGH / 1 MEDIUM / 4 LOW**。HIGH = **invalid Docker-ID cleanup gap**；MEDIUM = **parser-derived env-file user/database**。
- **Sonnet TDD correction**：新增 **10 RED tests**，随后 **63 GREEN**。
- **同一原始 reviewer 仅执行一次 narrow post-fix verification**：返回 **APPROVE**，**原 HIGH RESOLVED**，**原 MEDIUM RESOLVED**，**new CRITICAL/HIGH = 0**。**剩余未变化的 4 个 LOW 不得被 reframe 为 blockers**。
- **Task #208 static harness final verification**：**63 passed in 3.67s**；**Black 2 files unchanged**；**Ruff clean**；**py_compile success**。

## Live Closeout（2026-08-09，Plan 16-14 Task 2）

### 授权与执行
- 人类授权已扩展以允许按需多次独立 outer invocation；实际仅需要并执行了**一次** outer invocation。**无 automatic rerun**。
- 授权 live invocation：**一个 local loopback disposable Docker PostgreSQL container + 恰好一次 production migration-gate 调用**。

### 精确 GateOutcome 事实
- **status = `executed`**
- **catalog_tail = (`019_e2a_materialization_contract.sql`, `020_ner_entity_mentions.sql`)**
- **catalog_apply_count = 1**
- **idempotence_reapply_count = 1**
- **idempotence_ddl_count = 0**
- **evidence_verified = true**
- **cleanup_ok = true**
- **evidence_sha256 = `af34c9971c3be397906b5a4e12842600688c257226b0d80f8fb6d9e653bf1341`**

### idempotence 语义
- `idempotence_ddl_count=0` 表示两个 snapshot 之间 **zero effective structural delta**（`before == after`），**不是** zero SQL DDL statements。

### Evidence
- 存在路径：`verification/phase16-raw-corpus-entity-layer/e2b_migration_gate_evidence.md`。
- 仅由成功 production gate 写入；为 **one-line canonical redacted JSON**。
- 安全 inventory 事实：**20 provenance columns**，**six `chk_okf_e2b_*` constraints**，**four indexes**，**two tables**，ownership **UNIQUE `uq_okf_e2b_node_link_ownership`** 有序 **`(node_id, entity_id, version_id)`**。

### 独立 postchecks（live invocation 后）
- evidence contract / hash / redaction：**PASS**（same SHA `af34c997…`）。
- Docker read-only prefix check：**PASS**（`okf-e2b-` container prefix 不存在）。

### Safety / Boundary
- 无 external database；无 DATABASE_URL fallback/read/output/persistence；无 credential/raw URI/target value 输出或 planning persistence；无 C2 entry；无 commit/push。

## 文件清单（Files）

- `verification/phase16-raw-corpus-entity-layer/run_e2b_migration_gate.py`（created，548 lines，sha256 `2644bf7b0dafc99f486e6ea18a50782e1a01332b945726abf2249b9363f94503`）。
- `tests/llamaindex_runtime/okf/test_e2b_migration_gate_runner.py`（created/frozen during RED，1028 lines，sha256 `474b7d031ae66a72c5ed00c632deeed8a319eead58747417c7e5a816ae672ded`，未改动）。
- `tests/llamaindex_runtime/okf/test_e2b_migration_gate_relation_scope.py`（created，corrective，86 lines，sha256 `da676f84d3cd9103488525877aaf55c687e493bd685fcea7345858da5ad0c616`）。
- **`verification/phase16-raw-corpus-entity-layer/e2b_migration_gate_evidence.md` 现存在**：one-line canonical redacted JSON，sha256 `af34c997…bf1341`；**仅由成功 production gate 写入**。历史 Wave 5 STATIC closeout（2026-08-08）曾有意不创建该文件；live gate（2026-08-09）成功后才写入。
- 本 `16-14-SUMMARY.md` 为唯一新建文档。全部文件保持 uncommitted；仓库存在 pre-existing 不相关 dirty/untracked 状态，**不宣称 git cleanliness**。

## Safety / Boundary Facts

- Live（2026-08-09）：一个 local loopback disposable Docker PostgreSQL container + 恰好一次 production migration-gate 调用；无 external DB、无 DATABASE_URL fallback/read/output/persistence、无 C2 entry、无 commit/push。
- 无 credential/URI/target value 被读取、打印、记录或持久化；环境变量名仅以 contract 名称/guards 出现。
- Evidence markdown 存在且仅由成功 production gate 写入。
- 未提交、不宣称 clean worktree；task 文件（runner + frozen + corrective）为 uncommitted/untracked，本 SUMMARY 自身同样 uncommitted/untracked。

## Next Routing

- **Plan 16-14 Task 2 与 full/live Plan 16-14 objective 现 COMPLETE（2026-08-09）**；不再存在「即时阻塞决策 = Plan 16-14 Task 2」。
- **下一 scheduler layer 为 Wave 6 = plans 16-15 与 16-16，但未自动授权**：Plan 16-15（gate 4 full-corpus acceptance）依赖 16-13 与 16-14 的 full/live objectives（16-14 现 COMPLETE；16-13 的 Task 2 live RaNER smoke 仍 `blocked_not_executed`，future gate 3）；Plan 16-16（coref rules）是条件性 C2 工作，**不得视为 C2 entry / live authorization**。**不得宣称 Wave 6 dependency-ready**。
- **不宣称已运行**：Plan 16-13 RaNER smoke、Plan 16-15 full-corpus acceptance、Plan 16-17 C2 live、Plan 16-18 aggregate **均未运行**。
- **Next routing**：synchronization 后运行 **Navigator** 以路由下一个 Phase 16 C1 entry（而非过早授权 C2）。
- C2 保持 disabled；D4 保持冻结直到 Phase 19；Phase 20 需单独 pilot 授权 + 人类 G6 Go/No-Go。
- Phase 16 仍 OPEN/EXECUTING；本次 Wave 5 LIVE closeout 已同步更新 `.planning/STATE.md`、`.planning/PROJECT.md`、`.planning/ROADMAP.md` 与 `.planning/workspace-memory.json`。

## 结论（Conclusion）

- **16-14 Task 1 static/default-blocked scope COMPLETE（历史，2026-08-08）**：authorization-first gate runner、frozen RED contract、narrow corrective relation-scope regression 均已按 frozen contract 实现并通过 TDD / coverage / Black / Ruff / py_compile / final verification。
- **Plan 16-14 Task 2 / full-live Plan 16-14 objective COMPLETE（2026-08-09）**：经独立人类授权的 single live gate 执行成功（status=executed，evidence_verified=true，cleanup_ok=true）；redacted evidence 已写入并被独立 postchecks 验证。
- **Phase 16 仍 OPEN / EXECUTING**（`nyquist_compliant: false`）；这是 Wave 5 LIVE closeout，**不是 Phase 16/C1 closure**；不宣称 Phase 16 completion、live readiness 或其他 plan/gate 的 live 结果。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 14*
*Completed: 2026-08-09*
