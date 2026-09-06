# OKF 权威源 + 多路检索统一架构：执行交接书

> **历史交接快照（2026-07-12）：原始实施准备状态，保留不可变历史事实。**
> **当前状态：v2.0 为活动工作流；Phase 15/E2a 已授权、已规划、执行未开始。用户选择为 授权规划和实施（推荐）；授权来源为 interactive Claude Code session；此非独立仓库传输收据，不主张日期、收据 ID 或独立持久证据。修正计划须独立审查后才可实施。Phase 14/E1 历史事实保持不变。**
> **记录日期：2026-07-12**
> **适用仓库：`E:\github\rag`**
> **目标读者：下一位负责规划或实施的工程 Agent / 工程师**

本文件把本轮讨论已经拍板的架构决定、仓库已验证的事实、明确未实现的工作、技术上仍需定稿的分叉，以及阶段 A 的验收边界放到一个地方。它是交接入口，不替代详细设计；详细计划和证据文件在第 2 节列出。

> **2026-07-17 Phase 14 canonical-path ratification / amendment (active and controlling).** The user has approved the following amendment to this handoff and its §10 acceptance predicates. `OKF_BUNDLE_ROOT` is the Phase 14 bundle-root authority and defaults to `okf_bundle`; canonical Phase 14 templates are `okf_bundle/templates/`; and the sole canonical E1 CLI is `scripts/rebuild_from_okf.py`. `scripts/rebuild-from-okf.py` is not a supported compatibility interface; no wrapper or duplicate tree is required. The existing `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` remains only a legacy sample/test fixture and is not a second canonical root. This amendment supersedes conflicting active path wording below and in lower-precedence plans, while preserving historical execution facts. Canonical-path ratification is no longer a Phase 14 closure blocker. The bounded A–F closure is recorded by [artifact 13](../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md), **APPROVE_FOR_FORMAL_CLOSURE** with no CRITICAL/HIGH findings; it does not authorize Phase 15.

---

## 1. 当前结论：先做什么、不要做什么

> **历史快照说明（不改写 2026-07-12 记录）：** 本节及后续标记“尚未实现/下一步”的当日叙述保留为原始交接上下文；不得将其作为当前实施状态。
>
> **Current gate correction (2026-07-17):** Phase 14/E1 is **BOUNDED CLOSED/PASS** within its A–F acceptance scope. [Artifact 13](../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md) is **APPROVE_FOR_FORMAL_CLOSURE** with no CRITICAL/HIGH findings. Gates A-E have PASS execution evidence and independent reviews 03/08/09/10/11 are **APPROVE**. Gate F is **PASS within declared Phase 14 non-goal scope**: artifact 12 maps all five exact §10-F non-goals and its independent review is **APPROVE**. Artifacts 04-07 retain their PASS/WARN limits; this is not a clean-worktree, full-worktree, intended-commit-scope, security, production, or full-derived-database-rebuild PASS. E1 remains limited to admitted raw-sidecar-to-`canonical_spans` reconciliation for registered/protected parents. Current Phase 14 closeout/verification artifacts contain no credential values; protected variables were isolated as recorded. The canonical path mapping is ratified by the controlling amendment above; active §10 predicates use `okf_bundle/templates/` and `scripts/rebuild_from_okf.py`. Phase 15/E2a is **AUTHORIZED / PLANNED / EXECUTION-UNSTARTED**; the exact interactive Claude Code selection `授权规划和实施（推荐）` satisfies Gate 3. Implementation waits for independent review of corrected plans; no date or receipt is invented, and no later-phase, Git, production, or disposable PostgreSQL/Docker acceptance authority is granted. This overlay preserves the historical snapshot and does not alter its canonical predicates.

系统将建设为：

1. **OKF Bundle 是唯一持久化知识权威源（SSOT）**。知识以 OKF Markdown + YAML frontmatter 存在 Git 中；PostgreSQL 是可删除并从 OKF 重新构建的派生检索缓存。
2. **所有 PDF、Word 等非 OKF 文档先由 docling 解析并序列化到 OKF `raw/`**，再走唯一的 OKF 摄入管道。不能继续长期维护“docling 直入 DB”和“OKF 入 DB”两条独立事实来源。
3. **检索不是替换三条原有路线，而是统一索引底座上的并联联用**：纯向量、PageIndex 默认树状、PageIndex 热点、实体/图谱多跳同时存在，可融合，也会互相提供信号。
4. **先完成功能底座，不先做质量调优**。Level 2 的命中率问题是 PageIndex 配置/遍历问题，Phase 14 横向对比、评测集扩建和 PageIndex 参数诊断均明确延后。
5. **下一项实施工作是阶段 A，OKF 底座**。阶段 A 尚未编码；开始前必须先解决本文件第 9 节的技术定稿项，特别是 `span_id` round-trip 稳定性方案。

### 1.1 本轮最重要的用户澄清，不能改写

- Level 2 的 `hit_rate = 70%` 是 **PageIndex 路的配置/检索问题**，不是实体/图谱层造成的，也不能宣称实体层是把它提升到阈值的最短路径。
- 当前应视作四个可并行、可联用的召回视图：
  - **R1**：纯向量；
  - **R2a**：PageIndex 默认树状检索；
  - **R2b**：PageIndex 热点检索；
  - **R3**：实体/图谱召回与多跳扩展。
- 用户要求的是“**同时用，也可以联用**”，不是在“新管线还是旧管线”之间二选一。
- 用户要求底层打通 OKF 文档格式，并进一步选择“**全部转 OKF**”。
- 用户对评测/诊断的指令是：**“这个诊断再说吧，后续怎么提高再说，我们先把功能的计划实现。”**

---

## 2. 文档权威顺序与交接资料

活动规则按**适用范围**而非无条件的全局排序处理：

| 适用顺序 | 文件 / 来源 | 受控范围 |
|---|---|---|
| 1 | 本交接书 `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` | **Phase 15 的范围与路由**，以及活动阶段门和交接约束 |
| 2 | `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` | 与活动交接书相容的统一架构 |
| 3 | 已接受 ADR，包括 `.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` 与 raw-pair ADR | 各 ADR **明示的技术范围**；ADR 不在其明示范围外取代 Phase 15 范围或路由 |
| 4 | `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` 与 roadmap | 执行映射、里程碑和阶段定位 |
| 5 | `.planning/LLM-WIKI-Integration-PLAN.md`、`.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md`、`.planning/okf_extracted.md`、原始 DOCX 与 `.planning/workspace-memory.json` | 历史设计、调研或跨会话参考；不单独授予活动执行授权 |

