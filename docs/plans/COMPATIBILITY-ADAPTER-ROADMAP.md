# 兼容层路线图（PageIndex / LightRAG / RAG-Anything）

更新时间：2026-05-19

## 0. 目标

目标不是替换本地 formal runtime 的 provenance 主干，而是：

1. 保留本地 source-of-truth 与可追溯契约
2. 用 donor 项目的更强内部逻辑替换当前较弱的 tree / tree-internal semantic distribution / graph 内部逻辑
3. 把 `tree retrieval`、`tree-internal vector distribution`、`graph retrieval` 拆成独立链路，而不是强行做 graph/vector 二合一 donor 替代
4. 继续把 LlamaIndex 保持为统一 façade / orchestration 层，而不是 donor 逻辑重写层

---

## 1. 不可动的本地契约

以下契约必须保持本地实现拥有主权：

- `doc_id`
- `version_id`
- `span_id`
- `chunk_id`
- `node_id`
- `entity_id`
- `relation_id`
- `evidence_id`
- `QueryHit`
- PostgreSQL registry 作为 provenance / version / evidence 的 source-of-truth

外部 donor 项目可以接管内部树构建、图抽取、图检索、图文融合、排序等逻辑，
但不能直接替代这些本地身份体系。

---

## 2. donor 项目结论

| donor | 代码级结论 | 适合放在哪一层 | 是否推荐 |
|---|---|---|---|
| PageIndex | 真正提供 page-level / TOC-like 树构建与树检索能力，但缺少 span-level provenance | Tree backend adapter 层 | 推荐 |
| LightRAG | 真正提供 graph/text 一体化抽取、merge、graph retrieval 逻辑，但不是 provenance-first；当前先保留为 graph 备选支线，不作为下一刀默认方案 | Graph / extraction adapter 备选层 | 有条件推荐 |
| RAG-Anything | 代码上是构建在 LightRAG 之上的 multimodal 层，不是 LightRAG core 的替代者；不能单独解决 tree/vector/graph 主问题 | Multimodal enhancement 层（在 LightRAG 之上） | 条件性推荐 |
| Yuxi | 更像 KB / agent / middleware 编排平台，不是 tree / graph / provenance donor | 产品编排参考层 | 不推荐用于 runtime 兼容层 |

---

## 3. 分层架构

### Layer 0 — 本地 provenance / registry 主层

保留当前本地实现：

- `llamaindex_runtime/registry/contracts.py`
- `llamaindex_runtime/registry/postgres_adapter.py`
- 全部 migrations
- `evidence_links`, `tree_node_spans`, `vector_chunk_spans`

职责：

- 版本管理
- source-of-truth
- 证据锚定
- provenance traceability

### Layer 1 — Adapter seam 层

在本地 runtime 内定义 donor 兼容接口：

- `TreeBackendAdapter`
- `TreeSemanticDistributionAdapter`
- `GraphExtractionAdapter`
- `GraphRetrievalAdapter`
- `OptionalMultimodalAdapter`

职责：

- donor-native 结构 → 本地契约映射
- donor-native 命中 → `QueryHit` / backend-hit dict 映射
- donor-native page/chunk/node identity → `span_id/chunk_id/node_id/evidence_id` 映射
- donor-native tree/vector semantics → 本地 `node_id/span_ids/chunk_id` 统计输出映射

### Layer 2 — donor core logic 层

- Tree donor：**PageIndex**
- Tree-internal semantic distribution donor：**本地 vector provenance + 可选 donor tree semantics**
- Graph / extraction donor（备选支线）：**LightRAG**

职责：

- 更强树构建和树检索
- 树内部向量分布统计（节点内/节点间语义浓度、离散度、聚类倾向）
- 更强 entity/relation extraction（如果后续重开 graph 支线）
- 更强 graph-aware retrieval / graph+text fusion（如果后续重开 graph 支线）

### Layer 3 — optional multimodal enhancement 层

- **RAG-Anything**

职责：

- image/table/equation 等 multimodal 处理
- VLM-enhanced query
- multimodal context assembly

> 结论：RAG-Anything 不应替代 LightRAG core。
> 它应当作为 Layer 3，可选地叠加在 LightRAG donor 之上。

### Layer 4 — façade / orchestration 层

继续保留：

- `llamaindex_runtime/entrypoints/query.py`
- `llamaindex_runtime/agent/retrieval_tool.py`
- `llamaindex_runtime/workflow/hybrid_retrieval_workflow.py`

职责：

- 统一调用入口
- mode 路由
- hybrid 编排
- 对外稳定 API

---

## 4. 本地 seam 定位

### Tree seam

核心文件：

- `llamaindex_runtime/tree/runtime.py`
- `llamaindex_runtime/tree/query.py`
- `llamaindex_runtime/entrypoints/query.py`
- `llamaindex_runtime/registry/tree_generator.py`

