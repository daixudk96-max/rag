---
phase: 11-level-agnostic-hotspot-cluster-tracking
plan: 02
type: execute
wave: 2
autonomous: true
requirements: [REQ-11-NO-ROUTE-BONUS, REQ-11-DENSEST-ANCESTOR, REQ-11-ROOT-AVOIDANCE, REQ-11-SHORT-NODE]
requirements_addressed: [D-01, D-02, D-03, D-04, D-08]
key_files:
  created:
    - tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py (test fixtures fixed)
  modified:
    - llamaindex_runtime/tree/semantic_distribution.py
decisions:
  - "GitNexus impact analysis completed before edits per D-08: SubtreeHotspotSelector, RecursiveTreeTraversalRunner, QueryHit all MEDIUM risk (14 impacted files, 6 direct callers each)"
  - "Test fixture bugs fixed as Rule 1 deviations: parent embedding [0.6, 0.8] for cosine sim 0.6, missing parent_node_id fields added"
  - "Task 3 requirements satisfied in Task 2 implementation due to overlapping scope"
metrics:
  duration_seconds: 3277
  task_count: 3
  completed_tasks: 3
  file_count: 2
  test_count: 5
  red_tests: 0
  green_tests: 5
---

# Phase 11 Plan 02: ClusterHotspotSelector Implementation Summary

## One-Liner

Implemented ClusterHotspotSelector with level-agnostic similarity-only scoring, ancestor clustering, and cluster-based hotspot inference, passing all 5 Wave 1 tests.

## Execution Timeline

- **Start**: 2026-06-17T13:53:14Z
- **End**: 2026-06-17T14:47:50Z
- **Duration**: 3277 seconds (~55 minutes)
- **Status**: Complete (GREEN gate achieved)

## Tasks Completed

### Task 1: Add immutable cluster contracts and run GitNexus impact analysis ✓

**Status**: Complete
**Commit**: c2c79c2
**Files**: llamaindex_runtime/tree/semantic_distribution.py

**Implementation**:
- Added `NodeSemanticHit` dataclass (level-agnostic semantic candidate)
- Added `ClusterCandidate` dataclass (ancestor cluster aggregation)
- Both use `@dataclass(frozen=True)` per Phase 11 requirements
- Preserved existing `SubtreeHotspotSelector` and `QueryHit` unchanged

**GitNexus Impact Analysis (D-08 compliance)**:
- SubtreeHotspotSelector: MEDIUM risk, 14 impacted files, 6 direct callers
- RecursiveTreeTraversalRunner: MEDIUM risk, 14 impacted files, 6 direct callers
- QueryHit: MEDIUM risk, 14 impacted files, 6 direct callers
- No HIGH or CRITICAL risk symbols identified

**Acceptance criteria met**:
- [x] File contains exact strings `class NodeSemanticHit` and `class ClusterCandidate`
- [x] Both classes use exact decorator `@dataclass(frozen=True)`
- [x] Existing `class SubtreeHotspotSelector` and `class QueryHit` preserved
- [x] GitNexus impact analysis reported for HIGH-risk semantic symbols (all MEDIUM)

### Task 2: Implement similarity-only candidate collection and ancestor clustering ✓

**Status**: Complete
**Commit**: 85e80e9
**Files**: llamaindex_runtime/tree/semantic_distribution.py, tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py

**Implementation**:
- Added `ClusterHotspotSelector` class with `select_hotspots` method
- Dimension validation identical to `SubtreeHotspotSelector`
- Similarity-only scoring: `_cosine_similarity(query_embedding, prototype)` with NO bonuses (D-01)
- Candidate breadth: `candidate_top_n = max(limit * 4, 20)` (D-03)
- Ancestor clustering: `_build_ancestor_clusters` aggregates candidates under each ancestor (D-02)
- Cluster scoring formula: `max_score * 0.40 + avg_score * 0.30 + normalized_support * 0.20 + density * 0.10` (D-02)
- Helper functions: `_build_path_to_root`, `_build_ancestor_clusters`, `_count_subtree_candidates`, `_score_cluster`

**Test fixture fixes (Rule 1 deviations)**:
- Fixed parent embedding: [0.6, 0.0] → [0.6, 0.8] to achieve cosine similarity 0.6 with query [1.0, 0.0]
  - Original embedding [0.6, 0.0] had similarity 1.0 (normalized matches query direction)
  - Fixed embedding [0.6, 0.8] has similarity 0.6 (cos(53°) angle difference)
- Added missing `parent_node_id` fields in p6 regression test fixture
  - DNA node: parent_node_id = product_characteristics_id
  - Product node: parent_node_id = root_id
  - Douyin/Data/Tesla nodes: parent_node_id = root_id
- Fixes applied to tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py

**Acceptance criteria met**:
- [x] File contains exact string `class ClusterHotspotSelector`
- [x] File contains exact string `candidate_top_n = max(limit * 4, 20)`
- [x] Selector uses `_cosine_similarity(query_embedding, prototype)` without bonus logic
- [x] Selector code path does NOT contain `_ROUTE_NODE_BONUS`, `_DEPTH_BONUS_PER_LEVEL`, `_SUPPORT_BONUS_PER_CHUNK`, or `is_route_node` as scoring inputs
- [x] Test `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus` passes

### Task 3: Implement cluster scoring, root avoidance, and hotspot return shape ✓

