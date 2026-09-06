# PageIndex Complete Integration — MASTER

## Mission

Complete PageIndex migration with full implementation (resolve all TODOs/stubs) and verify integration functionality through real testing.

## Mode

**INTEGRATION MODE — COMPLETE IMPLEMENTATION** — Not just architecture, but runnable outcomes.

## Current Reality (Verified)

**Phase 1-5 status** (inspection results):
- ✓ Phase 1: PageIndexClient complete (412 lines, full implementation)
- ✓ Phase 2: Registry extensions complete (write_node_embeddings/write_semantic_distribution implemented)
- ⚠ Phase 2: reasoning_backend STUB ONLY (TODOs: line 114, 134-137, 169, 190)
- ✓ Phase 3: Configuration unified (llm/ module, RuntimeSettings extended)
- ✓ Phase 4: Migrations complete (013_node_embeddings.sql, 014_semantic_distribution.sql)
- ✓ Phase 5: Graph backend integrated (query.py line 236-242)
- ✓ PageIndex donor installed (C:\Python311\Lib\site-packages\pageindex\)

**Completion percentage**: 80% implemented + 20% TODO/stub

**Frozen contracts verified**:
- ✓ PageIndex donor unchanged (copied to site-packages, not modified)
- ✓ RegistryWriter seam preserved (PostgresRegistryWriter protocol intact)
- ✓ BackendHit format extended (backend_source, retrieval_path added, frozen fields preserved)
- ✓ RuntimeSettings unified seam (from_env_llm_only functional)

## Remaining Work

**Task 1**: Implement reasoning_backend TODOs
- LLM reasoning call (line 114)
- Extract heading_path, node_id, span_ids (line 134-137)
- Content extraction from tree_nodes (line 190)

**Task 2**: Real integration testing
- Test PageIndexClient.index() with actual markdown document
- Verify Registry write success (tree_nodes, node_spans populated)
- Test retrieve_tree_hits() functionality
- Verify token savings (query < 300 tokens)

**Task 3**: Backend stack verification
- Tree backend (PageIndexTreeAdapter)
- Reasoning backend (reasoning_backend.py after TODO resolution)
- Hybrid routing (existing query() infrastructure)
- BackendHit → QueryHit conversion

## Read Order

Executor MUST read in this order:
1. `00-MASTER.md` (this file) — Current reality, remaining work
2. `01-ROADMAP.md` — Task sequence, verification steps
3. `02-INTERFACES.md` — Immutable contracts, adapter seams
4. `03-CURRENT-PHASE.md` — Current task, exit criteria (changes frequently)

## Execution Rules

- **GitNexus**: Run `gitnexus impact` before ANY symbol edit
- **TDD**: RED → GREEN → IMPROVE for each implementation
- **Reindex**: `gitnexus analyze --embeddings --skills --verbose` after each slice
- **Frozen Contracts**: PageIndex donor unchanged, Registry seam preserved
- **Stop on**: HIGH/CRITICAL impact, frozen violation, confidence < 0.7

## Success Criteria

Complete integration requires:
- ✓ reasoning_backend TODOs implemented (LLM reasoning functional)
- ✓ PageIndexClient tested with real document (index writes to Registry)
- ✓ retrieve_tree_hits() returns filtered hits (not all nodes)
- ✓ Token savings demonstrated (< 300 tokens per query)
- ✓ Backend stack integration verified (tree + reasoning + hybrid)
- ✓ GitNexus reindexed (embeddings + skills updated)

## Total Effort

2-3 days (reasoning_backend implementation + integration testing)

---

**STOP CONDITION**: All TODOs resolved, integration tests pass, backend stack verified → await user gate decision.