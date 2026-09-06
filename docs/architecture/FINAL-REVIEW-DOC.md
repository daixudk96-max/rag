# 最终审查文档

> **这是最终给你审查的一份总文档。**  
> 如果你只想看一份，后面就只看这份，不需要再在 `architecture/`、`research/`、`verification/` 之间来回翻。

---

## 1. 最终结论先说

### 当前真正的目标主线是：
> **LlamaIndex-first 的 provenance-centric multi-view RAG 系统**

也就是：
- **LlamaIndex** 做主编排层
- **Docling** 做一次解析
- **PostgreSQL** 做 identity / version / provenance 主干
- **Neo4j** 做 graph layer
- **Milvus / Qdrant** 做正式 vector layer
- **Tree / Parent-Child** 做结构层
- **Keyword / Vector / Graph / Deep Hybrid** 做四条查询路径
- 对外统一暴露成：
  - Tool
  - API
  - CLI

### 当前 `verification/` 里的代码是什么？
它是：
- **验证实现**
- **参考实现**
- **行为基线**

它的作用是证明这条路线能跑通，**不是最终交付主线本身**。

---

## 2. 这份文档要回答的三个问题

### Q1. 现在的最终架构到底是什么？
### Q2. 这些能力分别是从哪些项目里吸收来的？
### Q3. 第一部分（正式主线）应该怎么开始，而不是继续在 `verification/` 里打转？

下面依次回答。

---

## 3. 最终目标架构（以最终 HTML 架构图为准）

### 最终目标图的核心原则

1. **一次解析原文**
2. **统一的是 `span_id`，不是 chunk**
3. **统一的是 identity / version / evidence，不是三层切片边界**
4. **LlamaIndex 是主编排层，不是唯一数据库**
5. **PostgreSQL 是 source of truth，Neo4j / VectorStore / Tree 是派生执行视图**

### 最终架构分层

#### A. Parsing / Ingestion
- `DoclingReader`
- `DoclingNodeParser`
- 输出：
  - `page_no`
  - `headings`
  - `offset`
  - `canonical spans`

#### B. Identity / Version / Provenance 主干
- **PostgreSQL**
- 维护：
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

#### C. Vector Layer
- **LlamaIndex `VectorStoreIndex`**
- 正式后端：
  - **Milvus / Qdrant**
- 负责：
  - 轻量语义检索
  - metadata filtering

#### D. Tree Layer
- **主采用候选 A：LlamaIndex `HierarchicalNodeParser`**
- **主采用候选 A：LlamaIndex `AutoMergingRetriever`**
- **正式对照候选 B：PageIndex**
- 负责：
  - Parent-Child
  - Small2Big
  - 命中回并
  - 或数据库型目录树索引

这里要改正一个点：
- 之前我把 PageIndex 直接排掉，这个判断不严谨
- 更准确的说法应该是：
  - **当前 LlamaIndex-first 主线更偏向 `HierarchicalNodeParser + AutoMergingRetriever`**
  - **但 PageIndex 既然是你明确提出的树状数据库候选，就应该保留为正式对照项**

也就是说，现在不是“PageIndex 不存在”，而是：
> **Tree Layer 目前有两个正式方向：A = LlamaIndex 原生树层；B = PageIndex 这类树状知识库项目。**

#### E. Graph Layer
- **LlamaIndex `PropertyGraphIndex`**
- **Neo4jPropertyGraphStore**
- **Neo4j**
- 负责：
  - entity / relation
  - evidence links
  - graph traversal

#### F. Hybrid / Strategy Layer
- 自定义 `BaseRetriever` / `CustomPGRetriever`
- 主链：
  - `KG -> Keyword/Vec -> Tree -> 聚合 -> 扩展`
- `HitDistributionAnalyzer` 做扩展决策输入
- `Reranker` 做多路候选重排

#### G. Agent / Orchestration Layer
- **LlamaIndex `Workflow`**
- **LlamaIndex `ReActAgent`**
- 对外暴露：
  - `knowledge_router_tool`
  - API
  - CLI

---

## 4. 最终查询路径

最终系统要有这 **4 条路径**：

### 1) Keyword path
适合：
- `PM2.5`
- 标准号
- 节目名
- 缩写
- 型号
- 人名
- 精确术语

