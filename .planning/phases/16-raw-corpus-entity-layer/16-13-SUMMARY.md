---
phase: 16-raw-corpus-entity-layer
plan: 13
type: execute
wave: 3
macro_wave: W4
depends_on: [16-12]
requirements: [R-OKF-04, R-OKF-06]
files_modified:
  - verification/phase16-raw-corpus-entity-layer/run_raner_smoke.py
  - tests/llamaindex_runtime/entity/test_raner_smoke_runner.py
  - llamaindex_runtime/entity/compatibility.py
  - tests/llamaindex_runtime/entity/test_compatibility.py
  # NOTE: the plan also lists raner_smoke_evidence.md / raner_resource_report.json.
  # Neither exists in the repo: both are produced ONLY by an authorized Task 2
  # smoke run, which was never authorized. They are intentionally NOT present.
summary:
  - .planning/phases/16-raw-corpus-entity-layer/16-13-SUMMARY.md
key-decisions:
  - "Task 2 (blocking decision gate, future gate 3) was NOT authorized; the default blocked_not_executed path is the delivered, tested, frozen contract."
  - "Bounded static scope only: runner never carries an exact-authorization live branch and never sets/reads the exact authorization value beyond the strict-equality fail-closed check; exact value also remains fail-closed in this static build."
  - "Task 2 (no evidence file on unauthorized) vs Task 3 (record blocked status in evidence) conflict is resolved by recording blocked_not_executed only via runner stdout, compatibility current constants, and this summary — no live evidence/resource file is fabricated."
  - "16-13-PLAN.md:99 stale candidate-fails-closed prose is overridden by the frozen existing MentionCandidate contract: a model candidate may carry runtime_compatibility_id=None until a separately authorized smoke."
requirements-progress: [R-OKF-04, R-OKF-06]
duration: "multi-round TDD + coordinator verification + single one-time Sonnet broad review (0 CRITICAL / 0 HIGH / 2 MEDIUM / 5 LOW, APPROVE_WITH_NOTES, no second review)"
completed: 2026-08-08
---

# Phase 16: Plan 13 Summary

**16-13 bounded static scope COMPLETE；full/live Plan 16-13 objective 仍 OPEN / BLOCKED_NOT_EXECUTED（Task 2 未授权）；Phase 16 仍 OPEN/EXECUTING**

## 状态边界（Status Boundaries）

- **16-13 bounded static scope COMPLETE**：`run_raner_smoke.py`、`compatibility.py` 及两份 frozen RED test 已按 frozen contract 实现并通过 TDD / coverage / review / final verification。本计划当前授权仅覆盖静态/default-blocked 范围。
- **full/live Plan 16-13 objective 仍 OPEN / BLOCKED_NOT_EXECUTED**：真实本地 RaNER offline smoke、Windows/WSL 资源测量、以及从实测 smoke 结果冻结 `runtime_compatibility_id`，均要求 **Task 2（blocking decision gate，未来 gate 3）的单次授权**；Task 2 未获得授权，故这些 live 目标未执行、未完成。**不得宣称 full Plan 16-13、live readiness、C1 live-model closure 或 Phase 16 完成**。
- **Phase 16 仍 OPEN / EXECUTING**；本文件仅为 16-13 bounded static 收尾，不宣称 Phase 16 closure。下一 authorized 静态工作为 **Wave 3 static closeout**，而非 Task 2 执行。
- **无真实模型/网络/持久化**：没有真实 RaNER offline smoke、没有 model/mirror access/create/download、没有 heavy import、没有 inference、没有 ModelScope、没有 WSL/resource measurement、没有 evidence generation、没有 DB/PostgreSQL/Docker/network、没有 live gate、没有 C2、没有 commit/push。
- **无凭据**：未读取/打印/记录/持久化任何 credential value、connection URI 或 target value；变量名仅以守卫约束文字出现在 canonical selector 中。
- **未提交、不宣称 clean worktree**：四个新 production/test task 文件（`run_raner_smoke.py`、`compatibility.py` 与两份 frozen 测试）保持 uncommitted/untracked；本 `16-13-SUMMARY.md` 自身同样 uncommitted/untracked；仓库存在大量 pre-existing 不相关 dirty/untracked 状态，本文件不宣称 git cleanliness。

