# GitNexus RAG — Package A (Gate 3 隔离运行时) 交接文档

**交接时间：** 2026-08-29 · **交接人：** 前会话协调器（non-implementing）· **接替对象：** 下一位工程会话

---

## 0. 一句话状态

**Package A（isolated Gate 3 runtime，Task #229）未关闭。** A4 的第二次 HIGH-安全修复已由 sole owner 提交候选，协调器尚未完成独立验证；当前工作最终止于：识别出一个仍待判断/关闭的残余 shadow attack（contract+wheel 双替换），且尚未重新运行 ordered review chain。**首次 Gate 3 live attempt = 0。**

---

## 1. 现在具体进行到哪一步

工作链：`/goal` 命令 + skill → Phase 16 Plan 16-13 → Gate 3 live harness（TDD 完成）→ **Gate 3 需要隔离运行时，因此拆出 Package A（Task #229）**，按 A1→A2→A3→A4 四个子包冻结推进。

| 子包 | 内容 | 状态 |
|---|---|---|
| **A1** | 只读 wheelhouse：`WheelhouseEntry`/`WheelhouseManifest` frozen dataclass + `copy_wheelhouse`（逐字节、无覆盖、按 identity 重校验） | ✅ FROZEN |
| **A2** | staging lifecycle：`create_staging`/`publish_staging`/`cleanup_staging`（prep lock、原子 rename、无覆盖、identity 校验后才清理）+ `StagingError`/`LockContentionError` | ✅ FROZEN |
| **A3** | planning/proof/CLI：`plan_runtime_build`、`run_import_proof`、`build_import_provenance`、`materialize_dependency_provenance`、`verify_runtime_artifacts`、CLI `prepare_raner_runtime.py`（默认 dry-run，需 `--execute`） | ✅ ACCEPTED |
| **A4** | `provision_runtime`：staged execution；无 `allow_execution=True` 时 fail-closed；4 次 subprocess（create_venv、pip deps、pip repo、import-proof）；staged verify→publish→final verify | 🔴 **进行中，未通过** |

**A4 档案（本次要判断的核心）：**
- **第一次 HIGH（source-path TOCTOU）已修复并合入**，对应 RED 测试已存在。
- **第二次 ROUND-RED/GREEN**：sole owner 提交候选修复，机制为三件套：
  1. **pip 消费时 hash 固化** —— `--require-hashes -r <staged contract>`，contract 为 `"<abs path> --hash=sha256:<digest>\n"`；
  2. **verifier 绑定 dist 中的 repo artifact** —— `verify_runtime_artifacts` 末尾对 `dist/<repo_artifact>.name` 哈希并要求等于 `plan.repo_artifact_digest`；
  3. **`mirror_dir=None` 时在任何 runner 调用前 fail-closed**。
- 新增 `repo_artifact_contract_path` 字段（默认为 `None`，非 None 才走 hash-contract 分支）。

**当前执行点：** 协调器只完成了对 `_runtime_builder.py` 与 `test_runtime_builder.py` 关键段的代码阅读，并**已明确识别一个残余 pending attack**，但尚未下结论：

> **contract+wheel 双替换 shadow case**：hash contract 文件本身位于 owned staging tree 内，与它所保护的 wheel 属于同一 attacker domain。若 adversary 同时覆盖 wheel+contract，让 pip 安装 evil 并 hash-check 通过，随后在 staged verify 之前恢复 clean dist，当前 verifier 会读到"干净"的 dist 并接受。**这是否在威胁模型内、是否有代码路径关闭它，尚未判定。**

**尚未完成（防止误报为已完成）：**
- ❌ 未独立重新运行 focused/full/static 验证（owner 声称 GREEN/static PASS 未核实）。
- ❌ 未 hash-verify owner 声称的字节 —— 但**本次交接已由接替会话独立核实**：见 §3 哈希表，**完全一致**。
- ❌ 未重新启动 ordered review chain。
- ❌ A4/Package A 未关闭；Task #229 仍 `in_progress`。

---

## 2. 现在的流程是怎样的

### 2.1 运行约束（用户逐条授权的，均有效，接替会话必须继续遵守）

- **完整禁用**：Docker/PostgreSQL、外部数据库、网络下载、模型下载、RaNER 推理、任何 live gate、C2、commit、push。
- **Workflow 工具禁用**；普通 `Agent` 子代理多 agent 编排**可用**。
- **授权模型**：当前命令级别禁止 proscribed ops；未来 Wave 2–4 须另行授权。
- **Gate 3 可多次运行**（用户已单独授权），但每次 attempt 仍是**单次、不自动重试** safety contract。
- **单一实现 writer**（sole owner）+ **非实现协调器**；reviewer findings 返回给 owner，协调器不得直接改文件。
- **claims untrusted until independently verified**：owner 声称的 GREEN/静态 PASS 一律在接替会话重新跑，不以 owner 陈述为准。
- 所有 Bash 用 `rtk`；需要完整无过滤 pytest 输出时用 `rtk proxy python -m pytest ...`。

