---
phase: 7
slug: db-backed-evidence-chain-rerun
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-08
---

# Phase 7 — Validation Strategy

> Validation contract for DB-backed evidence-chain rerun.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + JSON artifact checks |
| **Config file** | pytest.ini |
| **Quick run command** | `PYTHONPATH=E:/github/rag pytest tests/verification/test_validation_integrity.py -q` |
| **Full suite command** | `PYTHONPATH=E:/github/rag pytest tests/verification/test_validation_integrity.py tests/llamaindex_runtime/test_vector_loader.py tests/llamaindex_runtime/test_evidence_chain_completeness.py -q` |
| **Estimated runtime** | ~240 seconds |

---

## Sampling Rate

- **After every task commit:** Run focused grep/compile/pytest checks for the changed artifact.
- **After every plan wave:** Run the full suite command if code changed; otherwise run JSON artifact grep checks.
- **Before `/gsd-verify-work`:** `evidence_chain_delta.json` and `07-SUMMARY.md` must exist.
- **Max feedback latency:** 240 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | T-07-01 | DB readiness artifact must not leak raw DATABASE_URL | unit/artifact | `rtk grep "database_url_configured" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | T-07-02 | Counts must be active-version scoped before/after materialization | integration/artifact | `rtk grep "classification" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 2 | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | T-07-02 | Delta must classify READY/BLOCKED from before/after counts | artifact | `rtk grep "final_classification" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 3 | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | T-07-03 | Summary must preserve Level 2 and defer judgments to Phase 8 | doc integrity | `rtk grep "Level 2 remains authoritative" .planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

Existing Phase 5 utilities cover the code paths:

- `verification/phase5-evidence-chain-verification/verify_active_version_counts.py`
- `verification/phase5-evidence-chain-verification/invoke_vector_loader.py`
- `verification/phase5-evidence-chain-verification/validation_integrity_gate.py`
- `tests/verification/test_validation_integrity.py`
- `tests/llamaindex_runtime/test_vector_loader.py`
- `tests/llamaindex_runtime/test_evidence_chain_completeness.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Configure DB access if `DATABASE_URL` is missing | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | Secrets must not be invented or printed by Claude | If `db_readiness.json` reports `not_configured`, user must provide DB configuration outside source files. |
| Interpret persistent evidence-chain zeros | REQ-P7-DB-EVIDENCE-CHAIN-PROOF | A zero state may represent real ingestion/materialization blocker | Review `evidence_chain_delta.json`; decide whether to fix ingestion before Phase 8. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency < 240s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
