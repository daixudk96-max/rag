# 中文低 Token GraphRAG 升级方案（差距分析 + 实施路线）

> 来源：`C:\Users\daixu\Downloads\中文低Token_GraphRAG完整实施路线图 (1).docx`（V1.0, 2026-07-01）
> 对照对象：本仓库 v1.0 现状（Phase 13 CLOSED，Level 2 基线：hit_rate 70% / top1_relevance 59% / stability 65%）
> 撰写日期：2026-07-12

> **2026-07-12 v2.0 对账说明（本注不删原文，原 WS 表与细节全部保留作源头参照）：**
> 本文件先于 v2.0 里程碑（Phase 14-20）与 ADR T1-T9 定稿。规划归属以补充交接书
> `.planning/OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md` 为准，对账要点：
> 1. **WS2 指代层** → 已归属 **Phase 16-C2**（条件性第二 wave，默认关闭，净收益由 Phase 19 G3 裁决）。
>    WS2 的 relation_mentions/qualifiers 部分**不随** 16-C2 授权——仍按 ADR T6"C 后按需"。
> 2. **阶段 6 试点/生产化** → 已归属 **Phase 20**（三重入口门；见 20-BOUNDARY.md）。
> 3. **migration 编号**：本文各 WS 提到的"新增 migration"一律按 ADR T5 取执行时下一个连续空闲号，
>    不采用本文写作时的假设编号。
> 4. **符号勘误**：§2.2 融合行写的 `_fuse_candidate_scores` **不存在于代码库**（ADR 核验）。
>    有效符号是 `tree/semantic_distribution.py::_compute_fusion_score`（热点固定权重
>    0.40/0.30/0.20/0.10，T7 冻结）与 `analysis/fusion.py:40::fuse_candidates`（RRF，
>    R3 唯一注入点）。任何引用 `_fuse_candidate_scores` 的计划即作废（里程碑边界裁决 4）。
> 5. **评测与裁决**（本文 WS0 与消融阶梯）：八类题集、All-Evidence Recall、A→G 阶梯与
>    G3/G4/G5 裁决门全部归属 Phase 19，且以用户解冻 D4 为前置——在此之前不做任何质量宣称。

---

## 1. 路线图文档的核心主张（一句话版）

**入库阶段实体/关系抽取零生成式 Token**：用非生成式中文 NER + 实体归一/别名消歧 +
跨句指代 + Entity-KU-Chunk 确定性索引 + SQL 1-3 跳动态扩展，替代传统 GraphRAG 的
全量 LLM 三元组抽取。**关系图不是系统中心，原始证据和实体归一才是中心。**

## 2. 对齐度结论：本项目是该路线图的天然宿主

文档的架构哲学（证据坐标为中心、多视图不强制对齐、模块可插拔、决策门驱动）与本项目的
provenance-centric 设计**完全同构**。文档阶段 0/1（基线、文档解析、树、Chunk/KU、来源定位）
在本项目已基本完成；真正的增量集中在阶段 2/3/4（实体层、指代层、实体召回+多跳）。

### 2.1 数据模型逐表对照（文档 §7.1 vs 现有 migrations 001-014）

| 文档要求的表 | 现状 | 落点 |
|---|---|---|
| documents | ✅ `documents` + `document_versions`（比文档多版本化/checksum） | 无需改动 |
| tree_nodes | ✅ `tree_nodes` + `tree_node_spans`（003） | 无需改动 |
| chunks | ✅ `vector_chunks` + `vector_chunk_spans`（001/004） | 无需改动 |
| knowledge_units | ≈ `canonical_spans`（docling 最小逻辑单元，语义上等价 KU） | 第一版直接以 span 充当 KU |
| entities | ⚠️ 表存在（005/006：entity_key/type/canonical_name/description/community_id），**零数据、无抽取器** | WS1 填充 |
| entity_aliases | ❌ 缺表 | WS1 新增 migration |
| entity_mentions | ⚠️ `evidence_links`(entity→span_id+confidence) 近似；`chunk/node_entity_links` 有 mention_text（012），但**缺 char 级偏移** | WS1 新增 mention 表或扩 evidence_links |
| coref_clusters | ❌ 缺 | WS2 新增 |
| ku_entities | ≈ `evidence_links` / `chunk_entity_links`（有结构无数据） | WS1 物化 |
| semantic_edges | ❌ 缺（共现/语义近邻边） | WS3 新增 |
| relation_mentions + 限定词 | ⚠️ `relations` 表存在但无否定/条件/方向/时间 qualifiers | WS2 扩展 |
| eval_questions / retrieval_logs | ⚠️ verification/ 用 JSON 文件，未表化 | WS0 表化 |

