# PROJECT — PageIndex Quality-Verified Main-Function Readiness

## What This Is

This project is a brownfield PageIndex quality-readiness program for the `rag` repository. It started after technical PageIndex integration succeeded, then shifted to proving whether PageIndex can meet main-function quality gates under real PostgreSQL / pgvector / LLM retrieval conditions.

The program now tracks both delivered infrastructure and remaining validation blockers. It does not treat fixture success as production readiness.

## Core Value

Raise PageIndex from technical integration to quality-verified main-function readiness.

## Current State

- Authoritative baseline: Level 2
- Level 2 remains authoritative after Phase 8 produced a valid matched DB-backed `level_assessment.json` but missed all frozen quality thresholds.
- Current route: Phase 9 milestone close readiness after Phase 6 traceability restoration, Phase 7 DB evidence proof, and Phase 8 matched validation completion.
- Current phase: Phase 9 — Milestone Close Readiness and Git Hygiene
- Current milestone: v1.0 close-readiness cycle after `.planning/v1.0-MILESTONE-AUDIT.md` returned `gaps_found`

### Baseline Truth

| Source | Status | Meaning |
|--------|--------|---------|
| Phase 2 fixture validation | Non-authoritative Level 3 | Validates the quality framework only. |
| Phase 3 real validation | Authoritative Level 2 | Real DB/LLM/human judgment exposed quality below readiness thresholds. |
| Phase 4 rerun attempt | Invalid Level 3 discarded | Retrieval and judgment artifacts came from different corpora. |
| Phase 5 integrity gate | Complete fail-closed infrastructure | Active-version diagnostics, resolver hydration, and integrity gates were implemented. |
| Phase 7 DB evidence proof | Complete DB_EVIDENCE_READY | Active version has 54 canonical spans, 54 vector chunks with node_id, 54 vector_chunk_spans, and 54 tree_node_spans. |
| Phase 8 matched validation | Complete matched assessment | 95 matched judgment rows passed integrity; metrics remained below thresholds, so Level 2 stays authoritative. |

## Requirements

### Validated / Complete

- Phase 1 technical PageIndex integration path repaired.
- Phase 2 validation framework and frozen thresholds established.
- Phase 3 real validation established the authoritative Level 2 baseline.
- Phase 4 reconciled split-brain baseline state and aligned the validation corpus.
- Phase 5 implemented active-version diagnostics, shared resolver hydration, and fail-closed integrity gates.
- Phase 6 restored project/requirements traceability and phase verification artifacts.
- Phase 7 repaired DB-backed evidence-chain proof to `DB_EVIDENCE_READY` for the intended active version.
- Phase 8 completed matched retrieval/judgment/metrics/Level assessment with `MATCHED_VALIDATION_COMPLETE`.

### Active / Gated

- Phase 9 must isolate milestone-close/git/tag scope from unrelated dirty working-tree changes.
- Commit, tag, push, reset, clean, delete, checkout, and stash remain disallowed without explicit approval.
- Level 3/4 advancement remains blocked by Phase 8 metrics: hit_rate 0.70 < 0.80, top1_relevance 0.59 < 0.90, stability 0.65 < 0.85.

### Out of Scope for Phase 9

- Runtime PageIndex code changes.
- New DB materialization or evidence-chain repair.
- New human judgment collection.
- Level 3/4 promotion.
- Automatic commit/tag/push/milestone archival.

## Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-28 | Freeze explicit quality thresholds | Readiness gates are measurable: hit_rate, relevance, stability, tree depth, node-chunk mapping, heading path. |
| 2026-05-31 | Treat Phase 2 Level 3 as fixture-provisional | Prevents fixture results from becoming authoritative quality claims. |
| 2026-05-31 | Preserve Phase 3 Level 2 as authoritative baseline | Current quality truth stays conservative until matched DB-backed validation passes. |
| 2026-06-07 | Discard invalid Phase 4 Level 3 | Metrics mixed new-corpus retrieval with old-corpus judgments. |
| 2026-06-07 | Add Phase 5 integrity gates | Metric calculation and judgment collection now fail closed on mismatched artifacts. |
| 2026-06-08 | Add Phases 6-9 from milestone audit gaps | Gap closure route restores traceability, DB proof, matched validation, and safe close hygiene. |

## Known Blockers

- Level 3/4 quality readiness remains blocked because Phase 8 metrics missed frozen thresholds: hit_rate 0.70 < 0.80, top1_relevance 0.59 < 0.90, stability 0.65 < 0.85.
- Several Phase 8 retrieval hits are structural headings with all-zero `chunk_id`; this is a close-readiness concern to document, not a Phase 8 integrity blocker.
- Milestone commit/tag remains unsafe until Phase 9 scopes the dirty working tree and the user explicitly approves final closure scope.
- Secret-sensitive files and unrelated scratch files must stay excluded from staging unless separately reviewed and approved.

## Next Milestone / Gap-Closure Route

1. Phase 6 — restore planning traceability and reconstructed verification artifacts. ✅ Complete
2. Phase 7 — run DB-backed evidence-chain diagnostics/materialization proof. ✅ Complete as `DB_EVIDENCE_READY`
3. Phase 8 — run matched validation rerun and publish valid Level assessment. ✅ Complete as `MATCHED_VALIDATION_COMPLETE`; Level 2 remains authoritative
4. Phase 9 — prepare safe milestone close and git hygiene. ▶ In progress

---

*Last updated: 2026-06-08 during Phase 9 planning-truth reconciliation.*