现状：

- 已存在 persisted tree backend path
- 适合作为 `TreeBackendAdapter` 的落点
- 目前 persisted tree 对弱结构文档容易 root 化，需要 donor tree build 逻辑增强

### Tree-internal vector distribution seam

核心文件：

- `llamaindex_runtime/vector/loader.py`
- `llamaindex_runtime/registry/postgres_adapter.py` (`query_vector_chunks_by_version`, `query_vector_chunk_spans_by_version`, `query_tree_node_spans_by_version`)
- `llamaindex_runtime/analysis/analyzer.py`
- `tests/llamaindex_runtime/test_hit_distribution.py`

现状：

- 已有 `vector_chunks -> span_ids` 映射
- 已有 `tree_nodes -> span_ids` 映射
- 已有 `HitDistributionAnalyzer`，但它统计的是**召回 hit** 在树上的分布，不是**整棵树内向量语义分布**
- 因此需要一条独立的 `TreeSemanticDistributionAdapter` / analyzer lane

### Graph seam

核心文件：

- `llamaindex_runtime/processing/callbacks.py`
- `llamaindex_runtime/graph/projector.py`
- `llamaindex_runtime/graph/query.py`
- `llamaindex_runtime/entrypoints/query.py`

现状：

- 已存在 extraction callback 与 graph projection/query seam
- 适合作为 `LightRAGExtractionAdapter` / `LightRAGGraphRetrievalAdapter` 落点

### Vector seam

核心文件：

- `llamaindex_runtime/vector/backend.py`
- `llamaindex_runtime/vector/runtime.py`
- `llamaindex_runtime/vector/loader.py`

现状：

- `VectorBackend` seam 已成型
- 无需 donor 替换本地 provenance，保留为后端投影层即可

---

## 5. 构建与检索分离原则

这条主线必须明确分成两套逻辑：

### A. 构建阶段（build time）
目标：先把树长好。

职责：
- 文档结构识别
- 标题/目录/页级树构建
- node 与 span 的落库映射
- donor 若需要最小 LLM，可在这一步使用统一 LlamaIndex LLM seam

当前 donor 候选：
- **PageIndex**（主）
- **RAPTOR**（结构参考）

### B. 检索阶段（query time）
目标：query 来了以后，尽量少用 LLM，主要靠 embedding 与树内统计来决定：
- 先从哪个父节点/子树开始
- 继续往下钻还是停在父节点
- 哪些 branch 直接剪掉

职责：
- query embedding
- node / subtree semantic distribution
- hotspot 头部定位
- branch decision（keep_parent / drill_down / prune）
- 返回可追溯的命中结果

当前 donor 候选：
- **Psi-RAG**（主 traversal / node representation donor）
- **HIRO**（主 decision donor）
- **RAPTOR**（cluster-tree / collapsed retrieval 参考）

### 结论
- **PageIndex 主要解决 build 问题，不应主导 tree-internal vector distribution decision**
- **TreeSemanticDistributionAdapter + TreeBranchDecisionPolicy 主要解决 retrieve 问题**
- baseline 目前是可用保底路径，不应被误当成最终理想方案

---

## 6. 路线图

## Phase A — 冻结 adapter contract

目标：先把 donor 可接入的边界定义清楚。

输出：

- `TreeBackendAdapter`
- `GraphExtractionAdapter`
- `GraphRetrievalAdapter`
- `OptionalMultimodalAdapter`
- provenance mapping rules

## Phase B — PageIndex tree build adapter PoC

目标：验证 PageIndex 是否能在不丢 provenance 的情况下增强当前 tree **构建阶段**，优先解决结构树质量问题，而不是直接接管 tree-internal vector distribution 决策。

做法：

1. 引入 `PageIndexTreeAdapter`
2. PageIndex page-level tree → 映射为本地 `tree_nodes`
3. page range → page_no → `canonical_spans` → `tree_node_spans`
4. donor 若需要结构化 TOC / 结构提取，可通过统一 LlamaIndex LLM seam 获取最小 LLM 能力
5. retrieval 结果如需暴露，统一映射为 backend-hit dict：
   - `node_id`
   - `score`
   - `text_preview`
   - `heading_path`
   - `span_ids`

成功标准：

- 比当前 root 化 persisted tree 更细
- 保留 `span_id` 级回原文能力
- build 侧 donor 不破坏本地 provenance 主权
- 不要求它接管最终 query-time decision layer

## Phase C — Tree-internal vector distribution lane

目标：把“向量表示语义”这条链独立出来，用它做 **query-time** 的树内部语义分布统计与热点子树选择，而不是直接把向量检索和 graph 两次召回绑死。

做法：

