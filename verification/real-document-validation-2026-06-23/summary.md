# Real Document Validation Summary — hybrid_cluster Selector Quality

**Date**: 2026-06-23T01:37:56.961184+00:00
**Version ID**: 8abb98c4-a70f-4176-924a-d26d3f4da1bb
**Corpus**: PageIndex完整功能分析与集成方案.md
**Selector**: hybrid_cluster (embedding backend)
**Queries**: 20
**Queries with hits**: 10
**Zero-hit queries**: 10
**Hits**: 18

## Quality Metrics

| Metric | Value | Threshold | Pass |
|--------|-------|-----------|------|
| hit_rate | 0.10 | 0.80 | ❌ |
| top1_relevance | 0.20 | 0.90 | ❌ |
| stability | 0.20 | 0.85 | ❌ |

**Level**: Level_2 — 能查但质量未验证 - retrieval works, quality not verified

## Comparison with Phase 8

| Run | Backend | Selector | hit_rate | top1 | stability | Level |
|-----|---------|----------|----------|------|-----------|-------|
| Phase 8 | ReasoningTreeBackend | (ignored) | 0.70 | 0.59 | 0.65 | Level_2 |
| This run | embedding | hybrid_cluster | 0.10 | 0.20 | 0.20 | Level_2 |

## ⚠️ CRITICAL CAVEATS

**Caveat 1 — Not Algorithm-Comparable**

Phase 8 used `ReasoningTreeBackend` (LLM navigation path). This run uses
`embedding` backend with `hybrid_cluster` selector. These are **different
retrieval algorithms**. This is a **new measurement**, not a regression test
or improvement comparison.

**Caveat 2 — AI-Judged Proxy**

Relevance judgments were produced by AI reading the corpus and scoring hits.
This is a **directional proxy**, not human-annotated ground truth. Does not
constitute certification-level Level promotion.

**Caveat 3 — Chinese Corpus with English-Centric Embedding Model**

This run used `all-MiniLM-L6-v2` (384 dimensions), which is English-centric.
The corpus and queries are Chinese, so this likely depresses retrieval quality.
The low score is still a valid production-path measurement for the current
configuration, but it should not be treated as the ceiling of a Chinese-capable
embedding model.

## Failure Breakdown

- Zero-hit queries: 10/20
- Total retrieved hits: 18 (expected upper bound: 100)
- Result: Level_2 is preserved; no Level promotion is justified.

## Provenance

- Corpus SHA256: `2e515964e932f4e26540991e8d5b2f222f31dae4816b80f8047bc46003d93056`
- Git commit: `d7f77259bcab4af3cec3f462863ef45364b0875f`
- Selector env: `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster`
- Backend: `embedding` (forced via parameter)
- Judgment source: AI in-context reading

## Artifacts

- `01_environment_check.json`
- `02_document_ingestion_status.json`
- `03_tree_vector_status.json`
- `04_query_set.json`
- `05_retrieval_results.json`
- `06_evidence_chain_report.json`
- `07_judgment_template_metadata.json`
- `judgment_completed.csv`
- `08_quality_metrics.json`
- `09_level_assessment.json`
- `validation_integrity_report.json`
- `summary.md` (this file)