# Provenance-Centric Multi-View RAG 完整路线图

生成时间：2026-05-09  
目标：构建一个 **provenance-centric multi-view RAG / versioned provenance mapping layer** 系统，把 **知识图谱、向量检索、树状层级检索、命中分布分析、Agent 自主扩展** 组装成一个统一的内部检索与推理内核，并可对外暴露成 Tool / API / CLI。

---

# 0. 最终结论

这套系统不应该被理解为：
- “找一个最强数据库”
- “找一个最强框架”
- “让三层用同一种 chunk 标准”

它真正应该被理解为：

> **先建立一个 versioned provenance mapping layer（身份层 + 版本层 + 证据层），再用 LlamaIndex 把 Graph / Vector / Tree 三层编排起来。**

一句话总结：

> **不要统一 chunk，要统一 span。**  
> **不要统一三层结构，要统一三层主键和版本。**

---

# 1. 最终要组装成什么系统

## 1.1 系统目标

最终系统要具备四种查询模式：

### A. 关键词问题（BM25 / exact keyword / code / 指标词）
- 直接走关键词检索路径
- 适合 `PM2.5`、标准号、缩写、术语、节目名、人名、型号等精确匹配需求
- 返回命中的 span / chunk / node，并可附带 parent node 摘要

### B. 轻量问题（factual / semantic retrieval）
- 直接走向量数据库
- 返回最相关 chunk
- 可附带 parent node 摘要

### C. 概念关系问题（entity / concept / relation）
- 直接走知识图谱
- 返回实体、关系、证据链接
- 必要时局部补向量证据

### D. 复杂知识问题（multi-hop / cross-section / deep reasoning）
- 先知识图谱锁定概念与关系
- 再受约束关键词/向量检索
- 再树层级回并
- 再命中分布分析
- 再父节点 / 兄弟节点 / 相邻 chunk 扩展
- 最终生成答案

---

## 1.2 最终系统形态

### 内部核心（检索与推理大脑）
- LlamaIndex
  - Query Classifier
  - Keyword Path
  - Vector Path
  - Graph Path
  - Deep Hybrid Path
  - Unified Response Builder
  - Rerank Stage（第二阶段加入）

### 数据底座
- PostgreSQL：registry / mapping / provenance / versioning
- Neo4j：graph projection
- Milvus 或 Qdrant：vector projection
- Tree/docstore：hierarchy projection

### 对外暴露
- 一个总工具：`knowledge_router_tool`
- 或一个 API：`/query`
- 或一个 CLI：`knowledge-router`
- 或接入 langclaw / LangChain / Claude 的 Tool 调用层

---

# 2. 使用哪些项目、各自负责什么

## 2.1 主底座

### 1) LlamaIndex（主底座）
**负责：**
- 检索与推理编排
- PropertyGraphIndex
- VectorStoreIndex
- HierarchicalNodeParser
- AutoMergingRetriever
- Workflow / ReActAgent
- Tool 封装

**为什么选它：**
- 唯一全组件覆盖：KG / Vec / Tree / Parse / Cas / Map / Agent
- MIT 许可
- 官方扩展点清晰
- 适合做“内部大脑”

---

## 2.2 数据层

### 2) PostgreSQL（系统事实层 / source of truth）
**负责：**
- documents
- document_versions
- canonical_spans
- tree_nodes
- vector_chunks
- entities / relations registry
- evidence_links
- chunk↔span / node↔span / mention↔entity 映射
- 关键词检索底座（第一阶段可直接用 PostgreSQL FTS / trigram / BM25 类方案）
- 幂等更新
- 版本切换
- provenance

**为什么必须有它：**
- 三库对齐的核心不是检索，而是身份、版本与证据建模
- 没有 registry 层，重切片会把图 / 向量 / 树全打散

---

### 3) Neo4j（图层）
**负责：**
- 实体、关系、关系链路
- 子图查询
- Cypher
- 图遍历 / 图算法（PageRank、社区等，按需）
- KG Path 的主要执行层

