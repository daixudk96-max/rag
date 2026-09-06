# Phase 1 Empirical Implementation Plan

**Date**: 2026-06-29
**Decision**: Empirical formula with honest documentation
**Approach**: Heuristic adaptation inspired by academic concepts, validated empirically

---

## Formula Design

### BM25-Inspired Saturation Formula

**Core Formula**:
```python
parent_score = avg_quality × coverage_ratio × support_saturation
```

**Components**:
- `avg_quality`: Average similarity of dual_hot children (0-1 range)
- `coverage_ratio`: dual_hot_count / total_children (coverage percentage)
- `support_saturation`: dual_hot_count / (dual_hot_count + k) (nonlinear growth)

**Semantic Interpretation**:
- Quality factor: Higher average similarity → better hotspot
- Coverage factor: Higher percentage of relevant children → better hotspot
- Support saturation: More hits contribute, but nonlinearly (avoid over-counting)

---

## Parameter Selection

### k = 2 (Empirical Tuning)

**Tuning Process**:
1. Tested k values: 1, 2, 3, 5 on Phase 14 scenario
2. Evaluated: Parent A (2/2, Q=0.53) vs Parent B (5/7, Q=0.57)
3. Criterion: Parent B should win (more dual_hot children)

**Results**:
| k | Parent A Score | Parent B Score | Winner |
|---|----------------|----------------|--------|
| 1 | 0.53×1.0×(2/3)=0.353 | 0.57×0.71×(5/6)=0.406 | B ✓ |
| 2 | 0.53×1.0×(2/4)=0.265 | 0.57×0.71×(5/7)=0.291 | B ✓ |
| 3 | 0.53×1.0×(2/5)=0.212 | 0.57×0.71×(5/8)=0.255 | B ✓ |
| 5 | 0.53×1.0×(2/7)=0.151 | 0.57×0.71×(5/10)=0.203 | B ✓ |

**Decision**: k=2 (middle ground, not too aggressive saturation)

**Academic Status**:
- ❌ NOT derived from BM25 Robertson & Zaragoza (2009) k1 parameter
- ❌ BM25 k1=1.2 controls term frequency (different semantics)
- ✓ Empirically tuned for Phase 14 support count saturation
- ✓ Need theoretical derivation (future work)

---

## Implementation Code

### semantic_distribution.py Modification

**Current Code** (Line 1172-1177, approximate):
```python
parent_score = (
    coverage_ratio * self._COVERAGE_WEIGHT
    + avg_child_vector * self._COVERAGE_VECTOR_WEIGHT
    + support_bonus * self._COVERAGE_SUPPORT_WEIGHT
)
```

**New Code**:
```python
# BM25-inspired saturation formula (heuristic adaptation)
# Inspired by BM25 nonlinear saturation mechanism, adapted for parent-child support count
# Parameter k=2 empirically tuned for Phase 14 (no academic derivation)
support_saturation = hot_count / (hot_count + 2.0)
parent_score = avg_child_vector * coverage_ratio * support_saturation
```

**Documentation Comments**:
```python
"""
Parent Coverage Score: BM25-inspired saturation formula (heuristic).

Academic Honesty Statement:
- Inspired by BM25 saturation mechanism (nonlinear contribution growth)
- Adapted for parent-child hierarchy: support count saturation (not term frequency)
- Parameter k=2 empirically tuned on Phase 14 data (not from BM25 theory)
- Formula semantics: avg_quality × coverage_ratio × support_saturation
- Validation: Phase 14 empirical testing (no BEIR/TREC benchmark)
- Future work: Need theoretical derivation for parent-child support saturation

References (Inspiration, Not Derivation):
- BM25: Robertson & Zaragoza (2009) - saturation concept (term frequency)
- CombMNZ: Fox & Shaw (1994) - coverage intuition (multi-appearance reward)
- Lucene BayesianScoreQuery (2026) - probability calibration concept

DO NOT CITE:
- BM25 k1 parameter derivation (semantic mismatch: term frequency vs support count)
- TREC-2 CombMNZ evaluation (scenario mismatch: independent documents vs parent-child)
- Lucene BayesianScoreQuery validation (different task: flat retrieval vs tree traversal)
"""
```

---

## Validation Method

### Phase 14 Specific Test

**Test Scenarios**:

1. **Phase 14 Document** (Expected: Parent B wins)
   - Parent A: 2 children, 2 dual_hot, coverage=1.0, quality=0.53
   - Parent B: 7 children, 5 dual_hot, coverage=0.71, quality=0.57
   - Expected winner: Parent B (more dual_hot children)

2. **Extreme Case** (Expected: Parent D wins)
   - Parent C: 100 children, 5 dual_hot, coverage=0.05, quality=0.80
   - Parent D: 10 children, 3 dual_hot, coverage=0.30, quality=0.60
   - Expected winner: Parent D (Parent C too many irrelevant children)

3. **High Quality Low Coverage** (Expected: Either competitive)
   - Parent E: 50 children, 10 dual_hot, coverage=0.20, quality=0.90
   - Parent F: 20 children, 8 dual_hot, coverage=0.40, quality=0.70
   - Expected: Parent F competitive (coverage higher, but E has more hits)

**Evaluation Metrics**:
- Correct hotspot selection (matches expected winner)
- Hit rate improvement (Phase 14 queries with hits)
- Evidence chunk rate improvement (real content returned)

