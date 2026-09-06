# STATE

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 不管切片策略、向量表示或图谱抽取怎么变化，系统都能稳定回到原文证据位置，并且能够安全做版本化更新而不打断检索链路。
**Current focus:** 当前路线图主线与会话目标均已推进完成。v1 PoC 及其后续 v2 主链（Tree / Graph / Analyzer / Hybrid / Reranker）已实现，Neo4j 真运行验证与生产级硬化也已补齐。当前全量测试为 108 passed。

## Current Mode

- Project mode: v1 收缩版 / 可运行 PoC
- Planning mode: yes
- Execution mode: no

## Locked v1 Scope

### Included
- PostgreSQL registry / mapping / provenance / versioning
- canonical spans
- Keyword path
- Vector path
- unified query entry
- Docling 一次解析
- 单 PostgreSQL 方案（registry + keyword path + pgvector）

### Beyond locked v1 baseline
- Neo4j graph projection 已实现并完成真运行验证，但不属于 locked v1 baseline
- Qdrant / Milvus 可选向量后端已实现，但默认基线仍是 pgvector
- Tree 正式回并机制
- Deep Hybrid path
- HitDistributionAnalyzer
- 独立 reranker
- 复杂 entity resolution
- 多通道 Tool / API / CLI 分发层

## Immediate Next Step

当前 session 目标已完成。如继续推进，下一步建议转到：1) 真实数据集评测；2) 参数调优；3) 部署与观测体系完善。\n
## Risks To Watch

- 在未冻结 normalization contract 前开始切 spans
- 在未建 registry 前先做检索逻辑
- 误把 `chunk_id` 当成全局主身份
- 过早引入独立图层或独立向量库导致复杂度膨胀

---
*Initialized: 2026-05-11 during AUTOD phase-1 planning continuation*