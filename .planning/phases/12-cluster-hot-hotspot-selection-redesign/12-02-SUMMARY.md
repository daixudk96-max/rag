---
phase: 12-cluster-hot-hotspot-selection-redesign
plan: 02
subsystem: hotspot-selection
tags: [tdd, red-phase, coverage, dual-hot, theta, leaf-fallback]

# Dependency graph
requires:
  - phase: 12-01 (parent_to_children denominator)
provides:
  - RED test specification for D-01/D-02/D-05/D-06
  - D-10 test rewrite surface classification
affects: [hotspot-selection, tdd-cycle]

# Tech tracking
tech-stack:
  added: []
  patterns: [tdd-red-stub-tests, import-error-failures]

key-files:
  created:
    - tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_red.py
  modified:
    - tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py

key-decisions:
  - "TDD RED phase: Minimal stub tests that fail on import (implementation in 12-03)"
  - "D-10 classification: exact-heading tests PRESERVE-AS-IS (leaf fallback preserves behavior)"
  - "Remove old union-semantics distribution test (replaced by coverage+dual-hot tests)"

requirements-completed: [D-01-spec, D-02-spec, D-05-spec, D-06-spec, D-10-classification]

# Metrics
duration: 16 min
completed: 2026-06-22T14:39:37Z
---

# Phase 12 Plan 02: RED Test Specification for Cluster-Hot Coverage Summary

**TDD RED phase complete. 9 stub tests added that MUST FAIL until 12-03 implementation. Old union-semantics distribution test removed. D-10 classification completed for exact-heading tests.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-06-22T14:23:00Z
- **Completed:** 2026-06-22T14:39:37Z
- **Tasks:** 1 (RED test specification commit)
- **Files modified:** 2 (main test file + new RED test file)
- **Tests added:** 9 RED tests (all failing)
- **Tests preserved:** 36 GREEN tests (unchanged)

## Task Commits

1. **Task 1: RED test specification** - `63a59d2` (test: add RED tests for cluster-hot coverage + dual-hot gate)
   - Added 9 minimal stub tests that fail on ImportError
   - Removed old union-semantics distribution test (:245-290)
   - Added D-10 classification comments to exact-heading tests
   - All 36 preserved contract tests remain GREEN

## Files Created/Modified

### Created
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_red.py` - 9 RED stub tests:
  - `TestClusterCoverageGate` (3 tests: 1/3, 2/3, 3/3 coverage + outrank)
  - `TestDualHotGate` (2 tests: vector-only excluded, keyword-only excluded)
  - `TestConfigurableTheta` (2 tests: theta 0.5 vs 0.75 flip)
  - `TestLeafFallback` (2 tests: leaf preserved, root avoided)

### Modified
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py` - Removed old distribution test + D-10 comments

## Accomplishments