> **注意**：`LLM-WIKI-Integration-PLAN.md` 与 `LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` 中部分符号名、迁移编号和“待做”描述未经本轮代码核验。实施前以第 7 节“代码事实”与第 9 节“不能静默决定的事项”为准。

---

## 3. 已拍板的决策账本

| ID | 决策 | 已确认内容 | 对实施的约束 |
|---|---|---|---|
| **D1** | OKF 的角色 | **OKF 是唯一 SSOT**。所有持久化知识以 `.md` + frontmatter 留在 OKF Bundle，Git 管版本；DB 是派生缓存，可随时 `DROP` 后重建。 | 禁止把 DB 作为唯一不可重建的知识来源；持久化写入必须有 OKF 对应物。 |
| **D2** | 非 OKF 文档入口 | **所有 PDF/Word 等由 docling → OKF 序列化器 → `okf_bundle/raw/`**，然后统一从 OKF 摄入。 | 不允许新增另一条长期 docling→DB 事实链；原始二进制可保留归档，但不绕开 OKF 摄入。 |
| **D3** | 起步顺序 | **OKF 底座先行**。先完善 parser、冻结表结构、把 OKF 实体页零 Token 摄入打通，再让 NER 抽取器为 raw 文档补实体数据。 | 阶段 A/B 在 C（NER）之前；Phase A 不得提前引入模型实现以替代 OKF 基础设施。此阶段边界不改变 Phase 16-C1 已冻结的 RaNER 主模型裁决。 |
| **D4** | 质量诊断和评测 | **后置**。PageIndex Level 2 诊断、Phase 14 三路横向对比、300-500 题评测扩建和联用权重调优都在功能完成后再做。 | 不能把 hit-rate 调参作为阶段 A-D 的前置；唯一允许提前的“评估型”工作是 `span_id` 正确性回归。 |
| **D5** | 多路检索关系 | 四路不是互斥产品，也不是彼此备份；它们是同一个证据索引底座的不同遍历和排序视图。 | 新模块必须向共享 `canonical_spans` / chunks / tree / entity link 提供可解释信号，而不是建孤岛库。 |
| **D6** | PageIndex 与图谱的边界 | PageIndex 的默认树状与热点模式是 R2 的两个子模式；图谱不是用来“修复 PageIndex 配置”的替代品。 | 给热点/树增加实体信号是增强，不得重写 Level 2 问题归因。 |
| **D7** | Token 策略 | 入库以确定性处理为主，避免全量 LLM 三元组抽取。PageIndex 节点摘要默认关闭。 | 关系/实体的入库优先来自 OKF frontmatter、规则、词典与非生成式模型；Agent/LLM 仅在后续回写发现中受控使用。 |
| **D8** | 回写安全 | 后续 Agent 发现关系/别名要回写 OKF，人的编辑优先；先经过 review/staging，不可直接让低置信 Agent 污染权威知识。 | 阶段 E 初始默认应为 proposal/review 优先，除非用户单独批准自动提交。 |

---

## 4. 目标架构（已确定）

```text
原始 PDF / Word
       │
       ▼
  docling 解析
       │
       ▼
 docling → OKF 序列化器
       │
       ├────────────────────────────────────────────┐
       ▼                                            │
okf_bundle/                                  │
  ├── raw/          由原始文档转写，保留证据坐标   │
  ├── entities/     canonical entity + aliases      │
  ├── relations/    relation + negation/condition   │
  ├── concepts/     概念知识                         │
  ├── synthesis/    综合结论                         │
  ├── templates/    格式契约                         │
  ├── index.md / log.md / AGENT.md                  │
  └── 原始二进制归档与 source checksum              │
       │                                            │
       │ Git 版本控制，OKF 为唯一权威源             │
       ▼                                            │
OKFParser + SyncService ────────────────┐           │
       │                                │           │
       ▼                                ▼           │
Entity / Relation / Vector / Tree processors        │
       │                                            │
       ▼                                            │
PostgreSQL 派生缓存（可全量重建）                   │
  canonical_spans · vector_chunks · tree_nodes      │
  entities · aliases · mentions · evidence links    │
  semantic_edges · OKF sync/rebuild state           │
       │                                            │
       ├───────────┬────────────┬────────────┐      │
       ▼           ▼            ▼            ▼      │
R1 纯向量     R2a 树状     R2b 热点      R3 实体/图谱 │
       \           │            │           /       │
        \──────────┴──────┬─────┴──────────/        │
                           ▼                           │
              统一候选融合与证据重排                   │
                           ▼                           │
          QueryHit（含 OKF 文件与段落溯源）           │
                           ▼                           │
          Agent 产生待审关系/别名 proposal ───────────┘
                    人工审阅后回写 OKF
```

### 4.1 三层联用方式

1. **并联融合**：R1、R2a、R2b、R3 同时召回，各自贡献候选证据；融合层统一排序、去重和保留来源标签。
2. **路间增强**：
   - `node_entity_links` 将实体命中映射到树节点，帮助默认树和热点选择；
   - jieba + 领域词典改善关键词与热点查询特征；
   - `entity_mentions` / `evidence_links` 将实体、span、chunk、node 绑定到同一证据坐标。
3. **知识闭环**：检索发现的别名、关系、概念先成为 OKF proposal；经人审后写回 OKF，随后增量同步让所有检索路共享新知识。

---

## 5. 统一实施路线

