# Phase 14 New Document Validation

**Date:** 2026-06-27
**Validation directory:** `verification/phase14-new-doc-validation/`
**Corpus:** `docs/research/deep-research-report (1).md` (34.8KB)
**Target:** Verify Phase 13 hotspot traverse design on new document

## Purpose

验证 Phase 13 hotspot traverse 设计原理在全新文档上的表现：

1. **Hotspot 返回 waypoint + evidence chunks**（不是 waypoint-only）
2. **Zero-chunk fallback 不发生**（Q18 style 问题不再出现）
3. **Evidence chain integrity**：`chunk_id_present_rate >= 0.95`

## Document Content

混合 RAG 开源项目深度研究报告，涵盖：

- KAG、NexusRAG、LlamaIndex、LightRAG、RAPTOR/HIRO 对比
- A-F 六项能力维度分析
- 模块拼接蓝图与实施建议

## Queries

20 个基于文档内容的真实业务问题，按难度分级：

- L1：摘要类（核心结论、成熟度排序）
- L2：对比类（项目区别、能力维度、实施建议）
- L3：技术类（架构机制、聚合公式）

## Execution

```bash
rtk python verification/phase14-new-doc-validation/run_validation.py --phase retrieve
```

## Expected Results

基于 Phase 13 修复后的预期：

- `missing_chunk_hits = 0`
- `evidence_chunk_rate = 1.0`
- `queries_with_hits = 20/20`
- 每个查询返回真实 `chunk_id`（不是 MISSING_CHUNK_ID）