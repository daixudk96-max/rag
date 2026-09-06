# Package A / A4 — 独立验证判定记录（接替会话 · planning-only）

**日期：** 2026-08-29 · **角色：** 接替会话（non-implementing 协调器复核）· **标的：** A4 第二次 HIGH-安全修复候选（`_runtime_builder.py` d80170fb… / `test_runtime_builder.py` ad38e598…）

> 本文档为 planning-only 判读记录，不改动任何生产/测试代码。依据：接替清单 §4 (b)/(c)；§2.3 确证套路；§2.1 约束（claims untrusted until independently verified；不因任何 reviewer 的 PASS 而跳过独立复现）。

---

## 1. (b) focused / full / static 独立复跑结果（全部由接替会话重新执行）

| 检查项 | 命令 | 结果 |
|---|---|---|
| 新 RED→GREEN 关键用例 | `rtk proxy python -m pytest tests/llamaindex_runtime/gate3/test_runtime_builder.py -q -k test_staged_repo_copy_mutation_rejected_at_pip` | **1 passed, 104 deselected** |
| 全量 A4 测试文件 | `… test_runtime_builder.py -q` | **105 passed** |
| 全量 gate3 测试目录 | `… tests/llamaindex_runtime/gate3/ -q` | **566 passed, 4 skipped** |
| black | `python -m black --check llamaindex_runtime/gate3 tests/llamaindex_runtime/gate3` | **35 files unchanged** |
| ruff | `python -m ruff check …` | **All checks passed** |
| isort | `python -m isort` | 未安装该模块（环境无 standalone isort）；等价检查 `ruff --select I` 仅冻结文件 `_lifecycle.py:14` 报既有 I001（非 A4 候选文件） |
| py_compile | `python -m compileall -q llamaindex_runtime/gate3 tests/llamaindex_runtime/gate3` | **exit 0** |
| mypy scoped | `python -m mypy llamaindex_runtime/gate3/_runtime_builder.py` | **A4 候选文件 0 错误**；gate3 包内其余错误全部位于冻结/既有组件（`_lock.py`、`_wsl.py:105`、`_paths.py:29`、`_registry.py:496`、`_publisher.py:123`、`_lifecycle.py` 多处），与 A4 候选变更无关 |

**结论：owner 声称的 GREEN/静态 PASS 已由接替会话独立复核成立。**

## 2. (b) §2.3 复现信号确证 — 独立真实 pip 实验（非模拟 runner）

实验（`.tmp/pip_hash_semantics_test.py`，全本地 wheel、`--dry-run`、无网络、无产物落地；pip 24.0 / Python 3.11.9）：

| 测试 | 场景 | 真实 pip 结果 |
|---|---|---|
| A | good wheel + contract 内 good hash | **rc 0，接受**（"Would install"） |
| B | 同路径覆盖为 evil 字节，contract 仍为 good hash（单替换 = HIGH-1 TOCTOU 核心主张） | **rc 1，拒绝**——`THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE… Got 1579ba…` |
| C | 同路径 evil 字节 + contract 改为 evil hash（双替换 wheel+contract） | **rc 0，接受**（pip 层无法阻止双替换） |
| F | bare 路径 arg + `--require-hashes`（无 -r） | rc 1（pip 要求 hash 规格；裸路径无 hash 被拒） |

**§2.3 复现信号逐项核实：**
- `PIP_CONSUMED_EVIL=True` → **不可能**：真实 pip 在 hash 校验处拒绝（TEST B rc 1），builder 将 `RuntimeBuildError("build step failed: pip_install_repo")` fail-closed，绝不 publish。
- `PUBLISHED_COPY_EVIL=True` → **不可能**：`_materialize_repo_artifact_copy`（读回重校验）+ staged `verify_runtime_artifacts` 末尾 dist digest 绑定（"repo artifact digest does not match the plan digest"）双重防护；且 publish 为原子 no-overwrite。
- `FINAL_VERIFY_ACCEPTED=true` → **不可能**：final verify 用原始 plan（digest 绑定）重校验 dist。

**⇒ HIGH-1（source-path / staged-copy TOCTOU 单替换）视为已被关闭。**

## 3. (c) 判定：contract+wheel 双替换 shadow attack **不在威胁模型内，无需新 RED→GREEN**

