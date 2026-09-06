# Phase 8 Summary: Matched Validation Rerun and Level Assessment

**Requirement:** `REQ-P8-MATCHED-VALIDATION-RERUN`  
**Status:** `MATCHED_VALIDATION_COMPLETE`  
**Completed:** 2026-06-08  
**Baseline decision:** Level 2 remains authoritative

## Outcome

Phase 8 completed the matched validation rerun against the Phase 7 DB-backed evidence chain. The run produced matched retrieval, Phase 8-only completed judgments, an integrity report, quality metrics, and a Level assessment.

The Phase 8 assessment is valid because:

- `validation_integrity_report.json passed`
- `retrieval_judgment_integrity.passed: true`
- `evidence_chain_gate.passed: true`
- `judgment_collection_status.json.status: JUDGMENTS_COMPLETE`
- `validation_integrity_report.json.next_allowed_action: calculate_metrics`
- `level_assessment.json` was written only after the integrity gate allowed metrics
- `baseline_update_allowed: true`

## Artifacts

| Artifact | Status | Notes |
|---|---:|---|
| `verification/phase8-matched-validation-rerun/phase8_preflight_status.json` | Complete | Phase 7 readiness accepted as `DB_EVIDENCE_READY` |
| `verification/phase8-matched-validation-rerun/retrieval_results.json` | Complete | 20 queries completed, 95 retrieval hit rows |
| `verification/phase8-matched-validation-rerun/judgment_template.csv` | Complete | Phase 8-only judgment template with 95 rows |
| `verification/phase8-matched-validation-rerun/judgment_completed.csv` | Complete | Phase 8-only completed judgments; no placeholders remain |
| `verification/phase8-matched-validation-rerun/validation_integrity_report.json` | Passed | Matched retrieval/judgment/evidence-chain gate passed |
| `verification/phase8-matched-validation-rerun/judgment_collection_status.json` | Complete | `JUDGMENTS_COMPLETE` |
| `verification/phase8-matched-validation-rerun/quality_metrics.json` | Complete | Metrics calculated after integrity gate passed |
| `verification/phase8-matched-validation-rerun/level_assessment.json` | Complete | Valid Phase 8 Level assessment |

## Metrics

Frozen thresholds:

| Metric | Result | Threshold | Passed |
|---|---:|---:|---:|
| `hit_rate` | 0.70 | 0.80 | No |
| `top1_relevance` | 0.59 | 0.90 | No |
| `stability` | 0.65 | 0.85 | No |

## Level Assessment

`level_assessment.json` reports:

- `level: Level_2`
- `level_description: 能查但质量未验证 - retrieval works, quality not verified`
- `baseline_update_allowed: true`

Because all three frozen thresholds missed, the validated Phase 8 result confirms the existing Level 2 baseline rather than promoting to Level 3 or Level 4.

## Gate Decisions

- `MATCHED_VALIDATION_COMPLETE`
- Level 2 remains authoritative
- No baseline promotion performed
- No stale Phase 3/4 judgments were reused
- No raw `DATABASE_URL` was written

## Next Route

Proceed to Phase 9: Milestone Close Readiness and Git Hygiene.

Phase 9 should isolate the dirty working tree, reconcile stale planning text where appropriate through GSD-owned mechanisms, verify expected affected scope, and prepare safe close/commit/tag boundaries without leaking secrets.
