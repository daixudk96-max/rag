# Academic Integrity Decision Log

**Date**: 2026-06-29
**Decision Type**: Theory Validation Gap
**Severity**: HIGH - Requires Phase 2 research before production deployment

## Current Research Status

### What We Found ✓

**Implemented Formulas**:
1. Lucene 2026 LogOddsFusion (BayesianScoreQuery + LogOddsFusionQuery)
2. BM25 Saturation Formula (H/(H+k))
3. ranx CombMNZ / Log-ISR
4. LlamaIndex AutoMergingRetriever

**Recommended Parameters**:
- `miss_probability = 0.40` (coverage penalty)
- `support_alpha = 0.5` (sqrt(N) confidence)
- `k = 2` (BM25 saturation)

**Phase 14 Validation**:
- Parent B wins over Parent A ✓
- 95% irrelevant severely penalized ✓
- High quality low coverage competitive ✓

---

### What We Missing ❌

**Critical Gap 1: Lucene BayesianScoreQuery Evaluation**

**What we know**:
- PR merged 2026-03-27 ✓
- Located in Lucene core experimental API ✓

**What we DON'T know**:
- ❌ PR number (LUCENE-XXX?)
- ❌ Test dataset (TREC? NIST? Internal?)
- ❌ Evaluation metrics (NDCG? MAP? Precision@K?)
- ❌ Parameter tuning method (grid search? empirical?)
- ❌ Task type (ad-hoc retrieval vs parent-child traversal)

**Risk**: HIGH
- If Lucene tested on ad-hoc retrieval → Formula may not fit parent-child scenario
- If evaluation metrics differ → Our validation may be invalid

---

**Critical Gap 2: TREC-2 CombMNZ Paper Evaluation**

**What we know**:
- Fox & Shaw, TREC-2 conference ✓
- CombMNZ: (Σ scores) × H ✓
- Ranx implementation available ✓

**What we DON'T know**:
- ❌ Full paper (Evaluation Method section)
- ❌ Task description (ad-hoc? routing? filtering?)
- ❌ Dataset size (query count, document count)
- ❌ Evaluation metrics (recall? precision? utility?)
- ❌ Relevance judgment method (human? automatic?)

**Risk**: HIGH
- TREC-2 likely tested ad-hoc retrieval (independent documents)
- Phase 14 is tree traversal (parent-child hierarchy)
- Scenario mismatch → CombMNZ may not apply

---

**Critical Gap 3: BM25 Parameter Tuning**

**What we know**:
- Lucene default k1=1.2 ✓
- BM25 used for document length normalization ✓

**What we DON'T know**:
- ❌ k1 theoretical derivation (Robertson & Zaragoza 2009?)
- ❌ Tuning method (empirical? theoretical?)
- ❌ Applicable scenarios (short vs long documents?)
- ❌ Semantic difference (document length vs support count)

**Risk**: MEDIUM
- BM25 k1: document length normalization
- Phase 14 k: support count saturation
- Different semantics → Parameter recommendation may lack basis

---

**Critical Gap 4: ranx Benchmark**

**What we know**:
- ranx implements CombMNZ, Log-ISR ✓
- Open-source Python library ✓

**What we DON'T know**:
- ❌ Benchmark datasets (TREC-COVID? BEIR? MS MARCO?)
- ❌ Evaluation metrics (NDCG@10? MAP? MRR?)
- ❌ Task types (retrieval fusion vs parent scoring?)

**Risk**: MEDIUM
- ranx likely tests retrieval fusion (multiple systems)
- Phase 14 is single-system parent scoring
- Task mismatch → Formula applicability uncertain

---

## Academic Integrity Risks

| Risk Type | Specific Issue | Severity | Impact |
|-----------|---------------|----------|--------|
| **Scenario Mismatch** | TREC-2 (ad-hoc) vs Phase 14 (parent-child) | HIGH | Formula may not apply |
| **Metric Mismatch** | NDCG (TREC) vs hit_rate (Phase 14) | MEDIUM | Validation may be invalid |
| **Parameter Gap** | miss_probability=0.40 no academic basis | HIGH | Parameters may be unreasonable |
| **Dataset Gap** | TREC dataset vs Phase 14 document | MEDIUM | Need scenario validation |
| **Theory Gap** | BM25 semantic difference | MEDIUM | Parameter recommendation lacks basis |

---

## Decision: Three-Phase Implementation Strategy

### Phase 1: Conservative Deployment (NOW)

**Formula Choice**: BM25 Saturation Formula
```python
Score = Q × C × (H / (H + k))
```

**Justification**:
- BM25 is 40-year mature algorithm ✓
- Saturation mechanism theoretically sound ✓
- Phase 14 empirical validation (k=2) ✓
- No dependency on probability calibration ✓
- Lowest implementation risk ✓

**Acknowledged Limitations**:
- Parameter k=2 is empirical (not academic tuning)
- Semantic difference: support count vs document length
- Requires Phase 2 academic validation

**Deployment Criteria**:
- Immediate fix for Phase 14 retrieval quality
- Acceptable risk for pilot testing
- Clear documentation of parameter source

