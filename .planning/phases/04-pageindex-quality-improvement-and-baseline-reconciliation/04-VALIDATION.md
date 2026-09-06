---
phase: 4
slug: pageindex-quality-improvement-and-baseline-reconciliation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-29
---

# Phase 4 — Validation Strategy

> 质量改进与基线校准阶段的验证契约。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + real validation scripts |
| **Config file** | pytest.ini |
| **Quick run command** | `pytest tests/llamaindex_runtime/test_tree_structure_quality.py -q` |
| **Full suite command** | `pytest tests/llamaindex_runtime/test_query_quality_validation.py tests/llamaindex_runtime/test_tree_structure_quality.py tests/llamaindex_runtime/test_evidence_chain_completeness.py tests/llamaindex_runtime/test_level_assessment.py -q` |
| **Estimated runtime** | ~240 seconds |

---

## Sampling Rate

- **After every task commit:** run the most relevant focused test or validation script
- **After every workstream:** refresh the corresponding machine-readable artifact
- **Before closeout:** full validation suite + manual judgment consistency check must be green
- **Max feedback latency:** 240 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 04-01-01 | 01 | 1 | P4-QUAL-01 | state / artifact consistency | compare ROADMAP/STATE/workspace-memory vs validation outputs | pending |
| 04-01-02 | 01 | 1 | P4-QUAL-02 | tree-quality regression | `pytest tests/llamaindex_runtime/test_tree_structure_quality.py -q` | pending |
| 04-01-03 | 01 | 1 | P4-QUAL-03 | evidence-chain regression | `pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py -q` | pending |
| 04-01-04 | 01 | 1 | P4-QUAL-04 | final level gate | `pytest tests/llamaindex_runtime/test_level_assessment.py -q` | pending |

---

## Wave 0 Requirements

- [ ] authoritative baseline report or equivalent state reconciliation output
- [ ] refreshed `validation_status.json`
- [ ] refreshed `judgment_completed.csv`
- [ ] refreshed `level_assessment.json`

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|------------|-------------------|
| Confirm document/query domain alignment | Human review needed to confirm business-query set actually matches selected corpus | Review query set and selected validation document(s) before re-run |
| Confirm final readiness conclusion | Final no-go / go decision must match both machine artifacts and human judgment | Compare `level_assessment.json`, `FINAL-REPORT.md`, and status board wording |

---

## Validation Sign-Off

- [ ] Current phase and Level baseline are stated consistently across planning files and verification artifacts
- [ ] New validation corpus matches intended business-query domain
- [ ] Tree depth reaches >= 3
- [ ] node-chunk mapping and heading-path completeness are restored to measurable, non-empty values
- [ ] Revalidation follows frozen Phase 2 thresholds without relaxation
- [ ] Final Level judgment is consistent across JSON/report/state outputs

**Approval:** partial; Phase 4 closed with blockers documented
