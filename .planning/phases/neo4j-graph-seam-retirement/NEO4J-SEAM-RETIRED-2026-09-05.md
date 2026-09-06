# Neo4j 旧图接口清退 — NEO4J-SEAM-RETIRED-2026-09-05

## 授权链
- 用户原话 (2026-09-05): 「第一个：把 Neo4j 这个接口去掉吧，把早期的旧图接口给清理掉。」 — 直接指令。
- 同消息第二问 (keyword/vector 换 LlamaIndex) 为疑问句, 本波不动手, 评估结论见文末, 待用户拍板。
- 执行模式: Phase 19 退役同款 — 归档先行 → fail-closed 编辑 → focused+组合验证 → 记账。

## 归档 (先行)
- 27 个受影响文件 → `.planning/phases/neo4j-graph-seam-retirement/archive-neo4j-seam-pre-retirement.zip`
- sha256: `cda69874f837cff3da7138694f0dd73d360c51b24f1e58dd8429c3b85ef1832d` (54972 bytes)
- 注: git 中 `llamaindex_runtime/graph/` 本就未跟踪 (仓库长期不逐波提交), 删除不以 git 记录, 以本 zip+sha 为持久凭证。

## 清退范围 (两层)
### A. 正式运行时 (llamaindex_runtime)
- 删除 3 文件: `graph/query.py` (retrieve_graph_hits), `graph/projector.py` (GraphProjector/EntityProjection/RelationProjection/EvidenceLinkProjection/project_version_to_graph, Cypher 投影), `graph/seam.py` (GraphRuntimeSeam/create_graph_runtime_seam)。
- `graph/__init__.py` 重写为空导出 (仅保留 LightRAG 通道说明; `from llamaindex_runtime.graph import lightrag_backend` 经子模块回退机制继续可用)。
- `integration.py`: 删 `load_property_graph_index_class` + `load_neo4j_property_graph_store_class` (仅 seam.py 消费)。
- `entrypoints/_query.py`: mode Literal 去 graph; driver/entity_id/depth 三参数删除; hybrid graph leg (:254-262) 与 graph mode 块 (:289-305) 删除; modes 集合/Literal/resolved_mode 同步。
- `entrypoints/types.py`: QueryResult mode Literal + _VALID_MODES 去 graph。
- `entrypoints/classifier.py`: graph_signals 路由删除 (原 concepts/entities/neighbors 类问题改道 keyword/vector/tree 启发式), `ql = q.lower()` 保留。
- `cli/__init__.py`: _VALID_MODES/Literal/参数/文档/委托同步删 graph。
- `agent/retrieval_tool.py` + `agent/query_agent.py` + `workflow/hybrid_retrieval_workflow.py`: driver/entity_id/depth 参数、属性、委托、文档全删; ToolMetadata 描述改 'keyword, vector, and tree'。
- `processing/callbacks.py`: build_finalize_callback 去 projector 参数与 project_version_to_graph 调用 (保留缺产出的 ValueError fail-closed 校验)。
- `pyproject.toml`: optional extra `graph = ["llama-index-graph-stores-neo4j"]` 删除。
### B. 早期验证 harness (verification/) — 「早期的旧图接口」本体
- 删除 `src/graph_path/` 全目录 (connection/projection/query/span_resolver/health/__init__) + `src/api/graph_query_handler.py`。
- `src/api/routes.py`: 删 /health/neo4j + /query/graph 端点、graph imports、lifespan reset_neo4j_driver; HTTPException 导入随之收缩。
- `src/hybrid_path/collector.py`: collect_graph_hits 删除, collect_all_paths 收缩为 keyword+vector 两路 (PathContribution 同步)。
- `tests/`: 删 test_graph_api/test_graph_integration/test_graph_projection/test_graph_query/test_neo4j_connection/test_neo4j_health/test_span_resolver; conftest.py 删 neo4j_driver fixture + NEO4J_* 默认值; test_runtime_cleanup.py 仅保留 pool-hooks 测试。
- test_candidate_fusion/test_normalize_policy/test_hybrid_types 中的 "graph" 仅为聚合数学测试的路径标签 (无 graph_path 导入), 按最小改动原则保留。
- `docker-compose.yml`: neo4j service 删除; `verification/README.md`: Neo4j 段落清退注记。

## 测试清退
- 删 3: test_graph_projector.py (47 hits), test_graph_query.py (43, 含 classifier graph 路由测试), test_kg_graphrag_enrichment.py (13)。
- 编辑 9: test_backend_harness (4 断言), test_hybrid_path (helpers+类+两用例), test_hybrid_workflow, test_query_agent, test_retrieval_tool, test_query_entrypoint (limit-budget 图 patch), test_runtime_packaging (EXPECTED_GRAPH_EXPORTS→[] + import-order 重写), test_incremental_processing (projector finalize 测试), test_llamaindex_factories (graph seam 测试)。
- 影响面侦查: 手动 grep 全仓 (GitNexus MCP 本会话不可用, 沿用 W7 先例); scripts/ 零 neo4j 引用; 主仓 facade __init__.py 无 graph 符号; phase17 测试只 import lightrag_backend (无碍)。

## 验证结果
- 引擎执行: 165 ops 全 OK / 0 FAIL (两处脚本笔误当轮修复: graph/__init__ 三引号, callbacks 尾冒号); py_compile 23 文件通过。
- 冒烟: `from llamaindex_runtime.graph import lightrag_backend` OK; `classify_query('find concepts related to PM2.5')` → 'keyword' (不再 'graph'); black 格式化 9 个受影响测试文件。
- verification/tests: **146 skipped, 0 failed** (27.04s, 无 DB 环境全跳过 = 导入面干净)。
- mypy: 59 errors / 18 files — 均为预存 (tree/runtime.py 等 8 个未触碰文件 + _query.py:177 auto-assignment 在 base 即存在: mode Literal 含 auto 而 resolved_mode 不含, 本次仅行号位移)。
- 6 域组合 (entity+extraction+graph+llm_openai+phase17+phase18): **1287 passed / 0 failed** (38.91s, 与基线零漂移)。
- 清退面 focused (13 根文件: hybrid/agent/workflow/entrypoint/packaging/incremental/factories/backend_harness/classifier/cli/phase6/candidate_fusion): **270 passed / 0 failed** (138.96s)。
- 预存问题 (非本波回归): 全 non-okf 树跑会触发 test_evaluation_baseline.py 收集错 (headroom_ai.pth 劫持 `import tests`, Phase 19 W2 已登记)。

## 残留与不做
- 历史文档提及 (docs/PROJECT-FREEZE.md, .qoder/repowiki, .claude/skills/generated, changes/) 不改 — 历史记录性质。
- tmp_replay_verify/ 为历史快照副本, 不动。
- Phase 17 LightRAG 通道 (lightrag_backend/graph_channel/live_bridge) 完整保留 — 唯一图引擎。

## 待用户拍板: 问题2 (keyword/vector → LlamaIndex)
- vector: 已是 LlamaIndex 生态 (BaseEmbedding + NodeParser); 自建 VectorBackend = SSOT 持久化 + 版本过滤, 换内置内存库属倒退 → 建议不换。
- keyword: 自研 query_spans_by_keyword 直查 OKF 账本 (版本过滤+溯源, 零耦合是特性); LlamaIndex BM25Retriever/KeywordTable 为内存索引, 每查重建、丢版本过滤 → 建议不换。
- 若用户坚持, 归档执行成本可控 (两模块独立), 但不建议。