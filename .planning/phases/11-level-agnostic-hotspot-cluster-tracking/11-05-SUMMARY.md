---
phase: 11-level-agnostic-hotspot-cluster-tracking
plan: 05
subsystem: semantic-distribution
tags: [gap-closure, cluster-scoring, weight-adjustment, regression-test]
dependency_graph:
  requires: [11-01, 11-02, 11-03, 11-04]
  provides: [WR-01-fix, cluster-density-prioritization]
  affects: [ClusterHotspotSelector, DNA-query-validation]
tech_stack:
  added: []
  patterns: [cluster-scoring-weight-adjustment, regression-test]
key_files:
  created: []
  modified:
    - llamaindex_runtime/tree/semantic_distribution.py (_score_cluster weights)
    - tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py (regression test)
decisions:
  - Reduce max_score weight from 0.40 to 0.20 to prevent single-node dominance
  - Increase avg_score weight from 0.30 to 0.35 to prioritize cluster consistency
  - Increase support weight from 0.20 to 0.30 to reward cluster breadth
  - Increase density weight from 0.10 to 0.15 to reward tight clustering
  - Create regression test validating DNA query hotspot selection fix
metrics:
  duration: ~10 minutes
  completed_date: 2026-06-18T03:52:32Z
  task_count: 2
  file_count: 2
---

# Phase 11 Plan 05: Cluster Scoring Weight Adjustment Summary

## One-Liner

Adjusted ClusterHotspotSelector scoring formula weights to prioritize dense clusters over isolated high-similarity nodes, fixing DNA query hotspot selection failure.

## Objective

Fix root cause of DNA query selecting forbidden hotspot region (抖音案例) instead of expected hotspot region (产品特性对比) by reducing max_score weight from 40% to 20% and increasing avg_score, support, and density weights.

## Context

Phase 11 validation failed because cluster scoring formula with max_score 40% weight caused isolated high-similarity node (抖音案例 0.69) to win over dense cluster (产品特性对比 0.57 avg). This violated D-02 design intent: "densest shared local region".

## Implementation

### Task 1: Adjust Cluster Scoring Formula Weights

Modified `_score_cluster` function in `llamaindex_runtime/tree/semantic_distribution.py`:

**Before:**
- max_score: 0.40 (40%) — **PROBLEMATIC**
- avg_score: 0.30 (30%)
- normalized_support: 0.20 (20%)
- density: 0.10 (10%)

**After:**
- max_score: 0.20 (20%) — reduced to prevent single-node dominance
- avg_score: 0.35 (35%) — increased to prioritize cluster consistency
- normalized_support: 0.30 (30%) — increased to reward cluster breadth
- density: 0.15 (15%) — increased to reward tight clustering

**Rationale:** Current 40% max_score weight caused "single highest similarity wins" instead of "densest shared local region". New weights prioritize avg_score (cluster consistency) and support (cluster breadth) over single max_score.

**Commit:** a2eeda4

### Task 2: Create DNA Query Regression Test

Added `test_p6_dna_query_selects_expected_hotspot_not_forbidden` in `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py`:

**Test Structure:**
- Mock setup: two competing clusters
  - Forbidden cluster: single node with similarity 0.69 (抖音案例)
  - Expected cluster: two nodes with similarity 0.57 avg (产品特性对比) — dense cluster
- Query embedding produces 0.69 similarity with forbidden, 0.57 with expected
- Test asserts hotspot is NOT forbidden region
- Test asserts hotspot IS expected region (产品特性对比 or its child DNA node)

**Validation:** Test passes with adjusted weights, validating fix correctness.

**Commit:** d6801be

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stubs introduced.

## Threat Flags

None — no new security-relevant surface introduced.

## Gaps Addressed

**WR-01: Cluster scoring formula max_score weight (40%) causes wrong hotspot selection**

- **Root Cause:** max_score 40% weight allowed isolated high-similarity node (抖音案例 0.69) to win over dense cluster (产品特性对比 0.57 avg), violating D-02 design intent.
- **Fix:** Reduced max_score weight to 20%, increased avg_score to 35%, support to 30%, density to 15%.
- **Validation:** Regression test passes, all 6 cluster tests pass.

**Gap 1: DNA query selected forbidden hotspot region instead of expected region**

- **Symptom:** validation_status.json shows dna_forbidden_hotspot_selected=true.
- **Fix:** Weight adjustment ensures dense cluster wins over isolated high-similarity node.
- **Validation:** Regression test explicitly asserts forbidden region is NOT selected.

## Verification

- grep verification confirms weight values in code (0.20/0.35/0.30/0.15)
- pytest verification confirms regression test passes
- Full cluster test suite: 6 tests passing (5 existing + 1 new regression test)

## Success Criteria

- [x] _score_cluster uses adjusted weights (max 0.20, avg 0.35, support 0.30, density 0.15)
- [x] DNA query regression test exists and passes
- [x] Test validates hotspot selection matches expected region, not forbidden region
- [x] No other cluster tests broken by weight adjustment

## Commits

1. **a2eeda4** — fix(11-05): adjust cluster scoring weights to prioritize density
2. **d6801be** — test(11-05): add DNA query regression test for hotspot selection

## Next Steps

Await checkpoint approval before proceeding to validation rerun.

---

**Self-Check: PASSED**

- [x] Created files exist: test_tree_semantic_cluster_hotspot.py contains new test
- [x] Commits exist: a2eeda4 and d6801be in git log
- [x] All tests pass: 6 cluster tests passing