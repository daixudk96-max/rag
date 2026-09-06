# Phase 10 Summary — Reranker

## Status
DONE

## What shipped
- `src/reranker/__init__.py`
- `src/reranker/types.py`：RerankedHit / RerankerConfig
- `src/reranker/normalize.py`：分数归一化
- `src/reranker/fusion.py`：RRF 融合 + 多路加成
- `src/reranker/reranker.py`：统一 rerank 入口
- `src/hybrid_path/orchestrator.py`：已接入 rerank_hits
- `src/api/routes.py`：`/query/hybrid` 返回 rerank 后 evidence
- `tests/test_reranker_types.py`
- `tests/test_reranker_normalize.py`
- `tests/test_reranker_fusion.py`
- `tests/test_reranker_api.py`

## Verification evidence
- Phase 10 tests: `11 passed`
- Full suite after Phase 10: `90 passed, 6 skipped`

## Key verified truths
1. 多路召回结果可以被统一重排
2. 重排后 evidence 按 `rerank_score` 排序
3. provenance 字段未丢失：`span_id / page_no / heading_path / raw_text / node_id` 均保留
4. 多路径命中项会获得额外加成
5. `/query/hybrid` 已返回 `rerank_score` 与 `original_score`

## Notes / caveats
- 当前 reranker 是最小本地实现：min-max 归一化 + RRF + 多路加成
- 仍未引入外部 cross-encoder 或学习型权重
- Graph 运行时验证仍受本地 Neo4j 环境限制，但 reranker 不依赖其在线

## Overall project status
当前路线图中的主要阶段已推进完成：
- Phase 1 Registry
- Phase 2 Canonical Spans
- Phase 3 Keyword Path
- Phase 4 Vector Path
- Phase 5 Unified Query
- Phase 6 Tree Formal Rollup
- Phase 7 Graph Path（代码完成，运行时验证受环境限制）
- Phase 8 HitDistributionAnalyzer
- Phase 9 Deep Hybrid Path
- Phase 10 Reranker

## Next best step
当前计划主线已推进完成。如继续推进，应转入：
1. Neo4j 运行时验证补齐
2. 生产级配置/池化/日志/错误处理
3. 真实数据集评估与调参
4. v3 级别的模型化重排与更复杂图推理。