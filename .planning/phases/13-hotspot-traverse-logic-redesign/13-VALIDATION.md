---
phase: 13
slug: hotspot-traverse-logic-redesign
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-25
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python) |
| **Config file** | implicit pytest discovery (no pytest.ini in root) |
| **Quick run command** | `python -m pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q` |
| **Full suite command** | `python -m pytest tests/llamaindex_runtime/test_tree_traversal.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_hiro_traversal_integration.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q` |
| **Estimated runtime** | ~35 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q`
- **After every plan wave:** Run full suite command above
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~35 seconds

---

## Per-Task Verification Map

> Task-ID format is `{phase}-{plan}-{task}`. The Plan/Wave columns below match each
> plan's frontmatter ownership (Plan 01 → Wave 1; Plan 02 → Wave 2; Plan 03 → Wave 3).
> The PLAN.md files are authoritative; this map is the executor's verification index.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-00 | 01 | 1 | Safety gate: GitNexus impact analysis before edits (CLAUDE.md) | — | N/A | manual | GitNexus MCP `gitnexus_impact` (no automated cmd); proven by blast-radius table in 13-01-SUMMARY.md | n/a | pending |
| 13-01-01 | 01 | 1 | P13-07: BaselinePolicy.evaluate_children returns correct dict shape | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildren -q` | Wave 0 | pending |
| 13-01-02 | 01 | 1 | P13-08: Baseline selects best-similarity child for drill_down | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildrenDrillDown -q` | Wave 0 | pending |
| 13-01-03 | 01 | 1 | P13-09: Baseline returns keep_parent when best child is keep_parent | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildrenKeepParent -q` | Wave 0 | pending |
| 13-01-04 | 01 | 1 | P13-11: HIRO evaluate_children regression (pre-existing test, guarded below) | — | N/A | regression | `pytest tests/llamaindex_runtime/test_hiro_traversal_integration.py -q` | Exists ✓ | pending |
| 13-02-01 | 02 | 2 | P13-01: dispatch detection (hotspot_node_id == start_node_id) | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotTraversalDispatch -q` | Wave 0 | pending |
| 13-02-02 | 02 | 2 | P13-02: waypoint + evidence hits returned | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotWithChildren -q` | Wave 0 | pending |
| 13-02-03 | 02 | 2 | P13-03: waypoint drill_depth=0, evidence drill_depth=1 | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestWaypointShape -q` | Wave 0 | pending |
| 13-02-04 | 02 | 2 | P13-04: evidence hits carry real chunk_id | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestEvidenceHitShape -q` | Wave 0 | pending |
| 13-02-05 | 02 | 2 | P13-05: no-children edge case returns waypoint only | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotNoChildren -q` | Wave 0 | pending |
| 13-02-06 | 02 | 2 | P13-06: route-only children edge case — waypoint only, no evidence | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotRouteOnlyChildren -q` | Wave 0 | pending |
| 13-02-07 | 02 | 2 | P13-10: policy.evaluate_children called on child stats (not hotspot parent) | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestPolicyEvaluateChildrenCalledOnChildStats -q` | Wave 0 | pending |
| 13-02-08 | 02 | 2 | P13-14: non-hotspot root traversal unaffected | — | N/A | regression | `pytest tests/llamaindex_runtime/test_tree_traversal.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q` | Exists ✓ | pending |
| 13-03-01 | 03 | 3 | P13-12: fallback dict has chunk_id field after fix | — | N/A | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestFallbackDictChunkId -q` | Wave 0 | pending |
| 13-03-02 | 03 | 3 | P13-13: p6 DNA regression still passes | — | N/A | regression | `pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py::TestClusterHotspotSelector::test_p6_ai_product_manager_core_dna_routes_to_product_characteristics -q` | Exists ✓ | pending |
| 13-03-03 | 03 | 3 | P13-15: _map_query_hits_to_backend_hits skips waypoints | — | N/A | regression | `pytest tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q` | Exists ✓ | pending |
| 13-03-99 | 03 | 3 | Safety gate: GitNexus detect-changes before commit (CLAUDE.md) | — | N/A | manual | GitNexus MCP `gitnexus_detect_changes` (no automated cmd); proven by affected-scope table in 13-03-SUMMARY.md | n/a | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- [ ] `tests/llamaindex_runtime/test_hotspot_traversal_logic.py` — New file; must be created before any Wave 1 task commits. Covers P13-01 through P13-12 (12 unit test cases). Required test classes:
  - `TestHotspotTraversalDispatch` — verifies detection and dispatch (P13-01)
  - `TestHotspotWithChildren` — waypoint + evidence returned (P13-02)
  - `TestWaypointShape` — drill_depth=0 for waypoint (P13-03)
  - `TestEvidenceHitShape` — real chunk_id in evidence hits (P13-04)
  - `TestHotspotNoChildren` — waypoint-only for childless hotspot (P13-05)
  - `TestHotspotRouteOnlyChildren` — waypoint-only when children have no chunk_ids (P13-06)
  - `TestBaselineEvaluateChildren` — correct return dict shape (P13-07)
  - `TestBaselineEvaluateChildrenDrillDown` — best similarity child selected (P13-08)
  - `TestBaselineEvaluateChildrenKeepParent` — keep_parent propagation (P13-09)
  - `TestPolicyEvaluateChildrenCalledOnChildStats` — policy.evaluate_children called on child stats not parent (P13-10)
  - `TestFallbackDictChunkId` — fallback dict contains chunk_id field (P13-12)

Existing infrastructure covers all regression tests (P13-11, P13-13, P13-14, P13-15) — no new files needed for those.

**Pre-existing regression files (must exist before their guarded task runs — grep-verifiable):**
- `tests/llamaindex_runtime/test_hiro_traversal_integration.py` (P13-11, Plan 01 Task 4) — guard: `test -f tests/llamaindex_runtime/test_hiro_traversal_integration.py`
- `tests/llamaindex_runtime/test_tree_traversal.py` + `test_tree_semantic_hotspot.py` (P13-14, Plan 02) — guard: `test -f tests/llamaindex_runtime/test_tree_traversal.py`
- `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py` (P13-13 p6 DNA, Plan 03) — guard: `test -f tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py`
- `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` (P13-15, Plan 03) — guard: `test -f tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py`

If any guard fails (file absent), the regression acceptance criterion is a false-negative — surface as a setup error, do not mark the task green. All four were confirmed present at plan time (2026-06-25).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Q18 `chunk_id=null` resolved in real DB | P13 overall goal | Requires running PostgreSQL + live validation pipeline | Run `python verification/real-document-validation-2026-06-23/run_validation.py --phase retrieve` with DATABASE_URL set; verify Q18 shows chunk_id != null and zero_chunk_hits decreases |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 35s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
