# PROJECT FREEZE

> **这是当前项目的唯一冻结入口文档。**
> 以后不管是 Claude、别的 AI，还是人，只要先读这一份，就能知道：
> - 这个项目最后定的是什么
> - 哪条线是正式主线
> - 哪条线只是验证实现
> - 从哪些项目吸收了哪些部分
> - 现在已经做到哪一步
> - 下一步应该怎么继续
>
> **如果其他文档和这份文档有冲突，以这份为准。**

---

## 1. 项目现在到底是什么

这个项目现在有两条线，必须区分：

### A. 正式目标主线
这是你真正要做的项目，方向已经锁定为：

> **LlamaIndex-first 的 provenance-centric multi-view RAG 系统**

它的核心是：
- **LlamaIndex** 作为主编排层
- **Docling** 做一次解析
- **PostgreSQL** 做 identity / version / provenance 主干
- **Neo4j** 做 graph layer
- **Milvus / Qdrant** 做正式 vector layer
- **Keyword / Vector / Graph / Deep Hybrid** 做四条查询路径
- 对外暴露成：
  - Tool
  - API
  - CLI

### B. 验证实现线
`verification/` 里的代码不是最终交付主线，而是：
- 参考实现
- 架构验证器
- 行为基线

它的作用是证明：
- provenance / span / version 这套主干能跑
- keyword / vector / graph / tree / hybrid / rerank 这些能力能闭环

> **不要再把 `verification/` 当成正式实现主线继续扩。**
> 正式实现应该回到 LlamaIndex-first 主线。

---

## 2. 当前已经冻结的总决策

### 冻结决策 1：统一的是 span，不是 chunk

系统的稳定坐标是：
- `doc_id`
- `version_id`
- `span_id`

而不是某一层自己的 chunk / node / entity 视图。

### 冻结决策 2：PostgreSQL 是 source of truth

PostgreSQL 负责：
- registry
- mapping
- provenance
- versioning
- keyword path（PoC / 轻量实现）
- pgvector（PoC 向量层）

### 冻结决策 3：LlamaIndex 是目标主编排层

正式主线应回归到：
- `VectorStoreIndex`
- `PropertyGraphIndex`
- `HierarchicalNodeParser`
- `AutoMergingRetriever`
- `Workflow`
- `ReActAgent`

### 冻结决策 4：验证线不等于目标线

验证线已经证明这条路线能跑，
但正式目标线不应该继续沿自定义 Python/FastAPI 内核扩下去。

---

## 3. 最终目标架构（冻结版）

### Parsing / Ingestion
- `DoclingReader`
- `DoclingNodeParser`
- 输出：
  - `page_no`
  - `headings`
  - `offset`
  - `canonical spans`

### Identity / Version / Provenance
- PostgreSQL
- 维护：
  - `doc_id`
  - `version_id`
  - `span_id`
  - `node_id`
  - `chunk_id`
  - `entity_id`
  - `relation_id`

### Vector Layer
- 主采用：**LlamaIndex `VectorStoreIndex`**
- 后端：
  - pgvector（PoC）
  - Qdrant / Milvus（正式向量层）

### Tree Layer
有两个正式方向：

#### A 方向（当前主线优先）
- LlamaIndex `HierarchicalNodeParser`
- LlamaIndex `AutoMergingRetriever`

#### B 方向（正式对照候选）
- **PageIndex**
- 角色：树状知识库 / 数据库型目录树索引

> 当前正式主线先按 **A 方向** 推进，
> 但 **PageIndex 不能再被忽略**，它是树层正式候选/对照项。

### Graph Layer
- LlamaIndex `PropertyGraphIndex`
- `Neo4jPropertyGraphStore`
- Neo4j

### Hybrid / Strategy Layer
- 自定义 `BaseRetriever` / `CustomPGRetriever`
- 主链：
  - `KG -> Keyword/Vec -> Tree -> 聚合 -> 扩展`
- `HitDistributionAnalyzer`
- `Reranker`

### Agent / Orchestration Layer
- LlamaIndex `Workflow`
- LlamaIndex `ReActAgent`
- 对外统一暴露：
  - `knowledge_router_tool`
  - API
  - CLI

---

## 4. 项目组合映射（冻结版）

下面是按“主采用 / 正式候选 / donor”划分的最终理解。

### 主采用项目
- **LlamaIndex**：主编排层 / 主底座
- **Docling**：解析层
- **PostgreSQL**：registry / provenance / versioning 主干
- **Neo4j**：graph 执行层
- **Milvus / Qdrant**：正式向量层后端
- **pgvector**：PoC 向量层

### 正式候选 / 对照项
- **PageIndex**：Tree Layer 的数据库型目录树索引候选

### donor / 借鉴项目
这些项目不是主底座，但应该明确知道借了什么：

