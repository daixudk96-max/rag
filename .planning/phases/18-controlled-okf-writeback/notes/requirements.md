# Phase 18 requirements (tdd-graph-plan collect 产物; 2026-09-03)

## options
- repoRoot: E:/github/rag; testsRoot: tests; allowTestsUpdate: false (新测试文件为主); checks: security/architecture 由既有 4 路评审链承担 (引擎 AI 审查节点不用); coverage/gauntlet: 不启用 (引擎不跑)。

## 全局 mustNot
- raw/ 与 sidecar 零回写; 自动合入代码不存在 (T8); 无 git 自动操作; 无网络/模型下载/RaNER 推理/live gate 未经授权; 冻结件字节不动 (entity/{label_map,contracts,normalization,identity,fuzzy_recall,review_basket,relation_review,coref_rules,uie_adapter}.py, extraction/trial.py, graph/lightrag_backend.py, analysis/graph_channel.py); 测试永不削弱; .planning 历史文档零删除。

## waves (compile-ready schema 草案)
- wave-1-proposal-schema: tests=[okf/test_writeback_proposal.py, okf/test_parser_staging_exclusion.py]; spec=WritebackProposal frozen dataclass (proposal_id=uuid5(NAMESPACE_URL,'okf-writeback-proposal-v1'+payload), target_file 相对路径准入校验, patch/diff str, reason 非空, evidence=span_id refs tuple (空→unverified=True), proposed_by 非空, created_at 注入时钟 seam, status 钉 created); staging 落盘 .staging/<proposal_id>.json 原子写; parser.py 排除 .staging/ 路径 (lstat 链校验)。AC: A01 合法提案 round-trip==原值; A02 无 span_id → unverified=true 仍可落盘; A03 target_file 含 raw/ → ValueError; A04 parser 对 .staging/ 内容零摄取 (fixture: staging 放正文样张, parse 输出不含)。
- wave-2-lifecycle-journal: tests=[okf/test_writeback_lifecycle.py]; spec=transition(approved|rejected|discarded) 状态机 (非法迁移 ValueError; approved 必须 approvedBy; journal append JSONL 单行 ensure_ascii=False+换行, 记录 approvedBy/approvedAt/rejectedReason)。AC: B01 created→approved 合法且 journal+1; B02 approved→rejected 抛; B03 无裁决人 approve 抛。
- wave-3-review-cli: tests=[okf/test_writeback_review_cli.py]; spec=CLI 五子命令 list/show/approve/reject/merge; show 展示 diff 非全文; 审阅时锁下重读提案文件 (TOCTOU 防护, 蓝本); 退出码 0 ok / 1 无提案或用法错。AC: C01 list 空目录 exit 0 输出 0 行; C02 approve 无裁决人 exit 2; C03 show 输出含 diff 不含全文。
- wave-4-merge-executor: tests=[okf/test_writeback_merge_executor.py]; spec=合入执行器: 白名单前缀 (entities/|concepts/|synthesis/) 之外 raise; raw/ 尝试必抛 (专项测试); RFC7396 merge-patch frontmatter; 断链校验 (引用的 chunk/文件存在); 合入后 canonical-hash 变化记录; F3 同步触发经注入 seam (本波不真跑同步)。AC: D01 写 raw/ 路径 raise (专项); D02 未 approved 提案 merge 抛; D03 合入后 hash 记录变化。
- wave-5-retrieval-debts: tests=[analysis/test_bm25_route.py]; spec=F11 BM25 真路线: bm25_titles 真实源 seam (从既有检索面注入) + ranked_fusion 消费; F4 LLM-primary 路由可达性代码侧确认 (行使留 wave-8)。AC: E01 bm25 非空时 fusion 分数>0; E02 两路来源 sources=('graph','bm25')。
- wave-6-code-hygiene: tests=[phase17/test_shared_bridge.py 等]; spec=F3 抽共享桥接模块 (runner/demo ~210 行→共享); F6 验收不变量 (executed 需满足阈值断言); F7 demo 三门对齐+expected-DB 等值; F8 目录绝对+reparse 校验; F9 超时对称+loop 清理句柄; F10 语言杂项; F12 UNKNOWN 缓解; F13 working_dir 语义; fusion.py F401; keyword 去重; workspace 接线。AC: F01 共享模块导入零 litellm 重依赖; F02 demo 缺门 exit 1; F03 raw/ 外路径 spawn 拒。
- wave-7-verification: tests=[okf/test_phase18_verification_result.py]; spec=run_phase18_verification.py: 静态调用路径扫描 (grep 级证明无 bypass) + parser 零摄取运行时证明 + raw/ 拒写证明 + 审计完整性; 证据落盘 18-VERIFICATION.md。
- wave-8-live-gates: 需用户授权; 端到端 + 驳回路径 + F4 LLM-primary 行使; 证据归档。

## 边界与依赖锚
- 18-BOUNDARY.md (70 行) 为权威范围; 上游蓝本 = llm-wiki-compiler (MIT) §5/§7 审阅队列设计 + open-knowledge (GPL-3.0) PORT (frontmatter-merge RFC7396 / doc-name 写入准入 / atomic-yaml-write tmp 清扫 / 断链检测) + COPY (STOP 门提示语 / grounding 纪律 / log 纪律双层审计); GPL 衍生文件须源头标注; 全表 .planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md。
- F3 同步流 = 14-03 sync + 15 量产化成果 (Phase 15); okf_bundle/AGENT.md 编辑分区为准 (W0 核实)。