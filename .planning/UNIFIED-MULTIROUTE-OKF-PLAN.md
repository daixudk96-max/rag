# 联用方案 v3 —— OKF 权威源 + 多路检索统一架构（已拍板）

> 状态：**决策已定稿**（2026-07-12 navigator 会话）
> 本文档是总纲，编排下列两份既有计划，冲突处以本文档为准：
> - `.planning/LLM-WIKI-Integration-PLAN.md`（v2.0，OKF↔DB 双向闭环）
> - `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md`（低 Token 实体层 WS0-WS4）

---


> **Phase 14 canonical-path ratification (2026-07-17).** `OKF_BUNDLE_ROOT` (default `okf_bundle`) is the bundle-root authority; canonical templates are under `okf_bundle/templates/`; and `scripts/rebuild_from_okf.py` is the only canonical E1 CLI. `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` is a legacy sample/test fixture only, not a second canonical root. `scripts/rebuild-from-okf.py` is unsupported; no compatibility wrapper or duplicate tree is required. This ratification controls any earlier conflicting path wording. Phase 14/E1 is **BOUNDED CLOSED/PASS**; Phase 15 is authorized, planned, and execution-unstarted. No Git or DB authorization is inferred from this plan.

## 1. 已拍板的四项决策

| # | 决策点 | 用户裁决 |
|---|---|---|
| D1 | OKF 地位 | **OKF 为唯一权威源（SSOT）**：所有持久化知识存 OKF .md，Git 管版本，DB 是可重建的派生缓存；完整派生物化由 E2a/E2b 各自负责，E1 不构成全索引重建（维持 LLM-WIKI v2.0 的 SSOT 立场） |
| D2 | 非 OKF 文档入口 | **全部转 OKF**：docling 解析 PDF/Word 的输出落成 `okf_bundle/raw/*.md`，之后统一从 OKF 摄入，彻底单源 |
| D3 | 实施入口 | **OKF 底座先行**：先落地 OKFParser 完善 + 实体表 migration + OKF 实体页零 Token 入库；WS1 NER 抽取器随后为 raw 语料补数据 |
| D4 | 评测/诊断 | **延后**：Level 2（hit_rate 70%）的 PageIndex 配置诊断、Phase 14 三方对比、评测集扩建全部后置，先实现功能计划 |

用户原话（D4）："这个诊断再说吧，后续怎么提高再说，我们先把功能的计划实现。"

## 2. 目标架构

```
PDF/Word ──docling──→ OKF 序列化器 ──┐
                                     ├─→ okf_bundle/   ← 权威源（Git 版本控制）
人类(Obsidian) / Agent 回写 ─────────┘      ├── raw/        原始文档转写
                                            ├── entities/   实体页（canonical+aliases，零Token）
                                            ├── relations/  关系页（含否定/条件限定词）
                                            └── concepts/   概念页
                                     │ git commit → post-commit hook
                                     ↓
                    摄入管线（OKFParser → Entity/Relation/Vector/Tree Processor）
                                     ↓ 派生索引可在其 E2 owner 范围内重建（非 E1 全索引重建）
        派生索引 DB：canonical_spans | vector_chunks | tree_nodes
                     entities + entity_aliases + entity_mentions | semantic_edges
                                     ↓
        四路并联召回（同一索引底座上的四种遍历策略）：
          R1 纯向量        R2a PageIndex树状      R2b PageIndex热点      R3 实体/图谱多跳
                                     ↓
              `analysis/fusion.py::fuse_candidates` 统一融合（R3 作为额外来源；不新设融合函数）
                                     ↓
              QueryHit（含 okf_file_path 溯源）──→ Agent 发现新关系/别名 ──→ 回写 OKF（闭环）
```

联用的三种机制（递进，不互斥）：
1. **并联融合**：四路同时召回，融合层统一打分。
2. **路间增强**：实体层给其他路喂信号——`node_entity_links` 让树遍历/热点聚类按实体命中选节点；jieba+实体词典改善 keyword path。
3. **回写闭环**：检索发现的新知识写回 OKF → DB 重建 → 四路同时受益。

## 3. D2（全部转 OKF）的关键工程影响 ⚠️

这是四项决策里工程冲击最大的一项，实施阶段 A 必须正面解决：

