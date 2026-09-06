# PageIndex Migration Program — MASTER

## Mission

Complete PageIndex donor transplantation into llamaindex_runtime architecture while preserving all existing Phase 6/8 tree logic and adding PageIndex workspace/CLI/Agent reasoning capabilities.

## Mode

**INTEGRATION MODE** — Phase 1 code transplanted, now executing actual adapter integration.

## Frozen Strategy

### Donor Priority
- **PRIMARY**: PageIndex official repository (`VectifyAI/PageIndex`, cloned to `/tmp/pageindex-donor`)
- **REFERENCE**: PageIndex完整功能分析与集成方案.md (docs/)
- **CONSTRAINT**: PageIndex donor code NOT modified (frozen contract)

### Unified Seam
- Registry seam: `PostgresRegistryWriter` (llamaindex_runtime/registry/)
- LLM seam: `RuntimeSettings.from_env_llm_only()` (unified config)
- Tree backend: `TreeBackendAdapter` protocol (preserved)

### Architecture Principle
**保留 + 增强**（NOT replace）:
- ✓ Preserve: runtime.py, semantic_distribution.py, hiro_decision_policy.py, analyzer/, TreeGenerator
- ✓ Add: PageIndexClient (workspace management), CLI tools, Agent reasoning backend
- ✓ Integrate: Precomputed embeddings, hybrid retrieval routing

## Read Order

Executor MUST read in this order:
1. `00-MASTER.md` (this file) — Mission, strategy, donor priority
2. `01-ROADMAP.md` — Phase ordering, mainline route, paused branches
3. `02-INTERFACES.md` — Immutable contracts, adapter seams
4. `03-CURRENT-PHASE.md` — Current task, exit criteria (changes frequently)

## Execution Rules

- **GitNexus**: Run `gitnexus impact` before ANY symbol edit
- **TDD**: RED → GREEN → IMPROVE for each integration slice
- **Reindex**: `gitnexus analyze --embeddings --skills --verbose` after each slice
- **Frozen Contracts**: PageIndex donor unchanged, Registry seam preserved
- **Stop on**: HIGH/CRITICAL impact, frozen contract violation, confidence < 0.7

## Success Criteria

Phase completion requires:
- ✓ PageIndexClient functional (workspace management, document persistence)
- ✓ CLI tools runnable (run_pageindex.py integrated)
- ✓ Registry write success (tree_nodes, node_spans)
- ✓ Tests pass (PageIndex integration tests)
- ✓ Reindex complete (GitNexus embeddings updated)
- ✓ Token savings demonstrated (90%+ reduction vs PageIndex standalone)

## Total Effort

11 days (Phase 1-5 integration)

---

**STOP CONDITION**: Control file says phase complete → await user gate decision.