1. 引入 `TreeSemanticDistributionAdapter`
2. 输入：
   - `version_id`
   - `tree_nodes/tree_node_spans`
   - `vector_chunks/vector_chunk_spans`
   - embeddings（PostgreSQL / vector backend 二选一读取）
3. 输出：
   - 每个 `node_id` 的向量 centroid
   - 节点内 dispersion / entropy / variance
   - 节点间 semantic overlap / separation
   - subtree-level concentration signals
4. 与现有 `HitDistributionAnalyzer` 区分：
   - 现有 analyzer = **召回结果分布**
   - 新 lane = **整棵树内部向量分布**

成功标准：

- 不需要 graph 即可回答“树内部语义分布如何”
- 可对白盒输出每个 node 的向量统计
- 不破坏 `vector retrieval` 与 `tree retrieval` 原有路径

## Phase D — LlamaIndex Unified LLM Integration

目标：在 donor 需要最小 LLM 能力（例如结构化 TOC detection、轻量抽取）时，统一通过 LlamaIndex 的 LLM 抽象层接入，而不是让 donor 自己各配一套模型。

做法：

1. 明确本地 runtime 使用 LlamaIndex 的统一 LLM 入口（例如 `Settings.llm` 或统一工厂）
2. 让 donor adapter 只能通过这层获取 LLM
3. 允许 **minimal LLM for structural extraction only**，例如 TOC detection
4. 明确禁止：
   - donor 自己拥有独立 LLM 配置主权
   - donor 把 LLM summary generation 变成默认主路径
   - donor 直接绕过本地 adapter 调用任意模型

成功标准：

- donor 若需要 LLM 时，配置入口唯一
- PageIndex 的真实文档 structural parsing 可跑通
- 不新增第二套 project-specific LLM abstraction
- 仍保持本地 runtime 对模型配置的主导权

## Phase E — LightRAG extraction / retrieval adapter（备选支线）

目标：只有在 tree + tree-distribution 两条线跑通后，才重新评估是否需要 LightRAG 接管 graph/internal retrieval 逻辑。

做法：

1. 引入 `LightRAGExtractionAdapter`
2. 用 LightRAG 做 entity/relation extraction、merge、graph-text retrieval
3. 结果写回本地：
   - `entities`
   - `relations`
   - `evidence_links`
4. graph hits / graph-text hits 统一映射为 `QueryHit`

成功标准：

- transcript / weak-structure 文档不再只抽出 `concept:root`
- `graph` / `hybrid` 结果语义质量提升
- 仍保持 `version_id + span_id + evidence_id` 追溯能力

## Phase F — RAG-Anything optional multimodal layer

前提：Phase B / C（至少 tree adapter + tree-distribution lane）成功，且若采用 graph 支线，则 LightRAG adapter 成功。

做法：

- 不替代 LightRAG core
- 作为可选 `OptionalMultimodalAdapter`
- 只接 multimodal parsing / VLM-enhanced query / multimodal context assembly

成功标准：

- 不破坏本地 provenance
- multimodal retrieval 可以回落到本地 identity 契约

## Phase G — 对照评测与默认切换决策

同一批文档、同一批 query 比较：

- 当前 baseline
- PageIndex Tree adapter
- LightRAG Graph adapter
- 可选 RAG-Anything multimodal layer

指标：

- provenance integrity（是否还能回到 `span_id`）
- retrieval usefulness
- graph quality
- latency
- error rate

只有 donor adapter 在这些指标上稳定优于当前 baseline，才考虑切默认。

---

## 6. 风险与约束

### 最大风险

1. PageIndex 是 page-level，不是 span-level
2. LightRAG 不是 provenance-first
3. RAG-Anything 不是 LightRAG 替代者，而是其上层
4. donor-native identity 与本地 identity 冲突
5. 如果 adapter 越过本地 registry 写入，会直接破坏 traceability

### 硬约束

- donor 不拥有最终 ID 主权
- donor 不拥有最终 storage 主权
- donor 不允许绕开本地 `evidence_links`
- donor 结果必须能落回 `QueryHit`

---

## 7. 当前候选结论（本地仓库 + 本地 GitNexus 索引后）

**当前分拆策略：**

- `tree build / tree retrieval`：继续优先看 **PageIndex**
- `tree-internal vector distribution`：优先看 **Psi-RAG**，其次 **HIRO**，再其次 **RAPTOR**
- `graph / graph-text`：保留 **LightRAG** 作为备选支线
- `multimodal enhancement`：只把 **RAG-Anything** 放在 Layer 3 可选增强层

**推荐验证顺序：**

