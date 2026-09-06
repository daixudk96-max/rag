# Roadmap: Provenance-Centric Multi-View RAG

**Created:** 2026-05-11
**Mode:** v1 收缩版 / 可运行 PoC
**Goal:** 在最少系统复杂度下，先证明统一 span / version / provenance 主干成立，并跑通 Keyword + Vector 两条路径与统一 query 入口。

## Phase 0 — Contract Freeze

### Goal
锁定 identity / normalization / entity canonicalization 的最小规则，避免后续 `span_id` 漂移与 mapping 失真。

### Deliverables
- identity contract 文档
- normalization contract 文档
- entity canonicalization 最小原则文档

### Exit Criteria
- 明确 `doc_id / version_id / span_id / chunk_id` 的职责边界
- 明确 `offset_basis`
- 明确 parser / cleaning / heading 规则

---

## Phase 1 — PostgreSQL Registry Foundation

### Goal
建立最小 registry / mapping / provenance / versioning 台账。

### Deliverables
- `documents`
- `document_versions`
- `normalization_contracts`
- `canonical_spans`
- `vector_chunks`
- `vector_chunk_spans`

### Exit Criteria
- 能创建文档与版本
- 能写入 spans
- 能保存 version 与 contract 的绑定关系
- 约束和索引合理

---

## Phase 2 — One Parse → Canonical Spans

### Goal
通过 Docling 一次解析生成可追溯的 canonical spans。

### Deliverables
- Docling 解析流程
- spans 生成规则
- `page_no` / `heading_path` 保留验证

### Exit Criteria
- 同一 contract 下重复解析稳定
- 每个 span 可回原文
- span 带 page_no / heading_path

---

## Phase 3 — Keyword Path

### Goal
建立 v1 的精确术语检索路径。

### Deliverables
- PostgreSQL FTS / trigram / BM25 类路径
- Keyword path 输出结构
- 精确术语样例集验证

### Exit Criteria
- `PM2.5`、节目名、标准号这类查询可正常命中
- 返回结果带 `span_id` / `page_no` / `heading_path`

---

## Phase 4 — Vector Path

### Goal
建立 v1 的轻量语义检索路径。

### Deliverables
- spans → vector chunks 组合规则
- pgvector 存储方案
- chunk ↔ span 回链
- Vector path 输出结构

### Exit Criteria
- 轻量语义问题可以召回
- 从 chunk 可以稳定回 span
- Vector path 与 Keyword path 共用同一 version / provenance 体系

---

## Phase 5 — Unified Query Entry

### Goal
提供一个统一 query 入口，并完成 Keyword / Vector 最小路由。

### Deliverables
- query classifier 最小规则
- unified `/query` 或 `knowledge_router(query)`
- 统一返回结构

### Exit Criteria
- Keyword query 自动走 Keyword path
- 非精确 query 自动走 Vector path
- 输出中包含答案与可追溯证据字段

---

## Deferred to v2

- Tree 正式回并机制
- Neo4j graph projection
- HitDistributionAnalyzer
- Deep Hybrid 主链
- Reranker
- 独立 Milvus / Qdrant 向量库
- 复杂 entity alias resolution
- 多通道 Tool / API / CLI 分发层

---

## v2 Phases

## Phase 6 — Tree Formal Rollup

### Goal
把当前 Phase 2 的 spans 和 Phase 4 的 vector chunks 组织成正式 Tree 视图，并支持 parent-child 回并。

### Exit Criteria
- 存在稳定的 `tree_nodes` 与 `tree_node_spans`
- 可从 leaf 命中回并到 parent context
- Tree 视图与既有 `version / span / provenance` 主干对齐

---

## Phase 7 — Graph Path

### Goal
引入 Neo4j 独立图层，支持实体 / 关系 / evidence links 查询。

### Exit Criteria
- Graph 查询可用
- 图谱证据能回到 `span_id`
- Graph path 与统一 query 主干兼容

---

## Phase 8 — HitDistributionAnalyzer

### Goal
在 Tree / Graph / Vector 基础上建立命中分布分析，给后续 Deep Hybrid 的扩展决策提供基础。

### Exit Criteria
- 可以计算命中集中 / 分散状态
- 结果可用于 parent / sibling / adjacent 扩展决策

---

## Phase 9 — Deep Hybrid Path

### Goal
建立 `KG -> Keyword/Vector -> Tree -> 聚合 -> 扩展` 的主链。

### Exit Criteria
- 复杂查询可走 Hybrid 主链
- 结果统一回到原文证据
- 扩展策略已接入

---

## Phase 10 — Reranker

### Goal
在多路召回基础上增加重排，提高最终答案质量。

### Exit Criteria
- 多路候选可统一重排
- 不破坏 provenance 回链

---

## Dependency Order

1. Phase 0 → 先锁规则
2. Phase 1 → 再建最小 registry
3. Phase 2 → 再跑一次解析，生成 spans
4. Phase 3 → 先建 Keyword path
5. Phase 4 → 再建 Vector path
6. Phase 5 → 统一 query 入口
7. Phase 6 → Tree Formal Rollup
8. Phase 7 → Graph Path
9. Phase 8 → HitDistributionAnalyzer
10. Phase 9 → Deep Hybrid 主链
11. Phase 10 → Reranker

**Hard rule:** 不允许跳过 Phase 0 和 Phase 1 直接做检索。

---

## Success Definition for v1

v1 成功，不是“做出完整最终系统”，而是证明下面 5 件事成立：

1. 原文只解析一次是可行的
2. `span_id` 能成为稳定坐标
3. Keyword path 可用
4. Vector path 可用
5. 两条路径能共用同一套 version / provenance / mapping 主干

---

## Next Command

完成本阶段策划后，进入：
- `/gsd-plan-phase 1`

由 Phase 1 开始正式细化执行计划。