# Phase 18 wave-plan (tdd-graph-plan 产物; 2026-09-03)

## Self-check 四问

1. **本阶段解决什么问题?** 让 Agent 能把知识回写提案进 OKF: .staging/ 提案区 + 强制人审 + 白名单合入执行器 + F3 同步触发。核心不变式 = '不存在未经 approved 状态写 OKF 正文的代码路径' (R-OKF-07)。同时按用户 2026-09-03 决策清偿 Phase 17 全部登记欠账 (F3/F4/F6/F7/F8/F9/F10/F11/F12/F13 + fusion F401/keyword 去重/workspace 接线)。
2. **怎么验证解决?** 每波 TDD (canonical 测试先行, RED→GREEN); 4 路只读评审 (Spec/General/Python/Security); 协调器 fresh verification; wave-7 18-VERIFICATION 证明无人审旁路 (静态调用路径 + raw/ 拒写测试 + parser 零摄取); wave-8 live 端到端 (届时用户授权)。
3. **依赖与顺序?** wave-1 → wave-2 → wave-3 → wave-4 → wave-5 (检索债, 独立可并行) / wave-6 (卫生债, 依赖 wave-4 共享模块裁决) → wave-7 (18-VERIFICATION, 依赖 1-4) → wave-8 live (依赖全部, 需授权)。
4. **失败回退?** tdd-graph 引擎本环境 4/4 prepare FAILED_FATAL 无重试原语 → **正式决策: 不用引擎, 全程手动接力棒模式** (协调器备稿 canonical 测试+工单 → 转写/实现工人 TDD → 评审链 → 协调器复验), 16-16/W6/W7/W6.5 五次成功先例。compile 不跑 (canonical tests 每波执行期才 author, 引擎 run 必死无收益)。单波失败 → 工单退回 owner 修复, 评审链重验; 全链失败 → 备稿自检。

## 波次表

| Wave | 交付 | dependsOn | 状态 |
|---|---|---|---|
| W0 | 侦查: okf_bundle 结构+AGENT.md 编辑分区+parser.py 现状+F3 同步流实况+上游蓝本核实 (llm-wiki-compiler §5/§7, open-knowledge PORT/COPY) | - | todo (协调器侦查, 无代码) |
| wave-1-proposal-schema | NEW llamaindex_runtime/okf/writeback/{__init__,proposal}.py (WritebackProposal schema: proposal_id/target_file/patch/reason/evidence/proposed_by/created_at/status/unverified 标记) + EDIT llamaindex_runtime/okf/parser.py (.staging/ 排除) | wave-0 | todo |
| wave-2-lifecycle-journal | NEW writeback/lifecycle.py (状态机 created→reviewed(approved/rejected)→merged/discarded, 非法迁移 fail-closed) + writeback/journal.py (JSONL 审计含 approvedBy/approvedAt/rejectedReason) | wave-1 | todo |
| wave-3-review-cli | NEW verification/phase18-controlled-okf-writeback/run_writeback_review.py (list/show/approve/reject/merge; diff 展示; 锁下重读防 TOCTOU) | wave-2 | todo |
| wave-4-merge-executor | NEW writeback/merge_executor.py (可写白名单 entities/concepts/synthesis 前缀; RFC7396 merge-patch; raw/ 拒写必抛; 断链校验; F3 同步触发 seam 注入) | wave-3 | todo |
| wave-5-retrieval-debts | F11 BM25 真路线 (ranked_fusion 真实 bm25_titles 源 seam 接线 TDD) + F4 LLM-primary 路由代码可达性 (行使留 wave-8 live) | wave-4 | todo |
| wave-6-code-hygiene | F3 共享桥接模块抽取 / F6 验收不变量 / F7 demo 三门+expected-DB 等值 / F8 目录校验 / F9 超时对称+loop 清理 / F10 语言杂项 / F12 UNKNOWN 缓解 / F13 working_dir 语义 / fusion.py F401 / keyword 去重 / workspace 接线 | wave-4 | todo |
| wave-7-verification | NEW run_phase18_verification.py + tests: R-OKF-07 goal-backward (静态无旁路+raw 拒写+parser 零摄取) | wave-4 | todo |
| wave-8-live-gates | 端到端: 产提案→CLI 批准→合入→hash 变化→同步→检索可见 + 驳回路径零变化 | wave-7 | todo (**需用户届时授权**) |

## 执行模式记录
- 引擎决策: tdd-graph run 本环境确定性坏死 (4/4 FAILED_FATAL) → 接力棒; compile 推迟到 wave-1 执行期 (canonical 测试先行时点)。
- 每波节奏: 协调器备稿 (canonical 测试+工单) → 转写/实现工人 TDD → 4 路只读评审 → 修复轮 → 协调器 fresh verification → 关单。