# Phase 18 (交接书阶段 E): Controlled OKF Writeback — Boundary Document

**Drawn:** 2026-07-12（plan-everything-execute-nothing 指令下的预规划产物）
**Depth:** 边界级。进入 PLAN 时由 `/gsd-plan-phase 18` 细化——本文件即其输入。
**Authority:** 交接书 §11-E + 总纲 D8 + ADR T8 + 里程碑边界裁决 5。

## Entry Gate

1. Phase 17 关闭（检索消费面就绪——回写改善的对象存在）。
2. 用户明确放行执行。

## Goal

让 Agent 能把检索/使用过程中沉淀的知识**提案**回 OKF：proposal/staging 区 + 强制人工审阅后合入，合入后走 canonical-hash 同步流（F3）入库。人类编辑始终一等公民；Agent 自动 commit 不存在于本阶段（需未来单独用户批准 + 质量门）。

## In Scope

- staging 区设计：`okf_bundle/.staging/`（或 PLAN 时定的等价位置，明确在 bundle 内但不被 parser 当正文摄取——parser 需显式排除 staging 路径）。
- 提案格式：目标文件 + diff/新内容 + 理由 + 证据引用（span_id 溯源）+ 提案者标识 + 时间戳。
- 提案生命周期：created → reviewed(approved|rejected) → merged|discarded；全程落审计记录（OKF 内 journal 文件或 DB 表，PLAN 时定，倾向 OKF 内——审计本身也是知识资产）。
- 人审界面形态：最小可行 = CLI 审阅命令（列出/查看/批准/驳回）；不做 Web UI。
- 合入执行：批准后由工具把提案应用到 `entities/`、`concepts/`、`synthesis/`（绝不触碰 `raw/` —— T1/T2 机器专属区），随后 F3 同步入库。
- 权限硬化：以测试证明不存在任何"未经 approved 状态即修改 OKF 正文文件"的代码路径。

## Out of Scope（红线）

- Agent 自动 commit / 自动合入（T8：需单独用户批准，本阶段不实现该开关，连 off 状态的实现都不做——不存在的代码是最安全的代码）。
- 对 `raw/` 与 sidecar 的任何回写（机器生成区只能由 serializer 重新生成）。
- git 自动操作（提案合入只改工作区文件；commit/push 永远由人做——沿用全程 git 纪律）。
- 提案质量的自动评分（属 19 的评估域）。

## Deliverables（PLAN 时映射为 waves）

1. 提案 schema + staging 区 + parser 排除规则（TDD）。
2. 提案生命周期状态机 + 审计 journal。
3. CLI 审阅工具（list/show/approve/reject/merge）。
4. 合入执行器（只写 entities/concepts/synthesis + F3 同步触发）。
5. 18-VERIFICATION：R-OKF-07 goal-backward——重点证明"无人审旁路"。

## Draft Acceptance Criteria

- 端到端演练：Agent 产提案 → staging → CLI 人审批准 → 合入 entities/ → canonical hash 变化 → 同步入库 → 检索可见。
- 驳回路径演练：驳回后 OKF 正文零变化、审计留痕。
- 静态 + 测试双证：不存在绕过 approved 状态写 OKF 正文的调用路径；raw/ 在合入执行器的可写路径白名单之外。
- parser 对 .staging/ 内容零摄取。

## Key Files / Context Pointers

- `okf_bundle/AGENT.md`（14-01 已声明编辑分区——本阶段的机器可写白名单以它为准并回写更新）
- `llamaindex_runtime/okf/parser.py`（staging 排除规则落点）
- F3 同步流实现（14-03 sync + 15 的量产化成果）
- **上游设计蓝本（研究文档 §5/§7）**：审阅队列按 llm-wiki-compiler（MIT，TypeScript——设计翻译为 Python）：一提案一 JSON 文件、驳回入 archive/、结构化 HeldReason 码表、锁下重读候选（TOCTOU 防护）、"正文原子 + 尾段 best-effort 可重跑"的诚实分层；**我们增补**其缺失的显式审计字段 approvedBy/approvedAt/rejectedReason。
- **open-knowledge（GPL-3.0，用户裁决 2026-07-12 解禁——项目自用不分发；衍生文件必须打 GPL 来源头标，绊线见研究文档 §7）**：
  - PORT：`frontmatter-merge.ts` 的 RFC 7396 merge-patch 语义（提案的 frontmatter 变更表达）、`doc-name.ts` 写入准入校验（合入执行器白名单前置）、`atomic-yaml-write.ts` 陈旧 tmp 孤儿清扫、断链检测（提案合入前校验）。
  - COPY：`consolidate-body.ts` 的 STOP 决策确认门文本（人审 approve 提示语底稿）、grounding/persist-as-you-go 纪律（agent 提示词）、log 纪律 `## YYYY-MM-DD: <summary>` + 每次写操作 ≤80 字符 summary 字段的双层审计结构。
- 全表见 `.planning/research/UPSTREAM-SOURCE-ANALYSIS-2026-07-12.md`。

## Open Questions（进 PLAN 时必须先答）

1. 提案的证据引用强制性：无 span_id 溯源的提案是否允许进 staging？（倾向允许进但标记 unverified，人审时可见）
2. 审计 journal 放 OKF 文件还是 DB 表？（倾向 OKF：审计随知识包走；DB 只是缓存）
3. 并发提案对同一目标文件的冲突策略：先到先审 + 合入后其余提案强制 rebase 重审？

## Risks

| 风险 | 缓解 |
|---|---|
| 提案污染知识正文 | staging 物理隔离 + parser 排除 + 状态机门 |
| 人审疲劳导致橡皮图章 | 提案必须带理由与证据引用；CLI 展示 diff 而非全文 |
| 合入器越权写 raw/ | 可写路径白名单 + 专项测试（尝试写 raw/ 必须抛错） |
