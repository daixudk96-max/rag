---
phase: 12
slug: cluster-hot-hotspot-selection-redesign
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-22
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` / existing `tests/llamaindex_runtime/` |
| **Quick run command** | `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q` |
| **Cluster/regression command** | `python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` |
| **Full suite command** | `python -m pytest tests/llamaindex_runtime/ -q` |
| **Estimated runtime** | ~30–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the touched selector test file.
- **After every plan wave:** Run the full `tests/llamaindex_runtime/` suite.
- **Before `/gsd-verify-work`:** Full suite must be green, including p6 DNA regression.
- **Max feedback latency:** ~90 seconds.

---

## Per-Task Verification Map

> One row per task across all 4 plans (9 tasks total). GitNexus impact-analysis and
> detect-changes tasks are `checkpoint:manual` — they have no automated command and are
> verified by a file-existence gate (the SUMMARY artifact). Sampling-continuity holds:
> the automated/manual sequence is M, A, A, A, M, A, A, A, M — no 3 consecutive tasks
> without an automated verify (each manual checkpoint is bracketed by automated tasks).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-T1 | 01 | 1 | D-07 (safety gate) | T-12-01 | provenance: real node_ids only | checkpoint:manual | `manual` — file-existence: 12-01-SUMMARY.md blast-radius table for HotspotSelectionContext / _build_report / analyze_tree_semantic_distribution | ✅ | ⬜ pending |
| 12-01-T2 | 01 | 1 | D-07 | T-12-01 | denominator carries only real node_ids | unit | `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q -k "context or parent_to_children"` | ✅ | ⬜ pending |
| 12-01-T3 | 01 | 1 | D-07 | T-12-03 | additive kwarg, rollback branches untouched | unit | `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q` | ✅ | ⬜ pending |
| 12-02-T1 | 02 | 2 | D-01/D-02/D-05/D-06/D-10 | T-12-04 | test-as-spec; no domain literals | unit (RED) | `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q -k "coverage or dual or theta or fallback"` (RED in wave 2, GREEN after 12-03) | ✅ | ⬜ pending |
| 12-03-T1 | 03 | 3 | D-01..D-09 (safety gate) | T-12-05 | impact-before-edit on CRITICAL path | checkpoint:manual | `manual` — file-existence: 12-03-SUMMARY.md blast-radius table for HybridClusterHotspotSelector / select_hotspots | ✅ | ⬜ pending |
| 12-03-T2 | 03 | 3 | D-01/D-02/D-03/D-04/D-05/D-06/D-08/D-09 | T-12-05/T-12-06 | emit only node_stats-backed hotspots; bounded coverage loop | unit | `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q -k "coverage or dual or theta or fallback"` | ✅ | ⬜ pending |
| 12-04-T1 | 04 | 4 | D-10 | T-12-09 | DNA assertions unweakened; evidence-bearing only | regression | `python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q` | ✅ | ⬜ pending |
| 12-04-T2 | 04 | 4 | D-09/D-10 | — | rollback paths + anti-hardcode intact | regression | `python -m pytest tests/llamaindex_runtime/ -q` | ✅ | ⬜ pending |
| 12-04-T3 | 04 | 4 | D-09 (safety gate) | T-12-08 | scoped commit; detect-changes before commit | checkpoint:manual | `manual` — file-existence: 12-04-SUMMARY.md detect-changes scope table + commit hash | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs are `{plan}-T{n}` matching the `<task>` order in each PLAN.md.*

---

## Wave 0 Requirements

- [x] No new framework — existing `tests/llamaindex_runtime/` pytest infrastructure covers all phase requirements.
- [x] New/rewritten test cases land in the two existing selector test files (no new conftest needed).

*Existing infrastructure covers all phase requirements; no MISSING automated references remain (the three `manual` rows are `checkpoint:manual` GitNexus gates verified by SUMMARY file-existence, not MISSING test scaffolds).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GitNexus impact blast radius before editing guarded symbols (12-01-T1, 12-03-T1) | D-07 / D-09 safety gates | GitNexus MCP step; no CLI/API equivalent | Run `gitnexus_impact(...)` for the listed symbols; record the blast-radius table in the plan SUMMARY (file-existence gate) |
| GitNexus detect-changes before commit (12-04-T3) | D-09 safety gate | GitNexus MCP step; no CLI/API equivalent | Run `gitnexus_detect_changes()`; record affected-scope table + commit hash in 12-04-SUMMARY.md |
| DB-backed live retrieval still returns span_ids / navigation_path / drill_depth on p6 | D-08 | Needs Docker/PostgreSQL + embeddings; not a unit test | Start Postgres, run a focused p6 deep query under `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster`, confirm hit metadata present |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the three GitNexus tasks are `checkpoint:manual` with file-existence gates, correctly excluded from the automated-verify requirement)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (sequence M,A,A,A,M,A,A,A,M)
- [x] Wave 0 covers all MISSING references (none remain; no MISSING test scaffolds)
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
