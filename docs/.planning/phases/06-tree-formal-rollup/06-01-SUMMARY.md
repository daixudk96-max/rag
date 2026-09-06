# Phase 6 Summary — Tree Formal Rollup

## Status
DONE

## What shipped
- `src/registry/migrations/004_tree_extension.sql`：tree_nodes / tree_node_spans / vector_chunks.node_id 扩展
- `src/tree_path/__init__.py`
- `src/tree_path/generator.py`：从 `heading_path` 派生层级树节点
- `src/tree_path/loader.py`：tree_nodes / tree_node_spans 写入与 leaf node 关联
- `src/tree_path/query.py`：leaf -> parent 回并查询
- `tests/test_tree_schema.py`
- `tests/test_tree_generation.py`
- `tests/test_tree_loader.py`
- `tests/test_tree_query.py`
- `tests/test_tree_integration.py`

## Verification evidence
- Phase 6 tree tests: `10 passed`
- Full suite after Phase 6: `61 passed`

## Key verified truths
1. Tree 视图可建立在 `canonical_spans` 之上而不破坏 provenance 主干
2. `tree_node_spans` 可以稳定回映 `span_id`
3. `tree_nodes` 通过 `parent_node_id` 形成稳定层级
4. 可以从 leaf node 回并到 parent context
5. `vector_chunks` 可挂接 `node_id`，形成 Vector -> Tree 对齐
6. Tree / Vector / Registry 三层共用同一套 `version_id / span_id` 坐标

## Notes / caveats
- 当前 tree generator 只基于 `heading_path` 做最小层级拆分，不是最终复杂结构策略
- `summary_text` 仍为空，占位保留给后续摘要能力
- 还没有命中分布分析，也没有复杂 sibling / root context 组合策略

## Next best step
进入 Graph path，把实体 / 关系 / evidence links 独立到图层，并继续保持 `span_id` 作为证据主锚点。