# Phase 1 Summary — PostgreSQL Registry Foundation

## Status
DONE

## What shipped
- `docker-compose.yml`：PostgreSQL 16 + pgvector 本地环境
- `pyproject.toml`：Python 依赖与 pytest 配置
- `src/registry/connection.py`：数据库连接入口
- `src/registry/migrations/001_initial.sql`：6 张核心表 DDL、索引、约束
- `src/registry/crud.py`：文档 / 版本 / spans / chunks / chunk-span 映射写入函数
- `src/registry/queries.py`：active version、span 查询、chunk→document 追踪查询
- `tests/test_schema.py`：Schema 行为测试
- `tests/test_crud.py`：CRUD 与全链路查询测试
- `.planning/contracts/*.md`：identity / normalization / entity canonicalization 三份最小合同文档
- `README.md`：本地运行说明

## Verification evidence
- Schema tests: `7 passed`
- CRUD tests: `9 passed`
- PostgreSQL container healthy and serving on `localhost:5432`

## Key verified truths
1. 可以创建稳定的 `doc_id`
2. 可以创建新 `version_id` 并绑定 `normalization_contract_id`
3. 可以写入 `canonical_spans` 并按 `version_id` 查询
4. 可以写入 `vector_chunks` 与 `vector_chunk_spans`
5. 可以通过 `chunk_id -> span_id -> version_id -> doc_id` 回链到原文上下文
6. `activate_version()` 可以退休旧版本并激活新版本
7. 不同版本之间的数据相互隔离

## What was intentionally deferred
- Neo4j 独立图层
- Qdrant / Milvus 独立向量库
- Tree 正式回并机制
- Deep Hybrid path
- HitDistributionAnalyzer
- 独立 reranker
- 复杂 entity alias resolution

## Risks / caveats
- 当前 `query_spans_by_version()` 暂时固定 `LIMIT 1000`，适合 v1 PoC，不适合作为最终分页方案
- 当前连接层要求显式 `DATABASE_URL` 才能在应用代码中连接；测试通过 conftest 的默认本地 DSN 跑通
- 目前 registry 层只验证了数据库主干，还没有接入 Docling 真解析和 pgvector 真向量检索

## Next best step
进入 Phase 2：One Parse -> Canonical Spans，把 Docling 的真实解析结果写入 `canonical_spans`，并验证 page_no / heading_path / offset 的稳定性。