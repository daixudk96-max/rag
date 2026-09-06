# Requirements: Provenance-Centric Multi-View RAG

**Defined:** 2026-05-11
**Core Value:** 不管切片策略、向量表示或图谱抽取怎么变化，系统都能稳定回到原文证据位置，并且能够安全做版本化更新而不打断检索链路。

## v1 Requirements

### Identity & Versioning

- [ ] **CORE-01**: 系统为每篇文档生成稳定 `doc_id`
- [ ] **CORE-02**: 系统为每次文档更新生成新的 `version_id`
- [ ] **CORE-03**: 系统为规范证据单元生成稳定 `span_id`
- [ ] **CORE-04**: 系统记录用于生成 spans 的 normalization contract

### Parsing & Spans

- [ ] **SPAN-01**: 系统通过一次 Docling 解析生成 canonical spans
- [ ] **SPAN-02**: 每个 span 必须带 `page_no` 与 `heading_path`
- [ ] **SPAN-03**: 相同 contract 下重复解析结果稳定
- [ ] **SPAN-04**: 文档改动后，新版本 spans 不覆盖旧版本

### Registry & Mapping

- [ ] **REG-01**: PostgreSQL 持久化 documents / versions / spans / chunks
- [ ] **REG-02**: 系统能从 `chunk_id` 回映到 `span_id`
- [ ] **REG-03**: 系统能从 query 结果回到 `doc_id / version_id / page_no / heading_path`
- [ ] **REG-04**: 系统支持 active version 切换而不覆盖历史版本

### Keyword Retrieval

- [ ] **KEY-01**: 系统支持精确术语检索（如 PM2.5、标准号、节目名）
- [ ] **KEY-02**: Keyword path 返回结果必须带 `span_id`
- [ ] **KEY-03**: Keyword path 支持从 active version 检索

### Vector Retrieval

- [ ] **VEC-01**: 系统支持基于 pgvector 的轻量语义检索
- [ ] **VEC-02**: 向量 chunk 必须映射回一个或多个 `span_id`
- [ ] **VEC-03**: Vector path 返回结果必须带 `chunk_id` 与 `span_id`

### Unified Query

- [ ] **API-01**: 系统提供统一 query 入口
- [ ] **API-02**: 系统能在 Keyword path 与 Vector path 之间路由
- [ ] **API-03**: 统一输出必须包含答案与可追溯证据字段

## v2 Requirements

### Graph & Hybrid

- **GRAPH-01**: 引入独立图层（Neo4j）
- **GRAPH-02**: 支持实体 / 关系 / evidence links
- **HYB-01**: 支持 Deep Hybrid path（KG → Keyword/Vec → Tree → 聚合 → 扩展）
- **HYB-02**: 支持命中分布分析与扩展决策

### Ranking & Quality

- **RANK-01**: 引入独立 reranker
- **RANK-02**: 支持多路召回结果融合排序

### Entity Resolution

- **ENT-01**: 支持 alias normalization
- **ENT-02**: 支持 mention → entity 映射
- **ENT-03**: 支持跨版本实体稳定化

## Out of Scope

| Feature | Reason |
|---------|--------|
| 独立 Neo4j 图层 | v1 先验证 provenance 主干，避免多库过早耦合 |
| 独立 Milvus / Qdrant | v1 先用 pgvector 降低运维复杂度 |
| Deep Hybrid 主链 | v1 不做复杂级联与扩展 |
| 命中分布分析器 | 需要在基本检索跑通后再引入 |
| 独立 reranker | v1 先用轻量融合或不做重排 |
| 多通道 Tool/CLI/API 分发层 | v1 先证明 query 内核成立 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 0/1 | Pending |
| CORE-02 | Phase 0/1 | Pending |
| CORE-03 | Phase 0/2 | Pending |
| CORE-04 | Phase 0/2 | Pending |
| SPAN-01 | Phase 2 | Pending |
| SPAN-02 | Phase 2 | Pending |
| SPAN-03 | Phase 2 | Pending |
| SPAN-04 | Phase 2 | Pending |
| REG-01 | Phase 1 | Pending |
| REG-02 | Phase 4 | Pending |
| REG-03 | Phase 5 | Pending |
| REG-04 | Phase 1/5 | Pending |
| KEY-01 | Phase 3 | Pending |
| KEY-02 | Phase 3 | Pending |
| KEY-03 | Phase 3 | Pending |
| VEC-01 | Phase 4 | Pending |
| VEC-02 | Phase 4 | Pending |
| VEC-03 | Phase 4 | Pending |
| API-01 | Phase 5 | Pending |
| API-02 | Phase 5 | Pending |
| API-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0

---
*Requirements defined: 2026-05-11*
*Last updated: 2026-05-11 after AUTOD phase-1 planning initialization*