| 阶段 | 名称 | 目标 | 依赖 | 当前状态 |
|---|---|---|---|---|
| **A / Phase 14 — E1** | OKF 底座与 canonical-span 证明 | 已存在的注册/受保护 `documents` 与 `document_versions` provenance parents 不重建；由 admitted raw OKF frontmatter + sidecar 确定性重算并协调 `canonical_spans`，证明 `S_direct == S_okf`、坐标、事务/审计和第二次等价运行零 canonical-span DML。E1 不重建 chunks、tree nodes、entities、relations、evidence 或 NER associations；FK cascade cleanup 不是 reconstruction。 | 无 | **BOUNDED CLOSED/PASS** — artifact 13 is **APPROVE_FOR_FORMAL_CLOSURE**. This active status overlay does not alter the preserved historical execution record or expand E1 scope. |
| **B / Phase 15 — E2a** | OKF 全语料摄入管线 | 全语料 OKF-only 入库并物化 vector/tree 及人工 OKF entities/relations/evidence，证明 identity/scope/provenance/association parity。 | E1 关闭 | **AUTHORIZED / PLANNED / EXECUTION-UNSTARTED** — Gate 3 satisfied by `授权规划和实施（推荐）`; no implementation execution asserted |
| **C / Phase 16 — E2b** | raw 语料实体层 | NER-derived `entity_mentions`、aliases/merge provenance、`node_entity_links` 的物化、parity 和幂等；不重复 E2a 已物化的人工 OKF entities/relations/evidence。**C2（条件性第二 wave，默认关闭）**：中文局部指代链 `coref_clusters`，见 §11-C2。 | E2a 关闭；C2 另需 C1 验收关闭 | 未开始 |
| **D** | 图谱召回与联用 | 实体 1-3 跳 SQL、语义边、树/热点实体信号、联用候选来源；coref 仅作可关闭的受限扩展信号（开关独立于 R3 路由开关） | C | 未实施 |
| **E** | 受控 OKF 回写 | proposal、冲突处理、人审、Agent 发现与 OKF 回写 | D，可与 D 后段交叉 | 未实施 |
| **F** | 评测与调优 | 三路/四路消融、PageIndex 配置诊断、质量阈值与联用权重；八类中文问题评测、消融阶梯与 G3/G4/G5 裁决（见 §11-F） | A-E | **明确后置** |
| **G** | 受限业务试点与生产就绪 | 单一受控业务库试点：权限/隔离、索引运维、可观测性、灰度/回退、G6 Go/No-Go（Phase 20，见 §11-G） | 三重门：D4 已解冻且 F 关闭 + 用户独立试点授权 + 试点 corpus P0 | 未实施（规划级新增 2026-07-12，见补充交接书） |

### 5.1 阶段 A 的完整范围

阶段 A 不是“只写一个 parser”。它必须完整交付下列能力，才允许开始阶段 B：

1. **OKF Bundle 结构和格式契约**
   - 建立 `raw/`、`entities/`、`relations/`、`concepts/`、`synthesis/`、`templates/`；
   - 建立 `index.md`、`log.md`、`AGENT.md`；
   - 把 entity/relation/concept/raw 的 frontmatter 契约形式化，而不是继续只依赖 `e001` 示例。
2. **docling → OKF 序列化器**
   - 为原始文档生产 OKF `raw/*.md`；
   - 保存 `doc_id`、`version_id`、source checksum、docling 版本、页码、heading path、offset、原文 text 等重建 `span_id` 所需信息；
   - 原始二进制不销毁，保留可审计归档指针。
3. **OKF parser 补全**
   - frontmatter 校验；
   - 增量解析、删除检测；
   - 段落/证据锚点解析不能依赖裸 `split("\n\n")` 的不稳定语义。
4. **基础 migrations 一次定稿**
   - `okf_sync_state`、`okf_rebuild_log`；
   - `entity_aliases`、`entity_mentions`、`entity_merge_log`；
   - 同时处理关系限定词的持久化目标，不能让 OKF relation 字段无表可写。
5. **E1 canonical-span reconciliation 与正确性证据**
   - `scripts/rebuild_from_okf.py` 只接受 admitted raw OKF frontmatter + sidecar，前提是注册/受保护的 `documents` 与 `document_versions` provenance parents 已存在；
   - 同一份原始文档经“docling 直出”和“docling→OKF→再摄入”得到的 `span_id` 集合 100% 相等，且逐项核对坐标；
   - 在事务内确定性协调 `canonical_spans`，连续两次等价运行的第二次没有 canonical-span DML，并记录重建日志和失败审计；
   - 不删除或重建 parents，也不重建 vector chunks、tree nodes、entities、relations、evidence 或 NER associations。完整派生关联 parity 由 E2a/E2b 共同验收。

---

## 6. 已完成、存在、尚未实现

### 6.1 已存在且可复用的代码/数据

| 能力 | 实际位置 | 已验证状态 | 使用说明 |
|---|---|---|---|
| OKF parser | `llamaindex_runtime/okf/parser.py` | 已实现基础读入 | 可读 YAML frontmatter、body、SHA256 文件 hash，解析 Bundle 与单个文件 |
| OKF public exports | `llamaindex_runtime/okf/__init__.py` | 已存在 | 仅导出 `OKFParser`、`OKFDocument`、`OKFFrontmatter`、`OKFParagraph` |
| OKF entity 示例 | `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` | 已存在 | 仅作为 legacy sample/test fixture，不是第二个 canonical root；含 aliases、mentions、relation qualifiers |
| 图谱基础表 | `llamaindex_runtime/registry/migrations/005_kg_extension.sql` | 已存在 | `entities`、`relations`、`evidence_links`、`chunk_entity_links`、`node_entity_links` |
| 图谱扩展字段 | `.../006_kg_graphrag_enrichment.sql` | 已存在 | entities/relations description；entities community_id |
| mapping 元数据 | `.../012_mapping_table_enrichment.sql` | 已存在 | chunk/node entity links 有 `confidence_score`、`mention_text` |
| span_id 生成公式 | `llamaindex_runtime/ingestion/docling_ingestor.py:78` | 已验证 | `uuid5(doc_id|version_id|page_no|headings|offset|text)`，是全方案最关键兼容锚点 |
| 热点路径加权融合 | `llamaindex_runtime/tree/semantic_distribution.py:942-946,1567+` | 已验证 | `_compute_fusion_score`：vector 0.40、keyword 0.30、rerank 0.20、distribution 0.10 |
| 多路径 RRF 融合 | `llamaindex_runtime/analysis/fusion.py:40` | 已验证 | `fuse_candidates`，与热点加权融合是另一条独立机制 |
| PageIndex 零 Token 默认 | `llamaindex_runtime/tree/pageindex_adapter.py:210,320` | 已验证 | `if_add_node_summary='no'` 默认关闭节点 LLM 摘要 |
| 当前计划总纲 | `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` | 本轮创建 | 已拍板的 architecture master plan |

### 6.2 已存在但不能直接当作完成品