### 2.2 管线对照

| 环节 | 文档要求 | 现状 |
|---|---|---|
| 文档解析 | 规则优先，保留页码/版本 | ✅ docling → NormalizationContract → canonical_spans，**零 LLM**，确定性 span_id |
| 树构建 | 自建中间层，PageIndex 思路作备选 | ✅ heading_path 规则树（003）；PageIndex LLM 树为可选路径（摘要可关） |
| 实体抽取 | UIE/DeepKE/HanLP + 领域词典，非生成式 | ❌ 完全没有；无任何中文 NLP 依赖 |
| 实体归一 | 别名表+候选生成+Embedding重排+类型约束 | ❌ 没有 |
| 指代 | 规则优先（该X/其/上述/主体继承） | ❌ 没有 |
| 关键词抽取 | — | ⚠️ 正则版（会粘连长句）；jieba 计划已定稿未执行（`.planning/jieba-keyword-extraction-PLAN.md`） |
| 检索 | BM25+Dense+Entity+SQL 1-3跳+融合 | ⚠️ keyword path（PG FTS/trigram）+ vector + tree hotspot（Phase 13）已有；**缺实体召回路和多跳** |
| 融合 | RRF/Reranker | ✅ `_fuse_candidate_scores`：40% vector + 30% keyword + 20% rerank + 10% child_distribution，可扩实体信号 |
| 评测 | 300-500 题证据链集 + 消融阶梯 | ⚠️ verification 框架 + 95 条判定存在，规模与题型覆盖不足 |

**关键事实**：本项目入库管线本来就不调 LLM（除可选的 PageIndex 树摘要）。文档的
"零 Token 入库"底座已经存在——升级 = **在零 Token 前提下补上实体层，而不是拆掉什么**。

## 3. 实施路线（映射文档阶段 0-6 → 本项目工作流 WS0-WS4）

### WS0 — 基线冻结与评测集扩建（对应文档阶段0，约1周）
- 冻结当前 Phase 13 hybrid_cluster 检索为对照基线 A（模型/Prompt/top-k/上下文预算全部版本化）。
- 评测集从 95 题扩到 300-500 题，按文档附录 B 八类：全称-简称、同名消歧、显式指代、零指代、
  否定、条件/例外、跨章节/跨文档多跳、不可回答。每题标注**全部证据 span_id**（All-Evidence Recall 是主指标）。
- migration 015：`eval_questions`、`retrieval_logs` 表化（替代散落 JSON）。
- 决策门 G0：基线可一键重跑，每题有标准答案与证据链。

### WS1 — 非生成式中文实体层（对应文档阶段2，核心增量，约3-4周）
- **先执行 jieba 计划**（已定稿，低风险，直接改善 keyword path 与 hotspot 关键词信号）。
- 新增 `llamaindex_runtime/entity/` 模块，抽取器可插拔（文档 §7.2 模块边界）：
  - 起步组合：**领域词典 + HanLP**（pip 友好，Windows 可用）；
  - 并行评估 PaddleNLP UIE / DeepKE（文档首选 UIE，但 paddle 在 Windows 安装不友好，建议 WSL/Linux 跑对比）。
- migration 016：`entity_aliases(entity_id, alias, alias_type, source, confidence)`、
  `entity_mentions(mention_id, entity_id, span_id, char_start, char_end, mention_text, confidence)`、
  `entity_merge_log`（文档要求所有自动合并可追踪、可回滚）。
- EntityResolver 归一五步（文档 §4.2）：文本标准化（简繁/全半角/机构后缀/数字日期）→
  候选生成（精确别名/前后缀/字符相似/拼音缩写/embedding 近邻——复用现有 sentence-transformers + pgvector）→
  上下文排序 → 高阈值自动合并（中间区间保留多候选）→ 别名表持续学习。
