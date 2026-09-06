# Phase 14 New Document Validation Summary

**Date:** 2026-06-27
**Validation directory:** `verification/phase14-new-doc-validation/`
**Corpus:** `docs/research/deep-research-report (1).md` (34.8KB)
**Target:** Verify Phase 13 hotspot traverse design on completely new document

## Execution

1. Created new isolated validation workspace.
2. Designed 20 business queries based on document content (RAG开源项目深度研究).
3. Ran `run_validation.py --phase retrieve` with `hybrid_cluster` selector.
4. Verified Phase 13 design principle: hotspot returns waypoint + evidence chunks.

## Evidence Chain Results

```json
{
  "total_hits": 99,
  "queries_with_hits": 20,
  "zero_hit_queries": 0,
  "zero_hit_query_rate": 0.0,
  "missing_chunk_hits": 0,
  "placeholder_chunk_hits": 0,
  "evidence_chunk_hits": 99,
  "chunk_id_present_rate": 1.0,
  "evidence_chunk_rate": 1.0,
  "measured_not_assumed": true,
  "phase_13_validation": {
    "target": "hotspot traverse returns waypoint + evidence",
    "missing_chunk_hits_expected": 0,
    "actual_missing_chunk_hits": 0,
    "pass": true
  }
}
```

## Per-Query Results

| Query ID | Query Text (abbr) | Hits | Evidence Hits |
|----------|-------------------|------|---------------|
| Q1 | 研究报告的核心结论是什么？ | 5 | 5 |
| Q2 | KAG 和 NexusRAG 在知识图谱能力上有什么区别？ | 5 | 5 |
| Q3 | A-F 六项能力中哪几项最稀缺？ | 5 | 5 |
| Q4 | LlamaIndex 如何实现向量命中回映？ | 5 | 5 |
| Q5 | 快速做 POC 应该选择哪个项目？ | 4 | 4 |
| Q6 | LightRAG 支持哪些向量数据库后端？ | 5 | 5 |
| Q7 | 图触发向量检索策略是什么？ | 5 | 5 |
| Q8 | RAPTOR 和 HIRO 的核心贡献是什么？ | 5 | 5 |
| Q9 | KAG 增强实现需要多少人日？ | 5 | 5 |
| Q10 | KAG 的 mutual indexing 结构是什么？ | 5 | 5 |
| Q11 | NexusRAG 如何保留文档结构？ | 5 | 5 |
| Q12 | Agent 自主扩展机制的建议顺序是什么？ | 5 | 5 |
| Q13 | A-F 六项能力的判定标准是什么？ | 5 | 5 |
| Q14 | 从仓库成熟度来看哪个项目最稳？ | 5 | 5 |
| Q15 | 本次检索排除了哪些 GraphRAG 项目？ | 5 | 5 |
| Q16 | NexusRAG 和 LightRAG 分别使用什么向量数据库？ | 5 | 5 |
| Q17 | 向量命中回映树节点的聚合公式建议是什么？ | 5 | 5 |
| Q18 | 必须自研的四个模块是什么？ | 5 | 5 |
| Q19 | 最终执行顺序建议是什么？ | 5 | 5 |
| Q20 | 需求贴合度综合判断的排序是什么？ | 5 | 5 |

## Retrieval Path Verification

所有 99 个 hits 的 retrieval_path 都是：

- `subtree_hotspot_traversal`
- `backend_source`: `tree_semantic`

这证明 Phase 13 的 hotspot traverse 逻辑（`_traverse_hotspot_with_children`）在全新文档上正常工作。

## Phase 13 Design Principle Confirmed

**设计原理**：hotspot traversal 应返回 waypoint + evidence chunks，而不是 waypoint-only 导致 backend mapping 跳过并触发 zero-chunk fallback。

**验证结果**：

- `missing_chunk_hits = 0`（目标：0） — 没有任何 hit 使用 MISSING_CHUNK_ID
- `evidence_chunk_rate = 1.0` — 所有 99 个 hit 都有真实 chunk_id
- Phase 13 修复（leaf fallback hotspot direct-chunk handling）在全新文档上有效

## Verdict

**PASS** — Phase 13 hotspot traverse design verified on completely new document.

- 20/20 queries have hits
- 99/99 evidence chunks (no placeholder/missing)
- Q18-style zero-chunk fallback problem eliminated
- Design principle holds across different document domains