| 项目 | 实际限制 |
|---|---|
| `OKFParser.parse_bundle()` | 每次 `rglob("*.md")` 全量扫；没有增量解析或删除 tombstone 处理。 |
| `OKFParser.compute_hash()` | 对文件原始 bytes 做 SHA256。格式化、空白、YAML 键顺序变化都会导致 hash 改变。|
| `OKFParagraph` | 只有 `id`、`content`、`heading`、`okf_file_path`；没有 `page_no`、`offset`、`heading_path`、`span_id`。无法天然保证 D2 的 round-trip。|
| 段落划分 | 当前按双换行切分；列表、表格、代码块和空行都可能改变 `P1/P2...` 编号。|
| `llamaindex_runtime/okf/__init__.py` 文档串 | 描述了 entity_processor、sync_service 等组件，但这些模块文件当前并不存在。不要把文档串误认为实现。|
| `e001` 示例 | 是目前事实上的 schema 样例，不是已校验/版本化的正式规范。|
| `evidence_links` | 绑定 entity/relation→span，有 confidence，但没有 mention 的字符起止 offset 和原始 mention text。|

### 6.3 确认未实现，不能假定存在

| 组件 / 表 | 计划阶段 |
|---|---|
| docling→OKF serializer | A |
| `raw/`、`relations/`、`concepts/`、`synthesis/`、`templates/`、`AGENT.md`、`index.md`、`log.md` | A |
| `okf_sync_state`、`okf_rebuild_log` | A |
| `entity_aliases`、`entity_mentions`、`entity_merge_log` | A |
| `scripts/rebuild_from_okf.py` | A |
| incremental `sync_service.py`、post-commit hook | B |
| entity/relation/vector/tree processors | B |
| `llamaindex_runtime/entity/`、jieba 接入、RaNER 主适配器；UIE/Base News/HanLP/DeepKE 仅按已裁决状态保留扩展或研究位 | C |
| `coref_clusters` 及规范化 membership 表（中文局部指代链） | **C（Phase 16-C2 条件性 wave，默认关闭；净收益由 F/G3 裁决，见补充交接书）** |
| `relation_mentions`、关系 qualifiers 的完整查询逻辑 | C 后按需插入（T6 不变；不随 16-C2 隐式授权） |
| `semantic_edges`、实体 SQL 1-3 跳召回 | D |
| 实体信号接入树/热点及融合层 | D |
| `OKFWriter`、discovery services、agent committer、conflict resolver | E |
| 300-500 评测题、完整消融矩阵、Phase 14 对比、Level 2 诊断 | F |

---

## 7. 现有 schema 与目标 schema 对照

### 7.1 当前 migration 005 基础结构

```text
entities(entity_id, entity_key UNIQUE, entity_type, canonical_name)
relations(relation_id, relation_key UNIQUE, relation_type,
          source_entity_id, target_entity_id)
evidence_links(version_id, entity_id | relation_id, span_id,
               source_kind, confidence_score)
chunk_entity_links(chunk_id, entity_id, ordinal_no,
                   confidence_score, mention_text)
node_entity_links(node_id, entity_id, ordinal_no,
                  confidence_score, mention_text)
```

### 7.2 阶段 A 必须补齐的结构

建议目标，**但创建 migration 前必须按第 9 节的技术定稿结果确认**：

```text
okf_sync_state(
  okf_file_path PK, okf_version_hash, file_type,
  last_synced_at, last_sync_commit, is_deleted, db_record_count
)

okf_rebuild_log(
  id PK, rebuild_type, started_at, completed_at,
  files_processed, records_rebuilt, status, error_detail
)

entity_aliases(
  entity_id FK, alias, alias_type, source, confidence,
  unique/entity normalization constraints TBD
)

entity_mentions(
  mention_id PK, entity_id FK, span_id FK,
  char_start, char_end, mention_text, confidence,
  source / OKF paragraph provenance TBD
)

entity_merge_log(
  merge decision, source, confidence, prior/current targets,
  reviewer and rollback provenance TBD
)
```

目标还需要确定 relations 的限定词落点。OKF 示例已经有：

```yaml
relations:
  - type: 隶属
    target: /entities/e002-内蒙古自治区政府.md
    evidence_paragraph: P1
    negation: false
    condition: null
    direction: subject-to-object
    confidence: 0.95
```

但现有 `relations` 表没有 `negation`、`condition`、`direction`、时间范围或 relation confidence 的持久化字段。阶段 B 之前必须有数据库落点，不能让 parser 无声丢字段。

---

## 8. 两条融合机制：计划文本与代码事实不一致

旧计划曾把统一融合接点写成 `_fuse_candidate_scores`。**代码库中不存在这个函数。** 下一位执行者不得按该名称搜索/修改。

现有实际有两条融合机制：

| 机制 | 实际符号与位置 | 行为 | 阶段 D 的影响 |
|---|---|---|---|
| 热点/分布路径 | `semantic_distribution.py::_compute_fusion_score` | 固定加权：0.40 vector + 0.30 keyword + 0.20 rerank + 0.10 child distribution | 如果加入 entity score，现有权重总和已为 1，必须重分配或另设组合逻辑。D4 已延后调优，不能假称权重已验证。|
| 多路径通用融合 | `analysis/fusion.py::fuse_candidates` | RRF + multi-path bonus | 可携带 R3 来源作为额外路径，未受固定权重约束，但需确定是否为正式 runtime 接入点。|

**尚未拍板的技术问题**：实体信号进热点加权路径、RRF 路径，还是两者都进？当前正确状态是“未定”，不是“已经会接到 `_fuse_candidate_scores`”。

---

## 9. 下一执行者不得静默决定的技术分叉

这些不是推翻 D1-D4 的产品决定，而是执行 D1-D4 时必须显式定稿的工程契约。若没有用户/架构负责人确认，下一位执行者应先写 ADR/设计说明并请求确认，不要自行选一种实现后继续。