**为什么选它：**
- 原生图查询成熟
- 和 LlamaIndex PropertyGraphIndex 对接清晰

**不负责：**
- 不做系统事实源
- 不做版本控制中心
- 不做 chunk 主存储

---

### 4) Milvus 或 Qdrant（向量层）
**负责：**
- embedding 检索
- metadata 过滤
- 受约束向量召回
- 向量 path 的主要执行层
- 与关键词路径、图路径合并后的候选重排前召回层

**选择建议：**
- **Milvus**：如果你更看重大规模性能
- **Qdrant**：如果你更看重 metadata-heavy 过滤与开发舒适度

**不负责：**
- 不负责版本真相
- 不负责实体稳定性
- 不负责树结构

---

### 5) Tree / docstore（树层）
**负责：**
- parent-child 层级结构
- section / paragraph / summary anchor
- 命中回并
- Small2Big / Parent-Child retrieval

**主机制：**
- HierarchicalNodeParser
- AutoMergingRetriever

---

## 2.3 解析与切片层

### 6) Docling（主解析器）
**负责：**
- 文档解析
- page_no
- headings
- 结构元数据保留
- 结构自适应切片基础

**为什么选它：**
- 与 LlamaIndex 原生集成
- 自动保留 citation 所需元数据

---

### 7) LlamaIndex SemanticSplitter（可选增强）
**负责：**
- 语义自适应切片
- embedding 相似度断点

**作用：**
- 作为 leaf chunk 的切片策略增强
- 提升向量 chunk 的语义连贯性

---

## 2.4 补件（不是主底座）

### 8) RAPTOR / HIRO（思想补件）
**负责：**
- 树层 coarse-to-fine 检索思想
- branch pruning 思路
- tree scoring 参考

**用途：**
- 借鉴，不作为系统主底座

### 9) Psi-RAG（思想补件）
**负责：**
- 树层多粒度检索思路
- 复杂树检索与扩展参考

### 10) Chonkie（可选切片参考）
**负责：**
- 更丰富的 chunking-only 能力
- 仅在后期你要强化切片策略时参考

---

# 3. 哪些部分先做，哪些后做

## 3.1 必须最先做的（编码前）

这是整个路线图最关键的一步，**必须在真正写任何业务代码之前锁定**。

## Phase 0：冻结 identity / normalization / entity canonicalization contract

### 必须先锁定的内容

#### A. 主键责任边界
- `doc_id`：逻辑文档身份
- `version_id`：文档版本身份
- `span_id`：规范证据身份
- `node_id`：树视图身份
- `chunk_id`：向量视图身份
- `entity_id`：实体身份
- `relation_id`：关系身份

#### B. normalization contract
- parser / OCR 版本
- 文本清洗规则
- heading 归一化规则
- offset_basis（raw_char / normalized_char / token）
- page_no 生成规则

#### C. entity canonicalization contract
- entity_key 生成规则
- canonical_name 规则
- alias / mention normalization 规则
- mention -> entity 映射策略

### 为什么必须先做
如果这一步没先锁定，后面会出现：
- `span_id` 漂移
- 同一实体跨版本不稳定
- chunk 变了以后所有映射断裂
- 更新策略完全失效

---

## 3.2 第一阶段：先做数据底座，再做检索逻辑

### Phase 1：Registry / Mapping / Provenance 层
**先做 PostgreSQL schema**：
- documents
- document_versions
- normalization_contracts
- canonical_spans
- tree_nodes
- tree_node_spans
- vector_chunks
- vector_chunk_spans
- entities
- entity_aliases
- entity_mentions
- relations
- evidence_links
- chunk_entity_links
- node_entity_links

**这一阶段的目标：**
- 三层还没接起来也没关系
- 先把“谁是谁、谁属于谁、谁从谁派生、哪个版本是 active”定清楚

---

