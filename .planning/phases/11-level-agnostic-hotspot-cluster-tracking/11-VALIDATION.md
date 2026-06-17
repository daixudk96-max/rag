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
