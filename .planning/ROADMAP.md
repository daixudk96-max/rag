# ROADMAP

## Phase 1: PageIndex Bug Fix

**Goal:** Repair the PageIndex client/adaptor path so markdown ingestion no longer triggers the client-layer double donor call and the real PostgreSQL / pgvector retrieval workflow can run successfully.

**Status:** Completed

**Delivered:**
- Client-layer double donor call fix completed
- Adapter-layer unified LLM seam preserved
- Real PostgreSQL / pgvector verification passed
- Real retrieval workflow passed

---

## Phase 2: PageIndex Main-Function Quality Validation and Closure

**Goal:** Move PageIndex from technical integration success to quality-verified main-function readiness.

**Status:** Completed

**Delivered:**
- Quality validation framework established (4 test files, 31 tests passing)
- Validation artifacts generated (4 JSON reports + status board)
- Level progression criteria frozen (Level 2/3/4 with explicit thresholds)
- Fixture-based validation confirms infrastructure correctness
- Commit d080850: feat(phase2): complete PageIndex quality validation framework

**Exit condition achieved:**
Project has explicit quality judgment infrastructure with measurable thresholds
(hit_rate ≥80%, top1_relevance ≥90%, stability ≥85%, tree_depth ≥3, node-chunk ≥80%, heading ≥95%).
Level gates enforce no subjective shortcuts.