| ID | 未定事项 | 为什么会影响架构 | 推荐方向（**未获用户拍板**） |
|---|---|---|---|
| **T1** | raw OKF 如何保存 `page_no`、`heading_path`、`offset`、`text` | 四个字段会进入 `span_id`；当前 `OKFParagraph` 不携带它们。丢任意一个，D2 将使全部历史证据锚点漂移。 | 每个 raw span 使用机器可读、版本化的段落级元数据或 sidecar。不要只靠 Markdown 空行和段落序号。|
| **T2** | metadata 表达方式：frontmatter、inline marker、sidecar JSON | 三种方案影响人工可读性、OKF 互操作性和 parser 复杂度。| 倾向“OKF Markdown 保持可读 + 与 raw 文件相邻的稳定结构化 sidecar”，但先确认 OKF 工具链兼容约束。|
| **T3** | `okf_version_hash` 是 raw bytes hash 还是结构 hash | 当前 raw bytes hash 会被空格和 YAML key 顺序扰动，造成无意义 rebuild。| 倾向保留原始文件 checksum 作审计，另计算 canonical structural hash 给 sync comparison。|
| **T4** | `entity_mentions` 新表还是扩展 `evidence_links` | 决定所有实体提及查询、迁移和回滚模型。| 统一总纲倾向 **新表**，保留 evidence_links 作为 entity/relation→span 高层证据映射。必须正式确认。|
| **T5** | migration 命名 | LLM-WIKI 旧计划写 `001_okf_authoritative.sql`，现有仓库最高为 `014_*`；重复编号会破坏 migration 序列。| 继续现有序列，使用 `015_*` 起。必须实际检查 migration runner 的排序策略。|
| **T6** | relation qualifiers 持久化模型 | OKF frontmatter 已有 negation/condition/direction，但 DB 无列。| 不做全量 LLM 三元组；为高价值限定词设 relation mention/qualifiers JSONB 或明确 relation columns。|
| **T7** | R3 实体信号注入哪个融合路径 | 当前有固定权重 hotspot path 和 RRF path 两套机制。| 建议先保持来源标签和可观察分数，F 阶段再以消融决定权重；不要在 D 阶段伪造“最优权重”。|
| **T8** | Agent 自动回写初始开关 | 低质量 LLM 写入会直接污染 D1 的权威源。| E 阶段初始仅 proposal/staging + 人审；自动 commit 需要单独确认和质量门。|
| **T9** | span_id 比对属于一次性人工验证还是自动回归 | 这是 D2 正确性的核心，不是普通质量评测。| 必须成为自动测试/验证脚本，并保留至少 PDF、表格 PDF、DOCX 三类 fixtures。|

---

## 10. 阶段 A 硬验收清单

以下是开始 B 前必须全部通过的标准。它们是**功能正确性**，不是 D4 延后的质量调优。

### A. 格式契约

- [ ] `okf_bundle/templates/entity.md`、`relation.md`、`concept.md`、`raw.md` 存在。
- [ ] 每个模板的必填与可选 frontmatter 字段有可读文档，`type` 与 OKF v0.1 兼容。
- [ ] `e001-内蒙古自治区卫健委.md` 的 aliases、relations、mentions 扩展字段被纳入正式契约或显式迁移，不继续只靠样例推断。
- [ ] parser 对无效必填字段、错误 YAML、未知/不支持扩展字段有明确行为和测试。

### B. `span_id` round-trip

- [ ] 选取至少三类 fixture：有章节的 PDF、有表格/复杂排版的 PDF、DOCX。
- [ ] 同一原文在“当前 docling 路”得到 `S_direct`，在“docling→OKF raw→OKF parser/adapter”得到 `S_okf`。
- [ ] **`S_direct == S_okf`，即 span ID 集合 100% 一致**；不能接受“多数相同”或只比总行数。
- [ ] 同时对每个 span 对比 `page_no`、heading path、offset、text，错误报告必须指出首个不一致坐标。
- [ ] 该比对作为自动化 regression test 或确定性验证命令，能在 CI/本地重复运行。

### C. schema 和迁移

- [ ] migration 编号和命名遵守现有 runner 的排序规则，无重复或历史重放问题。
- [ ] `okf_sync_state`、`okf_rebuild_log`、`entity_aliases`、`entity_mentions`、`entity_merge_log` 的键、索引、删除/回滚语义已写明。
- [ ] `entity_mentions` 若为新表，必须包括 `span_id`、字符 offset、mention 文本、confidence 和足够的 OKF 溯源；若选别的方案，必须有批准 ADR。
- [ ] relation 的 negation/condition/direction/time/confidence 有明确 DB 写入模型；不能只停留在 OKF 文件。

### D. parser 与增量检测

- [ ] 新文件、编辑文件、删除文件均被 `OKFSyncService` 或等价变更检测抽象清晰地区分。
- [ ] 变更 hash 语义已定稿；语义未变的格式化重写不会造成非预期全量重建，或有明确可解释的取舍。
- [ ] `tests/test_okf_parser.py` 覆盖 frontmatter、paragraph/span metadata、hash、增量、删除和错误输入。

### E. 可重建证明

- [ ] `scripts/rebuild_from_okf.py` 存在，运行范围和事务边界明确。
- [ ] 脚本不会无意删除 `documents`、`document_versions` 或原始二进制归档，除非经过专门设计和事务保护。
- [ ] E1 在已注册的 doc/version scope 内从 admitted raw frontmatter + sidecar 确定性协调 `canonical_spans`；`documents` 与 `document_versions` provenance parents 不被删除、截断或重建。
- [ ] 两次连续等价 E1 运行的第二次无 canonical-span DML；每次运行写入 `okf_rebuild_log`，失败时记录可行动但经脱敏的审计 context。
- [ ] `tests/test_rebuild.py` 证明上述 canonical-span 幂等性、span identity、坐标和事务/审计边界；不把 FK cascade cleanup 写成 chunks、nodes、entities、relations、evidence 或 NER association reconstruction。
- [ ] E2a/E2b 共同承担完整派生关联 parity：E2a 物化 vector/tree 与人工 OKF entities/relations/evidence，E2b 物化 NER-derived mentions、aliases/merge provenance 与 node/entity links。

### F. 阶段 A 明确非目标

> **Current Gate F status overlay (2026-07-17):** **PASS within declared Phase 14 non-goal scope.** [artifact 12](../verification/phase14-okf-foundation/12-gate-f-non-goals-scope-attestation.json) maps all five exact checkboxes below; its [independent review](../verification/phase14-okf-foundation/12-gate-f-independent-review.md) is **APPROVE** with no CRITICAL/HIGH findings. This bounded PASS does not supersede artifacts 04-07: index freshness is PASS, while tracked-diff-only mapping, HIGH/CRITICAL impact warnings, and non-exhaustive untracked coverage remain WARN limitations. It is not a clean-worktree, full-worktree, commit-scope, security, production, or aggregate-closure PASS.

- [ ] Phase A 不引入任何实体抽取模型实现；这只是 A/C 阶段边界，不否定 Phase 16-C1 已冻结的 RaNER 主模型。
- [ ] 不改变 PageIndex 路的配置、不调 Level 2 参数。
- [ ] 不改实体召回权重，不宣称质量提升。
- [ ] 不让 Agent 自动 commit 回写。
- [ ] 不执行 Phase 14 对比或大规模评测集扩建。

