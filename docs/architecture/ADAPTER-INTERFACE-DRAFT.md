# Adapter Interface 设计稿

更新时间：2026-05-19

## 0. 目标

本设计稿定义 donor 项目兼容层接口，目标是：

- 保留本地 provenance-first runtime
- 允许接入 PageIndex / LightRAG / RAG-Anything 等 donor 项目
- 支持把“树内部向量分布统计”单独抽成一条 adapter lane
- 不改变对外 `QueryHit` / `query()` 契约

---

## 1. 稳定不变的本地契约

这些契约视为系统不可破坏边界：

- `doc_id`
- `version_id`
- `span_id`
- `chunk_id`
- `node_id`
- `entity_id`
- `relation_id`
- `evidence_id`
- `QueryHit`

### 设计原则

1. donor 不生成最终本地身份
2. donor 不直接拥有最终 storage
3. donor 输出必须可映射回本地 ID
4. provenance 永远由本地 registry 负责落地

---

## 2. 标准命中结构

## 2.1 BackendHit

```python
class BackendHit(TypedDict):
    score: float | None
    text_preview: str
    heading_path: str | None
    page_no: int | None
    span_ids: list[UUID]
    node_id: UUID | None
    chunk_id: UUID | None
    entity_id: UUID | None
    relation_id: UUID | None
```
```

说明：

- tree / vector / graph donor 都应该先被适配成 `BackendHit`
- `entrypoints/query.py` 再统一把它映射成 `QueryHit`

---

## 3. TreeBackendAdapter

```python
class TreeBackendAdapter(Protocol):
    def index_tree(
        self,
        *,
        source_path: Path,
        version_id: UUID,
        registry: Any,
    ) -> None: ...

    def retrieve_tree_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int,
    ) -> list[BackendHit]: ...
```

### 语义

- `index_tree(...)`：把 donor-native tree 结果落回本地 `tree_nodes/tree_node_spans`
- `retrieve_tree_hits(...)`：返回统一命中结构

### PageIndex 适配要求

PageIndex 是 page-level tree，因此 adapter 必须补一层：

```text
PageIndex page/node
 -> page range
 -> canonical spans by page_no
 -> tree_node_spans
```

### 不可绕过

- 不可直接返回 donor-native page/node 结构给上层
- 必须落回本地 `node_id/span_ids`

---

## 4. GraphExtractionAdapter

```python
class GraphExtractionAdapter(Protocol):
    def extract_graph_artifacts(
        self,
        *,
        source_path: Path | None,
        version_id: UUID,
        registry: Any,
    ) -> None: ...
```

### 语义

这个 adapter 的职责不是“拥有图数据库”，而是把 donor 项目的抽取/merge 逻辑转成：

- `entities`
- `relations`
- `evidence_links`

### 必须满足

- 最终写入本地 registry
- `evidence_links` 必须能锚到 `span_id`
- 不允许 donor-native chunk/page identity 直接跳过本地 provenance

---

## 4a. LlamaIndex Unified LLM Integration

### 目标

当 donor 需要最小 LLM 能力时（例如 PageIndex 的 structural TOC detection），
统一通过 **LlamaIndex 的 LLM 抽象层** 接入，而不是在 donor 内部散落多套模型配置。

### 设计原则

1. 不单独再造一套 project-specific LLM 抽象层
2. donor 不拥有独立的 LLM 配置主权
3. donor 通过本地 runtime 提供的 LlamaIndex LLM 入口拿模型
4. 允许 **minimal LLM for structural extraction only**
5. 不允许 donor 把 LLM summary generation 变成默认主路径

### 建议接入点

- 本地配置层继续保留 provider/model 配置主权
- runtime 内部通过 LlamaIndex 统一 LLM 入口供给 donor adapter
- donor adapter 只依赖“可用的 LLM handle”，不直接管理 provider/api_key/base_url

### 适用 donor

- `PageIndexTreeAdapter`（真实文档 TOC / structural detection）
- 后续可能需要最小 LLM 抽取的 graph donor（若 graph 支线重开）

---

## 5. TreeSemanticDistributionAdapter

```python
class TreeSemanticDistributionAdapter(Protocol):
    def analyze_tree_semantic_distribution(
        self,
        *,
        version_id: UUID,
        registry: Any,
        limit: int | None = None,
    ) -> dict[str, Any]: ...
