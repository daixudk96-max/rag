# Phase 11 Summary — Production Hardening

## Status
DONE_WITH_CONCERNS

## What shipped
- `src/registry/connection.py`：PostgreSQL connection pool + 向后兼容 `get_connection`
- `src/api/validation.py`：query / top_k / limit 校验
- `src/api/errors.py`：统一错误体系 + JSON error handlers
- `src/api/logging_config.py`：结构化 JSON 日志
- `src/graph_path/health.py`：Neo4j 健康检查接口
- `src/api/routes.py`：接入 startup/shutdown、日志中间件、校验、错误处理、健康端点
- `tests/test_connection_pool.py`
- `tests/test_api_validation.py`
- `tests/test_api_errors.py`
- `tests/test_structured_logging.py`
- `tests/test_neo4j_health.py`

## Verification evidence
- Hardening tests: `10 passed`
- Full suite after hardening: `100 passed, 6 skipped`

## Key verified truths
1. PostgreSQL 已切到连接池模式
2. API 输入边界校验已接入
3. 数据库异常不再泄露 traceback
4. 结构化 JSON 日志可输出
5. `/health` 与 `/health/neo4j` 可用

## Notes
- FastAPI 生命周期已迁移到 lifespan，相关 on_event 弃用警告已收口为非 blocker。
- Neo4j 健康检查与运行时验证现已完成，不再是当前 session 的 blocker。

## Next best step
如继续推进，建议转入更高一级的生产化工作：真实数据集评测、参数调优、部署与观测体系完善。