### 3.1 事实（双替换为何成立）
真实 pip TEST C 证明：若 attacker 同时覆盖 wheel 与其 contract（后者含 `--hash=sha256:<evil>`），pip 会接受 evil。该组合未被任何现有代码路径关闭。

### 3.2 该攻击所要求的权限 = 与 builder 同权限的 staging-tree 内部文件写入
- A2 的 root-identity 绑定（lstat st_dev/st_ino + Linux parent-fd renameat2）只保护 **staging 根**：替换根目录会在 publish/cleanup 被检测并 fail-closed（内核级 inode 不可伪造）。
- 双替换必须**直接写 staging 内部文件**（`dist/<wheel>` 与 contract），或具备与 builder 相同的目录写权限。

### 3.3 该类攻击为何在 Package A 威胁模型之外（三条独立证据链）
1. **A2 官方文档化残余（`llamaindex_runtime/gate3/_staging.py` docstring 56-66、82-89）**：rename primitive 为 by-name 无 source-fd 绑定；替换落在窗口内**检测并 fail-closed 但不阻止**；明确写 "does not establish hostile writer exclusion"。
2. **项目唯一威胁模型声明（`.planning/ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md` 162-183）**："Hostile simultaneous writer"（173-177）明确 fail-closed 只防不稳定观测、**不建立 hostile writer exclusion**；182-183 进一步写明："Deployments requiring writer exclusion, ownership proof, or true multi-file atomicity need a stronger storage boundary or coordination mechanism outside this ADR."——同权限写文件（含"恢复 clean"从而绕过硬哈希）正属于该类 "stronger storage boundary" 之外。
3. **16-13-PLAN 的 <threat_model>（T-16-44…T-16-47）**：仅覆盖 model load / compatibility fabrication / model substitution / evidence disclosure，未声明同权限文件写入 adversary。

### 3.4 若双替换被纳入模型，则任何文件级修复都无效（一致性论证）
具有同权限写能力的 attacker 可对**最终产物**做同等攻击（build 成功后直接改写 final venv/site-packages 或各 proof JSON），无需依赖 staging 窗口；此时不存在任何基于文件哈希的闭环方案，唯一出路是 3.3-2 所指的"stronger storage boundary"（异机/只读介质/密封签名）。因此"双替换必须闭环"这一要求若成立会自我矛盾——除非改变存储边界假设，而边界假设归 ADR 管理，不在 A4 代码范围内。

### 3.5 结论
- 双替换 shadow attack **在 Package A / gate3 威胁模型内不可达**（须同权限写文件），**无需新增 RED→GREEN**。
- 但按诚实记录惯例，本判定及"真实 pip TEST C rc 0"证据须随 A4 通过材料一起保留，供后续 reviewer 复核（防止"reviewer 说了就接受"）。
- 上一次只读 security reviewer 将该缺陷降级为"威胁模型外 MEDIUM"并判 PASS：本接替会话**不依赖该 reviewer 的措辞**，基于 3.1-3.4 独立复现与推理给出同一结论。

## 4. 后续（对应 §4 清单）
- **(d)** 重启 ordered review chain（Specification → General → Python → Filesystem offline-Security → fresh coordinator verification）——本记录为 review 输入。
- **(e)** 首次真实 Gate 3 attempt 前修三处 stale single-use 措辞（`16-13-PLAN.md`、`.claude/skills/goal/SKILL.md`、`.claude/skills/goal/tests/test_goal_contract.py`）——gate 前动作，本次不动。
- 全程遵守 §2.1；不做 live/external/commit/push。

## 关闭标记 (2026-08-29)

A4 / Package A（Task #229）CLOSED. (e) TDD contract amendment 完成：test_goal_contract.py 3 failed (RED) → 88 passed (GREEN)；black/ruff clean；SKILL.md + 16-13-PLAN.md Task 2 已按 per-attempt 契约（16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json）修订。双替换判定在威胁模型外（本 adjudication §3 保持成立）。Gate 3 首次 attempt 前置条件满足；launch 前仍需验证 Task #221 实现（attempt registry + supervised-launch + startup barrier）与 preflight（exact runner、read-only mirror、offline-only env、no DB routes、no writable model/cache persistence）。
