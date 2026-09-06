# Lucene LogOddsFusion Research Summary

**Source**: ChatGPT Deep Research
**Link**: https://chatgpt.com/s/t_6a41f1b7668881918f794b25ea0ca61d
**Date**: 2026-06-29

## Executive Summary

**Core Finding**: Lucene 2026 `BayesianScoreQuery + LogOddsFusionQuery` provides the optimal solution for three-dimensional parent node scoring (coverage × quality × support).

## Key Implementations Found

### 1. LlamaIndex AutoMergingRetriever
- Coverage threshold + average of hot children scores
- Formula: `if dual_hot/total > threshold: parent_score = avg(hot_scores)`
- **Limitation**: Discontinuous threshold, no support count influence after threshold

### 2. Lucene/Elasticsearch Block Join
- Aggregation modes: `avg`, `sum`, `max`, `min`
- `avg`: `Score = Q` (quality only)
- `sum`: `Score = H × Q` (quality × support, no coverage)
- **Limitation**: No coverage penalty mechanism

### 3. ranx CombMNZ / Log-ISR
- CombMNZ: `(Σ scores) × H = Q × H²`
- Log-ISR: `(Σ scores) × log(H)`
- **Key insight**: Support should be logarithmic/confidence scaling, not linear

### 4. Lucene 2026 LogOddsFusion (BEST MATCH)
- **Probability calibration**: sigmoid(α(score-β) + logit(baseRate))
- **Log-odds fusion**: `L = N^α × (1/n) Σ logit(p_i)`
- **Confidence scaling**: `α = 0.5` (sqrt(N) growth)
- **Advantage**: Handles coverage (via negative evidence), quality, and support count simultaneously

## Recommended Formula for Phase 14

### Full LogOddsFusion (Long-term)

```python
L = N^(α-1) × [ Σ_hot logit(p_i) + (N-H) × logit(p_miss) ]
ParentScore = sigmoid(L)
```

**Parameters**:
- `miss_probability = 0.40` (coverage penalty strength)
- `support_alpha = 0.5` (sqrt(N) confidence growth)

**Phase 14 Validation**:
```
Parent A (2/2, Q=0.53): Score = 0.5424
Parent B (5/7, Q=0.57): Score = 0.5563
✓ Parent B wins (correct)
```

**Other Scenarios**:
- 95% irrelevant (5/100, Q=0.90): Score = 0.0599 (severe penalty ✓)
- High quality low coverage (2/10, Q=0.95): Score = 0.6977 (still competitive ✓)

### BM25 Saturation Formula (Immediate)

For cases without probability calibration:

```python
Score = Q × C^β × (H / (H + k))
```

**Parameters**:
- `k = 2` (saturation threshold)
- `β = 1` (coverage penalty strength)

**Phase 14 Validation**:
```
Parent A: 0.53 × 1.0 × (2/4) = 0.265
Parent B: 0.57 × 0.714 × (5/7) = 0.291
✓ Parent B wins
```

**95% Irrelevant**: 0.9 × 0.05 × (5/7) = 0.032 (severe penalty ✓)

## Parameter Control

### miss_probability
- `0.50`: No coverage penalty
- `0.45`: Light penalty
- `0.40`: Medium penalty (recommended)
- `0.35`: Strong penalty
- `0.30`: Extreme penalty

**Phase 14 Threshold**: `p_miss > 0.3823` for Parent B to win

### support_alpha
- `0.0`: Mean evidence only (no support scaling)
- `0.5`: sqrt(N) growth (recommended, matches Lucene default)
- `1.0`: Linear support accumulation

## Why Previous Formulas Failed

**Linear Addition**: coverage=1.0 absolute dominance → cannot break
**Simple Average**: Parent A has no irrelevant children → high average
**Multiplication**: coverage=0.05 → over-penalization (0.04)

**Root Cause**:
- No probability calibration → quality not normalized
- No negative evidence → cannot penalize irrelevant children
- No confidence scaling → unreasonable support weight

## Implementation Roadmap

### Phase 1: BM25 Saturation (Immediate)
- Replace linear addition with BM25 formula
- Parameters: `k=2, β=1`
- No probability calibration needed

### Phase 2: LogOddsFusion (Long-term)
- Add probability calibration in ingestion
- Upgrade node_stats schema for probability distribution
- Use full `parent_score()` function

## Python Implementation

```python
def parent_score_from_aggregates(
    *,
    total_children: int,
    dual_hot_count: int,
    avg_quality_probability: float,
    miss_probability: float = 0.40,
    support_alpha: float = 0.50,
) -> float:
    import math

    def _logit(probability: float) -> float:
        probability = max(min(probability, 0.999999), 0.000001)
        return math.log(probability / (1.0 - probability))

    def _sigmoid(value: float) -> float:
        if value >= 0:
            return 1.0 / (1.0 + math.exp(-value))
        exp_value = math.exp(value)
        return exp_value / (1.0 + exp_value)

    if total_children <= 0 or dual_hot_count <= 0:
        return 0.0

    positive_evidence = dual_hot_count * _logit(avg_quality_probability)
    negative_evidence = (total_children - dual_hot_count) * _logit(miss_probability)
    mean_log_odds = (positive_evidence + negative_evidence) / total_children
    fused_log_odds = (total_children ** support_alpha) * mean_log_odds

    return _sigmoid(fused_log_odds)
```

## References

1. **Lucene PR**: BayesianScoreQuery + LogOddsFusionQuery (merged 2026-03-27)
2. **Elasticsearch**: Nested query aggregation modes
3. **ranx**: CombMNZ / Log-ISR implementation
4. **TREC-2**: Fox & Shaw retrieval fusion research
5. **BM25**: Lucene BM25Similarity (k1 saturation parameter)

## Success Metrics

- [x] Found ≥3 concrete scoring formulas
- [x] Identified ≥1 mathematical fusion strategy (log-odds + sigmoid)
- [x] Discovered ≥1 academic reference (TREC-2)
- [x] Extracted ≥1 code snippet (Lucene, ranx)
- [x] Proposed formula solving Phase 14 + other scenarios

## Conclusion

Lucene LogOddsFusion provides the theoretical foundation and production-ready algorithm for solving the three-dimensional parent node scoring problem. BM25 saturation formula offers an immediate practical solution without probability calibration overhead.