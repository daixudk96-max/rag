# REQUIREMENTS — v1.0 PageIndex Quality-Verified Main-Function Readiness

## Coverage Summary

Coverage: 11 Complete / 1 Closed with blockers / 0 Pending

This requirements file was reconstructed during Phase 6 because `.planning/REQUIREMENTS.md` was missing when `.planning/v1.0-MILESTONE-AUDIT.md` ran and returned `gaps_found`.

Statuses intentionally distinguish delivered infrastructure from unresolved quality-readiness blockers:

- `Complete` — requirement has source-backed completion evidence.
- `Closed with blockers` — phase work closed honestly, but the requirement still carries explicit downstream blockers.
- `Pending` — follow-up phase must complete before milestone can close cleanly.

## Traceability Table

| ID | Requirement | Priority | Phase | Status | Evidence | Notes |
|----|-------------|----------|-------|--------|----------|-------|
| REQ-P1-TECH-INTEGRATION | Repair PageIndex client/adaptor path so markdown ingestion no longer triggers client-layer double donor call and real retrieval workflow can run. | must | Phase 1 | Complete | `.planning/ROADMAP.md` Phase 1; commits `2eb6724`, `f1cf3d0` listed in ROADMAP/history | Reconstructed from roadmap and git history. |
| REQ-P2-VALIDATION-FRAMEWORK | Establish explicit PageIndex quality validation framework, thresholds, status board, and Level gates. | must | Phase 2 | Complete | `.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md` | Fixture Level 3 is non-authoritative. |
| REQ-P3-REAL-BASELINE | Execute real PostgreSQL/LLM/human-judgment validation and determine true baseline quality. | must | Phase 3 | Complete | `.planning/STATE.md`; `verification/phase4-quality-validation/level_assessment.json` | Authoritative baseline is Level 2. |
| REQ-P4-BASELINE-RECONCILIATION | Eliminate split-brain between fixture and real quality baselines. | must | Phase 4 | Complete | `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md` | Level 2 unified as authoritative. |
| REQ-P4-CORPUS-ALIGNMENT | Align validation corpus to business-query domain and correct tree-depth misconception. | must | Phase 4 | Complete | `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md` | Selected `PageIndex完整功能分析与集成方案.md`; tree depth no fix required. |
| REQ-P4-EVIDENCE-CHAIN-BLOCKERS-DOCUMENTED | Document evidence-chain zeros and invalid Phase 4 Level 3 so follow-up work can proceed honestly. | must | Phase 4 | Closed with blockers | `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md`; `.planning/v1.0-MILESTONE-AUDIT.md` | `chunks=0`, `mapped_chunks=0`, `heading_path_rate=0`; invalid Level 3 discarded. |
| REQ-P5-ACTIVE-VERSION-DIAGNOSTICS | Implement active-version scoped evidence-chain diagnostics. | must | Phase 5 | Complete | `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md`; `verification/phase5-evidence-chain-verification/active_version_counts.json` | Local artifact fails closed because DB is unavailable. |
| REQ-P5-RESOLVER-CONSOLIDATION | Consolidate selected-node preview/content hydration into shared `EvidenceContentResolver`. | must | Phase 5 | Complete | `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md` | Resolver is used by both `ReasoningTreeBackend` and `PageIndexTreeAdapter`. |
| REQ-P5-INTEGRITY-GATE | Add fail-closed validation integrity gate before metrics and judgment collection. | must | Phase 5 | Complete | `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md`; `verification/phase5-evidence-chain-verification/validation_integrity_report.json` | Current gate blocks with `unknown_hit`, `missing_judgment_rows`, `corpus_mismatch`, `missing_canonical_spans`. |
| REQ-P7-DB-EVIDENCE-CHAIN-PROOF | Configure and run DB-backed active-version diagnostics/materialization proof for evidence-chain counts. | must | Phase 7 | Complete | `.planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md`; `verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`; `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json` | Repaired artifacts classify the active version as `DB_EVIDENCE_READY`: 54 canonical spans, 54 vector chunks with node_id, 54 vector_chunk_spans, and 54 tree_node_spans. |
| REQ-P8-MATCHED-VALIDATION-RERUN | Generate matched retrieval/judgment/metrics artifacts and publish valid Level assessment. | must | Phase 8 | Complete | `.planning/phases/08-matched-validation-rerun-and-level-assessment/08-SUMMARY.md`; `.planning/phases/08-matched-validation-rerun-and-level-assessment/08-VERIFICATION.md`; `verification/phase8-matched-validation-rerun/validation_integrity_report.json`; `verification/phase8-matched-validation-rerun/level_assessment.json` | `MATCHED_VALIDATION_COMPLETE`; 95 matched judgment rows; valid Level assessment confirms `Level_2` because all frozen thresholds missed. |
| REQ-P9-SAFE-MILESTONE-CLOSE | Isolate dirty working tree and prepare safe milestone close/commit/tag scope. | should | Phase 9 | Complete | `.planning/phases/09-milestone-close-readiness-and-git-hygiene/09-SUMMARY.md`; `.planning/phases/09-milestone-close-readiness-and-git-hygiene/09-VERIFICATION.md`; `verification/phase9-milestone-close/staging_plan.json`; `verification/phase9-milestone-close/final_closure_decision.json` | Close approval package is ready. `approved_by_user: false`; `next_allowed_action: await_user_closure_scope_approval`; no commit/tag/push performed. |

## Requirement Outcomes

### Complete

- `REQ-P1-TECH-INTEGRATION`
- `REQ-P2-VALIDATION-FRAMEWORK`
- `REQ-P3-REAL-BASELINE`
- `REQ-P4-BASELINE-RECONCILIATION`
- `REQ-P4-CORPUS-ALIGNMENT`
- `REQ-P5-ACTIVE-VERSION-DIAGNOSTICS`
- `REQ-P5-RESOLVER-CONSOLIDATION`
- `REQ-P5-INTEGRITY-GATE`
- `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`
- `REQ-P8-MATCHED-VALIDATION-RERUN`
- `REQ-P9-SAFE-MILESTONE-CLOSE`

### Closed with blockers

- `REQ-P4-EVIDENCE-CHAIN-BLOCKERS-DOCUMENTED`

### Pending

- *(none)*

## Audit Notes

- `.planning/REQUIREMENTS.md` was reconstructed during Phase 6 from ROADMAP, STATE, audit, summaries, and validation artifacts.
- Phase 6 restoration allows `/gsd-audit-milestone` to evaluate requirements coverage instead of failing solely because requirements traceability is absent.
- The file intentionally does **not** mark Level 3/4 advancement complete.
- `REQ-P7-DB-EVIDENCE-CHAIN-PROOF` is complete after repaired Phase 7 artifacts classified the active version as `DB_EVIDENCE_READY` with 54 canonical spans, 54 vector chunks with node_id, 54 vector_chunk_spans, and 54 tree_node_spans.
- `REQ-P8-MATCHED-VALIDATION-RERUN` is complete after Phase 8 produced matched retrieval, 95 completed judgment rows, a passed integrity report, quality metrics, and a valid `level_assessment.json`.
- Level 2 remains authoritative because Phase 8 metrics still miss frozen thresholds: hit_rate 0.70 < 0.80, top1_relevance 0.59 < 0.90, stability 0.65 < 0.85.
- `REQ-P9-SAFE-MILESTONE-CLOSE` is complete for approval-package readiness: dirty-tree classification, planning-truth reconciliation, audit rerun, staging plan, final closure decision, summary, and verification exist.
- Final commit/tag/push are intentionally not complete; they require explicit closure-scope approval and are not part of automatic Phase 9 execution.
