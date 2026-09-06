# LlamaIndex Target Architecture

## 一句话定义

这套系统的目标态是：

> **以 LlamaIndex 作为主编排层，以 PostgreSQL 作为 identity / version / provenance 主干，以 Neo4j 作为图层，以独立向量层作为语义检索层，以 Tree/Parent-Child 作为结构层的多视图知识检索与推理系统。**

## 目标不是现在 `verification/` 里的什么

当前 `verification/` 目录里的代码，定位应该是：
- 验证实现
- 参考实现
- 行为基线

它已经证明了主干概念可行，但它**不是**最终交付目标。

## 最终目标架构

### 1. Parsing / Ingestion
- `DoclingReader` / `DoclingNodeParser`
- 文档只解析一次
- 保留 `page_no`、`headings`、`offset`
- 形成统一 `canonical spans`

### 2. Identity / Version / Provenance 主干
- PostgreSQL
- 统一维护：
  - `doc_id`
  - `version_id`
  - `span_id`
  - `node_id`
  - `chunk_id`
  - `entity_id`
  - `relation_id`
- 负责：
  - mapping
  - provenance
  - versioning
  - update lifecycle

### 3. Vector Layer
- **LlamaIndex `VectorStoreIndex`**
- 后端可接：
  - pgvector（PoC / 轻量）
  - Qdrant / Milvus（正式向量层）
- 负责：语义检索

### 4. Tree Layer
- **主采用候选 A：LlamaIndex `HierarchicalNodeParser` + `AutoMergingRetriever`**
- **正式对照候选 B：PageIndex（树状知识库/页级目录树方案）**
- 负责：
  - Parent-Child
  - Small2Big
  - 命中回并
  - 或者以“数据库型目录树索引”方式做树层执行

当前目标态偏向 A，但这不意味着 B 被排除。更准确的说法是：
- A 更贴近当前 `LlamaIndex-first` 主线
- B 是你明确提出的树层正式候选，应保留为对照项，而不是一句话删掉

### 5. Graph Layer
- **LlamaIndex `PropertyGraphIndex`**
- `Neo4jPropertyGraphStore`
- 负责：
  - entity / relation
  - evidence links
  - graph traversal

### 6. Hybrid Retrieval Layer
- 自定义 `BaseRetriever` / `CustomPGRetriever`
- 主链：
  - KG → Keyword/Vec → Tree → 聚合 → 扩展
- `HitDistributionAnalyzer` 提供扩展决策输入
- `Reranker` 提供多路候选重排

### 7. Agent / Orchestration Layer
- LlamaIndex `Workflow`
- LlamaIndex `ReActAgent`
- 对外暴露：
  - `knowledge_router_tool`
  - API
  - CLI

## 最终查询路径

1. **Keyword path**
   - 精确术语 / 标准号 / 缩写 / 节目名

2. **Vector path**
   - 轻量语义问题

3. **Graph path**
   - 概念关系 / 实体关系

4. **Deep Hybrid path**
   - 复杂多跳 / 跨章节 / 扩展上下文问题

## 与当前验证实现的关系

当前验证实现证明了这些原则是对的：
- 一次解析
- 统一 span
- keyword / vector / graph / tree / hybrid / rerank 都能成立

但目标态仍然应该回到：
- 用 LlamaIndex 原生能力承接 Vector / Tree / Graph 主编排
- 把现在验证代码里那些纯自定义模块，收缩成：
  - 适配层
  - 自定义策略层
  - 验证基线

## 关键原则

1. **不要统一 chunk，要统一 span**
2. **不要统一三层结构，要统一三层主键和版本**
3. **LlamaIndex 是主编排层，不是唯一数据库**
4. **PostgreSQL 是 source of truth，Neo4j / VectorStore / Tree 是派生执行视图**