- **TDD RED phase executed correctly:** All 9 new tests fail with ImportError (helpers don't exist yet)
- **Minimal stub approach:** Tests import nonexistent functions and fail immediately - proper RED state
- **D-10 rewrite surface handled:** Old union-semantics test removed, replaced by coverage+dual-hot tests
- **D-10 classification documented:** Two exact-heading tests marked PRESERVE-AS-IS with reasoning
- **Preserved tests validated:** All 36 contract tests remain GREEN (registration, context, normalization, rerank-off, anti-hardcode, jieba, config)
- **Chosen defaults locked:** θ=0.5, min_support=2, vector_hot>=0.5, keyword_hot>=1 matched term (per plan frontmatter)

## RED Tests Status

All 9 tests MUST FAIL (proper TDD RED state):

```
FAILED TestClusterCoverageGate::test_parent_with_1_of_3_dual_hot_children_is_not_a_hotspot
FAILED TestClusterCoverageGate::test_parent_with_2_of_3_dual_hot_children_is_a_hotspot
FAILED TestClusterCoverageGate::test_parent_with_3_of_3_dual_hot_children_outranks_isolated_high_vector_node
FAILED TestDualHotGate::test_vector_only_child_does_not_count_toward_coverage
FAILED TestDualHotGate::test_keyword_only_child_does_not_count_toward_coverage
FAILED TestConfigurableTheta::test_theta_0_5_selects_2_of_3_parent
FAILED TestConfigurableTheta::test_theta_0_75_rejects_2_of_3_parent
FAILED TestLeafFallback::test_focused_exact_leaf_query_returns_strong_dual_hot_leaf_even_when_parent_coverage_below_theta
FAILED TestLeafFallback::test_root_with_many_children_is_not_promoted_by_coverage_alone
```

**Failure mode:** ImportError - helpers `_compute_child_coverage_score`, `_is_child_dual_hot`, `_apply_leaf_fallback`, `_apply_root_avoidance` do not exist yet. Implementation in 12-03.

## GREEN Preserved Tests Status

All 36 preserved contract tests remain GREEN:

```
PASSED TestHybridClusterHotspotSelectorRegistration (4 tests)
PASSED TestHotspotSelectionContextContract (5 tests including parent_to_children)
PASSED TestKeywordSpanHitContract (1 test)
PASSED TestScoreNormalization (3 tests)
PASSED TestChildDistributionScoring (2 tests - old distribution test removed)
PASSED TestParentToChildrenReportKey (2 tests - D-07 denominator)
PASSED TestHybridFusionScoring (4 tests - fusion weights + exact-heading preserved)
PASSED TestDefaultOffRerankerSeam (2 tests)
PASSED TestCrossDomainAntiHardcode (2 tests)
PASSED TestHybridRuntimeKeywordExtraction (9 tests - jieba keyword extraction)
PASSED TestConfigRegistration (3 tests)
```

## Decisions Made

### D-01: Coverage Gate Specification
- RED tests assert coverage 1/3 < θ → NOT hotspot, 2/3 ≥ θ → hotspot, 3/3 → outranks isolated
- Coverage helper `_compute_child_coverage_score` will be implemented in 12-03
- Tests will transition to GREEN after implementation

### D-02: Dual-Hot Gate Specification
- RED tests assert vector-only child excluded from coverage, keyword-only child excluded
- Intersection logic `_is_child_dual_hot` will be implemented in 12-03
- Tests prove union→intersection fix

### D-05: Configurable Theta Specification
- RED tests assert theta parameter on selector constructor (HybridClusterHotspotSelector(theta=0.5))
- Same 2/3 parent: theta 0.5 → selected, theta 0.75 → NOT selected
- Configuration path to be implemented in 12-03

### D-06: Leaf Fallback + Root Avoidance Specification
- RED tests assert leaf preserved when parent coverage < θ, root NOT promoted
- Helper `_apply_leaf_fallback` and `_apply_root_avoidance` will be implemented in 12-03
- Focused exact-leaf queries still return their position

### D-10: Test Rewrite Surface Classification

**Removed:** `test_parent_with_multiple_child_hits_beats_isolated_high_score_node` (old union-semantics distribution test)

**Preserved with classification comments:**
1. `test_selector_prefers_multi_term_heading_match_over_broad_single_term` (line ~430)
   - Classification: PRESERVE-AS-IS
   - Reason: Exact-heading leaf wins, which leaf fallback preserves
   - Status: GREEN after 12-03 implementation (leaf fallback path allows exact-heading single nodes)

2. `test_selector_prioritizes_exact_heading_match_over_high_vector_broad_match` (line ~518)
   - Classification: PRESERVE-AS-IS
   - Reason: Exact-heading leaf wins with low vector score, which leaf fallback preserves
   - Status: GREEN after 12-03 implementation (leaf fallback path allows exact-heading single nodes)

**No rewrite needed for exact-heading tests** - leaf fallback semantics preserve their current behavior.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Commands

Per plan verification section:

```bash
# NEW RED tests FAIL (ImportError)
python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_red.py -q -k "coverage or dual or theta or fallback"
# Result: 9 failed (ImportError) - proper RED state

# Preserved contract tests GREEN
python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q -k "registration or context or normaliz or rerank or hardcode or jieba or config"
# Result: 36 passed - preserved tests unaffected

# Test count increased
grep -v '^#' tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector_coverage_red.py | grep -c "def test_"
# Result: 9 new tests added

# Exact-heading tests classified and accessible
grep -n "test_selector_prefers_multi_term_heading_match\|test_selector_prioritizes_exact_heading_match" tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py
# Result: Line ~430 and ~518, with D-10 classification comments
```

## Next Phase Readiness

- D-01/D-02/D-05/D-06 RED tests ready for implementation in 12-03
- D-07 denominator already complete from 12-01
- D-10 test rewrite surface fully handled (removed + classified)
- All preserved contract tests validated GREEN
- Implementation phase can proceed from these RED tests

**Ready for 12-03 implementation phase** - GREEN transition target known.

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Plan: 02*
*Completed: 2026-06-22T14:39:37Z*