## 计划身份（Plan Identity）

- Plan **16-13**，scheduler **wave 3**，macro **W4**，requirements **R-OKF-04 / R-OKF-06**，depends_on **16-12**（gate 2 mirror builder）。
- Type：`execute`；Task 1 为 auto 实现（单次授权 smoke + 资源测量 runner）；Task 2 为 blocking decision gate（未来 gate 3，单次授权真实本地 smoke + Windows/WSL 资源测量）；Task 3 为 auto 冻结（从实测 smoke 冻结 `runtime_compatibility_id`）。Task 2 未获得授权，故 delivered 契约即默认 `blocked_not_executed` 路径。

## 授权范围（Authorization Scope）

**当前授权仅覆盖**：
- 静态 / default-blocked runner（`run_raner_smoke.py`）；
- 纯 stdlib + contract-helper 的 `compatibility.py`（unresolved/blocked 状态 + pure freeze seam）；
- 本地纯测试（`test_raner_smoke_runner.py` / `test_compatibility.py`）。

**不覆盖**：真实 RaNER model load/inference、model/mirror access/create/download、ModelScope、Windows/WSL resource measurement、evidence/resource 文件生成、DB/PostgreSQL/Docker/network、live gate、C2、commit/push。

## 生产实现事实（Production Implementation Facts）

### 1. `verification/phase16-raw-corpus-entity-layer/run_raner_smoke.py`

- **19 行**，sha256 `47384afc3a562c08ba6741f5ef45c6d816e21a0e482ddfd1a9b6723ce481dfa8`。
- **仅 import `os`**；常量 `AUTH_ENV = "OKF_E2B_RANER_SMOKE_AUTHORIZED"`、`AUTH_VALUE = "1"`、`BLOCKED_STATUS = "blocked_not_executed"`。
- **授权 env 是唯一的 env lookup，且是 `main()` 的第一个可执行动作**：无 env 枚举/复制、无 mirror-root 读取（`RAG_NER_MIRROR_ROOT`）、无其他 operational seam 位于 blocked decision 之前。
- 授权**缺失或非精确值**（`!= "1"`）时：stdout **恰好** `blocked_not_executed\n`、**返回码 1（非零）**、零模型加载、零 evidence/resource 写入。
- **精确授权值在本 bounded static build 中也有意保持 fail-closed**（同一 blocked 分支）：本静态构建不含 live path、不含 subprocess/WSL/psutil/timing/resource measurement、不含网络、不含 model/mirror loader、不含 evidence/resource writers；exact-auth 分支从未被设置/执行。
- **不导出**自 `llamaindex_runtime.entity` facade。

### 2. `llamaindex_runtime/entity/compatibility.py`

- **100 行**，sha256 `1ab888a0aefe51b03f9edb0d8f336895b0ed4b4d2cd01a2959c0d6bb8649da00`。
- **纯 stdlib + `canonical_json_sha256`**（来自 `llamaindex_runtime.entity.contracts`）；无 heavy/network/DB import。
- **immutable blocked/current 状态，id 为 None**：`BLOCKED = RuntimeCompatibilityState("blocked_not_executed", None)`；`CURRENT_STATUS = "blocked_not_executed"`；`CURRENT_RUNTIME_COMPATIBILITY_ID is None`。
- **exact-field pure validation**：`_validate_evidence` 要求顶层恰好 10 个记录字段、`resource_envelope` 恰好 4 个测量值；digest 必须是 64 lowercase hex；测量值必须为有限非负 int/float。
- **deterministic canonical hash**：`compute_compatibility_id` 对等值 evidence 稳定、对任一 material 分量变化而变化（canonical SHA-256）。
- **`freeze` pure seam**：production `freeze()` **纯粹校验 schema/值 并对 caller 提供的 evidence 做 canonical hash**，返回 `RuntimeCompatibilityState("frozen", computed)`；它**不能证明测量 provenance**，因此**不能替代独立授权的 Task 2 live evidence**。测试仅以**完整合成 recorded-shape mapping** 作为输入（非真实测量）。拒绝 non-mapping / 缺失 / 类型错误 / None / 非有限 / 显式 blocked evidence；不虚构 id。
- **unexported and unwired**：未从 facade 导出、未接入 adapter。

## TDD Evidence

