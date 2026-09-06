# Phase 7 Summary — Graph Path

## Status
DONE

## What shipped
- `src/registry/migrations/005_graph_entities.sql`：entities / relations / evidence_links 表
- `src/graph_path/__init__.py`
- `src/graph_path/connection.py`：Neo4j driver 入口
- `src/graph_path/projection.py`：entity / relation / evidence 投影
- `src/graph_path/query.py`：实体邻居查询
- `src/graph_path/span_resolver.py`：entity -> span 回链
- `src/api/graph_query_handler.py`
- `src/api/routes.py`：新增 `/query/graph`
- `tests/test_graph_schema.py`
- `tests/test_neo4j_connection.py`
- `tests/test_graph_projection.py`
- `tests/test_graph_query.py`
- `tests/test_span_resolver.py`
- `tests/test_graph_api.py`
- `tests/test_graph_integration.py`

## Verification evidence
- Graph PostgreSQL-side tests: `4 passed`
- Real Neo4j graph tests: `6 passed`
- Full suite after Neo4j validation: `108 passed`

## Key verified truths
1. PostgreSQL 侧的 graph registry（entities / relations / evidence_links）已建立
2. Graph path 的代码主干已经存在：projection / query / span resolver / graph api
3. 图谱证据锚定的是 `span_id`，不是 `chunk_id`
4. Graph / Keyword / Vector 继续共用同一套 `version / span / provenance` 主干

## Notes
- Neo4j 运行时验证已补齐，Graph Path 不再存在“代码完成但环境未验证”的 blocker。
- 本次验证使用了隔离的临时 Neo4j 测试实例，代码与主干逻辑已证明可工作。
- 旧的 skipped 现已被真实运行验证替换。

## Verification closure
- 已完成补跑：
  - `tests/test_neo4j_connection.py`
  - `tests/test_graph_projection.py`
  - `tests/test_graph_query.py`
  - `tests/test_graph_api.py`
  - `tests/test_graph_integration.py`
- 当前 Graph Path 已可按 DONE 处理。

## Next best step
继续进入 Phase 8：HitDistributionAnalyzer。