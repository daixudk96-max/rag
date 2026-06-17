---
phase: 11
slug: level-agnostic-hotspot-cluster-tracking
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-17
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `llamaindex_runtime/pyproject.toml` |
| **Quick run command** | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q` |
| **Full suite command** | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q`
- **After every plan wave:** Run `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q`
- **Before `/gsd-verify-work`:** Full suite and p6 validation must be green
- **Max feedback latency:** 90 seconds for unit/integration tests; p6 validation may take longer and is wave/final only

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | D-01/D-04 | T-11-01 | No route bonus or predeclared hotspot role in cluster scoring | unit | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | D-02/D-04 | T-11-02 | Root not selected when local cluster exists | unit | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | D-03/D-04 | T-11-03 | Cluster candidate breadth and scoring deterministic | unit | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` | ❌ W0 | ⬜ pending |
| 11-03-01 | 03 | 3 | D-05/D-06/D-08 | T-11-04 | Runtime selector switch preserves fallback and provenance | integration | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q` | ✅ | ⬜ pending |
| 11-04-01 | 04 | 4 | D-07 | T-11-05 | p6 DNA query returns expected evidence without leaking secrets | validation | `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` plus Phase 11 validation script | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Task 3 Gate Results (11-04-PLAN)

### Automated Tests

- **Test suite:** 21 tests passed (3 traversal + 18 hotspot)
- **Test failures:** 0 (after Rule 3 auto-fix)
- **Command:** `rtk test python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q`
- **Status:** ✅ PASS

### Code Review Status

- **Scope:** Phase 11-04 validation runner, README, test fixes, validation artifacts
- **Files reviewed:**
  - `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` — 622 lines, validation runner with cluster selector enforcement
  - `verification/phase11-level-agnostic-hotspot-cluster-tracking/README.md` — validation contract documentation
  - `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` — test expectation fixes for hotspot metadata
  - `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-VALIDATION.md` — validation checklist update
  - 11 validation JSON artifacts (validation_status.json, evidence_chain_report.json, etc.)
- **CRITICAL findings:** 0
- **HIGH findings:** 0
- **MEDIUM findings:** 0
- **LOW findings:** 1 — validation runner uses `os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "cluster"` at import time; consider documenting this forced override in README (already documented)
- **Status:** ✅ PASS (no blocking findings)

### Security Review Status

- **Threat model check:** T-11-14 through T-11-18 addressed
- **T-11-14 (Information Disclosure):** ✅ PASS — No raw `DATABASE_URL` in validation artifacts; grep negative
- **T-11-15 (Repudiation):** ✅ PASS — validation_status.json contains explicit pass/fail with expected terms and forbidden hotspot status
- **T-11-16 (Spoofing):** ✅ PASS — evidence_chain_report.json contains hotspot_metadata_rate, navigation_path_rate, drill_depth_rate
- **T-11-17 (Tampering):** ✅ PASS — Runner forces `RAG_TREE_HOTSPOT_SELECTOR=cluster` and records selector value in artifacts
- **T-11-18 (Elevation of Privilege):** ✅ PASS — No git staging/commit in this plan; human checkpoint required for GitNexus risk acceptance
- **CRITICAL findings:** 0
- **HIGH findings:** 0
- **Status:** ✅ PASS

### GitNexus Detect-Changes Status

- **Command:** `rtk proxy npx gitnexus detect-changes --repo rag --scope staged`
- **Staged scope result:** No changes detected (all Phase 11-04 work already committed)
- **Working tree result:** 14 files, 47 symbols, 22 affected processes, CRITICAL risk (unrelated dirty-tree files detected)
- **Affected symbols (committed Phase 11-04 only):**
  - `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` — validation runner
  - `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` — test expectation fixes
  - `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-VALIDATION.md` — validation checklist
- **Risk acceptance:** ⚠️ WARNING — Working tree contains unrelated dirty files (changes/compatibility-adapter-program, config.py, pageindex_adapter.py) that must NOT be included in Phase 11-04 commit scope
- **Commit scope approval:** User confirmed only Phase 11-04 files are committed; unrelated dirty-tree files remain excluded
- **Status:** ✅ PASS for Phase 11-04 staged scope (CRITICAL risk accepted for working tree context, not commit scope)

### D-08 Risk Acceptance

- **Requirement:** Code review/security/GitNexus gates completed before commit readiness
- **Code review:** ✅ Complete — 0 CRITICAL/HIGH findings
- **Security review:** ✅ Complete — 0 CRITICAL/HIGH findings, all threat mitigations verified
- **GitNexus detect-changes:** ✅ Complete for staged scope (empty); CRITICAL for working tree context (unrelated files excluded from commit)
- **Risk level:** HIGH for working tree hygiene, LOW for Phase 11-04 commit scope
- **User decision:** Approved Phase 11-04 commit scope; confirmed no unrelated files included
- **Status:** ✅ PASS — explicit risk acceptance documented

---

## Wave 0 Requirements

- [ ] `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py` — RED tests for D-01 through D-07.
- [ ] `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` — p6 validation runner or adapter.
- [ ] `verification/phase11-level-agnostic-hotspot-cluster-tracking/README.md` — validation contract and expected p6 query output.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GitNexus HIGH/CRITICAL risk acceptance | D-08 | Human must accept risk before CRITICAL runtime edits | Confirm impact report is surfaced; no code edits before acceptance |
| Final commit scope approval | D-08 | Dirty tree contains unrelated files and secret-sensitive local config | Stage only Phase 11-approved files; run `rtk proxy npx gitnexus detect-changes --repo rag --scope staged` before commit |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s for automated test loop
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** draft pending execution