- 物化 `evidence_links`（entity→span）、`chunk_entity_links`、`node_entity_links`。
- 决策门 G2：Mention 召回 ≥85%，归一准确率 ≥85%（全称/简称/别名/同名分开统计）。

### WS2 — 中文指代与高价值语义标记（对应文档阶段3，约2-3周）
- 规则优先三层：段落中心实体继承 → 显式指代（"该院/其/上述单位/本项目"词表+正则）→
  HanLP 指代模型补充（低置信度不合并）。
- migration 017：`coref_clusters`；`relation_mentions(subject, predicate, object, qualifiers JSONB, ku_id)`
  仅存否定/条件/例外/方向/时间等高风险语义标记，**不做全量三元组**。
- 决策门 G3：加指代后 All-Evidence Recall 有显著净提升且误合并率低于收益，否则关闭模块。

### WS3 — 实体召回路 + SQL 动态多跳 + 融合升级（对应文档阶段4，约2-3周）
- 新检索路径（纯 PostgreSQL，无需图数据库——文档附录A明确 MVP 不上图库）：
  query → jieba+NER → 实体归一 → 种子 span/chunk → **递归 CTE 经共享实体/章节/语义边做 1-3 跳扩展**
  （路径去重、度数上限、跳数预算）→ 候选证据 → 融合重排。
- migration 018：`semantic_edges(src, dst, edge_type, score, evidence_id)`（共现边 PMI 加权，可关闭）。
- 实体信号并入 `_fuse_candidate_scores`（权重经 WS4 消融调定）；带否定/条件标记的边**不参与扩展**，
  仅作 rerank 特征（文档 §10 回退路径）。
- 每次查询记录扩展路径到 `retrieval_logs`（可解释引用）。
- 决策门 G4：固定上下文预算下 All-Evidence Recall@20 显著优于基线 A，增量入库不触发全库重建。

### WS4 — 消融评测与架构裁决（对应文档阶段5，约1-2周）
- 复用 verification 框架跑文档 §8.3 阶梯：
  A 基线 → B +实体倒排 → C +KU多部索引 → D +实体归一 → E +指代 → F +语义边 → G +高价值限定词。
- 无净收益的模块**删除**（文档原则：不以单一总分决策，收益须覆盖延迟/维护/误差成本）。
- 产出成本-质量-延迟 Pareto 表，决定试点（阶段6）范围。

## 4. 关键决策点（需要用户拍板）

1. **PageIndex LLM 树摘要**：文档要求入库零 Token。建议默认关闭节点摘要
   （已支持 `if_add_node_summary=no`），docling heading 树为主；PageIndex 树作为可选增强保留。
2. **NER 选型**：HanLP 起步（Windows 友好）还是坚持文档首选 UIE（需 WSL/GPU 环境）？
   建议按文档"第4-7日并行对比"清单先跑三方对比报告再定。
3. **KU 粒度**：第一版以 canonical_span 充当 KU（避免动 NormalizationContract 影响 span_id 稳定性）；
   若 G2 后发现证据粒度过粗，再引入 sentence 级 KU 子层。
4. **与现有质量困境的关系**：当前 Level 2 卡在 hit_rate 70%（阈值 80%）。实体召回路正面解决
   别名/指代/多跳型漏检，是达标的最短路径——建议把 WS1-WS3 直接作为 v1.1 里程碑主线。

## 5. 风险与回退（继承文档 §10）

| 风险 | 应对 | 回退 |
|---|---|---|
| 通用中文 NER 在领域语料召回不足 | 领域词典优先 + 弱监督微调 | 保留 jieba 关键词/名词短语索引（现有 keyword path） |
| 实体误合并 | 高阈值+类型约束+merge_log 可回滚 | 拆分实体重建局部 evidence_links |
| 共现边噪声 | PMI/度数上限/跳数预算 | 只用 Entity-KU 确定性边（evidence_links） |
| 复杂度失控 | WS4 消融裁决，无收益即删 | 退回"实体倒排 + 现有 hotspot"简版 |