```

### 语义

这条 adapter **不直接召回答案**，而是统计：

- tree node 内部 embedding 分布
- tree node 之间的 semantic overlap / separation
- subtree 的语义浓度、离散度、异常点

### 推荐输出

```python
{
    "node_stats": [
        {
            "node_id": UUID(...),
            "span_ids": [...],
            "chunk_ids": [...],
            "centroid": [...],
            "dispersion": 0.23,
            "entropy": 0.81,
            "support_count": 12,
        }
    ],
    "tree_signals": {...},
}
```

### 与现有 analyzer 的关系

- 现有 `HitDistributionAnalyzer` = 已召回 hits 在树上的分布
- 新 `TreeSemanticDistributionAdapter` = 整棵树内 embedding 分布

### donor 文件级映射建议

- `Psi-RAG/src/tree_retriever.py:68-124`
  - 借：coarse-to-fine traversal skeleton
  - 不借：原始 threshold 语义
- `Psi-RAG/src/utils.py:23-50`
  - 借：`Node` / `Tree` 组织方式
  - 不借：最终身份体系（本地仍保留 `node_id/span_ids`）
- `Psi-RAG/src/utils.py:347-353`
  - 借：prototype/centroid 思路
  - 不借：直接作为最终 subtree stats 结果
- `HIRO/raptor/tree_retriever.py:240-256`
  - 借：`evaluate_children()` 递归 decision skeleton
  - 不借：distance-based 阈值判断本身
- `HIRO/raptor/tree_retriever.py:49-59`
  - 借：absolute + delta 双门槛参数结构
  - 不借：具体默认阈值语义
- `RAPTOR/raptor/cluster_tree_builder.py:54-150`
  - 借：cluster-tree build 备选思路
  - 不借：直接替代本地 provenance tree
- `PageIndex/pageindex/page_index_md.py:243-299`
  - 借：page/TOC tree build
  - 不借：把 page identity 直接当 `span_id`

### 设计结论

- `TreeSemanticDistributionAdapter` 的 **producer** 侧，更适合借 `Psi-RAG` 的 tree/node/vector primitives
- `TreeSemanticDistributionAdapter` 的 **decision** 侧，更适合借 `HIRO` 的递归 decision skeleton
- `PageIndex` 更适合留在 `TreeBackendAdapter` 线上
- `LightRAG` / `RAG-Anything` 当前不进入 tree-internal vector distribution 主线

---

## 6. GraphRetrievalAdapter

```python
class GraphRetrievalAdapter(Protocol):
    def retrieve_graph_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int,
    ) -> list[BackendHit]: ...
```

### 语义

- 允许 donor 项目做 graph-only 或 graph+text retrieval
- 但返回仍要转成本地统一命中结构
- 当前这条线视为备选，不作为 tree/vector distribution 的前置条件

### 与本地 graph query 的关系

- 当前 `llamaindex_runtime/graph/query.py` 是 Neo4j neighbor query
- 未来可在 `hybrid` 中增设 donor graph adapter path
- 但对外 `query(mode="graph")` 或 `query(mode="hybrid")` 的 `QueryHit` 形状不改

---

## 7. OptionalMultimodalAdapter

```python
class OptionalMultimodalAdapter(Protocol):
    def enrich_query_context(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,
        limit: int,
    ) -> list[BackendHit]: ...
```

### 语义

给 RAG-Anything 预留位置。

注意：

- 它不是 LightRAG core 替代者
- 只是 multimodal enhancement layer
- 它只能增强 query/context，不能夺走 provenance 主权

---

## 7. RAG-Anything 放在哪一层

RAG-Anything 不应替代 Tree adapter，也不应替代 LightRAG core。

它应该放在：

- **Layer 3 / OptionalMultimodalAdapter 层**

职责：

- multimodal parsing 增强
- VLM-enhanced query
- multimodal context assembly

不负责：

- 最终 provenance ID
- tree 主结构来源
- graph/vector 主 donor 逻辑

---

## 8. 本地写回规则

所有 donor adapter 的输出，必须最终写回本地这些表：

- `documents`
- `document_versions`
- `canonical_spans`
- `vector_chunks`
- `vector_chunk_spans`
- `tree_nodes`
- `tree_node_spans`
- `entities`
- `relations`
- `evidence_links`

### 写回规则

1. donor 不生成最终 `span_id`
2. donor 不直接决定最终 `entity_id`
3. donor 产生的 node/page/chunk/entity/relation 必须映射进本地身份体系
4. 本地 registry 是唯一真正落库入口

---

## 9. Query 层集成规则

`entrypoints/query.py` 保持 façade 地位。

### 当前推荐路由

- `keyword`：继续本地
- `vector`：继续本地 / backend seam
- `tree`：`TreeBackendAdapter`
- `graph`：本地 graph query 或 `GraphRetrievalAdapter`
- `hybrid`：本地 orchestrator，接多个 adapter path
- `auto`：继续 classifier + route

---

## 10. 失败模式清单

### 1. provenance 丢失
外部 donor 结果无法稳定映射回 `span_id`

### 2. version 泄漏
不同版本结果混在一起，破坏 `version_id` 语义

### 3. evidence 断链
图结果有 entity/relation，但没有 `evidence_links`

### 4. id collision
外部 donor 的内部 id 与本地 id 混用

### 5. façade 泄漏
上层 `query()` 直接依赖 donor-native 返回结构

---

## 11. 先做什么

推荐第一刀：

1. 定义 `TreeBackendAdapter`
2. 做 `PageIndexTreeAdapter` 最小 PoC
3. 验证 page-range → `span_id` 映射质量

推荐第二刀：

1. 定义 `GraphExtractionAdapter`
2. 做 `LightRAGExtractionAdapter` 最小 PoC
3. 验证 entity/relation/evidence 写回质量

推荐第三刀：

1. 定义 `OptionalMultimodalAdapter`
2. 只在前两刀稳定后，再接 `RAG-Anything`
