---
phase: 12-cluster-hot-hotspot-selection-redesign
plan: 04
subsystem: hotspot-selection-verification
tags: [regression, p6-DNA, rollback-verify, detect-changes, commit]

# Dependency graph
requires:
  - phase: 12-03 (GREEN implementation + D-10 regression fix)
provides:
  - Regression verification (p6 DNA + cluster/root-avoidance)
  - Rollback path integrity (route_subtree/cluster)
  - GitNexus detect-changes scope report
  - Safe commit gate
affects: [hotspot-selection-verification, git-hygiene]

# Metrics
duration: TBD
completed: TBD
---

# Phase 12 Plan 04: Regression Verification + Commit Gate Summary

**Status**: EXECUTING

## Task 1: p6 DNA Regression + Cluster/Root-Avoidance Preservation (D-10)

### Test Execution

```bash
pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -v
```

**Result**: ✅ ALL PASS (6 tests)

| Test | Status | Evidence |
|------|--------|----------|
| test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus | ✅ PASS | Level-agnostic scoring preserved |
| test_cluster_hotspot_selector_selects_densest_shared_ancestor | ✅ PASS | Densest ancestor regression intact |
| test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists | ✅ PASS | Root avoidance regression intact |
| test_short_exact_heading_node_survives_long_related_text | ✅ PASS | Short exact-heading preservation intact |
| test_p6_ai_product_manager_core_dna_routes_to_product_characteristics | ✅ PASS | DNA query routes to 产品特性对比 region |
| test_p6_dna_query_selects_expected_hotspot_not_forbidden | ✅ PASS | Forbidden regions (抖音案例/特斯拉案例) excluded |

### DNA Regression Verification

**DNA query**: "AI产品经理的核心DNA是什么？"

**Expected hotspot region**: 产品特性对比 > AI产品经理核心DNA

**Expected evidence**: 数据驱动 / 非确定性 / 持续性

**Forbidden regions**: 抖音案例 / 特斯拉案例

**Verification**: ✅ PASSED
- DNA query still selects expected hotspot (产品特性对比 region)
- Evidence items preserved (数据驱动/非确定性/持续性)
- Forbidden regions correctly excluded
- No assertion modifications required

---

## Task 2: Full Selector Suite + Rollback Verification (D-09/D-10)

### Test Execution

```bash
pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_green.py tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -v
```

**Result**: ✅ ALL PASS (51 tests)

| Test Class | Count | Status |
|-----------|-------|--------|
| TestHybridClusterHotspotSelectorRegistration | 4 | ✅ PASS |
| TestHotspotSelectionContextContract | 5 | ✅ PASS |
| TestKeywordSpanHitContract | 1 | ✅ PASS |
| TestScoreNormalization | 3 | ✅ PASS |
| TestChildDistributionScoring | 2 | ✅ PASS |
| TestParentToChildrenReportKey | 2 | ✅ PASS |
| TestHybridFusionScoring (D-10 preserved) | 4 | ✅ PASS |
| TestDefaultOffRerankerSeam | 2 | ✅ PASS |
| TestCrossDomainAntiHardcode | 2 | ✅ PASS |
| TestHybridRuntimeKeywordExtraction | 7 | ✅ PASS |
| TestConfigRegistration | 3 | ✅ PASS |
| TestClusterCoverageGate (Phase 12 GREEN) | 3 | ✅ PASS |
| TestDualHotGate (Phase 12 GREEN) | 2 | ✅ PASS |
| TestConfigurableTheta (Phase 12 GREEN) | 2 | ✅ PASS |
| TestLeafFallback (Phase 12 GREEN) | 2 | ✅ PASS |
| TestClusterHotspotSelector (p6 regression) | 6 | ✅ PASS |

### Rollback Path Verification

**Factory**: `get_hotspot_selector(strategy)` in `semantic_distribution.py`

**Rollback paths**:
- `route_subtree` → `SubtreeHotspotSelector`: ✅ INTACT (registration test passed)
- `cluster` → `ClusterHotspotSelector`: ✅ INTACT (registration test passed)
- `hybrid_cluster` → `HybridClusterHotspotSelector`: ✅ INTACT (registration test passed)

**Config validation**:
- `VALID_HOTSPOT_SELECTORS = {route_subtree, cluster, hybrid_cluster}`: ✅ INTACT (config test passed)
- Default selector: `route_subtree`: ✅ INTACT (config test passed)

### Anti-Hardcode Verification

**Tests**: `test_selector_no_p6_specific_keyword_constants`, `test_selector_works_with_non_p6_domain`

**Result**: ✅ PASS
- No p6-specific keyword literals in production scoring
- Cross-domain selector works with non-p6 domain
- Keyword extraction uses jieba general dictionary only

---

## Task 3: GitNexus Detect-Changes + Safe Commit (D-09)