**Status**: Complete (implemented in Task 2)
**Files**: llamaindex_runtime/tree/semantic_distribution.py (no changes since Task 2)

**Implementation (completed in Task 2)**:
- Cluster scoring with exact weights: 0.40, 0.30, 0.20, 0.10
- Root exclusion logic: `non_root_clusters` preferred over root clusters (D-04)
- Root fallback: root selected only when no non-root candidates exist
- Hotspot return shape: `SubtreeHotspot` objects with inferred ancestor_node_id, cluster score, and metadata
- Short exact nodes can survive as their own hotspot (validated by tests)

**Acceptance criteria met**:
- [x] File contains exact numeric constants `0.40`, `0.30`, `0.20`, `0.10` in cluster scoring
- [x] File contains logic that excludes root when non-root candidate exists
- [x] All tests in `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py` pass (5/5)
- [x] Existing `SubtreeHotspotSelector` preserved unchanged

## Deviations from Plan

### Rule 1 - Bug: Fixed incorrect parent embedding in test fixture

**Found during**: Task 2 test execution
**Issue**: Test fixture set parent prototype_embedding to [0.6, 0.0], expecting similarity 0.6 with query [1.0, 0.0], but cosine similarity calculation gave 1.0 (both vectors normalized to [1.0, 0.0] direction)
**Fix**: Changed parent embedding to [0.6, 0.8] which achieves cosine similarity 0.6 with query [1.0, 0.0] (cos(53°) angle difference)
**Files modified**: tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py
**Commit**: 85e80e9

### Rule 1 - Bug: Added missing parent_node_id fields in test fixture

**Found during**: Task 2 test execution (p6 regression test)
**Issue**: Test fixture node_stats missing `parent_node_id` fields required by `_build_path_to_root` function, causing path_to_root construction to fail
**Fix**: Added parent_node_id fields for all 5 nodes in p6 regression test:
  - DNA node → product_characteristics_id
  - Product node → root_id
  - Douyin/Data/Tesla nodes → root_id
**Files modified**: tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py
**Commit**: 85e80e9

### Overlapping Task Scope

**Found during**: Task 3 verification
**Issue**: Task 3 acceptance criteria already satisfied by Task 2 implementation (cluster scoring, root avoidance, hotspot return shape)
**Resolution**: Task 3 marked complete without additional changes; implementation already meets all criteria
**Files modified**: None (Task 2 commit satisfies Task 3)

## Verification Evidence

### Cluster Hotspot Tests

```bash
$ python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q
.....                                                                    [100%]
5 passed in 0.52s
```

**Tests passing**:
- test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus (D-01, D-03)
- test_cluster_hotspot_selector_selects_densest_shared_ancestor (D-02)
- test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists (D-04)
- test_short_exact_heading_node_survives_long_related_text (D-05)
- test_p6_ai_product_manager_core_dna_routes_to_product_characteristics (D-07)

### Old Hotspot Tests

```bash
$ python -m pytest tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q
ERROR collecting tests/llamaindex_runtime/test_tree_semantic_hotspot.py
ImportError: ModuleNotFoundError: No module named 'llamaindex_runtime.ingestion'
```

**Status**: Cannot run in worktree due to missing ingestion module dependency
**Expected**: Test will pass in main repo after merge (SubtreeHotspotSelector unchanged)

### GitNexus Impact Analysis

```bash
$ npx gitnexus impact SubtreeHotspotSelector --repo rag
MEDIUM risk, 14 impacted files, 6 direct callers

$ npx gitnexus impact RecursiveTreeTraversalRunner --repo rag
MEDIUM risk, 14 impacted files, 6 direct callers

$ npx gitnexus impact QueryHit --repo rag
MEDIUM risk, 14 impacted files, 6 direct callers
```

**Risk level**: MEDIUM for all three symbols (not HIGH or CRITICAL)
**Direct callers**: 6 files (demo scripts, validation scripts, runtime.py)
**Affected processes**: 0 (no execution flow disruption)

## Success Criteria Checklist

- [x] `NodeSemanticHit`, `ClusterCandidate`, and `ClusterHotspotSelector` exist in semantic_distribution.py
- [x] New cluster tests pass (5/5)
- [x] Old `SubtreeHotspotSelector` behavior remains available and unchanged for rollback
- [x] GitNexus impact analysis for HIGH-risk semantic symbols reported in summary (all MEDIUM risk)

## Threat Flags

None - no new security-relevant surface introduced. Implementation uses existing cosine similarity helper and proven ancestor walking pattern.

## Known Stubs

None - all implementation is complete and functional.

## Self-Check: PASSED

- [x] Created/modified files exist: semantic_distribution.py, test_tree_semantic_cluster_hotspot.py, 11-02-SUMMARY.md
- [x] Commits exist: c2c79c2 (Task 1), 85e80e9 (Task 2)
- [x] No unexpected deletions in commits
- [x] All 5 cluster tests present and passing
- [x] GREEN state validated (tests import and execute successfully)
- [x] GitNexus impact analysis completed before edits per D-08

---

**Phase**: 11-level-agnostic-hotspot-cluster-tracking
**Plan**: 02 (GREEN implementation)
**Status**: Complete
**Next**: Plan 11-03 (REFACTOR) or Plan 11-04 (VALIDATION)