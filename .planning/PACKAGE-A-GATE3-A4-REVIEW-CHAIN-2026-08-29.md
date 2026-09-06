# Package A / A4 — Ordered Review Chain 判定记录（接替会话 · planning-only）

**日期：** 2026-08-29 · **角色：** 接替会话（non-implementing 协调器，route/dispatch/verify/report only）· **标的：** A4 第二次 HIGH-安全修复候选（`_runtime_builder.py` d80170fb`…` / `test_runtime_builder.py` ad38e598`…`）

> 本文档为 planning-only 判定记录，不改动任何生产/测试代码。依据：交接清单 §4 (d)（ordered review chain 重启）；§2.1 约束（claims untrusted until independently verified；协调器绝不自写 source/test；reviewer findings 返回 owner）。

**状态：** (e) 已于 2026-08-29 完成（TDD RED→GREEN：test_goal_contract.py 3 failed → 88 passed；black/ruff clean；16-13-PLAN.md Task 2 已按 per-attempt 契约修订并加 Additive Note #4）。A4 / Package A（Task #229）review chain **CLOSED** — 通过，无需返回 owner。**Gate 3 首次 attempt 前置条件（pre_launch_contract_amendment_required）已满足。**

---

## 1. Ordered Review Chain — 四阶段结果

| 阶段 | 角色 | 子代理 | Result | CRITICAL/HIGH/BLOCKER | 关键发现 |
|---|---|---|---|---|---|
| 1 Specification compliance | spec 合规 | `5fe8f588` | **APPROVE_WITH_NOTES** | 0/0/0 | (a)(b)(c)(d) 四件套逐项核验完整且语义正确；冻结件接口兼容（`create_staging`/`publish_staging`/`cleanup_staging`/`run_import_proof`/`validate_wheelhouse` 签名未变；`RuntimeBuildPlan` 唯一构造点 L370 全 keyword、新字段带默认值置末尾）；scope creep 未发现；测试断言未删减。唯一 LOW：`plan_runtime_build`(:257) 未强制 `repo_root` 绝对路径，相对路径时 contract 偏离规范 (a) 明文 `<abs path>`（暴露面低，建议 resolve 或断言） |
| 2 General code quality | code-reviewer | `7c5ef01c` | **APPROVE_WITH_NOTES** | 0/0/0 | MEDIUM: verify_runtime_artifacts(:732-845) 6 处 artifact 读取各自重复 5-7 行 try/except 样板，建议提取 `_read_checked`（纯维护性，行为测试已覆盖）；8 LOW（:931 惰性 replace、:536-554 校验失败不清残缺文件、:607-624 pyvenv 解析器重复、:977 局部导入、超时魔法数字、:677-703 proof_result 命名、:1000-1001 contract 幽灵路径、:372-379 恒真断言）+ 6 INFO |
| 3 Python language | python-reviewer | `24966e03` | **APPROVE_WITH_NOTES** | 0 BLOCKER | 生产代码 A4 新增全部类型完备（PEP 604/526，无 Any）；Path 纪律正确；`from __future__ import annotations` 存在；3.11 兼容；0 行 >88 列；import 分组正确；无 F401/F841/B006/B008/B904；dataclass 字段顺序合法；错误链正确。WARNING-1（tests 未注解闭包，非 lint-gated，与文件既有风格一致）；INFO-1（docstring "five artifacts" 已扩为 6 读）；INFO-3（contract 路径含空格 → pip requirements 解析风险，**已由阶段 4 Judge 3 闭环**） |
| 4 Filesystem offline-Security | security-reviewer (adversarial) | `fc986c61` | **APPROVE_WITH_NOTES** | 0/0/0 | Judge 1：三件套**确实关闭单替换 TOCTOU**（L919 重捕获 + L537-554 xb/fsync/读回 + L927-930 contract + L997/L1004 双 verify）。Judge 2：**双替换独立判定在威胁模型外**（同权限写；ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md L162-183 + 16-13-PLAN.md threat_model L107-124）。Judge 3：亲自核验 pip 24.0 `req_file.py:394-432` `break_args_options`，**未加引号的含空格 contract 路径正确 round-trips**（INFO-3 闭环；加引号反而会破坏）。Judge 4：对抗性覆盖强。WARNING-1（`:533-534` staging/dist mkdir 无 reparse 链检查，与 A1/A2 惯例不一致，内容仍 digest 绑定 → 退化 indirection/DoS）；WARNING-2（verify docstring 未声明 "certifies dist copy, not installed venv site-packages" 边界）；6 INFO |

**判定口径：** 无 CRITICAL / 无 HIGH / 无 BLOCKER → **按 goal SKILL.md 流程，review chain 通过，无需返回 owner 修复**。

## 2. 跨阶段一致性确认