| Stage | Result | Detail |
|---|---|---|
| **Initial RED 修正** | 修正后接受 | 初始 RED 含一条不可能成立的 facade-attribute 断言；在验收前修正——因为 import 一个 Python 子模块会将其作为 package attribute 附加到包上。最终测试改为：无显式 facade import + 断言 `compatibility` 不在 `__all__`（并检查 package `__init__` source 中无 `.compatibility` / `import compatibility`）。 |
| **Black 预格式化** | 两份测试均冻结前机械 Black-formatted | `test_raner_smoke_runner.py` 与 `test_compatibility.py` 在冻结前均经 Black 格式化。 |
| **Final accepted RED（coordinator，Black 后）** | `2 errors in 2.28s` | 仅因 `run_raner_smoke.py` 缺失（`FileNotFoundError`）与 `compatibility` 子模块缺失（`ImportError`）而 collection 失败；此时**无任何生产文件**存在。 |
| **Minimal GREEN** | agent = `60 passed in 1.30s`；coordinator fresh focused = `60 passed in 2.97s`；coordinator coverage selector = `60 passed in 1.83s` | 最小实现满足 frozen contract：default blocked 路径 + unresolved compatibility + pure freeze seam。 |
| **Frozen 后** | hash 不变 | 冻结后（post-Black）的两份 test hash 自 GREEN 起经 review / final verification **从未改变**。 |

**Frozen test（Black 后、首个完整 GREEN 时冻结，此后未改动）：**

- `test_raner_smoke_runner.py` — **298 行**，sha256 `f95445475882243d48e7fe7b5c3134643890fc14102df119e54a1213391d52c9`
- `test_compatibility.py` — **348 行**，sha256 `166b8c21f942dd9a032aa9d104a9332721093711407fb7ba60ddbe421e33982d`

