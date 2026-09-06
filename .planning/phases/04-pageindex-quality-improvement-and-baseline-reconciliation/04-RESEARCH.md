# Phase 4: PageIndex 质量改进与基线校准 - Research

**Gathered:** 2026-05-29
**Status:** Ready for planning

## Summary

Phase 1 completed technical integration repair. Phase 2 completed the validation framework and froze the quality gates. Phase 3 completed real validation and exposed that the true system quality is below readiness, with the most trustworthy current planning baseline remaining Level 2.

This phase is not about building more framework. It is about improving the actual system quality and reconciling the baseline before the next real validation pass.

## Phase Boundary

This phase delivers a concrete quality-improvement program for PageIndex focused on:
1. reconciling the baseline and source-of-truth drift,
2. aligning document domain to business queries,
3. increasing tree depth to support specific section retrieval,
4. restoring evidence-chain / chunk mapping completeness,
5. re-running real validation under the already-frozen Level 4 gates.

Out of scope:
- new retrieval frameworks
- UI expansion
- workflow / skill redesign
- relaxing Phase 2 thresholds

## Confirmed Baseline

### Operative baseline
Use **Level 2** as the planning truth for Phase 4.

Reason:
- `.planning/STATE.md` and `.planning/workspace-memory.json` record the final real validation conclusion as Level 2 after manual judgment.
- `verification/phase3-real-validation/level_assessment.json` reports Level 3 from an artifact calculation path.
- This mismatch means the baseline is not yet reconciled, so planning must take the more conservative interpretation until the reporting chain is unified.

## Root-Cause Categories

### 1. Document / Query Mismatch (P0)
The validated document is a competitor-analysis artifact (`第二阶段-竞品分析-代旭`), while many business queries target a technical system domain. This means retrieval can only return weakly-related root or parent nodes even if the runtime is functioning correctly.

### 2. Shallow Tree Structure (P1)
Real validation and prior reports consistently show tree depth is too low to support strong section-level top1 relevance. The system remains biased toward root or large parent nodes.

### 3. Evidence-Chain / Mapping Incompleteness (P2)
State and verification artifacts disagree on chunks / mapped chunks / heading completeness. This blocks a trustworthy interpretation of how well the retrieval path is grounded in real spans and chunks.

### 4. Baseline Drift Across Artifacts
ROADMAP, STATE, workspace memory, and validation artifacts do not currently tell one coherent story. This undermines confidence in all later planning and verification unless corrected.

## Preserved Constraints

The following must remain frozen from Phase 2:
- hit_rate >= 80%
- top1_relevance >= 90%
- stability >= 85%
- tree_depth >= 3
- node_chunk_mapping >= 80%
- heading_path_completeness >= 95%

Manual human judgment remains mandatory for real validation.

## Workstream Hypotheses

### WS0 — Baseline Reconciliation
Unify the planning truth and reporting truth so the project has one authoritative level assessment.

### WS1 — Domain-Aligned Validation Corpus
Replace or supplement the current competitor-analysis validation document with one that actually matches the technical/business query set.

### WS2 — Tree Depth Improvement
Improve the PageIndex ingestion/adapter/runtime path so the live tree reaches at least 3 usable levels.

### WS3 — Evidence-Chain Recovery
Recover real chunk / node / heading-path completeness so validation metrics are meaningful.

### WS4 — Revalidation and Go/No-Go Closeout
Re-run the real quality validation and determine whether the system remains below readiness or reaches Level 3/4.

## Risks

- Using the wrong document domain again will invalidate the next validation cycle even if ranking improves.
- Improving tree depth without fixing evidence-chain completeness may create apparent quality gains without grounded provenance.
- Updating only JSON artifacts without updating planning state will preserve the current Level 2 / Level 3 split-brain.

## Non-Goals

- Do not redesign the validation framework.
- Do not introduce a new retrieval architecture.
- Do not weaken or reinterpret the frozen thresholds.
- Do not treat fixture performance as evidence of production readiness.

## Recommended Planning Inputs

**Canonical references:**
- `E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md`
- `E:/github/rag/verification/phase3-real-validation/FINAL-REPORT.md`
- `E:/github/rag/verification/phase3-real-validation/validation_status.json`
- `E:/github/rag/verification/phase3-real-validation/level_assessment.json`
- `E:/github/rag/llamaindex_runtime/tree/reasoning_backend.py`
- `E:/github/rag/llamaindex_runtime/tree/pageindex_adapter.py`
- `E:/github/rag/llamaindex_runtime/client/pageindex_client.py`
- `C:/Users/daixu/Downloads/rag-upstreams/PageIndex/pageindex/page_index_md.py`

## Next Step

This research is sufficient to support the initial Phase 4 plan and validation contract.
