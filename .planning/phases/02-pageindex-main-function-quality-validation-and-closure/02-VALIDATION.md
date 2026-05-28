---
phase: 2
slug: pageindex-main-function-quality-validation-and-closure
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-28
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for PageIndex quality validation and closure.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pytest.ini |
| **Quick run command** | `pytest tests/llamaindex_runtime/test_query_quality_validation.py -q` |
| **Full suite command** | `pytest tests/llamaindex_runtime/test_query_quality_validation.py tests/llamaindex_runtime/test_tree_structure_quality.py tests/llamaindex_runtime/test_evidence_chain_completeness.py tests/llamaindex_runtime/test_level_assessment.py -q` |
| **Estimated runtime** | ~180 seconds |

---

## Sampling Rate

- **After every task commit:** Run the focused validation file for the task area
- **After every plan wave:** Run the full Phase 2 validation suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | QUAL-01 | T-02-01 | query fixtures remain controlled and non-free-form | integration | `pytest tests/llamaindex_runtime/test_query_quality_validation.py -q` | ✅ | pending |
| 02-01-02 | 01 | 1 | QUAL-02 | T-02-04 | donor/tree diagnosis stays evidence-based | integration | `pytest tests/llamaindex_runtime/test_tree_structure_quality.py -q` | ✅ | pending |
| 02-01-03 | 01 | 1 | QUAL-03 | T-02-02 | provenance metrics are exported without raw document leaks | integration | `pytest tests/llamaindex_runtime/test_evidence_chain_completeness.py -q` | ✅ | pending |
| 02-01-04 | 01 | 1 | QUAL-04 | T-02-03 | readiness decision is derived only from measured artifacts | integration | `pytest tests/llamaindex_runtime/test_level_assessment.py -q` | ✅ | pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/llamaindex_runtime/test_query_quality_validation.py` — query-quality assertions and threshold checks
- [ ] `tests/llamaindex_runtime/test_tree_structure_quality.py` — tree-quality diagnosis assertions
- [ ] `tests/llamaindex_runtime/test_evidence_chain_completeness.py` — evidence completeness assertions
- [ ] `tests/llamaindex_runtime/test_level_assessment.py` — closeout gate assertions

*Existing infrastructure covers the rest of the phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Review the published status board against the JSON verdicts | QUAL-04 | Confirms the human-facing summary matches the machine-readable readiness decision | Open `verification/pageindex_main_status_board.html` and compare it with `verification/quality-validation-20260528/level_assessment.json` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all missing references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