- **RAPTOR**：树化检索、coarse-to-fine
- **HIRO**：分支剪枝、树评分
- **Psi-RAG**：多粒度树检索与扩展
- **Haystack**：`HierarchicalDocumentSplitter`、`AutoMergingRetriever` 模式
- **LangChain ParentDocumentRetriever**：child→parent 模式
- **Chonkie**：chunking-only 能力
- **KAG**：schema-constrained KG / logical solver 思想
- **LightRAG**：graph-enhanced text indexing / incremental update
- **Microsoft GraphRAG**：mapping tables / text_unit ↔ entity 思想
- **CogitoRAG**：evidence carrier 思想
- **EvidenceNet**：evidence object / `evidence_id`
- **MC-indexing**：multi-view indexing

### 关键原则
> **每一层应该先选一个主底座，再让其他项目作为 donor 补丁。**
> 不能把所有项目都平铺成“参考”。

---

## 5. 当前验证实现已经做到什么

这部分是 `verification/` 的现状总结，不是目标实现要求。

### 已验证通过的能力
- 一次解析 -> canonical spans
- PostgreSQL registry / versioning / provenance
- Keyword path
- Vector path
- Unified `/query`
- Tree formal rollup
- Graph path（代码与 PostgreSQL 侧完成，Neo4j 真运行验证也已经补齐）
- HitDistributionAnalyzer
- Deep Hybrid path
- Reranker
- 生产级基础硬化：
  - 连接池
  - 输入边界校验
  - 统一错误处理
  - 结构化日志
  - `/health`
  - `/health/neo4j`

### 验证线当前测试状态
- 在无 Neo4j 运行时配置时：`102 passed, 6 skipped`
- 在带临时 Neo4j 实例的真实运行验证时：`108 passed`

### 这意味着什么
- 验证线已经证明主干能跑
- 但它不是正式 LlamaIndex-first 交付主线
- 后续不能继续把它当成正式目录扩展

---

## 6. 真正应该继续做的“第一部分计划”

### 正式第一阶段不是继续扩 `verification/`
而是：

> **开始搭建基于 LlamaIndex 的正式项目骨架，并把已经验证通过的思路迁移到 LlamaIndex 原生能力上。**

### 第一阶段交付目标
1. 建立正式实现目录（建议：`app/` 或 `llamaindex_runtime/`）
2. 接入 LlamaIndex + Docling
3. 让 PostgreSQL registry 继续作为 source of truth
4. 用 LlamaIndex 原生能力承接：
   - Vector layer
   - Tree layer
5. 给 Graph layer 留清晰接口，但先不把整条 Deep Hybrid 主链一次做完

### 第一阶段 In Scope
- 正式项目骨架
- 接入：
  - `VectorStoreIndex`
  - `HierarchicalNodeParser`
  - `AutoMergingRetriever`
  - `DoclingReader`
  - `DoclingNodeParser`
- 继续沿用 PostgreSQL registry 主干
- 把当前验证线里的：
  - `vector_path`
  - `tree_path`
 迁移成 LlamaIndex 原生执行逻辑

### 第一阶段 Out of Scope
1. 继续扩展 `verification/`
2. 复杂 graph runtime 完整迁移
3. Deep Hybrid 全链一次落地
4. 高级 hit distribution 策略优化
5. 学习型 reranker / cross-encoder
6. 部署、监控、CI 完整化

### 第一阶段成功标准
1. 正式实现目录建立
2. LlamaIndex 已接入项目
3. Docling + PostgreSQL registry 主链打通
4. LlamaIndex 原生 vector path 可跑
5. LlamaIndex 原生 tree rollup 可跑
6. 不再继续依赖 `verification/` 作为正式实现主线

---

## 7. 你现在应该怎么读这个项目

### 如果你想看目标架构主线
按顺序看：
1. `docs/PROJECT-FREEZE.md`（本文件）
2. `docs/architecture/LLAMAINDEX-TARGET-ARCHITECTURE.md`
3. `docs/architecture/PROJECT-COMBINATION-MAP.md`
4. `docs/architecture/LLAMAINDEX-PHASE-1-PLAN.md`
5. `docs/diagrams/final-architecture-diagram.html`

### 如果你想追溯研究来源
看：
- `docs/research/`

### 如果你想看验证实现结果
看：
- `verification/README.md`
- `docs/validation/real-validation-report.md`

### 如果你想看过程规划
看：
- `docs/.planning/`
- `docs/plans/`

---

## 8. 最后一条冻结结论

> **最终系统不是“一个项目”，而是一个组合架构。**  
> **其中 LlamaIndex 是主底座，Docling / PostgreSQL / Neo4j / Milvus/Qdrant 是正式组成部分，PageIndex 是 Tree Layer 的正式候选/对照项，RAPTOR / HIRO / Psi-RAG / GraphRAG / KAG / CogitoRAG / EvidenceNet / MC-indexing 等提供方法论和局部 donor 逻辑。**

> **验证线已经证明这条路线能跑，但正式项目主线现在应该明确回到 `LlamaIndex-first`。**
