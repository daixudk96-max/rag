# 项目组合映射总表

## 这份文档解决什么问题

这份文档专门回答：

> **最终目标架构里，到底是从哪个项目吸收了哪个部分？**

它的目的就是把：
- 搜索研究结果
- 架构路线图
- 最终目标设计

重新接起来，避免只剩“结论”而看不到“来源”。

---

## 一、最终目标不是单一项目，而是组合架构

最终目标是：

> **LlamaIndex-first 的多视图 RAG / Agentic RAG 系统**

但它不是完全只靠 LlamaIndex 一家完成，而是：
- 用 **LlamaIndex** 做主编排层
- 用 **Docling** 做解析层
- 用 **PostgreSQL** 做 registry / provenance / versioning 主干
- 用 **Neo4j** 做 graph layer
- 用 **Milvus / Qdrant** 做正式 vector layer（目标态）
- 同时借鉴多个开源项目的思想来补齐策略层

也就是说：

> **LlamaIndex 是主底座，但不是唯一来源。**

---

## 二、项目组合总表（目标架构）

| 项目 / 方向 | 在最终目标架构中的角色 | 吸收的具体部分 | 状态 |
|---|---|---|---|
| **LlamaIndex** | 主编排层 / 主底座 | `VectorStoreIndex`、`PropertyGraphIndex`、`HierarchicalNodeParser`、`AutoMergingRetriever`、`Workflow`、`ReActAgent`、Tool 封装 | **主采用** |
| **Docling** | 解析层 | 一次解析、保留 `page_no` / `headings` / 结构元数据、作为 canonical spans 的生成输入 | **主采用** |
| **PostgreSQL** | Source of truth | `doc_id / version_id / span_id` 主干、registry / mapping / provenance / keyword path / pgvector（PoC） | **主采用** |
| **Neo4j** | 图层执行 | Entity / Relation / Evidence link 的图遍历与图查询 | **主采用（目标态）** |
| **Milvus / Qdrant** | 正式向量层 | 独立向量检索后端、metadata filtering | **主采用（目标态）** |
| **pgvector** | 轻量向量层 | PoC 阶段的 vector path 与最小语义检索 | **PoC 采用** |
| **PageIndex** | 树状知识库正式候选 / 对照项 | 文档目录树、页级回溯、结构化逐层定位；适合对照 Tree Layer 是否要走数据库型树索引 | **正式候选（需二次评估）** |
| **RAPTOR** | 树检索思想补件 | coarse-to-fine、树化检索思路 | **借鉴** |
| **HIRO** | 树评分 / 剪枝思想补件 | branch pruning、层级评分参考 | **借鉴** |
| **Psi-RAG** | 多粒度树检索与扩展参考 | Tree-based multi-granular retrieval、复杂扩展思路 | **借鉴** |
| **Haystack** | 回并机制参考 | `HierarchicalDocumentSplitter`、`AutoMergingRetriever` 的模式参考 | **借鉴** |
| **LangChain ParentDocumentRetriever** | Parent-Child 检索参考 | child retrieval + parent context 结构 | **借鉴** |
| **Chonkie** | chunking-only 参考 | 更丰富的 chunking strategy / overlap refinery | **可选借鉴** |
| **KAG** | KG+逻辑求解思路参考 | `mutual indexing`、逻辑求解器思想 | **借鉴，不作为主底座** |
| **LightRAG** | 图+文本索引参考 | graph-enhanced text indexing、增量更新思路 | **借鉴** |
| **Microsoft GraphRAG** | mapping tables 参考 | `documents / text_units / entities / relationships` 的映射表思想 | **借鉴** |
| **CogitoRAG** | 证据载体参考 | evidence carrier / provenance-preserving passage | **借鉴** |
| **EvidenceNet** | 证据主对象参考 | `evidence_id` 作为稳定引用对象的思想 | **借鉴** |
| **MC-indexing** | multi-view indexing 参考 | 同一源内容派生 raw / keyword / summary 多视图 | **借鉴** |

---

## 三、按系统层拆开看：每一层到底借了谁

## 1. Parsing / Ingestion 层

### 主采用
- **Docling**

### 借鉴
- **Chonkie**：如果后面要加强 chunking 策略，可借鉴 chunking-only 能力
- **LlamaIndex SemanticSplitter**：如果后续需要更强语义切片，可接入

### 当前定论
Parsing 层不是 LlamaIndex 独占，
而是：

> **Docling 做解析，LlamaIndex 消费解析结果。**

---

## 2. Registry / Provenance 层

### 主采用
- **PostgreSQL**

### 借鉴
- **GraphRAG**：mapping tables 思路
- **EvidenceNet / CogitoRAG**：evidence 作为稳定引用对象的思路
- **W3C PROV**：`wasDerivedFrom` / `wasRevisionOf` 的概念语义

### 当前定论
这个层不是来自某个现成 RAG 框架，
而是结合：
- PostgreSQL
- GraphRAG 映射表思想
- provenance / evidence-centric 思想

形成的：

> **versioned provenance mapping layer**

