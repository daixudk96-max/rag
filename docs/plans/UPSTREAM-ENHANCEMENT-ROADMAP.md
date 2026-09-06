# 上游项目对照后的增强路线图

> **2026-05-19 关闭说明**
> 这份路线图已按当前项目的设计意图完成一次完整收口：代码、测试、数据库后端能力与文档状态已经重新对齐。
> 当前实现已覆盖本项目选择吸收的实用增强切片，包括：Qdrant / Milvus 向量后端、GraphRAG 基础模型与 mapping enrichment、LightRAG 风格 doc status / incremental orchestrator / extraction callbacks、EvidenceNet evidence object / dedup / configurable scoring / ranking、KAG schema / constraint / mutual indexing / minimal solver 基础层。
> 文中后续仍提到的 donor 能力，应视为**可选未来探索项**，而不是当前版本的 blocking gap。

生成时间：2026-05-17  
范围：基于 `docs/PROJECT-FREEZE.md` 与 `docs/architecture/PROJECT-COMBINATION-MAP.md` 中列出的主采用 / 候选 / donor 项目，对当前 `formal runtime` 做源码级或论文级对照后，整理出的增强路线图。

兼容层后续路线见：
- `docs/plans/COMPATIBILITY-ADAPTER-ROADMAP.md`
- `docs/architecture/ADAPTER-INTERFACE-DRAFT.md`

---

# 0. 结论先说

当前项目已经把**正式主线骨架**做出来了：

- Parse / canonical spans
- Version / provenance
- Tree persistence + rollup
- Vector persistence + provenance link
- KG registry + graph projection
- keyword / vector / tree / graph / hybrid
- hit-distribution / expansion decision / candidate fusion / minimal rerank

所以现在的重点不再是“有没有主线”，而是：

> **按上游项目的能力对照，决定下一步该补哪些增强能力。**

这些增强能力里，有些是**正式组成部分尚未落地**，有些是**候选能力尚未评估**，有些是**donor 项目的高级特性尚未实现**。

---

# 1. 对照方法说明

本路线图基于三类对照来源：

## 1.1 源码级对照

已下载并对照的上游源码位于：

