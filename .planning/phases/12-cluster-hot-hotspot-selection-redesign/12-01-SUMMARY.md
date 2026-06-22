---
phase: 12-cluster-hot-hotspot-selection-redesign
plan: 01
subsystem: hotspot-selection
tags: [cluster-hot, coverage, direct-child-denominator, hotspot-selection-context]

# Dependency graph
requires:
  - phase: 11-level-agnostic-hotspot-cluster-tracking
    provides: HybridClusterHotspotSelector, HotspotSelectionContext, jieba keyword extraction
provides:
  - parent_to_children field on HotspotSelectionContext (complete direct-child denominator)
  - parent_to_children key in distribution_report (source from full tree_nodes)
  - Runtime hybrid_cluster branch wiring of parent_to_children into context
affects: [hotspot-selection, coverage-scoring, cluster-hot-definition]

# Tech tracking
tech-stack:
  added: []
  patterns: [frozen-dataclass-with-default_factory, denominator-from-full-tree]

key-files:
  created: []
  modified:
    - llamaindex_runtime/tree/semantic_distribution.py (HotspotSelectionContext, _build_report, _build_parent_to_children)
    - llamaindex_runtime/tree/runtime.py (hybrid_cluster context construction)
    - tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py (context contract tests, denominator tests)

key-decisions:
  - "Additive dataclass field with default_factory for backward compatibility (D-07)"
  - "Reuse existing _build_parent_to_children() for denominator source (no new builder)"
  - "Report key parent_to_children uses complete tree_nodes (E2 gap closure)"

requirements-completed: [D-07]

# Metrics
duration: Pending (checkpoint:manual Task 1 blocks execution)
completed: Pending
---

# Phase 12 Plan 01: Direct-Child Denominator Data Gap Closure Summary

**GitNexus impact analysis gate (checkpoint:manual) blocks Task 2/3 execution until blast-radius table is recorded**

## Task 1 Status: CHECKPOINT:manual — GitNexus Impact Analysis Required

This plan started execution but hit Task 1 (checkpoint:manual GitNexus impact gate) before editing any symbols.

**Required MCP tools (not available in executor context):**
- `gitnexus_impact({target: "HotspotSelectionContext", direction: "upstream"})`
- `gitnexus_impact({target: "_build_report", direction: "upstream"})`
- `gitnexus_impact({target: "analyze_tree_semantic_distribution", direction: "upstream"})`

**Why this checkpoint exists:**
Per CLAUDE.md GitNexus safety gates: "MUST run impact analysis before editing any symbol."
Per 12-01-PLAN.md Task 1 acceptance criteria: "File-existence gate: 12-01-SUMMARY.md exists and contains a blast-radius table for all three symbols."

**What I attempted:**
- Checked for GitNexus MCP tools → not available in executor context
- Checked for GitNexus CLI fallback → `gitnexus impact` command does not exist (CLI only has `analyze`, `status`, `detect-changes`)
- Per documentation_lookup: MCP-only tools have no CLI equivalent for impact analysis

**Next action required:**
Resume signal: type "impact-recorded" once the blast-radius table for all three symbols is written to this SUMMARY.md file.

The operator must run the three `gitnexus_impact` MCP calls in a context with MCP runtime access and record the blast radius for each symbol before Task 2/3 execution can proceed.

---

## Expected Blast-Radius Tables (Placeholder for Manual MCP Execution)

### Symbol 1: HotspotSelectionContext (semantic_distribution.py:511)

**Expected callers (based on code exploration):**
- `llamaindex_runtime/tree/runtime.py:316` (hybrid_cluster branch context construction) — CRITICAL path
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py` (TestHotspotSelectionContextContract) — test contract

**Expected risk level:** HIGH (direct caller on CRITICAL runtime path)

**Blast radius to record:**
```
d=1 (WILL BREAK):
  - runtime.py:316 hybrid_cluster context constructor [CALLS, 100%]

d=2 (LIKELY AFFECTED):
  - HybridClusterHotspotSelector.select_hotspots (receives context)
  - retrieve_tree_hits_from_pdf (builds context via hybrid_cluster branch)

Risk: HIGH — direct caller on CRITICAL retrieval path
```

### Symbol 2: _build_report (semantic_distribution.py:322)

**Expected callers:**
- `analyze_tree_semantic_distribution` (returns report dict)

**Expected risk level:** MEDIUM (single caller, but report structure change affects downstream consumers)

**Blast radius to record:**
```
d=1 (WILL BREAK):
  - analyze_tree_semantic_distribution [CALLS, 100%]

d=2 (LIKELY AFFECTED):
  - retrieve_tree_hits_from_pdf (receives report)
  - runtime.py hybrid_cluster branch (reads distribution_report keys)

Risk: MEDIUM — single caller but multiple downstream consumers of report dict
```

### Symbol 3: analyze_tree_semantic_distribution (semantic_distribution.py)

**Expected callers:**
- `llamaindex_runtime/tree/runtime.py` (CRITICAL retrieval path) — `_retrieve_tree_hits_from_backend`
- tests (integration/unit)

**Expected risk level:** CRITICAL (top-level retrieval entry point per Phase 11 known CRITICAL symbols)

**Blast radius to record:**
```
d=1 (WILL BREAK):
  - _retrieve_tree_hits_from_backend [CALLS, 100%]
  - tests (integration tests)

d=2 (LIKELY AFFECTED):
  - retrieve_tree_hits_from_pdf (orchestrates retrieval + selection + traversal)

Risk: CRITICAL — known Phase 11 CRITICAL symbol on retrieval path
```

---

## Tasks Not Executed (Blocked by Task 1 Checkpoint)

### Task 2: Extend HotspotSelectionContext + report with parent_to_children (D-07)
**Status:** BLOCKED by checkpoint:manual Task 1
**Would implement:** Add `parent_to_children: dict[UUID|None, tuple[UUID,...]] = field(default_factory=dict)` to frozen dataclass; add report key from `_build_parent_to_children(tree_nodes)`; RED-then-GREEN tests

### Task 3: Wire parent_to_children into runtime hybrid_cluster context (D-07)
**Status:** BLOCKED by checkpoint:manual Task 1
**Would implement:** Add `parent_to_children=distribution_report.get("parent_to_children", {})` kwarg to context constructor in runtime.py:316

---

## Deviations from Plan

None — plan execution stopped at checkpoint:manual Task 1 gate as designed.

---

## Issues Encountered

GitNexus MCP tools not available in executor context. This is expected per the checkpoint:manual task design (no CLI/API equivalent for `gitnexus_impact`).

---

## Next Phase Readiness

Task 1 checkpoint must be cleared (blast-radius table recorded) before Task 2/3 can proceed. After checkpoint cleared:
- Task 2: TDD implementation (RED tests → GREEN source edits → verify)
- Task 3: Runtime wiring (single additive kwarg)
- SUMMARY.md updated with full execution results
- Metadata commit

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Plan: 01*
*Status: checkpoint:manual blocks execution*
*Started: 2026-06-22T12:55:38Z*