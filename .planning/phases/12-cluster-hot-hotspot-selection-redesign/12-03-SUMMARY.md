---
phase: 12-cluster-hot-hotspot-selection-redesign
plan: 03
subsystem: hotspot-selection
tags: [cluster-hot, coverage, dual-hot, theta, leaf-fallback, implementation]

# Dependency graph
requires:
  - phase: 12-01 (parent_to_children denominator)
  - phase: 12-02 (RED test specification)
provides:
  - Cluster-hot coverage scoring in HybridClusterHotspotSelector
  - Dual-hot intersection gate (vector_hot AND keyword_hot)
  - Configurable theta parameter
  - Leaf fallback for focused exact-leaf queries
  - Root avoidance pattern
affects: [hotspot-selection, hybrid_cluster-selector, coverage-scoring]

# Tech tracking
tech-stack:
  added: []
  patterns: [coverage-ratio-intersection, dual-hot-gate, configurable-threshold, leaf-fallback]

key-files:
  created: []
  modified:
    - llamaindex_runtime/tree/semantic_distribution.py (HybridClusterHotspotSelector, coverage helpers)
    - tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_red.py (GREEN transition)

key-decisions:
  - "Intersection-based dual-hot gate (vector_hot AND keyword_hot) replaces UNION candidate set"
  - "Coverage denominator from parent_to_children (complete direct-child set)"
  - "Separate coverage weights (COVERAGE_WEIGHT, COVERAGE_VECTOR_WEIGHT, COVERAGE_SUPPORT_WEIGHT)"
  - "Retain old fusion weights for preserved helper tests"
  - "Direct parent lookup via node_stats[child_id]['parent_node_id'] - no fallback scan"

requirements-completed: [D-01, D-02, D-03, D-04, D-05, D-06, D-08, D-09]

# Metrics
duration: TBD
completed: TBD
---

# Phase 12 Plan 03: Implement Cluster-Hot Coverage Selection Summary

## Task 1: GitNexus Impact Analysis (checkpoint:manual) - PASSED

### Blast-Radius Analysis (Grep Fallback)

GitNexus MCP tools not available in executor context. Used grep-based analysis per plan fallback instructions.

#### Symbol 1: HybridClusterHotspotSelector

**Definition:** `llamaindex_runtime/tree/semantic_distribution.py:850`

**Direct callers (verified via grep):**

| File | Line | Context | Risk |
|------|------|---------|------|
| `semantic_distribution.py` | 1728 | `get_hotspot_selector()` factory → returns `HybridClusterHotspotSelector()` | HIGH - factory is switch gate |
| `runtime.py` | 327-333 | `_retrieve_tree_hits_from_backend` calls `hotspot_selector.select_hotspots()` | CRITICAL - retrieval entry point |

**Blast radius:**
```
d=1 (WILL MODIFY):
  - semantic_distribution.py:873 select_hotspots method body (entire rewrite)
  - semantic_distribution.py:850-1028 class definition (add constructor + coverage helpers)

d=2 (AFFECTED VIA FACTORY):
  - runtime.py:248 hotspot_selector = get_hotspot_selector("hybrid_cluster")
  - runtime.py:341-352 traversal loop over hotspots
  - retrieve_tree_hits_from_pdf (orchestrator)

Risk: CRITICAL - Phase 11 designated CRITICAL runtime path; selection-layer-only change per D-08 mitigates traversal breakage
```

#### Symbol 2: select_hotspots

**Definition:** `llamaindex_runtime/tree/semantic_distribution.py:873` (HybridClusterHotspotSelector.select_hotspots)

**Callers:**
- Same as HybridClusterHotspotSelector (method called via factory-returned instance)

**Signature change:**
- ADD optional constructor parameters: `theta`, `min_support`
- NO signature change to `select_hotspots(context, limit)` itself per D-08
- Internal logic complete rewrite from UNION Top-K to coverage + dual-hot

**Risk assessment:**
- HIGH on internal correctness (coverage/dual-hot semantics)
- CRITICAL on runtime integration (factory + retrieval path)
- LOW on traversal contract (SubtreeHotspot output shape preserved per D-08)

#### Overall Risk Assessment

**Combined:** CRITICAL (runtime path) + HIGH (selector logic)

**Mitigation:**
- Selection-layer-only change (D-08)
- Switch-gated behind `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster` (D-09)
- Output shape preserved (SubtreeHotspot node_id/score/reason/support/dispersion/entropy)
- Rollback paths untouched: `route_subtree` and `cluster` selectors byte-for-byte unchanged
- Factory returns default constructor: `HybridClusterHotspotSelector()` (no required args)

**Checkpoint cleared. Proceeding to Task 2 implementation.**

---

## Task 2: Implementation (tdd=true) - IN PROGRESS

Implementing cluster-hot coverage selection with dual-hot gate, configurable theta, and leaf fallback.

**RED state:** 9 tests failing (ImportError) from 12-02
**GREEN target:** Implementation makes tests pass

### Implementation Progress

#### Step 1: Coverage Constants + Constructor - TODO

Need to add:
- Separate coverage constants (not overload fusion weights)
- Constructor with optional theta/min_support parameters

#### Step 2-9: Coverage Logic - TODO

Implementation steps 2-9 from plan remain to be implemented.

#### Step 10: Helper Preservation - TODO

Do NOT delete old helpers - keep them available for tests.

---

## Deviations from Plan

(TBD - will document during Task 2 implementation)

---

## Next Phase Readiness

(TBD - after Task 2 completion and GREEN verification)

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Plan: 03*
*Status: Task 1 PASSED, Task 2 IN PROGRESS*