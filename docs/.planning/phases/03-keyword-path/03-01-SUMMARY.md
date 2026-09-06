# Phase 3 Summary — Keyword Path

## Status
DONE

## What shipped
- `src/registry/migrations/002_keyword_indexes.sql`：FTS / pg_trgm / tsvector trigger / keyword indexes
- `src/keyword_path/__init__.py`
- `src/keyword_path/search.py`：Keyword path 检索实现
- `src/api/routes.py`：`/query/keyword` 最小 API 入口
- `tests/fixtures/sample_terms.json`：精确术语样例集
- `tests/test_keyword_path.py`：Keyword path 行为测试
- `tests/test_keyword_e2e.py`：样例集端到端测试
- `tests/test_keyword_api.py`：API 冒烟测试

## Verification evidence
- Phase 1 tests: `7 passed`
- Phase 2 tests: `9 passed`
- Phase 3 keyword tests: `7 passed`
- Phase 3 API smoke test: `1 passed`
- Full test suite: `32 passed`

## Key verified truths
1. PostgreSQL 可以承载 v1 的 Keyword path
2. Keyword path 能处理精确术语、短语和前缀类查询
3. 默认只查 active version
4. 返回结果带 `span_id / doc_id / version_id / page_no / heading_path / raw_text / match_score`
5. Keyword path 与 registry / provenance 主干对齐正常
6. API 入口可直接返回结构化 payload

## Notes / caveats
- 当前检索策略是 v1 的“够用版”：`ILIKE + tsvector + trigram similarity` 混合，不是最终高质量 BM25/融合检索实现
- 中文场景现在用 `simple` tsquery，适合作为 v1 保守方案，但不是中文分词最优解
- `match_type` 目前仅按是否包含空格粗分 `exact/phrase`
- 还没有 query classifier，这一条仍是独立入口，不是统一 query 路由

## Next best step
进入 Phase 4：Vector Path，用 pgvector 建立最小语义检索能力，并证明它能和 Keyword path 共用同一套 `version / span / provenance` 主干。