### Phase 2：Parse + Span 生成
**用的项目：**
- Docling
- LlamaIndex Docling integration

**做什么：**
- 把原始文档解析成结构化内容
- 生成 canonical spans
- 验证 page_no / heading_path
- 固化 normalization contract

**这一阶段的交付物：**
- 每个 version 有稳定 span 坐标
- 每个 span 能回到原文

---

### Phase 3：Tree 层
**用的项目：**
- LlamaIndex HierarchicalNodeParser
- AutoMergingRetriever

**做什么：**
- 在 canonical spans 之上派生 tree nodes
- 建 parent-child
- 写 tree_node_spans 映射
- 验证 leaf → parent rollup

**这一阶段的目标：**
- 树结构稳定
- 可以从 node 回 span
- 可以从 chunk 回 node

---

### Phase 4：Vector 层
**用的项目：**
- Milvus 或 Qdrant
- LlamaIndex VectorStoreIndex
- SemanticSplitter（可选）

**做什么：**
- 从 canonical spans / tree leaves 派生 vector chunks
- 写 vector_chunk_spans
- 写 metadata：doc_id/version_id/chunk_id/node_id/page_no/heading_path/entity_ids
- 验证 metadata 过滤

**这一阶段的目标：**
- 向量检索能稳定回映 node_id / span_id
- 重 embedding / 重切片可版本化切换

---

### Phase 5：KG 层
**用的项目：**
- Neo4j
- LlamaIndex PropertyGraphIndex

**做什么：**
- 抽实体 / 关系
- 写 entity / relation registry
- 写 evidence_links（一定指向 span_id，不直接指向 chunk_id）
- 建 chunk_entity_links / node_entity_links

**这一阶段的目标：**
- KG 与 evidence span 稳定绑定
- KG → Vec / KG → Tree 有桥表可走

---

# 4. 第二阶段做什么：检索与推理大脑

## Phase 6：四条检索路径

### Path A：关键词问题（新增）
- 直接 PostgreSQL FTS / trigram / BM25 类路径
- 返回 span / chunk / node / page_no / heading_path
- 适合 `PM2.5`、标准号、节目名、人名、机构名、型号、代码、药名等精确术语检索

### Path B：轻量问题
- 直接向量检索
- 返回 chunk + parent context

### Path C：概念问题
- 直接图谱检索
- 返回 entity / relation / evidence

### Path D：复杂问题（主链）
- 先 KG 检索实体与关系
- 再 registry 找到相关 span_id / chunk_id / node_id
- 再关键词 / 向量库做受约束检索
- 再 tree 层回并
- 再命中分布分析
- 再扩展 parent / sibling / adjacent
- 最后答案生成

---

## Phase 7：命中分布、重排与扩展策略

### 用到的能力
- LlamaIndex Workflow
- ReActAgent
- 自定义 `CascadeKGVecTreeRetriever`
- 自定义 `HitDistributionAnalyzer`
- 关键词路径检索器
- 轻量融合排序（第一阶段）
- 独立 reranker（第二阶段）
- 自定义 expansion tools

### 这里真正要自研的逻辑
1. query classifier（关键词型 / 轻量语义型 / 概念关系型 / 复杂型）
2. keyword path（PostgreSQL FTS / trigram / BM25 类）
3. graph-first constrained keyword/vector retrieval
4. leaf -> parent aggregation
5. hit distribution scoring
6. candidate fusion + rerank policy
7. expansion policy

### 推荐的扩展规则
- 命中高度集中 → 只取高得分节点
- 命中中等集中 → 命中节点 + 父节点摘要
- 命中较分散 → 父节点 + 兄弟分支
- 信息残缺 → 相邻 chunk 扩展

---

# 5. 最终对外组装成什么

## 方案 A：一个总 Tool（最推荐）

### 对外只暴露一个能力
- `knowledge_router_tool(query, context?)`

### 内部隐藏三条路
- vector path
- graph path
- deep hybrid path

