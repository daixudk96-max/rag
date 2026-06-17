---
phase: 11-level-agnostic-hotspot-cluster-tracking
plan: 01
type: tdd
wave: 1
autonomous: true
requirements: [REQ-11-NO-ROUTE-BONUS, REQ-11-DENSEST-ANCESTOR, REQ-11-ROOT-AVOIDANCE, REQ-11-SHORT-NODE, REQ-11-P6-REGRESSION]
requirements_addressed: [D-01, D-02, D-03, D-04, D-05, D-07]
key_files:
  created:
    - tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py
  modified: []
decisions:
  - "All 5 tests created in single file for atomic RED gate validation"
  - "Tests import non-existent ClusterHotspotSelector to ensure RED state"
  - "Fixture-based mocking simulates adapter output without DB dependency"
metrics:
  duration_seconds: 500
  task_count: 3
  completed_tasks: 3
  file_count: 1
  test_count: 5
  red_tests: 5
  green_tests: 0
---

# Phase 11 Plan 01: Level-Agnostic Hotspot Cluster Selector RED Tests Summary

## One-Liner

Created 5 pytest tests for ClusterHotspotSelector semantics covering D-01 through D-07, establishing TDD RED gate for Phase 11 level-agnostic cluster-based hotspot tracking.

## Execution Timeline

- **Start**: 2026-06-17T13:26:10Z
- **End**: 2026-06-17T13:34:30Z
- **Duration**: 500 seconds (~8 minutes)
- **Status**: Complete (RED gate established)

## Tasks Completed

### Task 1: Add RED tests for unbiased scoring and candidate breadth ✓

**Status**: Complete
**Commit**: 4f26ad0
**Files**: tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py

**Test created**:
- `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus` (D-01, D-03)

**RED validation**:
- ImportError: ClusterHotspotSelector does not exist (expected)
- No route-node bonus, depth bonus, or support bonus fields allowed
- Candidate breadth validated via fixture coverage

**Key decisions**:
- Used MagicMock registry pattern from Phase 10 tests
- Manual node_stats construction simulates adapter output
- Query embedding [1.0, 0.0] matches child evidence node

### Task 2: Add RED tests for densest ancestor and root avoidance ✓

**Status**: Complete (included in Task 1 commit)
**Files**: tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py (same file)

**Tests added**:
- `test_cluster_hotspot_selector_selects_densest_shared_ancestor` (D-02)
- `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists` (D-04)

**Fixture structure**:
- Tree: Root -> A -> A1/A2/A3 (cluster with 3 hits)
- Tree: Root -> B -> B1 (highest single hit)
- Similarities: A1=0.85, A2=0.80, A3=0.70, B1=0.90
- Expected: A subtree wins over isolated B1 hit

**Key decisions**:
- Cluster scoring formula weights embedded in assertions
- Root penalty logic validated via root rejection
- Local ancestor preference over broad root hotspot

### Task 3: Add RED tests for short exact node and p6 DNA regression ✓

**Status**: Complete (included in Task 1 commit)
**Files**: tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py (same file)

**Tests added**:
- `test_short_exact_heading_node_survives_long_related_text` (D-05)
- `test_p6_ai_product_manager_core_dna_routes_to_product_characteristics` (D-07)

**Fixture structure (short node test)**:
- Short exact: "AI产品经理核心DNA" (similarity 0.70)
- Long related: "AI产品经理的思考方向" (similarity 0.85)
- Expected: Exact node survives in returned hits

**Fixture structure (p6 regression test)**:
- Corpus: AI产品经理项目实战与深度思考架构分析
- Query: "AI产品经理的核心DNA是什么？"
- Allowed hotspots: 00:31 - 产品特性对比, AI产品经理核心DNA
- Rejected hotspots: 05:40 - 抖音案例, 04:40 - 数据工作重要性, 06:29 - 特斯拉案例
- Expected evidence: 数据驱动, 非确定性, 持续性

**Key decisions**:
- Chinese text fixtures validate semantic anchor requirements
- Exact query string from D-07 requirement
- Evidence string validation deferred to Phase 11 validation runner (requires EvidenceContentResolver)

## Deviations from Plan

### None

Plan executed exactly as written. All 5 required tests created with exact names per specification.

**Note**: All tests were created in the initial file commit (Task 1) rather than incrementally across Tasks 2-3. This was acceptable because:
1. All tests share the same ImportError failure mode (RED state validated)
2. Single file simplifies fixture sharing and maintenance
3. Atomic commit still satisfies TDD RED gate requirement

## Implementation Notes

### Test Architecture

- **Test class**: `TestClusterHotspotSelector`
- **Mocking pattern**: MagicMock registry + manual node_stats construction
- **Fixture scope**: Per-test (no shared fixtures for isolation)
- **Assertion style**: Behavior validation + contract validation

### RED Gate Status

All 5 tests are in RED state:
```
ImportError: cannot import name 'ClusterHotspotSelector' from 'llamaindex_runtime.tree.semantic_distribution'
```

This is the expected failure mode for TDD RED phase. Implementation of `ClusterHotspotSelector` is out of scope for this plan (belongs to plan 11-02 GREEN phase).

### Next Steps

1. **Plan 11-02 (GREEN)**: Implement `ClusterHotspotSelector` class with:
   - `select_hotspots(query_embedding, node_stats, tree_signals, limit)` method
   - No route-node bonus, depth bonus, or support bonus logic
   - Cluster aggregation, scoring, and ancestor selection
   - Return list of hotspot nodes (dataclass structure TBD)

2. **Plan 11-03 (REFACTOR)**: Clean up implementation, add helper decomposition

3. **Plan 11-04 (VALIDATION)**: Run p6 validation runner to confirm D-07 regression fixed

## Verification Evidence

### RED Test Collection

```bash
$ rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q

ERROR collecting tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py
ImportError: cannot import name 'ClusterHotspotSelector' from 'llamaindex_runtime.tree.semantic_distribution'
```

**Result**: RED gate validated - tests fail because implementation does not exist.

### Acceptance Criteria Checklist

**Task 1 criteria**:
- [x] File contains exact string `class TestClusterHotspotSelector`
- [x] File contains exact string `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus`
- [x] File contains exact string `candidate_top_n` and candidate breadth assertion
- [x] RED failure is due to missing `ClusterHotspotSelector`, not syntax error

**Task 2 criteria**:
- [x] File contains exact strings for densest ancestor and root avoidance tests
- [x] File contains heading literals `Root`, `A`, `A1`, `A2`, `A3`, `B`, `B1`
- [x] Test asserts root rejection when local cluster exists

**Task 3 criteria**:
- [x] File contains exact query `AI产品经理的核心DNA是什么？`
- [x] File contains exact evidence strings `数据驱动`, `非确定性`, `持续性`
- [x] File contains exact allowed hotspot strings `00:31 - 产品特性对比`, `AI产品经理核心DNA`
- [x] File contains exact rejected hotspot strings for unrelated regions

## Threat Flags

None - test fixtures contain no secrets, no production code modified.

## Known Stubs

None - tests are complete fixtures with full assertions.

## Self-Check: PASSED

- [x] Created files exist: test_tree_semantic_cluster_hotspot.py, 11-01-SUMMARY.md
- [x] Commits exist: 4f26ad0 (test), 2d4b87a (docs)
- [x] No deletions in test commit
- [x] All 5 tests present with exact required names
- [x] RED state validated via ImportError

---

**Phase**: 11-level-agnostic-hotspot-cluster-tracking
**Plan**: 01 (RED)
**Status**: Complete
**Next**: Plan 11-02 (GREEN implementation)