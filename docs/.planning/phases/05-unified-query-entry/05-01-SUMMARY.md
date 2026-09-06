# Phase 5 Summary — Unified Query Entry

## Status
DONE

## What shipped
- `src/query_classifier/__init__.py`：最小 query classifier
- `src/unified_output/__init__.py`：UnifiedQueryResult 与转换函数
- `src/api/routes.py`：新增统一 `/query` 入口，并保留 `/query/keyword`、`/query/vector`
- `tests/test_query_classifier.py`
- `tests/test_unified_output.py`
- `tests/test_unified_api.py`

## Verification evidence
- Phase 5 tests: `9 passed`
- Full suite after Phase 5: `51 passed`

## Key verified truths
1. 用户可以通过统一 `/query` 入口发起查询
2. 精确术语类查询会自动路由到 Keyword path
3. 语义描述类查询会自动路由到 Vector path
4. 统一输出结构已经稳定：`route / answer / evidence`
5. 统一输出中的 evidence 包含可追溯字段（span / chunk / page / heading）
6. 既有 `/query/keyword` 与 `/query/vector` 没有被破坏

## Notes / caveats
- classifier 是 v1 最小规则版，只做保守路由，不追求复杂分类精度
- unified output 现在优先保证结构和可追溯性，不追求最终答案质量包装
- Deep Hybrid / reranker / graph path 仍然明确后置

## v1 PoC result
当前 v1 收缩版目标已全部达成：
- 一次解析 → canonical spans
- PostgreSQL registry / provenance 主干
- Keyword path
- Vector path
- unified query entry

## Next best step
v1 PoC 已完成。下一步应切到 v2 规划：Graph path、Tree 正式回并、Deep Hybrid、HitDistributionAnalyzer、Reranker。