---

## 11. 后续阶段边界

### B / Phase 15 — E2a：OKF 摄入管线

目标：全语料 OKF-only 入库，稳定物化到 DB 派生索引；这是 vector/tree 和**人工声明的** OKF entity/relation/evidence materialization、identity/scope/provenance/association parity 的 owner。它不执行 NER-derived mention、alias/merge provenance 或 node/entity-link materialization（E2b/Phase 16）。

- Entity Processor：人工 OKF 实体页 frontmatter/body → entities、aliases、人工 mentions、evidence links；
- Relation Processor：relation 或 entity 内嵌 relation → relations + 限定词 + 人工声明的证据 paragraph；
- Vector Indexer：OKF 段落 → vector chunks + vector_chunk_spans，保留 `okf_file_path`、paragraph/span 溯源；
- Tree Builder：OKF 的目录和 heading → tree nodes + tree_node_spans；
- Sync Service：新增/更新/删除的增量处理；
- E2a 证明全语料的 identity、scope、provenance 及这些关联的 parity；与 E2b 合在一起才构成完整 derived-association parity。
- Git hook 只能在 B 之后考虑，不要在 A 仅有 skeleton 时强行接入。

### C. raw 语料实体层

目标：让从 PDF/Word 转入 `raw/` 的原始证据也能填充与 OKF 人工实体页相同的实体表；**不能把纯词典匹配当作实体召回主方案**。