**Academic Benchmark Status**:
- ❌ NOT using BEIR benchmark (flat retrieval, not parent-child)
- ❌ NOT using NDCG@10 (document ranking metric, not parent-level metric)
- ✓ Phase 14 specific validation (parent-child scenario)

---

## Expected Outcomes

### Improvement Criteria

**Baseline** (Current linear addition formula):
- Parent A wins in Phase 14 (incorrect hotspot selection)
- Hit rate: ~80% (queries with results)
- Evidence chunk rate: ~95% (Phase 13 target)

**Target** (BM25-inspired saturation):
- Parent B wins in Phase 14 (correct hotspot selection) ✓
- Hit rate: >=80% (maintain or improve)
- Evidence chunk rate: >=95% (maintain or improve)
- Better relevance: Returned content matches query intent

**Success Criteria**:
- [ ] Phase 14: Parent B selected (not Parent A)
- [ ] Extreme case: Parent D selected (not Parent C)
- [ ] Hit rate >= 80%
- [ ] Evidence chunk rate >= 95%
- [ ] Retrieval relevance matches query intent

---

## Academic Integrity Documentation

### What We Can Claim

**Formula Inspiration**:
- ✓ BM25 saturation mechanism (nonlinear contribution growth concept)
- ✓ CombMNZ coverage intuition (reward multi-appearance/relevance)
- ✓ Lucene probability calibration concept (normalize scores)

**Parameter Source**:
- ✓ Empirical tuning on Phase 14 data (k=2 tested on Phase 14 scenarios)
- ✓ No academic derivation (acknowledge gap)

**Validation Method**:
- ✓ Phase 14 empirical testing (specific scenario validation)
- ✓ No BEIR/TREC benchmark (acknowledge different task type)

---

### What We Cannot Claim

**Academic Validation**:
- ❌ "Formula validated on BEIR benchmark" (scenario mismatch)
- ❌ "Parameters derived from BM25 theory" (semantic mismatch)
- ❌ "Evaluation metrics from TREC-2" (task type mismatch)

**Academic Justification**:
- ❌ Cite BM25 Robertson & Zaragoza (2009) for k parameter derivation
- ❌ Cite TREC-2 Fox & Shaw (1994) for evaluation validation
- ❌ Cite Lucene BayesianScoreQuery for parent-child scoring

**This prevents academic dishonesty and misleading citations**

---

## Future Research Plan

### Phase 2: Theoretical Derivation

**Research Tasks**:
1. **Derive Support Saturation Theory**
   - Model parent-child support count distribution (not 2-Poisson)
   - Derive saturation formula from probability theory
   - Justify k parameter theoretically

2. **Design Benchmark Dataset**
   - Parent-child tree traversal datasets
   - Ground truth hotspot annotations
   - Coverage × quality × support evaluation scenarios

3. **Define Evaluation Metrics**
   - Parent-level coverage quality metric
   - Hierarchical traversal effectiveness metric
   - Relevance judgment for hotspot selection

4. **Publish Original Research**
   - Novel contribution to hierarchical retrieval
   - Academic validation of Phase 14 scenario
   - Benchmark publication for community use

**Timeline**: Future research project (not blocking Phase 1 implementation)

---

## Implementation Checklist

### Code Modification

- [ ] Locate semantic_distribution.py Line 1172-1177
- [ ] Replace linear addition formula with BM25-inspired saturation
- [ ] Add academic honesty comment block
- [ ] Update parameter constants (remove old weight configuration)
- [ ] Document k=2 empirical tuning rationale

### Validation Execution

- [ ] Create test script for Phase 14 scenario
- [ ] Create test script for extreme case
- [ ] Create test script for high-quality-low-coverage
- [ ] Run retrieval validation (run_validation.py --phase retrieve)
- [ ] Measure hit rate improvement
- [ ] Measure evidence chunk rate improvement
- [ ] Verify retrieval relevance (manual inspection)

### Documentation

- [ ] Update ACADEMIC-DECISION-LOG.md with validation results
- [ ] Update weight_fix_summary.md with formula change rationale
- [ ] Create validation results report (Phase 14 specific metrics)
- [ ] Document future research tasks (Phase 2 plan)

---

## Success Metrics

**Primary Goal**: Improve Phase 14 hotspot selection quality
- Correct winner selection (Parent B over Parent A)
- Better retrieval relevance (query intent matches)

**Secondary Goal**: Maintain existing quality standards
- Hit rate >= 80%
- Evidence chunk rate >= 95%

**Academic Goal**: Honest documentation of gaps
- Clear academic honesty statement
- No misleading citations
- Plan future research

---

## Risk Mitigation

**Risk 1**: Formula fails in other scenarios
- Mitigation: Test multiple scenarios (extreme case, high-quality-low-coverage)
- Fallback: Keep old formula as backup, compare results

**Risk 2**: Parameter k=2 not optimal
- Mitigation: Test k values range (1-5), validate across scenarios
- Fallback: Grid search for optimal k

**Risk 3**: Academic integrity violation
- Mitigation: Clear documentation, honest statements, no false citations
- Review: User approval of academic honesty approach

---

## Conclusion

**This implementation follows responsible academic practice**:
1. ✓ Honest documentation of inspiration sources (not derivation)
2. ✓ Acknowledgement of parameter empirical tuning (no academic basis)
3. ✓ Phase 14 specific validation (no mismatched benchmark)
4. ✓ Plan future theoretical research (Phase 2)

**Implementation is ready for execution with clear academic integrity.**