1. **新增 docling→OKF 序列化器**：docling 输出 → Markdown + YAML frontmatter（`type: raw`、来源文件、checksum、版本）。页码/heading/字符偏移等 span 坐标要素必须以段落级元数据保留在 OKF 文件中（frontmatter 或段落锚点），否则证据链断裂。
2. **span_id 稳定性需重新验证**：现行 span_id = uuid5(doc_id|version_id|page|headings|offset|text)。摄入源从 docling 直出改为 OKF raw 中转后，同一文档必须产出**相同的 span_id**（或提供确定性映射），Phase 1-13 的全部验证数据以此为锚。这是阶段 A 的硬验收项。
3. **NormalizationContract 的输入面变化**：contract 的消费对象从 docling 数据结构变为 OKF 文档模型（OKFDocument/OKFParagraph），需要适配层而不是改写 contract 本身。
4. **E1 证明边界**：`scripts/rebuild_from_okf.py` 仅在已注册/受保护的 provenance parents 范围内，以 raw frontmatter + sidecar 确定性协调 `canonical_spans` 并证明幂等；它不进行 vector/tree/人工实体关系证据或 NER association 的全量物化。E2a 负责完整 vector/tree 与人工 OKF materialization，E2b 负责 NER-derived associations。

## 4. 实施阶段（合并两计划后的统一顺序）

| 阶段 | 内容 | 来源计划 | 前置 |
|---|---|---|---|
| **A. OKF 底座** | OKFParser 完善（增量/删除检测）；docling→OKF 序列化器（§3.1）；migration：okf_sync_state + okf_rebuild_log + **entity_aliases/entity_mentions/entity_merge_log**（表结构在此一次定稿）；rebuild-from-okf 脚本；span_id 稳定性验证 | LLM-WIKI Phase 1 + GraphRAG WS1 的 migration 前移 | 无 |
| **B. 摄入管线** | Entity/Relation/Vector/Tree Processor；post-commit hook + Sync Service；OKF 实体页/关系页**零 Token 直接入库**（frontmatter 即结构） | LLM-WIKI Phase 2 | A |
| **C. raw 语料实体层** | jieba 计划执行（已定稿）；`llamaindex_runtime/entity/` 抽取器（领域词典 + HanLP 起步，UIE 并行评估）；EntityResolver 归一五步；写入与 B 相同的实体表 | GraphRAG WS1 | B |
| **D. 实体召回路 + 联用上线** | 递归 CTE 1-3 跳；semantic_edges migration；R3 作为额外来源接入 `analysis/fusion.py::fuse_candidates`（不设独立融合函数）；node_entity_links 增强树/热点选择 | GraphRAG WS3 | C |
| **E. 回写闭环** | OKF Writer / Discovery Services / Agent Committer / 冲突解决（人类优先） | LLM-WIKI Phase 3 | D（可与 D 后半并行） |
| **F. 评测与调优（延后，D4）** | 评测集扩建（300-500 题）；消融矩阵 = WS4 阶梯 × Phase 14 三方对比 × 联用组合；Level 2 PageIndex 配置诊断在矩阵 R2 列内完成 | GraphRAG WS0/WS4 + Phase 14 | 明确后置，用户拍板功能先行 |

指代层（GraphRAG WS2）与高价值限定词：挂在 C 之后按需插入，关系页限定词（否定/条件）的 OKF 表示在阶段 B 的 Relation Processor 中预留字段。

## 5. 风险 Top 3

| 风险 | 应对 |
|---|---|
| D2 重做摄入链路导致 span_id 漂移，历史验证数据失锚 | 阶段 A 硬验收：同一文档 docling 直出 vs OKF 中转的 span_id 全量比对；不一致即阻塞 |
| SSOT 承诺过重（二进制文档转写有损） | raw/ 文件 frontmatter 记录源文件 checksum + docling 版本，原始二进制文件仍归档保留（OKF 管知识与转写，不销毁原件） |
| Agent 回写噪声污染权威源 | 继承 LLM-WIKI 风险表：先人工 review Agent commit，staging 目录 + confidence 标记，逐步放开 |

## Active Phase 15/E2a routing

Phase 15/E2a is authorized, planned, and execution-unstarted. User selection: 授权规划和实施（推荐）. Authorization source: interactive Claude Code session. This is not an independent repository transport receipt; no date, receipt ID, or durable independent authorization evidence is asserted. Implementation begins only after independent review of the corrected plans. This does not authorize Phase 16/E2b, Phases 19/20, production, Git operations, or disposable PostgreSQL/Docker acceptance. Historical Phase 14 summaries/evidence are unchanged.