- `llamaindex_runtime/entity/` 采用 schema-independent 的可插拔抽取器设计：公共契约为 `extract(inputs: Sequence[ExtractionInput]) -> list[MentionCandidate]`，`ExtractionInput` 是 `CorpusSpanInput | QueryTextInput` 判别联合。两者共享 `input_id/input_revision`、normalized-text 坐标、模型/label-map/provenance 语义；corpus 变体固定 `input_revision=document_revision`、带 document/sidecar projection 并写入 mention schema；query 变体固定 `input_revision=query_revision`、只带 query-local immutable identity，其 candidate/pre-merge/merger artifact 严格 request-scoped，不得写入任何 durable audit/mention/merge/alias/link/corpus-evidence store。未来 UIE schema 由其 adapter 配置持有，不污染公共 Protocol；
- **C1 模型主识别裁决（2026-07-13 用户需求澄清后冻结）**：唯一主模型为 ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic`，它是可直接推理的本地非生成式、固定六类通用中文 NER。项目不需要先标注、微调或训练才能使用；项目中文人工标注小集只用于验收评测。只留接口、mock，或只交付 jieba/领域词典，均不能关闭 C1；
- RaNER 标准输出 `type/start/end/span` 映射到统一 DTO，并强制 `input.normalized_text[start:end] == span`；标准输出没有 mention confidence，必须保存 `confidence=None`、`confidence_kind="unavailable"`，不得伪造概率。`PER/LOC/CORP/GRP/CW/PROD` 通过版本化 label map 映射到 OKF canonical type，并保留 `raw_label`；
- C1 坐标统一为对应输入的精确 normalized text 上按 Python Unicode code point 计数的零基左闭右开 input-local 坐标，不得混用 byte/UTF-16/token/document-global offset。`CorpusSpanInput` 绑定不可变 document revision、normalization/segmentation 版本和 sidecar 证据投影；`QueryTextInput` 只绑定 query-local immutable identity，不得伪造 document/span/projection。adapter 禁止用 `str.find`/substring search 猜回缺失坐标；契约异常按 input fail-closed、跨 input 可继续，corpus span 失败时保证不产生部分 entity/alias/link 写入，query 失败时不产生部分 R3 seeds；
- **词典是高置信补充而非主召回器**：既有 jieba 计划仍用于关键词、领域词典与热点信号；领域词典、OKF frontmatter 和规则用于业务简称/黑话补充、边界校正、置信度提升和实体归一；
- PaddleNLP `2.8.1` / `uie-base` 只保留为未来 schema-guided 领域扩展；`iic/nlp_raner_named-entity-recognition_chinese-base-news` 只作资源受限降级候选，不是通用主模型等价替代或自动 fallback；HanLP 只作研究/评测备用；DeepKE 未冻结；
- 首期总开关固定 `RAG_ENTITY_EXTRACTOR=off|raner`，默认 off；未实现/未验收 adapter 不得提前暴露配置值。启用后的基准组合是“RaNER Large Generic 主识别 + 词典/frontmatter/规则补充”，仍为零生成式 LLM token（D7）；
- Large Generic 约 2.26 GB，功能主模型地位不等于已证明 CPU 部署成本可接受。Phase 16 必须实测 Windows/WSL 的冷启动、峰值 RAM、吞吐、p95 latency 与离线加载；如超出预声明资源预算，只能在同一项目人工集上比较 Base News 的质量损失后形成显式降级裁决，不得静默替换；
- 必须用词典外人物/组织/地点及至少一个 `CW` 或 `PROD` fixture 证明上下文 NER、label mapping 与字符 offset；分别报告模型/词典/规则/frontmatter 的产出和重叠。最终净质量收益仍后置到 Phase 19，不改 D4；
- EntityResolver 的链路：文本标准化 → 多源原始候选生成与完整 pre-merge audit（同源重叠/嵌套不得先丢弃）→ 稳定排序和版本化确定性候选合并/上下文排序 → 高阈值实体挂靠 → 可追溯别名学习；NER 候选不得直接触发 canonical entity 永久合并；
- 所有自动 merge 必须可审计、可回滚。

### C2. 中文局部指代链（Phase 16 的条件性第二 wave，2026-07-12 补充分配）

目标：把 DOCX WS2 的中文跨句指代（主体继承、"该院/其/上述单位"显式指代、有界零主语）落为**默认关闭**的保守能力，产出 `coref_clusters` + 规范化 membership 表。详细契约见 `.planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md` §4。

- **子入口门**：C1 的 `entity_mentions`、provenance、默认关闭开关与 `node_entity_links` 已关闭验收后才可开始。
- **对 C1 的前向契约约束**：`entity_mentions.entity_id` 必须允许为空/待决（未归一候选 mention 先于实体解析存在）——C1 设计 schema 时必须满足，否则 C2 需要重构迁移。
- 规则优先（段落主体 → 显式指代表 → 有界零主语）；低置信/歧义保持未链接，不做猜测性合并。模型辅助只保留未来扩展位，不在 C2 初期冻结任何模型；
- C2 初期只支持 `RAG_COREF_RESOLVER=off|rules`，默认 off；如保留 `RAG_COREF_MODEL` 配置占位，其首期唯一合法值为 `off`。任何模型值必须先完成精确 checkpoint、许可、输出契约、fixture 与离线部署审查；
- 指代簇是"文本 mention 间的局部证据连接"，**不是** canonical entity 永久合并；删除走 per-cluster tombstone，不做破坏性 DELETE。
- migration 顺序：C1 schema 先于 C2 schema；C2 预期单一新编号 migration 同时建 `coref_clusters` + membership 表，实际编号按 ADR T5 取当时下一个连续空闲号。
- 非目标：跨文档实体同一化、`relation_mentions` 落库、LLM 全库指代、质量调参与默认开启（后者由 F/G3 裁决）。
- 验收分两级：Phase 16 只验收契约/安全边界/幂等重建/禁用回归不变（**C2 功能就绪门**）；是否产生净收益、能否默认开启由 Phase 19 的 **G3 门**在 D4 解冻后裁决。

### D. 实体/图谱召回与四路联用

目标：R3 能与 R1/R2a/R2b 共享证据和互相增强。

- query → 与 C1 相同的已启用抽取器契约和版本化 label map 做实体种子识别（首期为 RaNER Large Generic）+ 词典/规则补充 → entity normalization → 种子 span/chunk；R3 自身仍独立开关、默认关闭，但配置依赖 fail-closed：合法组合只有 `R3=off + extractor=off|raner` 或 `R3=on + extractor=raner`。`R3=on + extractor=off` 必须启动时报配置错误，不能自动启用约 2.26 GB 模型、不能纯词典降级、不能伪装为空路；query candidate/audit/merger artifact 只在请求内存在，不进入 durable corpus/audit/merge/alias/link 存储；
- PostgreSQL recursive CTE 进行 1-3 跳扩展；
- 扩展要有路径去重、最大度数、跳数与候选预算；
- 新的 `semantic_edges` 仅作为可关闭的共现/近邻增强，MVP 不上图数据库；
- 带否定/条件的关系不直接参与无约束扩展，应作 rerank/解释特征；
- 每个 QueryHit 保留命中的路线和扩展路径，便于 F 阶段消融。

### E. 受控回写闭环

目标：让长期知识可增厚，但不污染 SSOT。

- `OKFWriter` 只更新允许 Agent 管理的字段/章节；
- 人类内容优先，冲突时 Agent 变更放 staging；
- 初期 Agent 仅提出 aliases/relations/concepts proposal；
- 审核通过后写入 OKF、Git commit、触发 B 的同步；
- 需要防止“回写→重建→检索→再次回写”的循环，以及重复关系生成。

### F. 延后进行的质量工作

目标：只在 A-E 功能闭环存在后回答质量问题。

- 95 题扩展至 300-500 题，覆盖别名、同名、指代、否定/条件、跨文档多跳、不可回答；
- 建立同一证据集上的单路、两路、四路联用消融矩阵；
- Phase 14 的 pure_vector / keyword / tree 横向对比并入该矩阵；
- Level 2 的 PageIndex 配置诊断在 R2a/R2b 列完成；
- 通过质量、延迟、成本、可维护性一起决定权重和保留的模块。

**2026-07-12 源头级补充（DOCX 路线图对齐，详见补充交接书 §4/§5）：**

- 评测题集按 DOCX 八类中文难点分层组织：全称-简称、同名消歧、显式指代、零指代、否定、条件/例外、跨章节/跨文档多跳、不可回答；主指标为 **All-Evidence Recall**（一道题所有必要证据 span 全部召回才计通过）。
- 消融按 DOCX 阶梯顺序执行：A 基线 → B 实体倒排 → C KU 多索引 → D 归一化 → E 指代（16-C2） → F 语义边 → G 高价值 qualifiers（如已存在）；每级只开一个增量，量化各能力的净贡献。
- 三个专项裁决门（均以 D4 解冻为前置，属 Phase 19 工作）：
  - **G3（指代净收益门）**：16-C2 的 coref 能力在显式指代/零指代两类问题上的收益 vs 误链风险与维护成本，裁决"默认开启 / 保持关闭 / 移除"；
  - **G4（动态多跳门）**：R3 的跳数/预算策略是否需要 query 自适应；
  - **G5（试点价值门）**：面向 Phase 20 的业务价值评估——评测产出交给 G6 做 Go/No-Go 输入，Phase 19 本身**不部署试点**。

### G. 受限业务试点与生产就绪（Phase 20，2026-07-12 规划级新增）

目标：把 DOCX 阶段 6"试点与生产化"落为独立阶段，在单一受控业务知识库上验证整套架构的生产可用性。**规划级定义，无任何执行授权。**

- **三重入口门**（缺一不可）：(1) D4 已解冻且 Phase 19 关闭；(2) 用户对试点的独立明确授权（Phase 19 通过不自动等于试点授权）；(3) 试点 corpus 一致性 P0——在真实试点语料（与 Phase 19 评测语料同版本）上重跑 `S_direct == S_okf` round-trip。
- 能力域：数据治理与权限/隔离（在候选生成层强制，不是 UI 层过滤）、索引运维、可观测性（无 LLM 依赖的监控）、灰度/回退、经 Phase 18 通道的人工反馈闭环、运维与安全基线。
- 验收门：**P0**（SSOT 就绪）、**P1**（派生层可完全重建）、**P2**（可观测试运行）、**P3**（真实规模回滚演练——这是 D1"派生层可重建"主张唯一的真实规模证明）、**G5**（试点价值，输入来自 Phase 19）、**G6**（Go/No-Go，人类签署）。
- Agent 回写在试点中**默认关闭**；启用 proposal 流程需第四个独立授权（T8 人审框架不变）。
- DOCX 的"P95 ≤ 5s"是源头级目标线，作观测指标记录，不作为 G6 的硬性承诺。
- 详细边界见 `.planning/phases/20-pilot-productionization/20-BOUNDARY.md`。

---

## 12. 已知风险与控制措施

| 风险 | 影响 | 必须的控制 |
|---|---|---|
| `span_id` 漂移 | Phase 1-13 的历史验证证据链失锚，D2 方案不能成立 | 阶段 A 的 100% round-trip identity gate；不通过即停止进入 B。|
| Markdown 转写丢失表格/页码/offset | 原始证据不可审计、引用无法回原文 | 原始二进制归档 + source checksum；结构化 span metadata 不依赖裸 Markdown 文本。|
| raw file 的 bytes hash 太脆弱 | 无意义 rebuild、同步性能不稳定 | 原始 checksum 与结构 hash 分层，先设计后实现。|
| 实体误合并 | 跨文档实体污染，多跳检索扩大错误 | 类型约束、高阈值、merge log、回滚、人工 review 区间。|
| 共现边噪声 | 多跳把无关证据加入上下文 | PMI/度数/跳数/预算上限，semantic edges 可关闭。|
| Agent 回写幻觉 | 污染 SSOT，Git 历史带入错误事实 | proposal/staging、人的编辑优先、confidence、去重、一次 query 最多一次 proposal。|
| 迁移编号冲突 | DB 初始化/升级不可预测 | 先核实 runner，再延续当前 migration 序列。|
| 两套融合机制被混淆 | R3 只接进一条路或接入错误符号 | 阶段 D 前写清 runtime call graph；按不同路径分别测试。|
| 当前工作区很脏 | 把已有本地修改和新功能混进一次提交，难审查/难回滚 | 每阶段只暂存目标文件；不要 `git add -A`；先对比干净基线和当前 diff。|

---

## 13. 工作区与版本控制状态

- 当前分支：`master`。
- 主分支通常是：`main`。
- 本轮写入的规划文件均处于未追踪/未提交的工作区状态，包括：
  - `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md`
  - 本文件 `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md`
  - `.planning/LLM-WIKI-Integration-PLAN.md`
  - `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md`
- 工作区已有大量与本任务无关的修改、验证产物、调试脚本和未追踪文件。不要把它们作为阶段 A 的副作用提交。
- 当前用户没有要求 commit 或 push；下一位执行者只有在用户明确要求后才可做对外 Git 操作。

---

## 14. 执行约束（仓库规则）

下一位执行者开始任何代码修改前，必须遵守仓库 `CLAUDE.md`：

1. 修改任何函数、类、方法前，先运行 GitNexus 上游 impact analysis，并向用户报告 direct callers、affected processes 和 risk level；若 HIGH/CRITICAL，先警告再继续。
2. unfamiliar code 优先使用 GitNexus query/context 理解执行流；索引过期时先 `npx gitnexus analyze`。
3. commit 前必须跑 GitNexus `detect_changes()`，确认只影响预期符号/流程。
4. 对新功能使用 TDD：测试先红、实现后绿、重构后验证；Python 用 pytest，目标覆盖率不低于 80%。
5. 修改代码后进行 Python code review；schema/migration 改动使用 database review；任何涉及外部文件、Agent 回写或输入解析的实现加安全 review。
6. 新实现前按项目规范做研究：GitHub code search、官方/primary docs、包注册表；优先采用经过验证的库或模式。
7. 以小阶段和原子提交推进，绝不一次性把 A-F 都混入同一变更。

---

## 15. 给下一执行者的启动指令（可直接复制）

```text
你接手 E:\github\rag 的“OKF SSOT + 多路检索统一架构”阶段 A。

