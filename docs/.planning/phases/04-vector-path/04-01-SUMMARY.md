# Phase 4 Summary — Vector Path

## Status
DONE

## What shipped
- `src/registry/migrations/003_vector_extension.sql`：pgvector 扩展与 embedding 索引
- `src/vector_path/__init__.py`
- `src/vector_path/chunker.py`：最小一对一 span -> chunk 组合器
- `src/vector_path/embedder.py`：确定性轻量 embedding
- `src/vector_path/loader.py`：chunks + embeddings 写入流程
- `src/vector_path/search.py`：Vector path 检索实现
- `src/api/routes.py`：新增 `/query/vector`
- `tests/test_vector_schema.py`
- `tests/test_vector_path.py`
- `tests/test_vector_api.py`

## Verification evidence
- Phase 4 vector tests: `9 passed`
- Full suite after Phase 4: `42 passed`

## Key verified truths
1. PostgreSQL + pgvector 可以承载 v1 的 Vector path
2. `canonical_spans` 可以派生成 `vector_chunks`
3. `vector_chunk_spans` 可以稳定回映 `span_id`
4. 语义 query 可以返回 `chunk_id / span_ids / page_no / heading_path / score`
5. `/query/vector` API 可直接工作
6. Vector path 与 Keyword path 共用同一套 `version / span / provenance` 主干

## Notes / caveats
- 当前 embedding 是 v1 的确定性轻量实现，目的是验证链路，不是最终质量上限
- 当前 chunker 采用最小一对一 span->chunk，不是最终最优 chunking 策略
- 当前还没有统一 query 路由，Keyword 和 Vector 仍是独立入口
- 当前还没有 reranker

## Next best step
进入 Phase 5：Unified Query Entry，把 Keyword path 与 Vector path 收到一个统一入口里，并加入最小 query classifier 路由。