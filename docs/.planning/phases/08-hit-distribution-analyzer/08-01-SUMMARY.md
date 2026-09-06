# Phase 8 Summary — HitDistributionAnalyzer

## Status
DONE

## What shipped
- `src/hit_distribution/__init__.py`
- `src/hit_distribution/types.py`：NodeHit / AncestorScore / ExpansionDecision / HitDistributionResult
- `src/hit_distribution/analyzer.py`：向上聚合 + CV + Shannon Entropy
- `src/hit_distribution/decision.py`：集中 / 分散 / 中等 三态决策
- `src/hit_distribution/collector.py`：从 Vector path 收集 hits 并映射 Tree 节点
- `src/api/routes.py`：新增 `/query/analyze`
- `tests/test_hit_distribution.py`
- `tests/test_hit_distribution_api.py`

## Verification evidence
- Phase 8 tests: `8 passed`
- Full suite after Phase 8: `73 passed, 6 skipped`

## Key verified truths
1. Vector 命中结果可以沿 Tree 层级向上聚合
2. 可以稳定计算 `cv` 与 `entropy`
3. 可以输出三种决策状态：`high_concentration / high_dispersion / moderate`
4. `/query/analyze` 不依赖 Neo4j 在线即可工作
5. 无命中时可稳定返回 `no_hits`

## Notes / caveats
- 当前 analyzer 只分析 Vector -> Tree 单路命中，不做多路（Keyword + Graph + Vector）联合分析
- 当前 decision 规则是 v2 最小阈值版，后续可调优
- 当前 suggested_node_ids 只是建议，不会自动执行扩展

## Next best step
进入 Phase 9：Deep Hybrid Path，把 Graph / Keyword / Vector / Tree / analyzer 组合成复杂查询主链。