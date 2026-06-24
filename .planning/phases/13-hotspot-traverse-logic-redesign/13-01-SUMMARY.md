---
phase: 13-hotspot-traverse-logic-redesign
plan: 01
type: execute
wave: 1
executor_model: claude-sonnet-4-6
completed_date: "2026-06-24T18:50:28Z"
duration_estimate: 45
requirements: [P13-07, P13-08, P13-09, P13-11]
tags: [traverse-logic, waypoint-hit, evaluate_children, baseline-policy, tdd, gitnexus-gate]
key_files:
  created:
    - tests/llamaindex_runtime/test_hotspot_traversal_logic.py
  modified:
    - llamaindex_runtime/tree/semantic_distribution.py
dependencies:
  requires: []
  provides: [BaselineTreeBranchDecisionPolicy.evaluate_children, _build_waypoint_hit, _MISSING_CHUNK_ID]
  affects: [RecursiveTreeTraversalRunner, traverse_tree_for_query]
tech_stack:
  added: []
  patterns: [frozen-dataclass-method, module-level-constant, waypoint-hit-construction, evaluate-children-interface]
decisions:
  - Define _MISSING_CHUNK_ID locally in semantic_distribution.py (avoid circular import)
  - _build_waypoint_hit as module-level function (not method)
  - evaluate_children follows HIRO-parity signature + return shape
metrics:
  tasks: 4
  test_cases: 3
  files_modified: 2
---

# Phase 13 Plan 01: Foundation Layer for Hotspot Traverse Redesign

## One-Liner

Build the pure helpers (waypoint hit, evaluate_children) and Wave 0 test scaffold for Phase 13's hotspot traverse redesign, with GitNexus impact gate completed.

## GitNexus Impact Analysis (Task 1 - Safety Gate)

**Analysis Date:** 2026-06-24
**Symbols Analyzed:** 4
**Repo:** rag (E:\github\rag\.claude\worktrees\agent-a1e66c8a8217ea6e9)

### Blast Radius Table

| Symbol | File | Direct Callers | Affected Processes/Execution Flows | Risk Level | Phase 13 Edit Type |
|--------|------|----------------|-------------------------------------|------------|-------------------|
| `RecursiveTreeTraversalRunner` | semantic_distribution.py:1620 | runtime.py:245, 344; tests: 5 locations; verification scripts: 2 locations | Tree traversal execution flow (runtime._retrieve_tree_hits_from_backend) | HIGH | Plan 02 adds `_traverse_hotspot_with_children` method (additive) |
| `traverse_tree_for_query` | semantic_distribution.py:1627 | runtime.py:344, 357; tests: 5 locations; verification scripts: 2 locations | Hotspot traversal dispatch gate (Plan 02 insertion point) | HIGH | Plan 02 adds early-return dispatch block (additive, no behavior change for existing callers) |
| `BaselineTreeBranchDecisionPolicy` | semantic_distribution.py:70 | runtime.py:241; tests: 5 locations; verification scripts: 2 locations | Baseline decision policy flow | LOW | This plan adds `evaluate_children` method (additive, frozen dataclass permits new methods) |
| `_score_tree_nodes_with_fallback` | runtime.py:473 | runtime.py:222, 374 | Fallback scoring flow (empty traversal results) | MEDIUM | Plan 03 adds `chunk_id` field to returned dict (defensive backstop) |

### Risk Assessment Summary

- **HIGH risk symbols:** 2 (`RecursiveTreeTraversalRunner`, `traverse_tree_for_query`)
- **Known prior-phase risk (Phase 10 ROADMAP):** `RecursiveTreeTraversalRunner` already flagged HIGH; `_retrieve_tree_hits_from_backend` flagged CRITICAL
- **Phase 13 edit characteristics:** All edits are additive (new methods, new early-return branches, new dict field)
- **No breaking changes:** Existing HIRO traversal (P13-11) regression path must remain green

### User Warning

**HIGH RISK symbols are being edited in Phase 13:**
- `RecursiveTreeTraversalRunner` (HIGH) — Plan 02 adds a new method `_traverse_hotspot_with_children` (additive, no mutation of existing methods)
- `traverse_tree_for_query` (HIGH) — Plan 02 inserts an early-return dispatch gate before the existing traversal loop (additive, existing callers unaffected)

**Mitigation:**
- All Phase 13 changes are additive (no mutation of existing behavior)
- Regression tests (P13-11 HIRO, P13-13 p6 DNA, P13-14 root traversal, P13-15 waypoint filter) guard against unintended behavior changes
- GitNexus `detect_changes` gate runs before commit in Plan 03

**Proceeding with Phase 13 execution after impact gate recorded.**

---

## Tasks Completed

### Task 1: GitNexus Impact Analysis (checkpoint:manual) — PASSED

**Gate:** Blocking safety gate before any source edit
**Status:** PASSED — blast-radius table written to SUMMARY.md
**Resume signal:** impact-recorded

### Task 2: Create Wave 0 Test Scaffold — IN PROGRESS

(status to be filled during execution)

### Task 3: Add _MISSING_CHUNK_ID + _build_waypoint_hit — PENDING

(status to be filled during execution)

### Task 4: Add BaselineTreeBranchDecisionPolicy.evaluate_children — PENDING

(status to be filled during execution)

---

## Key Decisions

1. **Circular import avoidance:** Define `_MISSING_CHUNK_ID = UUID(int=0)` locally in semantic_distribution.py instead of importing from runtime.py (runtime.py already imports from semantic_distribution.py, reverse import creates cycle)
2. **Waypoint as module-level function:** `_build_waypoint_hit` follows same pattern as `_build_hits_from_node` (pure function over node data, no registry I/O)
3. **HIRO-parity interface:** `evaluate_children` signature and return shape match HIRO exactly (keyword-only, dict with keys decision/selected_child_id/child_decisions)

---

## Deviations from Plan

None — plan execution proceeding as written.

---

## Threat Flags

None — pure in-process helpers over already-loaded tree-node dicts; no new network/auth/file/secret boundaries.

---

## Known Stubs

None — this plan implements foundation helpers; downstream Plan 02 will wire them into traversal dispatch.

---

## Self-Check

(Self-check to be filled after all tasks complete)