### 2) Vector path
适合：
- 轻量语义问题
- 相似概念
- 段落召回

### 3) Graph path
适合：
- 概念关系
- 实体关系
- 结构化依赖

### 4) Deep Hybrid path
适合：
- 复杂多跳问题
- 跨章节问题
- 需要图谱 + 关键词/向量 + 树 + 扩展的情况

---

## 5. 从哪个项目吸收哪个部分

这块是你最关心的，我直接压成一个总表。

### 项目组合总表

| 项目 / 方向 | 在最终目标架构中的角色 | 吸收的具体部分 | 状态 |
|---|---|---|---|
| **LlamaIndex** | 主编排层 / 主底座 | `VectorStoreIndex`、`PropertyGraphIndex`、`HierarchicalNodeParser`、`AutoMergingRetriever`、`Workflow`、`ReActAgent`、Tool 封装 | **主采用** |
| **Docling** | 解析层 | 一次解析、保留 `page_no` / `headings` / 结构元数据、作为 canonical spans 的生成输入 | **主采用** |
| **PostgreSQL** | Source of truth | `doc_id / version_id / span_id` 主干、registry / mapping / provenance / keyword path | **主采用** |
| **Neo4j** | 图层执行 | Entity / Relation / Evidence link 图遍历与图查询 | **主采用（目标态）** |
| **Milvus / Qdrant** | 正式向量层 | 独立向量检索后端、metadata filtering | **主采用（目标态）** |
| **pgvector** | 轻量向量层 | PoC / 验证阶段的 vector path | **PoC 采用** |
| **PageIndex** | 树状知识库正式候选 / 对照项 | 文档目录树、页级回溯、结构化逐层定位；适合对照 Tree Layer 是否要走数据库型树索引 | **正式候选（需二次评估）** |
| **RAPTOR** | 树检索思想补件 | coarse-to-fine、树化检索思路 | **借鉴** |
| **HIRO** | 树评分 / 剪枝思想补件 | branch pruning、层级评分参考 | **借鉴** |
| **Psi-RAG** | 多粒度树检索与扩展参考 | Tree-based multi-granular retrieval、复杂扩展思路 | **借鉴** |
| **Haystack** | 回并机制参考 | `HierarchicalDocumentSplitter`、`AutoMergingRetriever` 模式参考 | **借鉴** |
| **LangChain ParentDocumentRetriever** | Parent-Child 检索参考 | child retrieval + parent context 结构 | **借鉴** |
| **Chonkie** | chunking-only 参考 | 更丰富的 chunking strategy / overlap refinery | **可选借鉴** |
| **KAG** | KG+逻辑求解思路参考 | `mutual indexing`、逻辑求解器思想 | **借鉴，不作为主底座** |
| **LightRAG** | 图+文本索引参考 | graph-enhanced text indexing、增量更新思路 | **借鉴** |
| **Microsoft GraphRAG** | mapping tables 参考 | `documents / text_units / entities / relationships` 的映射表思想 | **借鉴** |
| **CogitoRAG** | 证据载体参考 | evidence carrier / provenance-preserving passage | **借鉴** |
| **EvidenceNet** | 证据主对象参考 | `evidence_id` 作为稳定引用对象的思想 | **借鉴** |
| **MC-indexing** | multi-view indexing 参考 | 同一源内容派生 raw / keyword / summary 多视图 | **借鉴** |

### 解释一句话版
- **LlamaIndex** 是当前主底座
- **Docling / PostgreSQL / Neo4j / Milvus/Qdrant** 是正式组成部分
- **PageIndex** 是树层正式候选/对照项
- **RAPTOR / HIRO / Psi-RAG / GraphRAG / KAG / CogitoRAG / EvidenceNet / MC-indexing** 主要提供的是方法论和局部设计参考

---

## 6. 为什么后面看起来“把 LlamaIndex 去掉了”

这点必须明确，不然你会一直觉得路线图跑偏。

### 原路线图说的是
- **LlamaIndex-first**

### 后来验证线里做的是
- 自定义 Python / FastAPI / PostgreSQL / Neo4j / pgvector 内核

