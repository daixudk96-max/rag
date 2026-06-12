# Phase 10-03 Summary — Quality Impact and Phase 8 Baseline Comparison

**Date:** 2026-06-12
**Plan:** 10-03
**Status:** COMPLETE_REUSE_BLOCKED_LEVEL2_PRESERVED

## Objective

Compare Phase 10 hotspot semantic retrieval against the authoritative Phase 8 baseline.

## Phase 8 Baseline

Source artifacts:

- `verification/phase8-matched-validation-rerun/quality_metrics.json`
- `verification/phase8-matched-validation-rerun/level_assessment.json`
- `verification/phase8-matched-validation-rerun/judgment_completed.csv`

Baseline:

| Metric | Phase 8 | Threshold | Status |
|---|---:|---:|---|
| `hit_rate` | 0.70 | 0.80 | Missed |
| `top1_relevance` | 0.59 | 0.90 | Missed |
| `stability` | 0.65 | 0.85 | Missed |

Authoritative level remains:

```text
Level_2
```

## Phase 8 Active-Version DB Readiness

The Phase 8 active version was verified in PostgreSQL before hotspot comparison:

```text
active_version_id=a376679b-3a95-4724-a31f-ece0c9fa35b8
canonical_spans=54
tree_nodes=23
tree_node_spans=54
vector_chunks=54
vector_chunk_spans=54
vector_chunks_with_node=54
vector_chunks_with_embedding=54
embedding_dimension=16
```

## Hotspot Retrieval Output

Phase 10 hotspot retrieval was executed over the Phase 8 aligned active version and 20-query set.

Output artifact:

- `verification/phase10-hotspot-quality-comparison/phase10_hotspot_retrieval_results.json`

Observed result:

```text
query_count=20
total_hits=80
query_failures=0
zero_chunk_hits=0
parent_only_hits=0
hotspot_metadata_hits=80
```

Interpretation:

- DB-backed hotspot retrieval executed successfully on the aligned Phase 8 corpus/query set.
- Every returned hit was evidence-bearing; no all-zero chunk sentinel was returned.
- Every returned hit included hotspot/navigation metadata.
- The user’s semantic contract is preserved at DB-backed quality-comparison scale.

## Judgment Reuse Assessment

Output artifact:

- `verification/phase10-hotspot-quality-comparison/judgment_reuse_assessment.json`

Result:

```text
reuse_status=REUSE_BLOCKED
phase8_judgment_rows=95
phase10_hit_rows=80
matched_rows_by_query_rank_node_heading_preview=3
reuse_rate=0.0375
```

Rationale:

- Phase 8 judged `reasoning` retrieval hits.
- Phase 10 hotspot retrieval produced a different hit set and/or preview text from the Phase 8 judged rows.
- Only 3 of 80 Phase 10 hotspot hit identity/heading/preview rows matched Phase 8 judgments.
- Reusing Phase 8 judgments would produce invalid metrics.

## Metrics Calculation

Output artifact:

- `verification/phase10-hotspot-quality-comparison/phase10_quality_metrics.json`

Status:

```text
NOT_CALCULATED_REUSE_BLOCKED
```

Reason:

Phase 10 metrics require matched hotspot-specific judgments. Because Phase 8 judgment reuse is blocked, hit-rate/top1/stability metrics were intentionally not calculated from invalid labels.

## Metrics Comparison

Output artifact:

- `verification/phase10-hotspot-quality-comparison/phase10_metrics_comparison.json`

Status:

```text
COMPARISON_BLOCKED_BY_JUDGMENT_REUSE
```

Comparison decision:

- Phase 8 baseline metrics remain authoritative.
- Phase 10 evidence-chain integrity is improved relative to the structural-heading concern: `zero_chunk_hits=0`, `parent_only_hits=0`.
- Phase 10 quality metrics are not claimable until hotspot-specific judgments are collected.

## Level Impact

Output artifact:

- `verification/phase10-hotspot-quality-comparison/phase10_level_assessment.json`

Result:

```text
LEVEL_2_PRESERVED_REUSE_BLOCKED
```

Decision:

- Do not overwrite Phase 8 `level_assessment.json`.
- Do not claim Level 3/4 promotion.
- Preserve Phase 8 `Level_2` as authoritative.
- Open/execute a future hotspot-specific judgment collection phase before any Level promotion claim.

## Final 10-03 Decision

Phase 10-03 is complete as a quality-impact gate:

1. Hotspot retrieval output exists.
2. Evidence-chain integrity passed on the Phase 8 aligned corpus/query set.
3. Judgment reuse was tested and rejected.
4. Metrics calculation was intentionally blocked to avoid invalid claims.
5. Level 2 was preserved honestly.