### 适合谁调
- LangChain
- langclaw
- Claude
- API
- CLI

### 为什么最推荐
- 对外最简单
- 内部最可控
- 后续演进不影响接口

---

## 方案 B：多个 Tool（备选）

- `vector_search_tool`
- `graph_reasoning_tool`
- `deep_hybrid_tool`

### 缺点
- 外部 Agent 还要学会什么时候选哪个
- 增加提示词和调度复杂度

所以我建议：

> **先做一个总工具，再在内部做智能路由。**

---

# 6. 最终系统长什么样

## 最终形态

### 内部
- provenance-centric multi-view RAG kernel
- versioned registry layer
- graph projection
- vector projection
- tree projection
- hybrid retrieval engine
- expansion policy engine

### 对外
- 一个 Tool / API / CLI
- 外部 Agent 调它，不需要知道内部怎么查

## 实际上最终得到的是：

> **一个可被其他 Agent 调用的“知识检索与推理内核”**

它不是单纯的向量数据库问答器，
也不是单纯的图谱系统，
而是：

- 能按问题类型自动选检索路径
- 能把图、向量、树三层组合起来
- 能稳定回到原文证据
- 能处理重切片、重 embedding、重抽图谱后的版本问题

---

# 7. 哪些可以后置

这些不是第一阶段必须做的：

## 可以后置 1：高级 entity resolution
- 先用简单 `entity_key`
- 后续再补更复杂 alias / canonicalization

## 可以后置 2：Late Chunking
- 不是主链必须项
- 等基础检索稳定后再增强 embedding 质量

## 可以后置 3：Neo4j 中的 TreeNode / Chunk 投影
- 初期 registry 就够了
- 不需要一开始就把所有层都投影到图里

## 可以后置 4：思维导图生成 / 可视化
- 可作为命中分布树的展示层
- 不影响核心检索路线

## 可以后置 5：性能优化
- alias 切换、缓存、异步并发、observability 都可以在主链跑通后做

---

# 8. 最容易犯的顺序错误

## 错误 1：先做检索逻辑，再补 registry
后果：
- 一重切片，全断
- 图、向量、树三层无法回链

## 错误 2：把 chunk_id 当成全局身份
后果：
- 重切片后全部失效

## 错误 3：没先冻结 normalization contract
后果：
- span_id 漂移
- provenance 层失真

## 错误 4：图谱证据直接指向 chunk_id
后果：
- 一旦 chunk 变，图谱证据全断

---

# 9. 最终实施顺序（最实用版）

## Step 0（先于编码）
- 冻结 identity contract
- 冻结 normalization contract
- 冻结 entity canonicalization contract

## Step 1
- 建 PostgreSQL registry schema

## Step 2
- 接 Docling
- 生成 version + canonical spans

## Step 3
- 接 Tree 层（HierarchicalNodeParser）
- 建 node↔span 映射

## Step 4
- 接向量库（Milvus / Qdrant）
- 建 chunk↔span 映射

## Step 5
- 接 Neo4j
- 建 entity / relation / evidence_links

## Step 6
- 实现三条检索路径

## Step 7
- 实现 deep hybrid 主链
  - KG → Vec → Tree → 聚合 → 扩展

## Step 8
- 封成一个 Tool / API / CLI

## Step 9
- 做版本切换、旧版本回收、缓存、监控

---

# 10. 最后一句结论

我们最终不是在“拼几个项目”，而是在组装一个系统：

- **LlamaIndex** 负责检索与推理编排
- **PostgreSQL** 负责身份、版本、证据映射
- **Neo4j** 负责图谱视图
- **Milvus / Qdrant** 负责向量视图
- **Tree/docstore** 负责层级视图
- 最后对外暴露成一个 **knowledge_router_tool / API / CLI**

所以最准确的最终描述是：

> **一个 provenance-centric multi-view RAG 内核，内部统一身份层、版本层、证据层，对外暴露成可被其他 Agent 调用的知识检索与推理工具。**