---

## 3. Vector 层

### 主采用（目标态）
- **LlamaIndex `VectorStoreIndex`**
- 后端：**Milvus / Qdrant**

### PoC 采用
- **pgvector**

### 借鉴
- **LlamaIndex metadata filtering**
- **LightRAG / vector-graph-rag**：图/向量联合检索的一些实现启发

### 当前定论
最终不是“自定义 vector path”，而是：

> **LlamaIndex 主编排 + 独立向量后端**

---

## 4. Tree / Hierarchy 层

### 主采用
- **LlamaIndex `HierarchicalNodeParser`**
- **LlamaIndex `AutoMergingRetriever`**

### 借鉴
- **RAPTOR**：树化检索
- **HIRO**：分支剪枝
- **Haystack**：层级文档拆分与自动回并
- **LangChain ParentDocumentRetriever**：child→parent 模式

### 当前定论
树层在目标态目前更偏向：

> **A 方向：LlamaIndex 原生 Tree 组件**

也就是：
- `HierarchicalNodeParser`
- `AutoMergingRetriever`

但这不代表 `PageIndex` 被排除。更准确的表述应该是：

> **B 方向：PageIndex 作为树状知识库 / 数据库型目录树索引的正式对照候选。**

所以当前结论不是“只有 LlamaIndex 树层”，而是：
- 正式主线先按 A 方向推进
- `PageIndex` 作为明确的树层对照项保留，后续可以做二次评估或并行比较
- 不再继续扩展验证实现里的 `tree_path` 作为正式主线

---

## 5. Graph 层

### 主采用
- **LlamaIndex `PropertyGraphIndex`**
- **Neo4jPropertyGraphStore**
- **Neo4j**

### 借鉴
- **KAG**：schema / logical reasoning 思想
- **GraphRAG**：text unit ↔ entity 映射思想
- **Neo4j LLM Graph Builder**：document/chunk/entity 三层统一到底层图的模式

### 当前定论
图层不是自己重新发明图数据库，
而是：

> **LlamaIndex 负责图编排，Neo4j 负责图执行。**

---

## 6. Hybrid / Strategy 层

### 主采用
- **LlamaIndex 自定义 retriever / workflow / agent 扩展点**

### 借鉴
- **Psi-RAG**：多粒度树扩展
- **RAPTOR / HIRO**：层级扩展与树评分
- **HitDistributionAnalyzer**：来自我们基于这些思路归纳出的自定义层
- **Reranker**：本地轻量 RRF 先做，后续可升级更强重排

### 当前定论
这层是最需要自定义的，
不是任何一个现成项目能直接给你的。

也就是说：

> **LlamaIndex 提供骨架，策略层由你自己实现。**

---

## 四、为什么后面会“看起来像把 LlamaIndex 去掉了”

这是执行时跑偏造成的。

### 原路线图说的是
- **LlamaIndex-first**

### 后来验证线里做的是
- 自定义 Python / FastAPI / PostgreSQL / Neo4j / pgvector 内核

### 原因
为了：
- 更快闭环
- 更容易做 TDD
- 更快验证 provenance / span / version 主干

所以执行时就把很多本来应该由 LlamaIndex 承接的层，先自己写了一个验证实现。

### 这个验证实现的正确定位
它不是最终实现，
而是：

- 参考实现
- 架构验证器
- 行为基线

### 正式目标线不应该继续走它
所以现在要明确：

> **验证线证明“能跑”，目标线负责“回归到 LlamaIndex-first 正式实现”。**

---

## 五、最关键的纠偏结论

### 现在不应该再问：
“这些模块有没有？”

### 而应该问：
“这些模块在正式实现里到底是：
- 保留自定义
- 还是换回 LlamaIndex 原生？”

### 当前判断
| 层 | 正式实现建议 |
|---|---|
| Parsing | Docling 保留 |
| Registry / Provenance | PostgreSQL 保留 |
| Vector | 换回 LlamaIndex `VectorStoreIndex` |
| Tree | 换回 LlamaIndex `HierarchicalNodeParser` + `AutoMergingRetriever` |
| Graph | 换回 LlamaIndex `PropertyGraphIndex` + Neo4j store |
| Hybrid Strategy | 保留自定义策略层 |
| Reranker | 先保留轻量本地实现，后续可替换 |

---

## 六、你现在真正该怎么用这份文档

如果你要重新回到“真实项目主线”，这份文档就是桥：

### 它告诉你
1. 哪些项目真的进入最终架构
2. 哪些只是思想借鉴
3. 哪些代码是验证实现，不该继续扩成正式主线
4. 哪些层应该回归到 LlamaIndex 原生能力

---

## 七、一句话结论

> **最终系统不是“一个项目”，而是一个组合架构。**  
> **其中 LlamaIndex 是主底座，Docling / PostgreSQL / Neo4j / Milvus/Qdrant 是正式组成部分，RAPTOR / HIRO / Psi-RAG / GraphRAG / KAG / CogitoRAG / EvidenceNet 等提供的是方法论和局部设计参考。**