# PageIndex Migration Program — ROADMAP

## Mainline Route

**Phase ordering (sequential execution)**:

### Phase 1: PageIndex Client Transplantation (3 days) ✓ PARTIAL
- [ ] 1.1 PageIndexClient移植 → llamaindex_runtime/client/pageindex_client.py
- [ ] 1.2 CLI工具移植 → llamaindex_runtime/cli/run_pageindex.py
- [ ] 1.3 工具函数移植 → retrieve.py, utils.py (client/)
- [ ] 1.4 配置扩展 → RuntimeSettings添加pageindex_workspace, pageindex_lazy_load

**Exit Criteria**: PageIndexClient.index() writes to Registry (tree_nodes, node_spans)

### Phase 2: Retrieval Enhancement (4 days) — ACTIVE NEXT
- [ ] 2.1 预计算embedding加速 → registry.write_node_embeddings()
- [ ] 2.2 Agent reasoning backend → llamaindex_runtime/tree/reasoning_backend.py
- [ ] 2.3 Hybrid retrieval routing → tree + graph + vector backend router
- [ ] 2.4 BackendHit protocol extension → preserve frozen output format

**Exit Criteria**: retrieve_tree_hits() returns filtered hits (not all nodes), token savings demonstrated

### Phase 3: Configuration Unification (1 day)
- [ ] 3.1 OpenAI接口统一 → PageIndex LiteLLM → RuntimeSettings.from_env_llm_only()
- [ ] 3.2 .env参数统一 → PAGEINDEX_WORKSPACE, PAGEINDEX_MODEL
- [ ] 3.3 Monkey-patch验证 → llm_acompletion unified seam

**Exit Criteria**: PageIndex LLM calls route through RuntimeSettings, no config.yaml dependency

### Phase 4: Precomputation Acceleration (2 days)
- [ ] 4.1 预计算semantic distribution → registry.write_semantic_distribution()
- [ ] 4.2 加速决策策略 → BaselineTreeBranchDecisionPolicy uses precomputed stats
- [ ] 4.3 Embedding cache → node_embeddings table (PostgreSQL)

**Exit Criteria**: runtime.py决策使用预计算数据，query time < 300 tokens

### Phase 5: Graph Backend Completion (1 day)
- [ ] 5.1 Neo4j集成完善 → graph/query.py full KG backend
- [ ] 5.2 Graph→span_id routing → evidence links回到BackendHit
- [ ] 5.3 Hybrid graph+tree → graph backend as additional path

**Exit Criteria**: Graph backend returns BackendHit, KG retrieval functional

## Paused Branches

These branches are explicitly **PAUSED** (do not activate without user gate decision):

- **TreeGenerator升级** (embedding-based clustering): Optional, Phase 6 already has keyword clustering
- **PageIndex完整移植迭代** (workspace+CLI+Agent+工具函数): Already in Phase 1-5 mainline
- **Hybrid检索优化** (权重调优): Depends on Phase 2 completion

**No-drift rule**: Executor must NOT unpause branches. Read from control files, do not assume from memory.

## Phase Dependencies

```
Phase 1 (基础移植) → Phase 2 (检索增强) → Phase 3 (配置统一) → Phase 4 (预计算) → Phase 5 (Graph)
```

Sequential execution. No phase skipping.

## Current Phase

**READ FROM**: `03-CURRENT-PHASE.md` (do NOT assume from memory)

Executor must extract current task from 03-CURRENT-PHASE.md each time.

---

**STOP CONDITION**: Phase complete → report to user for gate decision. Do not auto-advance.