先阅读：
1. .planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md
2. .planning/UNIFIED-MULTIROUTE-OKF-PLAN.md
3. .planning/LLM-WIKI-Integration-PLAN.md
4. .planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md
5. CLAUDE.md 和 .planning/workspace-memory.json

硬约束：
- OKF 是唯一持久化知识权威源；DB 是可重建派生缓存。
- PDF/Word 必须 docling → OKF raw → 统一 OKF 摄入；不要另建 docling 直入 DB 的事实链。
- 纯向量、PageIndex 默认树、PageIndex 热点、实体/图谱是可并联联用的四条召回视图。
- 不要把 Level 2 的 PageIndex 质量问题归因于图谱；参数诊断与评测明确后置。
- 阶段 A 的首要正确性目标是 docling 直出与 OKF round-trip 的 span_id 100% 一致。
- 在选定 raw span metadata 表达、hash 语义、entity_mentions 模型、migration 编号、relation qualifier 模型前，不要开始写 migration 或 serializer；先提出设计并获得确认。

阶段 A 只做：OKF 格式契约、docling→OKF 序列化器、parser 增量/删除与验证、基础 migration、rebuild-from-okf、span_id identity tests。
阶段 A 不做：NER、图谱多跳、融合调参、PageIndex 诊断、Agent 自动回写、Phase 14 对比。

开始任何 symbol 编辑前，遵守 CLAUDE.md 的 GitNexus impact rules。保持工作区隔离，不能把既有大量未追踪/修改文件混入提交。
```

---

## 16. 交接完成定义

本交接文件满足以下条件：

- 已把用户明确确认的 D1-D8 写为不可重新解释的决策；
- 已区分“已验证的仓库事实”和“计划中但尚未实现的功能”；
- 已记录计划文本与代码不一致的两个高风险点：`_fuse_candidate_scores` 不存在、OKF parser 缺失 span 坐标；
- 已将质量调优明确放到 F，避免下一执行者提前偏航；
- 已将阶段 A 的停止条件和验收证据列为可测试清单；
- 已列出仍需显式确认的 T1-T9，不让实现者静默替用户做架构决定。

## Active Phase 15/E2a routing

The handoff governs Phase 15 scope and routing; the unified plan governs compatible architecture; accepted ADRs govern explicit scope. Phase 15/E2a is authorized, planned, and execution-unstarted. User selection: 授权规划和实施（推荐）. Authorization source: interactive Claude Code session. This is not an independent repository transport receipt; no date, receipt ID, or durable independent authorization evidence is asserted. Direct-persistence and dual-chain language is historical/superseded. Implementation requires independent review of corrected plans and does not authorize Phase 16/E2b, Phases 19/20, production, Git operations, or disposable acceptance.


## Active Phase 15 precedence correction

Gate 3 is satisfied by the exact interactive selection `授权规划和实施（推荐）`. Phase 15 remains authorized, planned, and execution-unstarted; no date, receipt, or independent durable authorization evidence is invented. This active correction does not alter historical Phase 14 evidence. Scoped precedence is: the execution handoff for scope and phase routing; the unified architecture where consistent; accepted ADRs in their explicit technical scope, including `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` and `ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md`; then milestone/roadmap execution mapping. The raw-pair ADR governs generated raw-pair binding and strict production admission.