### 2.2 工作流状态机（Package A 范围内的实际执行路径）

```
READ STATE (STATE.md / workspace-memory.json / ROADMAP.md)
  → 授权 & 约束核对（proscribed ops 检查）
  → GitNexus impact（编辑任何既有 symbol 前 MUST）
  → 选择最小 ready 工作包
  → 委托 sole owner：RED 测试 → GREEN → refactor
  → ordered review chain：
       Specification → General → Python → Filesystem offline-Security
       → fresh coordinator verification（独立跑，看 diff + 命令输出）
  → HIGH/CRITICAL finding 返给 owner 修复 → 重新投票 → 未解决则保持 BLOCKED
```

- **A1/A2/A3 已走完此链**。A4 第一次修复已走完并被接受；**A4 第二次修复（当前候选）被卡在"独立验证"环节**，尚未进入 review chain。
- `gitnexus_detect_changes()` 在 commit 前 MUST；`gitnexus_impact(... direction:"upstream")` 在编辑任何既有 symbol 前 MUST，HIGH/CRITICAL 需报告并等授权。

### 2.3 A4 复现/验证的确证套路（接替者直接可用）

已知对 staged-copy TOCTOU 的确证复现信号（决定性，不只是静态判断）：
```
PIP_CONSUMED_EVIL=True, PUBLISHED_COPY_EVIL=True, FINAL_VERIFY_ACCEPTED=true
```
→ 若当前候选修复后此组合不再可能成立（pip 层 hash 拒绝 evil、final verify 拒绝漂移的 dist），则该 HIGH defect 视为被关闭。**上一次只读 security reviewer 曾把该缺陷降级为"威胁模型外 MEDIUM"并判 PASS，协调器因与直接证据冲突而拒绝该 PASS —— 接替者不要因为"reviewer 说了"就接受，要以 fresh reproduction 为准。**

---

## 3. 涉及的计划文件、规划文件和产物（清单）

### 3.1 Package A 源码/测试（独立核实哈希 @ 2026-08-29，全部一致）

| 文件 | SHA-256 | 状态 |
|---|---|---|
| `llamaindex_runtime/gate3/_runtime_builder.py` | `d80170fbb3f33ad02b7c1cfdc32af9f45c542e707785e4cab3b16ddba303f068` | A4 当前候选（owner 已交付） |
| `tests/llamaindex_runtime/gate3/test_runtime_builder.py` | `ad38e59858462f05581707ef0dda1f69556817a44ea3c43e31ea27542cc3cec3` | A4 当前候选 |
| `llamaindex_runtime/gate3/_wheelhouse.py` | `38284982a378d2b4ff95f553c894d56943535b1d456a0b92e549973954a170c2` | A1 FROZEN |
| `tests/llamaindex_runtime/gate3/test_wheelhouse.py` | `1a7e3d5cb536067213e7ec1a9b939b082b67cfb80471412ba7f2d6bc01d23854` | A1 FROZEN |
| `llamaindex_runtime/gate3/_staging.py` | `af18d55bf8cfe2109e0bc12c15e29504c1e3b69da8c1f0a5f9acc7764ced7e6d` | A2 FROZEN |
| `tests/llamaindex_runtime/gate3/test_staging.py` | `cea40c60f3ed57f37d27bb1024826d312aac7169792be7b9bebac392af6d9150` | A2 FROZEN |
| `llamaindex_runtime/gate3/_prep.py` | `2480833452d7984fde2d2a77a781cb0592bafa1cbcaa8bc89152dcb2a8b7e0d8` | A3 ACCEPTED |
| `llamaindex_runtime/gate3/__init__.py` | 及 `_lock/_env/_paths/_constants/_reconcile/_fsguard/_publisher/_lifecycle/_registry/_wsl/_parent` | gate3 包既有组件 |

配套：`tests/llamaindex_runtime/gate3/test_prepare_cli.py`（A3）；CLI 运行入口 `verification/phase16-raw-corpus-entity-layer/prepare_raner_runtime.py`（A3，默认 dry-run）。

### 3.2 计划 / 规划 / 状态文件

| 文件 | 用途 |
|---|---|
| `.planning/PROJECT.md` | 项目主文档（modified） |
| `.planning/ROADMAP.md` | 总路线图（modified） |
| `.planning/STATE.md` | **routing snapshot**（modified） |
| `.planning/workspace-memory.json` | **resume/routing 记录，只读解释，非完成证明**（modified） |
| `.planning/phases/16-raw-corpus-entity-layer/` | Phase 16 全部 Plan/Summary：`16-01…16-18-PLAN.md`、`16-01…16-14-SUMMARY.md`、`16-RESEARCH/16-PATTERNS/16-BOUNDARY/16-VALIDATION.md` |
| `.planning/phases/16-raw-corpus-entity-layer/16-13-PLAN.md` | Gate 3 目标 plan；**仍含 stale single-use one-shot Gate 3 措辞，需在首次 attempt 前修正** |
| `.planning/phases/16-raw-corpus-entity-layer/16-13-SUMMARY.md` | Gate 3 静态范围收尾 |
| `.planning/phases/16-raw-corpus-entity-layer/16-LIVE-GATE-TOKENS.json` | live gate token 持久化（Gate 3 单次、不继承、不重试） |
| `.planning/phases/16-raw-corpus-entity-layer/16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json` | **Gate 3 attempt contract**（不消耗授权的 preflight/dry-run 判定基准） |

