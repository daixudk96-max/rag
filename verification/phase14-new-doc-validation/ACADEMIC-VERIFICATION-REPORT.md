# Academic Verification Report: Evaluation Consistency

**Date**: 2026-06-29
**Task**: Verify if scoring formulas/parameters match original academic evaluation
**Result**: ❌ **CANNOT APPLY DIRECTLY** — Fundamental scenario mismatch

---

## Executive Summary

**Critical Finding**: All four sources (Lucene BayesianScoreQuery, TREC-2 CombMNZ, BM25, ranx) evaluate **flat ad-hoc retrieval** (independent documents), but Phase 14 is **parent-child tree traversal** (hierarchical structure with coverage × quality × support dimensions).

**Academic Integrity Status**:
- ❌ No theoretical foundation for applying flat retrieval formulas to hierarchical traversal
- ❌ No evaluation evidence for parent-child scenarios
- ❌ Parameter recommendations lack academic basis (empirical guesses)
- ❌ Cannot cite these sources as justification for Phase 14

**Recommendation**: Phase 14 is a **novel problem requiring original research**, not direct application of existing formulas.

---

## Source-by-Source Verification

### 1. Lucene BayesianScoreQuery (LogOddsFusion)

**PR**: #15827 (merged 2026-03-27, Lucene 10.5.0)

**Evaluation Method**:
- Dataset: BEIR benchmark (5 datasets: MS MARCO, TREC-COVID, etc.)
- Metrics: NDCG@10 (primary), MAP, Recall@k
- Task: **Hybrid ad-hoc retrieval** (text + vector fusion on **independent documents**)
- Method: Retrieve top-1000 per signal → union candidates → evaluate with pytrec_eval
- Parameters: Alpha=0.5 default, unsupervised Bayesian calibration

**Compatibility Assessment**:
- ❌ **NOT COMPATIBLE**
- Lucene: Flat retrieval (each document scored independently)
- Phase 14: Parent-child hierarchy (coverage ratio = dual_hot/total children)
- Mismatch: No mechanism for parent aggregation or coverage ratio
- No evaluation evidence for hierarchical traversal

**Result**: Cannot apply directly. Probability calibration concept could inspire normalization, but needs significant adaptation.

---

### 2. TREC-2 Fox & Shaw CombMNZ

**Paper**: "Combination of Multiple Searches", TREC-2 Proceedings, pages 243-252 (1994)

**Evaluation Method**:
- Task: **Routing and ad-hoc retrieval** on **independent documents**
- Dataset: TREC-1&2 topics (51-150), ~50 queries, ~1-2M documents (AP, WSJ, ZIFF, FR, DOE)
- Metrics: Average non-interpolated precision, Exact R-Precision
- Relevance: **Human assessors** (NIST team, pooling method, binary relevance)
- Formula: CombMNZ(d) = (Σ scores) × (number of runs containing d)

**Compatibility Assessment**:
- ⚠️ **PARTIALLY COMPATIBLE (requires major adaptation)**
- CombMNZ intuition: Reward multi-appearance → could inspire coverage scoring
- Critical mismatch:
  - CombMNZ for independent documents from multiple retrieval runs
  - Phase 14 needs parent-child hierarchy with coverage ratio (dual_hot/total children, not run count)
  - CombMNZ treats appearances equally; Phase 14 needs relative coverage (2/2 vs 5/7)

**Result**: Adapt intuition, not formula. Coverage scoring concept valid, but formula needs redesign for hierarchy.

---

### 3. BM25 Robertson & Zaragoza (2009)

**Paper**: "The Probabilistic Relevance Framework: BM25 and Beyond"

**Evaluation Method**:
- Theory: k1 from **2-Poisson mixture model** (eliteness: elite vs non-elite documents)
- Formula: Term frequency saturation `tf × (k1+1)/(tf+k1)`
- Role: k1 controls term frequency saturation rate
- Tuning: Empirical for specific corpora (typical values 1.2-2.0)
- Scenario: **Flat ad-hoc retrieval** with term frequency saturation

**Compatibility Assessment**:
- ❌ **NOT COMPATIBLE**
- Semantic mismatch:
  - BM25 k1: term frequency saturation (how often term appears in document)
  - Phase 14 k: support count saturation (absolute dual_hot children under parent)
  - BM25 "eliteness": independent documents; Phase 14: parent-child hierarchy
- No theoretical justification for 2-Poisson model on parent-child support counts

**Result**: Cannot apply k1 directly. Saturation concept valid, but need new theoretical model for parent-child.