1. 先在独立实验目录里跑通 **Psi-RAG**，验证它的 distribution-adaptive tree / scoring / threshold 逻辑
2. 再用 **HIRO** 对照它的 branch pruning / recursive similarity scoring 是否更适合做决策层 donor
3. 再用 **RAPTOR** 对照 cluster-tree / collapsed-tree retrieval 是否更适合做 tree semantic structure donor
4. `PageIndexTreeAdapter` 单独作为 tree build / tree retrieve 方向的 PoC，不和 tree-internal vector distribution 混为一条线
5. `LightRAGExtractionAdapter / GraphRetrievalAdapter` 只有在 tree + tree-distribution 两条线稳定后，再作为 graph 支线重开
6. `RAG-Anything` 只在上述 donor 稳定后，再考虑叠加为 multimodal enhancement

**不推荐：**

- 直接让 `LightRAG` 承担 tree-internal vector distribution 主 donor
- 直接让 `RAG-Anything` 取代 `LightRAG` core
- 把 `tree retrieval`、`tree-internal vector distribution`、`graph retrieval` 三条链强行并成一条 donor 逻辑
- 直接让 donor 项目接管本地 provenance / registry
- 在 LlamaIndex 内重新抄写 donor 内部逻辑

### donor 文件级借鉴映射（当前结论）

| donor | donor 文件 | 建议借鉴内容 | 本地对应 seam | 借法 |
|---|---|---|---|---|
| **Psi-RAG** | `src/tree_retriever.py:68-124` | coarse-to-fine tree traversal 主循环 | `llamaindex_runtime/tree/runtime.py` / future `TreeSemanticDistributionAdapter` | **借遍历骨架**，不要直接照搬 threshold |
| **Psi-RAG** | `src/utils.py:23-50` | `Node` / `Tree` 数据结构 | `llamaindex_runtime/registry/tree_generator.py` / `tree/query.py` | **借节点语义模型**，保留本地 `node_id/span_ids` |
| **Psi-RAG** | `src/utils.py:347-353` | `prototype_embeddings()` | future `TreeSemanticDistributionAdapter` | **借 centroid/prototype 思路**，本地重算 subtree stats |
| **Psi-RAG** | `src/tree_builder/abstract.py:104-150` + `213-283` | exact hierarchical tree build | `TreeBackendAdapter`（候选分支） | 只作为 tree 结构 donor 参考，不直接接 provenance |
| **Psi-RAG** | `src/tree_builder/bucketed.py:35-116` + `273-355` | 大规模 bucketed hierarchy | `TreeBackendAdapter`（规模化阶段） | 后续用于大规模语料，不作为第一刀 |
| **HIRO** | `raptor/tree_retriever.py:240-256` | `evaluate_children()` 递归决策骨架 | future decision layer over `TreeSemanticDistributionAdapter` | **借 decision skeleton**，把 distance-threshold 改成 distribution-threshold |
| **HIRO** | `raptor/tree_retriever.py:49-59` | `selection_threshold + delta_threshold` 双门槛机制 | future decision config | **借参数设计**，不直接借语义 |
| **HIRO** | `raptor/tree_retriever.py:303-378` | retrieval orchestration | `entrypoints/query.py` / adapter wrapper | 只参考 orchestration，不替代本地 façade |
| **RAPTOR** | `raptor/cluster_tree_builder.py:54-150` | cluster-tree build | `TreeBackendAdapter` 备选实现 | **借语义树构建**，不作为 distribution 统计 donor |
| **RAPTOR** | `raptor/tree_retriever.py:157-194` + `251-326` | collapsed tree retrieval | `tree runtime` / retrieval experiments | 用于对照 tree retrieval，不直接解决树内统计 |
| **PageIndex** | `pageindex/page_index_md.py:243-299` | `md_to_tree()` page/TOC tree build | `TreeBackendAdapter` | **借 tree build**，page range 需映射回 `span_id` |
| **PageIndex** | `pageindex/retrieve.py:110-137` | page/node content retrieval | `tree runtime` persisted backend branch | **借树检索入口**，不负责 embedding stats |
| **LightRAG** | `lightrag/utils.py:2491-2611` | `pick_by_vector_similarity()` chunk vector selection | graph 支线 / graph-text retrieval 备选 | 当前**不借来做 tree-internal stats** |
| **LightRAG** | `lightrag/operate.py:4475-4631` | entity-related chunk selection | `GraphExtractionAdapter` / `GraphRetrievalAdapter` 备选 | graph 支线重开时再用 |
| **RAG-Anything** | multimodal processors / query mixin | multimodal enhancement only | `OptionalMultimodalAdapter` | 当前不进入 tree/vector distribution 主线 |

### 当前路线收束

- **第一刀主 donor**：`Psi-RAG`（遍历骨架 + 节点向量表示）
- **第一刀决策层 donor**：`HIRO`（递归决策骨架 + 双阈值机制）
- **第一刀不借**：`LightRAG` / `RAG-Anything` 进入 tree-internal vector distribution 主线
- **Tree build 备用 donor**：`PageIndex` / `RAPTOR`
