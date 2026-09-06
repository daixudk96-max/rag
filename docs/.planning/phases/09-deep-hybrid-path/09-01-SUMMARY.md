# Phase 9 Summary — Deep Hybrid Path

## Status
DONE

## What shipped
- `src/hybrid_path/__init__.py`
- `src/hybrid_path/types.py`
- `src/hybrid_path/collector.py`
- `src/hybrid_path/aggregator.py`
- `src/hybrid_path/expander.py`
- `src/hybrid_path/orchestrator.py`
- `src/api/routes.py`：新增 `/query/hybrid`
- `tests/test_hybrid_types.py`
- `tests/test_hybrid_orchestrator.py`
- `tests/test_hybrid_api.py`

## Verification evidence
- Phase 9 tests: `6 passed`
- Full suite after Phase 9: `79 passed, 6 skipped`

## Key verified truths
1. Hybrid 主链已建立：Keyword / Vector / Graph / Tree / Analyze 可被统一编排
2. 多路命中可归一化到 `span_id` 维度
3. Graph 不可用时可 graceful fallback，不中断主链
4. Tree 扩展可由 HitDistributionAnalyzer 决策驱动
5. `/query/hybrid` 已可返回结构化证据和路径使用信息

## Notes / caveats
- 仍未引入 reranker
- 多路 score 仍未做归一化或学习型加权
- Graph 路径运行时验证仍受本地 Neo4j 环境限制

## Next best step
进入 Phase 10：Reranker，对多路召回结果做统一重排，同时保持 provenance 回链不破坏。