---

### 4. ranx Benchmark

**Library**: ranx (Python, Numba-based ranking evaluation)

**Evaluation Method**:
- Datasets: BEIR (18 datasets: MS MARCO, TREC-COVID, Natural Questions, etc.)
- Metrics: NDCG@10 (primary), MAP@k, MRR@k, Precision@k, Recall@k
- Task: **Zero-shot ad-hoc retrieval**, passage ranking, QA
- Fusion: CombMNZ, Log-ISR, RRF, CombSUM

**Compatibility Assessment**:
- ❌ **NOT COMPATIBLE**
- ranx benchmarks flat retrieval (query → independent documents)
- Phase 14 needs hierarchical traversal (parent coverage × quality × support)
- NDCG@10 measures top-10 document ranking; Phase 14 needs parent-level metrics
- No benchmark datasets for parent-child tree traversal

**Result**: Cannot use ranx directly. Need to design new benchmark for parent-child evaluation.

---

## Academic Integrity Conclusion

### Fundamental Scenario Mismatch

| Dimension | All Sources | Phase 14 |
|-----------|-------------|----------|
| **Structure** | Flat documents | Parent-child hierarchy |
| **Independence** | Documents independent | Children belong to parent |
| **Scoring** | Single dimension (relevance) | Three dimensions (coverage × quality × support) |
| **Metrics** | NDCG@10, MAP, Precision | Parent-level coverage quality |
| **Task** | Ad-hoc retrieval | Tree traversal hotspot selection |

**Conclusion**: **Cannot apply any formula directly with academic justification**.

---

## What This Means for Phase 14

**Academic Honesty**:
- Current parameters (miss_probability=0.40, support_alpha=0.5, k=2) are **empirical guesses** without academic basis
- BM25 saturation formula is **inspired by** BM25 but **semantically different** (support count vs term frequency)
- CombMNZ coverage intuition is **adapted** but formula is **redesigned** for hierarchy

**This is acceptable if we**:
- Clearly document: "Inspired by BM25/CombMNZ, adapted for parent-child hierarchy"
- Acknowledge: "Parameters are empirical tuning (no academic derivation)"
- Validate: Empirical testing on Phase 14 data (not citing academic sources)
- Future work: Derive theoretical model for parent-child scoring

**This is NOT acceptable if we**:
- Claim: "Based on Lucene BayesianScoreQuery with academic validation"
- Cite: BM25 Robertson & Zaragoza as justification for k parameter
- Assert: "Parameters from TREC-2 evaluation"

---

## Responsible Implementation Path

### Phase 1: Empirical Implementation (NOW)

**Formula**: BM25-inspired saturation
```python
Score = avg_quality × coverage_ratio × (dual_hot / (dual_hot + k))
```

**Parameters**: k=2 (empirical tuning on Phase 14)

**Documentation**:
- Inspired by BM25 saturation mechanism (nonlinear growth)
- Adapted for parent-child support count (not term frequency)
- Parameter k=2 is empirical (not from BM25 k1)
- Needs theoretical derivation (future work)

**Validation**: Phase 14 empirical testing (not citing academic sources)

---

### Phase 2: Theoretical Derivation (FUTURE)

**Research Tasks**:
1. Derive theoretical model for parent-child support saturation (not 2-Poisson)
2. Design benchmark dataset for parent-child traversal evaluation
3. Define evaluation metrics for hierarchical coverage quality
4. Conduct experiments and validate against ground truth
5. Publish results with empirical evidence

**If successful**: Can claim academic foundation (original contribution)

---

## Academic Integrity Statement

**We acknowledge**:
- ❌ Cannot cite Lucene BayesianScoreQuery evaluation (different scenario)
- ❌ Cannot cite BM25 Robertson & Zaragoza for k parameter (semantic mismatch)
- ⚠️ Can cite CombMNZ intuition (but formula is redesigned)
- ❌ Cannot use ranx benchmark metrics (different task type)
- ✓ Current implementation is empirical with clear documentation
- ✓ Future research will derive theoretical foundation

**This is responsible academic practice**: admit gaps, avoid false citations, plan original research.

---

## References (Verified)

1. **Lucene PR #15827**: https://github.com/apache/lucene/pull/15827 ✓
2. **TREC-2 Fox & Shaw**: https://trec.nist.gov/pubs/trec2/papers/txt/23.txt ✓
3. **BM25 Robertson & Zaragoza**: https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf ✓
4. **ranx Documentation**: https://amenra.github.io/ranx/ ✓

---

**End of Verification Report**