---

### Phase 2: Academic Consistency Research (NEXT)

**Research Tasks**:

1. **Lucene BayesianScoreQuery Deep Dive**
   - Find PR number (LUCENE-XXX)
   - Read PR test code and evaluation results
   - Identify dataset and metrics
   - Verify scenario compatibility (ad-hoc vs parent-child)

2. **TREC-2 Full Paper Analysis**
   - Obtain Fox & Shaw complete paper
   - Read Section 4: Evaluation Method
   - Identify task type and dataset
   - Verify CombMNZ applicability to parent-child

3. **BM25 Original Paper**
   - Read Robertson & Zaragoza (2009)
   - Understand k1 theoretical derivation
   - Verify semantic adaptation (length → support)

4. **ranx Benchmark Analysis**
   - Read ranx documentation benchmark section
   - Identify evaluation datasets
   - Verify task compatibility

**Expected Findings**:
- If evaluation matches → Proceed to Phase 3
- If mismatch → Derive adapted formula
- If impossible → Document limitation and use empirical tuning

---

### Phase 3: Full Integration (FUTURE)

**Condition**: Phase 2 confirms academic consistency

**Implementation**:
- Full LogOddsFusion with probability calibration
- Academic-recommended parameters (miss_probability, support_alpha)
- Academic evaluation metrics (NDCG@10, MAP)
- Publish adaptation research (if novel)

**Otherwise**:
- Stay with BM25 saturation (empirical tuning)
- Document academic gaps
- Continue research as ongoing project

---

## Current Action Items

### Immediate (Phase 1)

- [ ] Modify semantic_distribution.py: BM25 saturation formula
- [ ] Parameter: k=2 (empirical, document source)
- [ ] Run Phase 14 validation
- [ ] Document parameter source and risk

### Next (Phase 2)

- [ ] Task #5: Academic consistency research
- [ ] Search Lucene BayesianScoreQuery PR
- [ ] Search TREC-2 Fox & Shaw full paper
- [ ] Search BM25 Robertson & Zaragoza (2009)
- [ ] Analyze ranx benchmark

### Future (Phase 3)

- [ ] Decide based on Phase 2 findings
- [ ] If match: Full LogOddsFusion integration
- [ ] If mismatch: Derive adapted formula
- [ ] Publish research (if novel contribution)

---

## Academic Honesty Statement

**We acknowledge**:
- Current research provides formulas but lacks academic evaluation validation
- Parameter recommendations are empirical without theoretical basis
- Scenario compatibility (ad-hoc vs parent-child) requires verification
- We proceed with Phase 1 deployment under acceptable risk with clear documentation
- Phase 2 research will fill academic gaps before production scaling

**This is responsible academic practice**: admit gaps, mitigate risks, plan validation.

---

## References (To Be Verified)

1. Lucene BayesianScoreQuery PR (LUCENE-XXX?) - **NEEDS VERIFICATION**
2. TREC-2: Fox & Shaw (1994) - **NEEDS FULL PAPER**
3. BM25: Robertson & Zaragoza (2009) - **NEEDS PARAMETER THEORY**
4. ranx benchmark documentation - **NEEDS EVALUATION METHOD**
5. Elasticsearch nested query aggregation - **NEEDS OFFICIAL DOCS**

---

## Decision Approval

**Approved by**: User ✓
**Date**: 2026-06-29
**Decision**: Proceed with **Phase 1 Empirical Implementation** with honest documentation

**Implementation Strategy**:
1. Use BM25-inspired saturation formula (heuristic adaptation)
2. Parameter k=2 from empirical tuning (no academic derivation)
3. Clear documentation of academic gaps and inspiration sources
4. Phase 14 empirical validation (not citing mismatched academic sources)
5. Plan Phase 2 theoretical research as future work

**Academic Honesty Commitment**:
- ✓ Acknowledge: Formula inspired by BM25, not derived from BM25 theory
- ✓ Acknowledge: Parameters empirical, not academically validated
- ✓ Acknowledge: Validation method Phase 14 specific, not BEIR/TREC benchmark
- ✓ Plan: Future theoretical derivation and benchmark design

**This is responsible academic practice**: implement with clear gaps, validate empirically, plan research.

---

## Appendix: Academic Risk Assessment Matrix

| Component | Theory ✓ | Eval ✓ | Param ✓ | Match ✓ | Risk |
|-----------|---------|--------|---------|---------|------|
| LogOddsFusion | ✓ | ❌ | ❌ | ❌ | HIGH |
| BM25 Saturation | ✓ | ✓ | ❌ | ❌ | MEDIUM |
| CombMNZ | ✓ | ❌ | ✓ | ❌ | HIGH |
| LlamaIndex Threshold | ✓ | ❌ | ✓ | ✓ | LOW |

**BM25 Saturation chosen for Phase 1 due to**:
- Strongest theory foundation ✓
- Empirical parameter tuning possible ✓
- Lowest implementation risk ✓
- Clear documentation of gaps ✓

---

**End of Decision Log**