- `C:\Users\daixu\Downloads\rag-upstreams\`

已做源码级对照的项目：

- LlamaIndex
- Docling
- PostgreSQL
- Neo4j
- pgvector
- Milvus
- Qdrant
- PageIndex
- RAPTOR
- HIRO
- Psi-RAG
- Haystack
- LangChain ParentDocumentRetriever
- Chonkie
- KAG
- LightRAG
- Microsoft GraphRAG
- EvidenceNet

## 1.2 论文 / 文档级对照

以下项目没有拿到稳定、明确、可直接 clone 的官方代码仓库，因此只做论文 / 文档级能力对照：

- CogitoRAG
- MC-indexing

## 1.3 当前 formal runtime 对照基线

当前本地正式实现主要位于：

- `llamaindex_runtime/`
- `tests/llamaindex_runtime/`

---

# 2. 项目对照总表

| 项目 | 当前对照结论 | 当前状态 |
|---|---|---|
| LlamaIndex | 数据平面已接上，控制平面未接 | **部分实现** |
| Docling | 一次解析主线已接上，结构元数据保留不完整 | **部分实现** |
| PostgreSQL | registry / provenance / versioning 主干已完成 | **已实现** |
| Neo4j | KG projection 与基础 graph query 已有，复杂图检索未做 | **部分实现** |
| pgvector | PoC 向量层已实现 | **已实现** |
| Milvus / Qdrant | 目标态向量后端尚未落地 | **未实现** |
| PageIndex | 数据库型树索引已部分接近，但页级校验与目录树深能力未做 | **部分实现** |
| RAPTOR | 树持久化与回卷有了，但聚类树 / summary tree 未做 | **部分实现** |
| HIRO | 树层存在，但 branch pruning / hierarchical scoring 未做 | **部分实现** |
| Psi-RAG | 多路径和 expansion 雏形已有，但真正多粒度树检索未做 | **部分实现** |
| Haystack | 类似 hierarchical split / auto-merge 能力已有，但非 Haystack-native 实现 | **部分实现** |
| LangChain ParentDocumentRetriever | child→parent 检索目标已实现，双存储/元数据细节未做 | **部分实现** |
| Chonkie | chunking/refinery 高级能力基本都没做 | **未实现** |
| KAG | 轻量 KG trace、schema/constraint、mutual indexing 与 minimal solver 基础层已做 | **已实现当前吸收切片** |
| LightRAG | graph/text 主干、version、doc status / incremental orchestrator / extraction callbacks 已做 | **已实现当前吸收切片** |
| Microsoft GraphRAG | mapping-table 思想部分实现，rich text_unit/community 模型未做 | **部分实现** |
| CogitoRAG | evidence carrier / provenance-preserving passage 思想已落实 | **已实现其被引用的核心思想** |
| EvidenceNet | evidence object / `evidence_id` / dedup / basic scoring / ranking / configurable scoring policy 已做 | **已实现当前吸收切片** |
| MC-indexing | raw 有，query-time keyword 有，独立 summary index 未做 | **部分实现** |

---

# 3. 增强路线优先级

下面按**价值 / 落地难度 / 与当前主线一致性**来排优先级。

> 说明：以下 P1-P5 在当前文档里保留的是 donor 对照与未来增强方向。
> 对于当前版本的设计闭环，它们不再作为“必须全部实现才算主线完成”的阻塞项。

## P0 — 当前主线收口与稳定性

这部分已经基本完成，原则上不再扩范围。

保留的工作只包括：
- 小范围 bugfix
- 测试稳定性
- 文档收口

不再把 donor 特性回填成“主线未完成”。

---

## P1 — 正式向量后端落地

## 目标
把当前向量层从：
- 本地 / PoC / 轻量实现

推进到：
- 正式后端
- metadata filtering
- 可扩展的生产级向量存储

## 主要上游参考
- Milvus
- Qdrant
- pgvector（现有基线）
- LlamaIndex VectorStoreIndex

## 当前状态
- `VectorStoreIndex` 已接上
- `vector_chunks` / `vector_chunk_spans` 已有
- `SentenceTransformers` 本地 embedding 已接上
- `pgvector` 仍是默认基线
- `Qdrant` / `Milvus` adapter、backend round-trip 与查询 canary 已有实现和测试覆盖

## 建议切片
1. 补齐三套后端（`pgvector` / `Qdrant` / `Milvus`）的运维与使用文档
2. 补更强的 metadata filtering / live canary 覆盖
3. 保持当前 `pgvector` 作为本地 baseline / fallback

## 价值
这是当前最实用、最贴近真实应用价值的一刀。

---

## P2 — LlamaIndex 控制平面落地

## 目标
把当前已经存在的 retrieval/data plane，提升到真正的 LlamaIndex-first orchestration：

- Workflow
- ReActAgent
- tool-facing orchestration

## 主要上游参考
- LlamaIndex Workflow
- LlamaIndex ReActAgent

## 当前状态
- 数据平面已实现：vector/tree/graph/query/hybrid
- 控制平面几乎没接

## 建议切片
1. 定义统一检索工作流
2. 把当前 `query()` 路由器升级成可 workflow 化节点
3. 后续再接 `ReActAgent`

## 价值
这一步能把“很多功能模块”变成“真正可编排系统”。

---

## P3 — Tree 层增强

## 目标
在当前 persisted tree / rollup 基础上，补上更强树层能力。

## 主要上游参考
- PageIndex
- RAPTOR
- HIRO
- Psi-RAG
- Haystack
- LangChain ParentDocumentRetriever

## 当前状态
当前已经有：
- `tree_nodes`
- `tree_node_spans`
- `rollup_chain`
- `AutoMergingRetriever`

当前缺失：
- PageIndex 式页级校验
- RAPTOR 的聚类树 / summary tree
- HIRO 的 branch pruning / 层级评分
- Psi-RAG 的多粒度扩展

## 建议切片顺序
1. **PageIndex 对照评估切片**
   - 决定是否要引入“数据库型目录树索引”作为树层正式分支
2. **summary_text 落地切片**
   - 先让树节点不再全是 `summary_text = None`
3. **branch pruning / tree scoring 切片**
   - 借鉴 HIRO / RAPTOR
4. **multi-granular expansion 切片**
   - 借鉴 Psi-RAG

## 价值
这是把“能回卷”升级成“树层真的变强”的关键。

---

## P4 — KG 层增强

## 目标
把当前 KG registry + graph projection，从“骨架可用”提升到“结构更丰富、约束更强”。

## 主要上游参考
- KAG
- LightRAG
- Microsoft GraphRAG
- EvidenceNet
- CogitoRAG

## 当前状态
已有：
- entities / relations / evidence_links
- chunk_entity_links / node_entity_links（含基础 extraction metadata）
- graph projection
- graph query
- span_id evidence binding
- schema / constraint / mutual indexing / minimal solver 基础层（KAG）
- processing status / incremental orchestrator / extraction callbacks（LightRAG）
- evidence object / `evidence_id` / dedup / configurable scoring / ranking（EvidenceNet）

当前关闭状态：
- 当前吸收切片已全部实现并验证通过
- 后续若继续推进，只保留研究型 donor 深化，不再作为主路线图缺口

后续研究方向：
1. **GraphRAG richer text-unit layer**
   - 补更重的 text_unit / community 模型
2. **KAG heavier logical solver / DSL**
   - 在已实现 minimal solver 之上继续增强

## 价值
这一步能把 KG 从“图里有点东西”升级成“可控、可解释、可扩的知识层”。

---

## P5 — Chunking / Multi-view indexing 增强

## 目标
补上 donor 项目里最缺的 chunking 与 multi-view indexing 能力。

## 主要上游参考
- Chonkie
- MC-indexing
- CogitoRAG（evidence-preserving passage）

## 当前状态
- raw text / spans 已有
- query-time keyword path 已有
- summary view 没有形成独立索引
- chunker 很轻量

## 建议切片顺序
1. **summary index slice**
   - 把 MC-indexing 的 raw / keyword / summary 三视图补齐
2. **chunking strategy slice**
   - 先引入一到两种更强 chunking
   - 不需要把 Chonkie 全部能力都搬进来
3. **overlap / embeddings refinery slice**
   - 若效果需要，再逐步加

## 价值
这是把“能检索”升级成“更聪明地索引和切分”的关键。

---

## P6 — 真正生产化

## 目标
把已经成型的主线变成可交付系统。

## 包括
- API / CLI / Tool 统一发布面
- workflow / orchestration 收口
- 部署 / 监控 / 运维硬化
- 评测集 / 回归基准
- 性能预算

这部分不是 donor 对照主导，而是产品化主导。

---

# 4. 建议执行顺序

## 推荐顺序
1. **Qdrant / Milvus 正式向量后端**
2. **LlamaIndex Workflow / ReActAgent 控制平面**
3. **Tree 层增强（先 PageIndex 对照，再 summary / pruning）**
4. **KG enrichment（GraphRAG / LightRAG / EvidenceNet / KAG）**
5. **MC-indexing / Chonkie / multi-view & chunking 增强**
6. **生产化收口**

---

# 5. 你现在怎么用这份路线图

如果你的问题是：

> “我们把 donor/candidate 项目真正看完后，下一步优先干什么？”

答案就是：

## 立刻值得做的
- **正式向量后端（Qdrant / Milvus）**
- **LlamaIndex 控制平面（Workflow / ReActAgent）**

## 中期增强
- **PageIndex 对照树层**
- **GraphRAG / LightRAG / EvidenceNet / KAG 的 KG 增强**
- **MC-indexing / Chonkie 的多视图和 chunking 增强**

## 一句话总结

> **主线已经做出来了，后面要做的是：把目标态主采用项目真正落地，把 donor 项目的增强能力按优先级一层层吸收进来。**
