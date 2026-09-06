# PageIndex Complete Integration — ROADMAP

## Mainline Route

**Task ordering (sequential execution)**:

### Task 1: Resolve reasoning_backend TODOs (1 day)

**Subtasks**:
- [ ] 1.1 Implement LLM reasoning call (reasoning_backend.py line 114)
  - Design: Use RuntimeSettings.from_env_llm_only() for LLM config
  - Implement: Call LLM to judge relevant nodes from tree structure
  - TDD: Write test for reasoning_backend.retrieve_tree_hits()

- [ ] 1.2 Extract provenance fields (line 134-137)
  - Extract heading_path from tree structure
  - Extract node_id from structure mapping
  - Map span_ids from Registry query
  - TDD: Write test for BackendHit construction

- [ ] 1.3 Implement content extraction (line 190)
  - Extract content from tree_nodes table
  - Map node_id → span_ids → chunk content
  - TDD: Write test for content retrieval

**Exit Criteria**: reasoning_backend.retrieve_tree_hits() returns BackendHit list (no TODOs)

---

### Task 2: Real Integration Testing (1 day)

**Subtasks**:
- [ ] 2.1 Test PageIndexClient.index() with real markdown
  - Document: Use C:\Users\daixu\Downloads\爱复盘竞品分析报告_终稿.md
  - Call: EnhancedPageIndexClient.index(file_path, write_to_registry=True)
  - Verify: Registry.query_tree_nodes_by_version() returns nodes

- [ ] 2.2 Test retrieve_tree_hits() functionality
  - Query: "爱复盘SWOT分析"
  - Expected: Filtered hits (not all 14 nodes)
  - Verify: BackendHit.backend_source == "tree" or "reasoning"

- [ ] 2.3 Verify token savings
  - Measure: Query token consumption
  - Target: < 300 tokens per query (vs PageIndex standalone 1000-5000)
  - Verify: 90%+ reduction achieved

**Exit Criteria**: Integration tests pass, Registry populated, token savings demonstrated

---

### Task 3: Backend Stack Verification (0.5 day)

**Subtasks**:
- [ ] 3.1 Test tree backend (PageIndexTreeAdapter)
  - Call: adapter.index_tree() → Registry write
  - Call: adapter.retrieve_tree_hits() → BackendHit list
  - Verify: BackendHit format correct

- [ ] 3.2 Test reasoning backend (reasoning_backend.py)
  - Call: backend.retrieve_tree_hits() with LLM reasoning
  - Verify: LLM navigation functional
  - Verify: BackendHit provenance fields populated

- [ ] 3.3 Test hybrid routing (query() infrastructure)
  - Call: query() with mode="hybrid"
  - Verify: tree + graph + vector routing
  - Verify: BackendHit aggregation functional

- [ ] 3.4 GitNexus reindex
  - Run: gitnexus analyze --embeddings --skills --verbose
  - Verify: Skills updated (Registry, Tree, LLM modules)

**Exit Criteria**: Backend stack verified, GitNexus updated, integration complete

---

## Paused Branches

These branches are explicitly **PAUSED** (do not activate without user gate decision):

- **Performance optimization** (Phase 4.2-4.3 deferred): Existing infrastructure covers
- **Real PostgreSQL testing** (Option B deferred): Integration tests can run with mock/stub
- **Production deployment**: Requires user approval after integration verification

**No-drift rule**: Executor must NOT unpause branches. Read from control files, do not assume from memory.

---

## Task Dependencies

```
Task 1 (reasoning_backend TODOs) → Task 2 (integration testing) → Task 3 (backend verification)
```

Sequential execution. No task skipping.

---

## Current Task

**READ FROM**: `03-CURRENT-PHASE.md` (do NOT assume from memory)

Executor must extract current task from 03-CURRENT-PHASE.md each time.

---

**STOP CONDITION**: Task 1-3 complete → report to user for gate decision. Do not auto-advance.