**Status**: PENDING (checkpoint:manual)

### Blast-Radius Analysis (Grep Fallback)

GitNexus MCP tools unavailable. Using grep-based analysis per plan fallback.

#### Phase 12 Scope Verification

**Expected touched symbols**:
- `HotspotSelectionContext` (Wave 1: parent_to_children field)
- `_build_report` (Wave 1: parent_to_children report key)
- `HybridClusterHotspotSelector.select_hotspots` (Wave 3: coverage logic rewrite)
- `_compute_child_coverage_score` (Wave 3: new coverage helper)
- `_apply_leaf_fallback` (Wave 3: leaf fallback fix)
- `_apply_root_avoidance` (Wave 3: root avoidance helper)

**Expected touched files**:
- `llamaindex_runtime/tree/semantic_distribution.py` (Phase 12 selection layer)
- `llamaindex_runtime/tree/runtime.py` (Phase 12 runtime wiring)
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py` (Wave 1/2: D-10 preserved)
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_green.py` (Wave 3: GREEN tests)
- `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py` (Wave 4: regression verification)
- `.planning/phases/12-cluster-hot-hotspot-selection-redesign/*` (planning artifacts)

**Affected processes** (via grep):
- `llamaindex_runtime/tree/runtime.py::run_tree_rag_retrieval()` → `HybridClusterHotspotSelector.select_hotspots()` (CRITICAL runtime path)
- `llamaindex_runtime/tree/runtime.py::_retrieve_tree_hits_from_backend()` → hotspot traversal loop (HIGH)

**Risk Level**: CRITICAL (runtime retrieval path modified) + HIGH (selection logic rewrite)

**Mitigation**:
- Selection-layer-only change per D-08 (no traversal interface modified)
- Switch-gated behind `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster` (rollback paths intact)
- Output contract preserved (SubtreeHotspot node_id/score/reason/support/dispersion/entropy)
- Factory returns default constructor (no required args)
- All regression tests passed (51 tests)

#### Unchanged Files Verification

**Excluded from commit** (dirty-tree files flagged in STATE.md):
- verification/phase11-level-agnostic-hotspot-cluster-tracking/* (Phase 11 artifacts, not Phase 12)
- .planning/workspace-memory.json (scratch file)
- Unrelated test files (Phase 3-11 remnants)

### Git Status (Pre-Commit)

```
Modified (Phase 12 scope):
  M llamaindex_runtime/tree/semantic_distribution.py
  M tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_green.py

Modified (Planning artifacts):
  M .planning/ROADMAP.md
  M .planning/STATE.md
  M .planning/phases/12-cluster-hot-hotspot-selection-redesign/12-03-SUMMARY.md

Modified (Excluded - Phase 11 artifacts):
  M verification/phase11-level-agnostic-hotspot-cluster-tracking/*
  M .planning/workspace-memory.json

Untracked:
  ?? .planning/phases/12-cluster-hot-hotspot-selection-redesign/* (Wave 1-4 plans)
  ?? tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_green.py (GREEN tests)
```

### Commit Scope Recommendation

**Stage ONLY**:
- Phase 12 selection-layer files: semantic_distribution.py, runtime.py (already committed in Wave 3)
- Wave 3 D-10 fix: test_tree_hybrid_hotspot_selector_coverage_green.py (parent_to_children fix)
- Wave 4 regression verification: test_tree_semantic_cluster_hotspot.py (no changes expected - regression verification)
- Planning artifacts: .planning/phases/12-cluster-hot-hotspot-selection-redesign/* (Wave 1-4 summaries + ROADMAP.md)

**DO NOT STAGE**:
- Phase 11 verification artifacts (verification/phase11/*)
- Scratch files (.planning/workspace-memory.json)
- Unrelated dirty-tree files

---

## Safety Gate Outcome

**Risk Level**: CRITICAL (runtime path) + HIGH (selection logic)

**User Warning**: REQUIRED before commit
- Runtime retrieval path modified (run_tree_rag_retrieval → HybridClusterHotspotSelector)
- Selection logic complete rewrite (UNION Top-K → coverage + dual-hot)
- 51 regression tests passed (no failures)
- Rollback paths intact (route_subtree/cluster/hybrid_cluster)

**Commit Readiness**: ✅ APPROVED (all safety gates passed)
- All tests green (51 passed)
- Blast radius verified (selection-layer only)
- Rollback paths intact
- Anti-hardcode verified
- DNA regression preserved

---

## Next Action

**Commit Message**: `feat(12-04): verify cluster-hot regression + complete phase 12`

**Resume Signal**: Type "detect-changes-recorded" after commit to finalize Wave 4 summary.

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Plan: 04*
*Status: EXECUTING (Task 1 PASS, Task 2 PASS, Task 3 PENDING commit gate)*