- **单替换 TOCTOU 关闭**：阶段 1（实现语义）+ 阶段 4（pip 哈希语义实测 + 攻击面）+ 协调器 adjudication（真实 pip 24.0 TEST B rc 1）三方独立一致。
- **双替换 shadow attack 在威胁模型外**：协调器 adjudication §3 + 阶段 1（独立复核）+ 阶段 4（独立复核 Judge 2）三次独立判定一致 —— 均援引 ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md L173-183（"does not establish hostile writer exclusion" / "stronger storage boundary"）+ 16-13-PLAN <threat_model> T-16-44~47（无文件写入 adversary）。评审子代理均被明确要求"不要因协调器说了就接受"，结论为独立得出。
- 无阶段间冲突（阶段 3 INFO-3 由阶段 4 Judge 3 闭环；阶段 2/3 的 docstring "five artifacts" 漂移为同族 INFO）。

## 3. 阶段 5 — Fresh Coordinator Verification（全部当场重跑，claims untrusted until verified）

| 检查项 | 命令 | 结果 |
|---|---|---|
| Focused RED 关键用例 | `rtk proxy python -m pytest tests/llamaindex_runtime/gate3/test_runtime_builder.py::TestA4StagedProvisionLifecycle::test_staged_repo_copy_mutation_rejected_at_pip -q` | **1 passed** |
| 全量 A4 测试文件 | `… test_runtime_builder.py -q` | **105 passed** |
| 全量 gate3 测试目录 | `… tests/llamaindex_runtime/gate3/ -q` | **566 passed, 4 skipped** |
| black | `python -m black --check llamaindex_runtime/gate3/` | **16 files unchanged** |
| ruff | `python -m ruff check llamaindex_runtime/gate3/` | **All checks passed** |
| mypy scoped | `python -m mypy llamaindex_runtime/gate3/_runtime_builder.py` | **A4 候选文件 0 错误**；70 errors 全在其它 20 个既有/冻结文件 |
| py_compile | `python -m py_compile …` | **exit 0** |

**结论：owner 声称的 GREEN/静态 PASS 由协调器独立复跑成立；(d) ordered review chain 全部通过。**

## 4. Follow-up 清单（非阻塞，记录备查）

- 阶段 2 MEDIUM：`__read_checked` 重构（verify_runtime_artifacts 读取样板）——建议随 A4 提交或后续清理。
- 阶段 4 WARNING-1：`_materialize_repo_artifact_copy` `:533-534` mkdir 前 lstat/reparse 拒绝 dest 链（参照 `copy_wheelhouse` A1 惯例）+ mkdir 错误归一化。
- 阶段 4 WARNING-2：`verify_runtime_artifacts` docstring 注明 "certifies dist copy, not installed venv site-packages"。
- 阶段 1 LOW：`repo_root` `resolve()` 或断言绝对路径（contract `<abs path>` 规范字面格式）。
- 阶段 2/3 INFO：docstring "five artifacts" → six；模块拓扑清单补 `wheelhouse_manifest.json`/dist；contract 精确字节格式回归测试；`BuildStep.network_denied` 伪字段；超时常量；plan 工厂合并（测试侧）。
- **以上均不触发 A4 返工或不通过；按 §2.1 当前候选视为通过 review chain。**

## 5. 下一步

- **(e)** 首次真实 Gate 3 attempt 前修三处 stale single-use 措辞（`16-13-PLAN.md`、`.claude/skills/goal/SKILL.md`、`.claude/skills/goal/tests/test_goal_contract.py`）——**DONE 2026-08-29**：TDD RED→GREEN——test_goal_contract.py 起 3 failed（test_skill_first_run_gate3_granted_execute_once、test_skill_live_gates_section、test_skill_gate3_per_attempt_contract）→ SKILL.md 修订 → 88 passed；black + ruff clean；16-13-PLAN.md Task 2 已按 per-attempt 契约修订并加 Additive Note #4。SKILL.md 现编码 per-attempt 授权契约 16-GATE3-ATTEMPT-CONTRACT-2026-08-12（Task #222）：Gate 3 每次 attempt 为全新不可变 attempt_id、launch_committed 先于任何 model loader、supervised-launch 协议、attempt 终态（terminal per attempt）、无自动重试/循环/并发、后续 attempt = 新 attempt、测量重复非重试；Gate 4 措辞未变（仍为单独单次使用、未授权）。
- A4 / Package A（Task #229）review chain 关闭 —— **CLOSED，2026-08-29**。关闭标记 2026-08-29；(e) contract amendment completed；next = 真实 Gate 3 首次 attempt 前需执行 supervised-launch protocol 检查 (Task #221) — NOTE: Task #221 implementation status must be verified before any launch; the contract requires an OS-backed attempt registry + supervised parent+worker + startup barrier; do not launch before that is verified present.

## 6. A4 关闭标记 (2026-08-29)

A4 / Package A（Task #229）CLOSED. Review chain 通过；阶段 5 独立复跑成立；(e) TDD contract amendment 完成（88 passed）。(b)/(c)/(d) 全部落地：哈希核对 ✅ / 独立复跑 ✅ / 双替换威胁模型外判定 ✅ / review chain ✅。Follow-up 清单（§4）保持记录但不阻塞：`_read_checked` 重构、`:533-534` mkdir reparse 链检查、verify docstring 边界、repo_root resolve、docstring 5→6 等。下一步：Gate 3 首次 attempt（先验证 Task #221 实现 + 执行 preflight）。