### 为什么会这样
为了：
- 更快闭环
- 更容易做 TDD
- 更快验证 `provenance / span / version` 主干

所以执行时就把很多本该由 LlamaIndex 承接的层，先自己写了一个验证实现。

### 这个验证实现的正确定位
它不是最终实现，而是：
- 参考实现
- 架构验证器
- 行为基线

### 正式目标线不应该继续走它
所以现在要明确：

> **验证线证明“能跑”，目标线负责“回归到 LlamaIndex-first 正式实现”。**

---

## 7. 真实项目第一部分应该怎么做

这部分现在最重要。

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

### 第一阶段范围（In Scope）
- 正式项目骨架
- 接入：
  - `VectorStoreIndex`
  - `HierarchicalNodeParser`
  - `AutoMergingRetriever`
  - `DoclingReader`
  - `DoclingNodeParser`
- 继续沿用 PostgreSQL registry 主干
- 把现在验证线里的：
  - `vector_path`
  - `tree_path`
 迁移成 LlamaIndex 原生执行逻辑

### 第一阶段明确不做（Out of Scope）
1. 继续扩展 `verification/`
2. 复杂 graph runtime 完整迁移
3. Deep Hybrid 全链一次落地
4. 高级 hit distribution 策略优化
5. 学习型 reranker / cross-encoder
6. 部署、监控、CI 完整化

### 第一阶段建议顺序
#### Step 0：定正式实现目录
- `verification/` 继续只保留验证实现
- 正式实现新开目录，比如：`app/`

#### Step 1：接 LlamaIndex 依赖和最小运行骨架
- 接 `VectorStoreIndex`
- 接 `HierarchicalNodeParser`
- 接 `DoclingReader`

#### Step 2：把解析链迁移到正式主线
- 原文 -> Docling -> spans
- spans 继续写 PostgreSQL registry

#### Step 3：做 LlamaIndex 版 Vector Path
- 用 `VectorStoreIndex` 替代现在纯自定义 vector 执行主链

#### Step 4：做 LlamaIndex 版 Tree Path
- 用 `HierarchicalNodeParser`
- 用 `AutoMergingRetriever`

#### Step 5：定义 Graph 接入点
- 不要求图全打通
- 但把 `PropertyGraphIndex + Neo4jPropertyGraphStore` 的接口位置定下来

### 第一阶段成功标准
如果下面这些做到，就算第一阶段成功：
1. 正式实现目录建立
2. LlamaIndex 已接入项目
3. Docling + PostgreSQL registry 主链打通
4. LlamaIndex 原生 vector path 可跑
5. LlamaIndex 原生 tree rollup 可跑
6. 不再继续依赖 `verification/` 作为正式实现主线

---

## 8. 你现在到底该看哪几份

如果你现在只想看一条清楚的主线，就按这个顺序看：

1. `docs/README.md`
2. `docs/architecture/LLAMAINDEX-TARGET-ARCHITECTURE.md`
3. `docs/architecture/PROJECT-COMBINATION-MAP.md`
4. `docs/architecture/LLAMAINDEX-PHASE-1-PLAN.md`
5. `docs/architecture/decision-llamaindex-first.md`
6. `docs/diagrams/final-architecture-diagram.html`

---

## 9. 最终审查结论

### 现在的状态
- **最终架构：清楚**
- **项目组合来源：清楚**
- **第一部分正式计划：清楚**
- **验证实现线：也被清楚标记为辅助线**

### 当前应该做的事
不要再继续把 `verification/` 当正式项目扩下去。  
真正的下一步应该是：

> **按 `LlamaIndex-first` 主线，重新搭正式实现目录，并把验证过的思路迁移回 LlamaIndex 原生能力。**

---

## 10. 一句话最终结论

> **最终系统不是“一个项目”，而是一个组合架构。**  
> **其中 LlamaIndex 是主底座，Docling / PostgreSQL / Neo4j / Milvus/Qdrant 是正式组成部分，RAPTOR / HIRO / Psi-RAG / GraphRAG / KAG / CogitoRAG / EvidenceNet 等提供的是方法论和局部设计参考。**

> **验证线已经证明这条路线能跑，但正式项目主线现在应该明确回到 `LlamaIndex-first`。**