Selector（focused，与 16-07/16-08/16-12 一致的完整 12-variable env-clean guards；canonical 执行/安全形式为外层 `rtk env -u ...`（完整 12 变量）+ 嵌套 `rtk proxy pytest ... -q`，变量名仅以守卫约束文字出现，不在此复述）：

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED rtk proxy pytest tests/llamaindex_runtime/entity/test_raner_smoke_runner.py tests/llamaindex_runtime/entity/test_compatibility.py -q
```

## 最新 coordinator final verification（post-summary-correction fresh run）

Fresh exact evidence（canonical 完整 12-variable cleanup + 嵌套 `rtk proxy pytest`）：
- **Focused selector**：`60 passed in 1.53s`。
- **Full pure entity suite**：`651 passed, 1 skipped in 6.66s`。
- **Coverage figures 说明**：`compatibility.py` **96%**（53 statements, 2 missed）、`run_raner_smoke.py` **83%**（12 statements, 2 missed；exact-authorization 分支**有意未执行**）、**total 94%** 为**先前 dedicated coverage measurement，予以保留**——summary-only 事实性修正期间**无 production/test 代码变更**；该 coverage run **未在 post-summary 重新执行**，本文件不声称其为 post-summary 运行。
- **CLI/coverage 链说明（历史，描述上述先前 coverage 测量）**：初始 `&&` 链式 coverage 命令因 CLI 期望的 rc 1 而在该处停止；随后**单独读取** coverage report——这是期望的 blocked 行为，**不是测试失败**。
- **Black**：`4 files would be left unchanged.`
- **Ruff**：`No issues found`
- **py_compile**：success（exit 0 / no output）
- **Hashes 未变**：冻结后 hash 与 final verification 一致。
- **evidence/resource artifacts 缺失**：`raner_smoke_evidence.md` / `raner_resource_report.json` 在 blocked 调用前后均不存在；verification 目录在 blocked 调用前后不变（无创建、无删除）。

## 审核（Review Boundaries）

- 同一稳定内容**仅执行一次 Sonnet broad review**；**未执行第二次 broad review**。
- 结果：**0 CRITICAL / 0 HIGH / 2 MEDIUM / 5 LOW；verdict `APPROVE_WITH_NOTES`**。

### MEDIUM（accepted/deferred——非当前静态缺陷，记录待后续硬化）

1. 公开 `RuntimeCompatibilityState` 构造器可绕过 `freeze`；在**未来 adapter 接线前**需硬化。
2. canonical hash 区分 numeric `int` 与 `float`；在真实 Task 2 测量前需先冻结 metric dtypes。

**明确**：以上 MEDIUM **未修复**，仅记录为 deferred；本 summary 不作"已修复"声明。

### LOW（recorded/unfixed）

1. runner 有意保留完全相同的 authorized/unauthorized fail-closed 分支，且无 exact-auth regression test（该 flag 现在**不得**被设置）。
2. magic literal `"frozen"` 而非常量。
3. nonempty-string helper 依赖 canonical serializer 实现 Unicode-scalar rejection / error precision。
4. 无 module-local `__all__`（cosmetic；package facade 有意保持 unexported）。
5. 可选显式测试 negative int / bool / bad digest / extra envelope key；当前行为经 inspection 确认拒绝。

**明确**：以上 LOW **均未被修复**；本 summary 仅如实记录。

## Frozen Plan Conflict Resolution / Deviations

- **Task 2 vs Task 3 冲突**：Task 2 说 unauthorized => 无 evidence file；Task 3 说在 evidence 中记录 blocked status。当前人类授权**明确只允许 deferred status**。**Resolution**：不创建任何 live evidence 文件；`blocked_not_executed` 仅通过 runner stdout、compatibility current constants 与本 summary 记录。**无虚构 live evidence/resource 数据**。
- **`16-13-PLAN.md:99` stale candidate-fails-closed prose**：被 frozen 的既有 `MentionCandidate` contract 覆盖——model candidate 在独立授权 smoke 之前**可以**携带 `runtime_compatibility_id=None`（contracts.py 已确认该字段 conditionally nullable）。**无 contracts/adapter 修改**。
- **Exact-auth live branch 有意缺失**：精确授权值从未被设置/执行。
- **无依赖真实 smoke 的 requirement-completion 声明**：R-OKF-04 / R-OKF-06 仅作为**静态 progress / guard coverage** 描述，不声称 live completion。

## Safety / Boundary Facts

- 无真实 smoke、model/mirror access/create/download、heavy import、inference、ModelScope、WSL/resource measurement、evidence generation、DB/PostgreSQL/Docker/network、live gate、C2、commit 或 push。
- 无 credential/URI/target value 被读取、打印、记录或持久化。
- 仓库存在大量 pre-existing 不相关 dirty/untracked 状态；**不宣称 repo cleanliness**。四个新 production/test task 文件（`run_raner_smoke.py`、`compatibility.py` 与两份 frozen 测试）为 untracked，本 SUMMARY 自身同样 uncommitted/untracked。
- **Operational honesty（缓存清理）**：GREEN 清理阶段，一个 subagent 在清理新生成 runner bytecode 时移除了 verification 目录的 `__pycache__`；RED 探索曾记录该目录已含一个 ignored/untracked pre-existing `build_raner_mirror` pyc。**无 tracked source/evidence 文件被移除**，但**不得声称零无关 generated-cache 清理**。
- **Command-guard honesty**：所有 substantive pytest / coverage / format / lint / compile / CLI 命令均使用完整 12-variable env-clean guards + `rtk`；**一次** coordinator 只读 `git diff --no-index` 命令中一个 E2A cleanup-key 名称有 typo（不枚举/读取/打印环境值，无 DB/network/model 行为）。因此**不得声称每次 Bash 调用都具备完美的 12-name guard**。

## 文件清单（Files Created）

- `verification/phase16-raw-corpus-entity-layer/run_raner_smoke.py`（created，19 lines，sha256 `47384afc3a562c08ba6741f5ef45c6d816e21a0e482ddfd1a9b6723ce481dfa8`）。
- `llamaindex_runtime/entity/compatibility.py`（created，100 lines，sha256 `1ab888a0aefe51b03f9edb0d8f336895b0ed4b4d2cd01a2959c0d6bb8649da00`）。
- `tests/llamaindex_runtime/entity/test_raner_smoke_runner.py`（created/frozen during RED，298 lines，sha256 `f95445475882243d48e7fe7b5c3134643890fc14102df119e54a1213391d52c9`）。
- `tests/llamaindex_runtime/entity/test_compatibility.py`（created/frozen during RED，348 lines，sha256 `166b8c21f942dd9a032aa9d104a9332721093711407fb7ba60ddbe421e33982d`）。
- **无 `entity/__init__.py` 修改**。
- **`raner_smoke_evidence.md` / `raner_resource_report.json` 未生成**（plan files_modified 列出但仅由授权 Task 2 smoke 产生）。
- 本 `16-13-SUMMARY.md` 为唯一新建文档。全部文件保持 uncommitted；仓库存在 pre-existing 不相关 dirty/untracked 状态，不宣称 git cleanliness。

## Next Integration Notes

- **Task 2 保持独立 gated**：需 `OKF_E2B_RANER_SMOKE_AUTHORIZED=1`（单次）**且** gate-2 verified mirror；未收到授权，无 auto-retry / 无 authorization inheritance。
- `raner_smoke_evidence.md`、`raner_resource_report.json`、measured/frozen `runtime_compatibility_id`、adapter wiring、Windows/WSL metrics 均属**未来授权工作**。
- **本 summary 之后的下一个 authorized 工作是 Wave 3 static closeout，而非 Task 2 执行**。
- Phase 16 仍 OPEN/EXECUTING；本文件不修改 STATE/ROADMAP/workspace-memory。

## 结论（Conclusion）

- **16-13 bounded static scope COMPLETE**：default-blocked runner、unresolved compatibility 模块、两份 frozen RED test 均已按 frozen contract 实现并通过 TDD / coverage / Black / Ruff / py_compile / final verification。
- **full/live Plan 16-13 objective 仍 OPEN / BLOCKED_NOT_EXECUTED**：真实 smoke、资源测量、实测冻结 `runtime_compatibility_id` 因 Task 2 未授权而未执行。
- **Phase 16 仍 OPEN / EXECUTING**；不宣称 live readiness、C1 live-model closure 或 Phase 16 completion。

---

*Phase: 16-raw-corpus-entity-layer*
*Plan: 13*
*Completed: 2026-08-08*


---

## Task #220 Gate 3 live-harness preflight reconciliation addendum（2026-08-11）

> **本 addendum 记录 Task #220（Gate 3 live harness）确切的非消费型 preflight 结果与 Gate 3 授权真相。它不取代本文件上方 16-13 bounded-static 状态与 `run_raner_smoke.py` frozen 静态契约；它补充当前 live-readiness/preflight 真相。Gate 3 仍为 `blocked_not_executed`；未发生任何 live smoke、model load、WSL benchmark、evidence 生成或 token 消费。**

### 协调者 fresh evidence（已只读核验）

- **Live runner** `verification/phase16-raw-corpus-entity-layer/run_raner_smoke_live.py` — sha256 `9e09ba547e94c35fc51c2bbde1ab234b1efee3e90d2c6e7499e9abc953ffb0cf`（磁盘核验一致）。
- **Live contract** `tests/llamaindex_runtime/entity/test_raner_smoke_live_runner.py` — sha256 `7b6578c51029c59b9346e8a071b2e9df0fe19eb5cc0273544b12c9ceb955ef4b`（磁盘核验一致）。
- **RSS contract** `tests/llamaindex_runtime/entity/test_raner_smoke_live_rss.py` — sha256 `22e7d28bddc17c0ad5e0653e6cbc65efa8fb6f440b802572a2c2f370ecd2206a`（磁盘核验一致）。
- **Frozen static runner** `run_raner_smoke.py` — sha256 `47384afc3a562c08ba6741f5ef45c6d816e21a0e482ddfd1a9b6723ce481dfa8`（不变，仍为本文件上方 frozen 契约）。
- **Frozen static test** `test_raner_smoke_runner.py` — sha256 `f95445475882243d48e7fe7b5c3134643890fc14102df119e54a1213391d52c9`（不变）。
- **Focused live-harness suite**：`63 passed in 1.11s`。
- **Mirror load_mirror 核验**：精确只读 mirror `.cache/raner-mirror`（artifact_digest `1c53105d095c7839446332d34f5693b6dfc56b286ed19de2ab27b68905895424`；7 个文件全部 Windows read-only 且 non-reparse）。
- **Output 目录缺失**：`verification/phase16-raw-corpus-entity-layer/raner_smoke_live_output` 不存在 —— 无 live 运行。

### Runtime blockers（preparation gaps，Task #221）

- `modelscope` 1.39.1 已安装，但 `modelscope.pipelines` import 失败：`ModuleNotFoundError: No module named 'addict'`（已只读复核）。
- NLP extra audit：17 个缺失依赖；已安装 `protobuf` 6.33.5 与 frozen 要求 `>=3.19,<3.21` 不兼容（已只读复核 protobuf 6.33.5）。
- `llamaindex_runtime/uv.lock` stale（`uv lock --check` exit 1）。
- WSL 可用，但当前 runner 的 default probe 记录 `unavailable` 而非实测 RaNER envelope —— formal available-WSL evidence 未解决。

### Authority truth（授权真相）

- 用户消息 `'允许'`（transcript line 82057）回答的是紧邻其前的 **static TDD package 请求**，该请求明确说明 **不会重新授权或消费 Gate 3**。
- Materialization ledger `16-LIVE-GATE-TOKENS.json` 明确声明 **grants no runtime authority**。
- **Gate 3 仍为 `blocked_not_executed`，`launch_committed=false`，`execution_claimed=false`**；workspace-memory `gate_token_ledger` 结构不变（`state=authorized_unconsumed`）。
- **Task #221 为 preparation blocker**，需要人工决定 network/package installation；**Task #220 未 launch，且被 #221 阻塞**。

### Next steps（next_recommended）

1. 取得 **preparation-only package/network 授权**（Task #221 人工决定）。
2. 构建并验证 **isolated runtime**（含 addict 与满足 `>=3.19,<3.21` 的 protobuf），使 `modelscope.pipelines` 可 import。
3. 关闭 **WSL measurement gap**（显式 available-WSL probe）。
4. **随后另行取得** Gate 3 单次 launch 授权，才可原子消费 `OKF_E2B_RANER_SMOKE_AUTHORIZED`，至多一次 real local RaNER offline smoke + Windows/WSL resource measurement。

**边界事实**：本次 addendum 为 planning-only；未 launch live gate、未设置授权、未安装包、未加载模型、未运行 WSL benchmark、未生成 evidence、未 commit/push。

*Appended: 2026-08-11 (Task #220 planning-only reconciliation)*


---

## Task #222 current Gate 3 authorization contract reconciliation addendum（2026-08-12）

> **本 addendum 记录 Task #222 对当前 Gate 3 授权模型的最新 reconcile（planning-only）。它不取代本文件上方的 16-13 bounded-static 状态、frozen 静态契约或 Task #220 preflight addendum；它补充当前 multi-attempt 授权真相。16-13 的 Task 2 措辞（single-use/no-retry）与 `/goal` skill/tests 仍编码过时的 single-use/no-retry Gate 3 语义，需在首次 Gate 3 launch 之前由单独 TDD-governed contract amendment 修正；Task #222 不改生产/test/skill 代码。**

- **Authorizing message**：`行，我授权继续吧然后 gate3 可以多次运行`（2026-08-11）。**Task #221 隔离运行时准备（official Python package access，仅限 repository-local 隔离准备；使 modelscope.pipelines 可 import；关闭 WSL measurement gap）已授权**；明确不授权 preparation-time model loading、RaNER inference、real WSL model benchmarking、live evidence publication、external DB、DATABASE_URL read/fallback、C2、commit、push、修改全局 C:\Python311。
- **Gate 3 = multi-attempt-by-explicit-launch**：每次 attempt 由 coordinator 单独显式发起，fresh immutable attempt_id，在任何 model loader 开始前 durable 记录（launch_committed），对该 attempt 在 success/failure/timeout/interruption/crash 上 terminal，失败永久保留；无 automatic retry、无 autonomous loop、无 concurrency；later attempt 是 new explicit attempt，绝非 failed ID 的 retry；attempt 内三次 timed inference passes 是 measurement repetitions，不是 retries。
- **当前契约 artifact**：`.planning/phases/16-raw-corpus-entity-layer/16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json`（schema 1.0；state machine `blocked_not_executed -> launch_committed -> ok | execution_failed`；timeout/interruption/crash 为 terminal failure reasons）。
- **历史 token 文件**：`16-LIVE-GATE-TOKENS.json` 逐字节保留，never reinterpreted as current runtime authority。
- **Canonical evidence / compatibility freezing**：只有独立验证成功的 attempt 才可被选为 canonical evidence；compatibility freezing 是独立 downstream action（绑定 named attempt_id + evidence hashes + mirror digest + measured artifacts），live runner/launcher 不得自动 freeze。
- **Gate 4** 仍未执行、本消息未授权；**C2** 仍 OFF/skipped_not_entered；**Task #181** 仍 pending；**no commit/push**。
- **Task #221 implementation blockers 已记录未实现**；read-only agent 的 obsolete single `.gate3-consumed` marker 与 single-use launcher proposal **未采用**；GitNexus CLI fallback `rtk proxy npx gitnexus ... -r rag` 已核验记录。
- **边界事实**：本 addendum 为 planning-only；未 launch live gate、未设置授权、未安装包、未加载模型、未运行 WSL benchmark、未生成 evidence、未 commit/push。

*Appended: 2026-08-12 (Task #222 planning-only reconciliation)*


---

## Task #227 Task #224 LIMIT_REACHED stop adjudication addendum（2026-08-12）

> **本 addendum 记录 Task #227 对 Task #224（Task #221 isolated-runtime-preparation scope 的实现）独立 specification review 后的当前停止状态：LIMIT_REACHED。它不取代上方 16-13 bounded-static 状态、frozen 静态契约、Task #220 preflight addendum 或 Task #222 授权契约；它补充当前 preparation 实现停止与 resume 授权真相。Gate 3 仍为 `blocked_not_executed`；未发生任何 live smoke、model load、WSL benchmark、attempt 发起、package 安装、evidence 生成或 token 消费。**

- **Task #224 remains INCOMPLETE；stop status = LIMIT_REACHED（NOT COMPLETE / NOT BLOCKED / NOT LIVE_GATE_FAILED）。**
- **Coordinator 此前观测的 fresh focused selector：`121 passed in 3.85s`** —— 仅证明 unit seams，**不是 specification compliance，也不是 production composition**。
- **两次 independent read-only specification reviews 均返回 BLOCK。**
- **Decisive preparation blocker**：runtime pip 配置为 `--no-index --find-links .cache/raner-runtime/dist`，但 **没有任何 production mechanism 去 populate/validate 该 dependency wheelhouse**；因此 fresh authorized build 无法安装 locked dependencies，也无法达成必需的 `modelscope.pipelines` import proof。
- **Additional confirmed gaps**：
  - parent-only WSL measurement provider **不跨越真实 subprocess boundary**；
  - runtime builder **增量地 mutate 最终 runtime**，而非 whole-runtime staging/atomic publication，且**缺乏 no-overwrite/preparation concurrency protection**；
  - prepare CLI **以 text mode 读取 lock**，CRLF raw-byte identity 未被保留；
  - import/network proofs **未绑定到精确的 build/venv/mirror/lock/repository artifact**；
  - **无 production launcher 组合 LaunchSpec+supervise_launch**。
- **Package history**：`Remediate Gate3 supervisor` 与 `Remediate Gate3 contract`（后者被明确识别为 active second remediation）。**Bounded changed-approach remediation allowance 已耗尽；不得再推断或静默派发任何 writer。**
- **Exact resume point**：需要 **explicit user authorization** 授予一个 **newly replanned/extended remediation package**；之后先对每个要编辑的现有 symbol 运行 **GitNexus upstream impact**，再执行 **fresh TDD**。**不得将其表述为 existing authorization。**
- **Tasks #221/#225/#226/#220/#215 保持 blocked/incomplete；Task #181 仍 pending。**
- **Gate 3 attempt count = 0**：未创建 runtime attempt registry、lock、attempt evidence 或 `.cache/raner-runtime` runtime；本次 adjudication 中**无 package installation / model / network / database / C2 / live 活动、无 compatibility freeze、无 commit、无 push**。
- **Exact user boundary 逐字保留、不作历史范围重释**：“禁止 Docker/PostgreSQL、外部数据库、网络或模型下载、RaNER 推理、任何 live gate、C2、commit 和 push；Wave 2–4 仍须另行授权。”
- **边界事实**：本 addendum 为 planning-only；未 launch live gate、未发起 attempt、未安装包、未加载模型、未运行 WSL benchmark、未生成 evidence、未 commit/push。

*Appended: 2026-08-12 (Task #227 planning-only adjudication record)*