### 3.3 `/goal` 命令 / skill / 契约测试

| 文件 | 用途 |
|---|---|
| `.claude/commands/goal.md` | 薄 wrap：加载 SKILL.md、透传参数，不含编排逻辑 |
| `.claude/skills/goal/SKILL.md` | 完整编排契约（coordinator hard gate、bounded state machine、writer ownership、GitNexus gate、TDD/review 顺序、live-gate safety、commit 政策） |
| `.claude/skills/goal/tests/test_goal_contract.py` | 契约测试；**仍含 stale single-use Gate 3 措辞，首次 attempt 前需修正** |

### 3.4 Phase 16 verification 产物（`verification/phase16-raw-corpus-entity-layer/`）

| 文件 | 状态 |
|---|---|
| `bin: build_raner_mirror.py`、`run_e2b_migration_gate.py`、`run_raner_smoke_live.py`、`run_raner_smoke_attempt.py`、`run_raner_smoke.py`、`prepare_raner_runtime.py` | 已存在，废弃单次措辞已（部分）修正 |
| `raner_mirror_manifest.json`（618B）、`raner_mirror_evidence.md`、`e2b_migration_gate_evidence.md` | Gate 2 只读镜像链路已证成功（不重跑 Gate 2） |
| **禁止创建**：`.cache/raner-runtime`、`raner_smoke_attempt_registry.jsonl`、`raner_smoke_live_output/<attempt-id>/` | 在真实 attempt 前不得预建 |

现状：**attempt registry 不存在 / attempt count = 0** —— Gate 3 尚未执行过一次真实 live run。

### 3.5 相关未完成 Task（tracker 状态）

- **#229** `in_progress`（== Package A，本交接标的）
- **#221** `in_progress`（isolated runtime，依赖 Package A）
- **#224** `in_progress`（Implement Task 221 with TDD）→ 其 TDD/review/verify 拆分 **#225/#226** `pending`，依赖 #229
- **#215 / #220** `in_progress`（Execute Gate 3 / 受控 runs），blocked by #221；attempt count 0
- **#181** `pending`（Aggregate Phase 16 evidence，等到有真实 runtime/live evidence）

---

## 4. 接替者立即行动（若选择直接继续）

按依赖顺序：

1. **(a)** 重新独立 hash §3.1 的 8 个文件，与表内值比对 —— 本次交接已核过一遍，但接替者应按唯一权威原则自核。
2. **(b)** 跑 focused/full/static：
   - `rtk proxy python -m pytest tests/llamaindex_runtime/gate3/test_runtime_builder.py -q -k test_staged_repo_copy_mutation_rejected_at_pip`（新 RED→GREEN 关键用例）
   - 全量 `test_runtime_builder.py` → 全量 `tests/llamaindex_runtime/gate3/` → black/isort/ruff 检查项 → 限定范围 py_compile/mypy 的 scoped 检查
   - 并**确证 staged-copy TOCTOU 复现信号已不可能**（见 §2.3）
3. **(c)** **判定 contract+wheel 双替换 shadow attack**：是否属威胁模型内、是否有路径关闭（若未关闭，应再走一轮 RED→GREEN）。这是目前唯一 open 的 security 判断点。
4. **(d)** 仅当修复通过且 fixes confirmed 后，**重新启动 ordered review chain**（Specification→General→Python→Filesystem offline-Security→fresh coordinator verification）。
5. **(e)** 首次真实 Gate 3 attempt **之前**，修正三处 stale single-use 措辞：`16-13-PLAN.md`、`.claude/skills/goal/SKILL.md`、`.claude/skills/goal/tests/test_goal_contract.py`。
6. **(f)** 全程遵守 §2.1 约束；**不做任何 live/external/commit/push**；核心工作仍在 Task #229 上。

**防坑提醒：**
- working tree 存在大量 unrelated pre-existing dirty/untracked 文件（`?.planning/**`、`verification/phase11-*`、`llamaindex_runtime/**` 等，见 `git status`）。**最终唯一 authorized commit 时绝不把它们扫进去。**
- owner 的 GREEN/静态 PASS 声称应被视为"待验证"，不是你自己的验收依据。
- 不要因任何 reviewer（包括之前那位把 HIGH 降成 MEDIUM 的）的 PASS 而跳过独立复现。