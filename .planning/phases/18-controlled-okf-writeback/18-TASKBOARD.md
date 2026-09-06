# Phase 18 任务板 (轻量; trellis allowlist 未解, 沿 17 惯例)

主规划: 18-PLAN-MASTER-2026-09-03.md | 更新: 2026-09-03

| Wave | 内容 | 状态 | 执行者 |
|---|---|---|---|
| W0 | 侦查 (bundle/parser/F3/蓝本/碰撞) | DONE (notes/w0-recon.md, 协调器抽查全吻合) | w0-recon (ff3a5e38) |
| W1 | 提案 schema + .staging + parser 排除 (TDD) | DONE (2026-09-03) 初版 30 + 修复轮 FIX-1..12 → 37 passed 协调器复验; 4 路评审 0C/3M→全修; 组合 7 域 29 failed 全预存 | w1-writer (25fb36ee) + graph compile (run-9423d5t4 引擎5连败→接力棒) |
| W2 | 提案生命周期状态机 + 审计 journal | DONE (2026-09-03) journal.py 67 passed 协调器复验 (golden 双 id/转移矩阵/tamper 检测/容器自证); okf 5 预存/3308; 组合 29 预存/4788 | w1-writer (25fb36ee) |
| W3 | CLI 审阅工具 list/show/approve/reject/discard | DONE (2026-09-03) cli.py 49 passed 协调器复验 (退出码表 0/1/2/3 + 5 子命令 + 适配层唯一 now + bundle 零写入红线测试); okf 5 预存/3357; 组合 29 预存/4837 | w1-writer (25fb36ee) |
| W4 | 合入执行器 (白名单+RFC7396+raw 拒写+F3 触发) + W2.1 per-proposal journal scoping | DONE (2026-09-04) graph run-w5yvgnis reviewer APPROVE candidate 300b93c → 引擎 writer 额度耗尽 → 协调器手动落地 + W2.1 FIX-2 (工人 7023e83d); focused 24 passed (15 apply + 9 scoping) 协调器亲验; okf 5 预存/3381/31; gate3 2/598/4 不变 | graph-writer (70f50301) + reviewer (246168ec) + fix-worker (7023e83d) |
| W5 | 债务清偿波 (F3/F4/F6/F7/F8/F9/F10/F11/F12/F13 + fusion F401/keyword 去重/workspace) | DONE (2026-09-04) 已在 Phase 17 任务板 W5a/W5b/W5c 行执行并关单 (交叉登记; 17-PLAN-MASTER §27): follow-ups 13→8 closed, F11/F12/F4-live/F14-residual recorded; focused 97→105→108→114 复验过 | transcriber (7023e83d) |
| W6 | 18-VERIFICATION 无人审旁路证明 | DONE (2026-09-04) 静态 4 + 功能 5 检查 verified 9/0 实跑 exit 0; focused 18 复验过; 组合 1559/3/1; 证据 sha 96F5D605… | transcriber (7023e83d) |
| W7 | Live 验收 (届时授权) | DONE (2026-09-04) 一次性副本全链 executed: 提案→CLI 人审 (rc 0)→合入 (frontmatter 保留+journal merged)→parser 重解析 (3 docs, .staging 零摄取); 真实 bundle 未动+副本已焚毁; 证据归档 executed_2026-09-04; 4 份预存 malformed 模板页如实登记 | 协调器 (用户 chat ok 授权) |

## 备注
- 引擎 5 连败 (run-9423d5t4 prepare FAILED_FATAL) → 接力棒模式: canonical 备稿 + 转写工人 (25fb36ee)。
- wave-1 冲突处理范例: worker 发现 canonical 夹具 bug (BundleDocuments 无 .documents 属性) 即停上报, 协调器修 canonical, 断言零削弱。
- 4 路评审 id: spec c4487a28 / general eeae0c2f / python c4ac539a / security 33b76c96 (2026-09-03 派发)。