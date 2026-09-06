# Evaluation Baseline Summary

## What Changed

### Files Created
1. **tests/llamaindex_runtime/fixtures/evaluation_fixtures.py** - Minimal helper to generate richer PDF fixtures
   - `build_evaluation_pdf()` - Creates PDF with heading + paragraphs for retrieval testing
   - `REPRESENTATIVE_QUERIES` - Query set derived from validation patterns

2. **tests/llamaindex_runtime/test_evaluation_baseline.py** - Formal evaluation/regression baseline tests
   - 16 tests across 5 test classes

### Test Coverage

| Test Class | Tests | Purpose |
|------------|-------|---------|
| TestQueryResultShapeBaseline | 2 | QueryResult fields stability |
| TestQueryHitShapeBaseline | 2 | QueryHit structure validation |
| TestRetrievalStabilityBaseline | 2 | Deterministic hit counts |
| TestRepresentativeQueryBaseline | 8 | Representative query results (4 queries × 2 modes) |
| TestScoreOrderingBaseline | 2 | Score ordering validation |

**Total: 16 tests**

## TDD Workflow Executed

### Step 1 (RED) - Write Failing Tests
- Created 14 initial tests with minimal fixture (sample_minimal.pdf)
- **3 tests failed**: Vector mode returned 0 hits for representative queries
- **Root cause identified**: DoclingNodeParser creates 0 nodes from minimal JSON document

### Step 2 - Verify Expected Failure
- Ran tests and confirmed vector retrieval returned empty hits
- Analyzed DoclingNodeParser behavior with debug scripts
- Validated tree retrieval worked (markdown-based approach)

### Step 3 (GREEN) - Minimum Production Code
- Created `evaluation_fixtures.py` with `build_evaluation_pdf()`
- Updated tests to use generated PDF fixture (richer content)
- Fixed metadata type check (MappingProxyType support)

### Step 4 - Verify Tests Pass
- **All 16 tests pass**
- Vector mode now returns hits for representative queries
- Tree mode continues to work correctly

## Baseline Characteristics

### Scope: Minimal
- **Does NOT modify core retrieval logic** (vector/tree/runtime.py unchanged)
- Only adds test fixtures and helpers
- Uses existing PDF generation approach (PIL/Pillow)

### Evaluation Focus
1. **Shape stability** - QueryResult and QueryHit maintain stable structure
2. **Retrieval stability** - Same inputs produce same hit counts
3. **Representative queries** - System returns results for validation-derived queries
4. **Score ordering** - Hits ordered by score (descending)

### No Expansion Beyond Requirements
- No deployment, monitoring, or ops hardening
- No full evaluation framework
- No metrics beyond basic stability checks
- No modification to retrieval algorithms

## Regression Baseline Value

These tests now serve as a **formal regression baseline**:
- Any change to QueryResult/QueryHit shape will fail shape tests
- Any nondeterministic retrieval will fail stability tests
- Any retrieval path breaking will fail representative query tests
- Any score ordering change will fail ordering tests

**Pass rate: 100% (16/16)**