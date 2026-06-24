# Phase 13: Hotspot Traverse Logic Redesign — Research

**Researched:** 2026-06-25
**Domain:** Python / Tree traversal logic / hotspot navigation (llamaindex_runtime/tree)
**Confidence:** HIGH

---

## Summary

Phase 13 fixes Q18 `chunk_id=null` empty-evidence hits by redesigning `RecursiveTreeTraversalRunner` so that when a traversal starts at a hotspot node, it unconditionally emits a **waypoint hit** (navigation marker, `chunk_id=MISSING_CHUNK_ID`, `drill_depth=0`) PLUS evidence hits from exactly one level of direct children, then delegates further drill-down decisions to `policy.evaluate_children` on child stats — not on the hotspot parent.

The root cause is a 7-step evidence chain confirmed by `BUG_ANALYSIS_Q18_TRAVERSE_LOGIC.md`: the `HybridClusterHotspotSelector` (Phase 12) correctly selects a parent node as the hotspot, but the parent node has no direct vectors and is filtered out at `semantic_distribution.py:243-244` from `node_stats_list`. `_traverse_from_node` finds `node_stats=None` at line 1720 and returns `[]`. The caller (`runtime.py:373-374`) sees `backend_hits=[]` and invokes `_score_tree_nodes_with_fallback`, whose dict (lines 486-494) has no `chunk_id` key — causing `chunk_id=null` in verification output.

The approved design (`.planning/TRAVERSE-LOGIC-REDESIGN-PLAN.md`, approved 2026-06-24) resolves this with 5 implementation areas: (1) hotspot-traversal detection at the `traverse_tree_for_query` entry, (2) new `_traverse_hotspot_with_children` method on `RecursiveTreeTraversalRunner`, (3) new `_build_waypoint_hit` module-level function, (4) `BaselineTreeBranchDecisionPolicy.evaluate_children` method (parity with HIRO), (5) fallback dict `chunk_id` field as a defensive backstop.

**Primary recommendation:** Implement the 5 areas in the order given. The hotspot detection + `_traverse_hotspot_with_children` combination short-circuits the `node_stats=None` early-return that is the proximate cause; the fallback dict fix is a defense-in-depth measure.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hotspot traversal dispatch | API / Backend (RecursiveTreeTraversalRunner) | — | Traversal runner owns the dispatch decision at entry |
| Waypoint hit construction | API / Backend (_build_waypoint_hit helper) | — | Pure function over tree-node data, no registry I/O |
| Evidence hit construction | API / Backend (_build_hits_from_node) | — | Existing helper; reused unchanged |
| Child stats similarity | API / Backend (_cosine_similarity) | — | Existing pure function; reused unchanged |
| Policy decision on children | API / Backend (policy.evaluate_children) | — | Both Baseline and HIRO policy live in the same layer |
| Fallback dict backstop | API / Backend (runtime._score_tree_nodes_with_fallback) | — | Runtime-layer safety net |
| Q18 E2E re-validation | Validation layer (run_validation.py) | — | Verification script maps hits to evidence chain |

---

## Standard Stack

### Core (verified against live code)

| Symbol | File | Current Lines | Confidence |
|--------|------|--------------|------------|
| `RecursiveTreeTraversalRunner.traverse_tree_for_query` | `llamaindex_runtime/tree/semantic_distribution.py` | 1627–1690 | HIGH [VERIFIED: read] |
| `RecursiveTreeTraversalRunner._traverse_from_node` | `llamaindex_runtime/tree/semantic_distribution.py` | 1692–1903 | HIGH [VERIFIED: read] |
| `BaselineTreeBranchDecisionPolicy` | `llamaindex_runtime/tree/semantic_distribution.py` | 70–106 | HIGH [VERIFIED: read] |
| `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children` | `llamaindex_runtime/tree/hiro_decision_policy.py` | 110–157 | HIGH [VERIFIED: read] |
| `QueryHit` dataclass | `llamaindex_runtime/tree/semantic_distribution.py` | 475–492 | HIGH [VERIFIED: read] |
| `MISSING_CHUNK_ID` | `llamaindex_runtime/tree/runtime.py` | 86 | HIGH [VERIFIED: read] |
| `_build_hits_from_node` | `llamaindex_runtime/tree/semantic_distribution.py` | 1930–1971 | HIGH [VERIFIED: read] |
| `_cosine_similarity` | `llamaindex_runtime/tree/semantic_distribution.py` | 1906–1927 | HIGH [VERIFIED: read] |
| `_score_tree_nodes_with_fallback` | `llamaindex_runtime/tree/runtime.py` | 473–497 | HIGH [VERIFIED: read] |
| `_map_query_hits_to_backend_hits` | `llamaindex_runtime/tree/runtime.py` | 500–565 | HIGH [VERIFIED: read] |

### Supporting

| Symbol | File | Notes |
|--------|------|-------|
| `node_stats_list` construction | `semantic_distribution.py:237-268` | `if not vectors: continue` at line 243 is the filter that excludes route parents |
| `is_route_node` flag | `semantic_distribution.py:266` | `not direct_chunk_ids and bool(subtree_chunk_ids)` |
| Hotspot traversal wiring | `runtime.py:340-353` | `start_node_id=hotspot.node_id, hotspot_node_id=hotspot.node_id` passed to runner |
| Fallback trigger | `runtime.py:373-374` | `if not backend_hits:` → `_score_tree_nodes_with_fallback` |
| `_map_query_hits_to_backend_hits` chunk-filter | `runtime.py:512` | `if hit.chunk_id == MISSING_CHUNK_ID ... : continue` — waypoint hits are already excluded here |

---

## Architecture Patterns

### System Architecture Diagram

```
Query Request
     │
     ▼
runtime._retrieve_tree_hits_from_backend
     │
     ├─► HybridClusterHotspotSelector.select_hotspots  → SubtreeHotspot(node_id=parent)
     │
     ▼
RecursiveTreeTraversalRunner.traverse_tree_for_query
     │  [NEW] is_hotspot_traversal? (hotspot_node_id == start_node_id)
     ├─► YES ──► _traverse_hotspot_with_children (NEW)
     │                │
     │                ├─► _build_waypoint_hit(hotspot_node) → QueryHit(chunk_id=MISSING_CHUNK_ID)
     │                │
     │                ├─► collect direct children from node_by_id
     │                │
     │                ├─► compute child similarities via _cosine_similarity
     │                │
     │                ├─► _build_hits_from_node(child) → QueryHit(chunk_id=real_uuid)  [per child]
     │                │
     │                └─► policy.evaluate_children(child_stats) → {decision, selected_child_id}
     │                         │
     │                         └─► if drill_down: _traverse_from_node(selected_child)
     │
     └─► NO ──► original _traverse_from_node (unchanged)
     │
     ▼
_map_query_hits_to_backend_hits
     │  (skips hits where chunk_id == MISSING_CHUNK_ID at line 512)
     │
     ├─► backend_hits non-empty → ranked result
     │
     └─► backend_hits empty → _score_tree_nodes_with_fallback [DEFENSIVE: add chunk_id field]
```

### Recommended Project Structure

No new files or directories are required. All changes are confined to:

```
llamaindex_runtime/tree/
├── semantic_distribution.py   # 4 of 5 implementation areas
└── runtime.py                 # 1 of 5 implementation areas (fallback backstop)

tests/llamaindex_runtime/
└── test_hotspot_traversal_logic.py   # NEW — Wave 0 test file
```

### Pattern 1: Hotspot Traversal Detection

**What:** At the entry of `traverse_tree_for_query`, detect when traversal is starting from a hotspot node (both `hotspot_node_id` and `start_node_id` are set and equal). Branch to a new dedicated method that enforces the "waypoint + one child level" contract.

**When to use:** Only when `hotspot_node_id is not None and start_node_id is not None and hotspot_node_id == start_node_id`.

**Key insertion point:** After line 1665 (after `start_nodes` resolution) and before the loop at line 1668.

```python
# [VERIFIED: read semantic_distribution.py:1627-1690]
# Insert after start_nodes resolution:
is_hotspot_traversal = (
    hotspot_node_id is not None
    and start_node_id is not None
    and hotspot_node_id == start_node_id
)
if is_hotspot_traversal and start_nodes:
    return self._traverse_hotspot_with_children(
        hotspot_node=start_nodes[0],
        version_id=version_id,
        query_embedding=query_embedding,
        node_stats_list=node_stats_list,
        node_by_id=node_by_id,
        tree_signals=tree_signals,
        policy=policy,
        registry=registry,
        doc_id=doc_id,
        chunk_to_span_ids=chunk_to_span_ids,
        max_depth=max_depth,
    )
```

### Pattern 2: Waypoint Hit Shape

**What:** `chunk_id=MISSING_CHUNK_ID`, `span_id=UUID(int=node_id.int & (2**63 - 1))` (synthetic, not in DB), `similarity_score=0.0`, `drill_depth=0`, `hotspot_node_id=hotspot_node_id`, `navigation_node_ids=(hotspot_node_id,)`.

**Critical constraint:** `_map_query_hits_to_backend_hits` at runtime.py:512 already skips hits where `chunk_id == MISSING_CHUNK_ID`. Waypoint hits will NOT appear in backend_hits. They only affect `backend_hits` being non-empty if the hotspot-traversal also produces evidence hits from children. This is the intended behavior — the waypoint prevents the `backend_hits=[]` trigger, but the waypoint itself is filtered before being exposed to the caller.

**Wait — landmine:** The current `_map_query_hits_to_backend_hits` at line 512 skips `MISSING_CHUNK_ID` hits. If ALL children are route-only (no chunk_ids), `_traverse_hotspot_with_children` returns only the waypoint hit, `_map_query_hits_to_backend_hits` filters it out, and `backend_hits` is still `[]` — fallback still triggers. The waypoint alone does NOT prevent the fallback. See Landmines section.

### Pattern 3: Baseline evaluate_children Signature

**What:** Must match HIRO's `evaluate_children` signature exactly (keyword-only, `child_stats: list[dict[str, Any]]`, `tree_signals: dict[str, Any]`, returns `dict[str, Any]` with keys `decision`, `selected_child_id`, `child_decisions`).

```python
# [VERIFIED: read hiro_decision_policy.py:110-157]
def evaluate_children(
    self,
    *,
    child_stats: list[dict[str, Any]],
    tree_signals: dict[str, Any],
) -> dict[str, Any]:
    ...
```

`BaselineTreeBranchDecisionPolicy` is a `@dataclass(frozen=True)` — the new method must not mutate `self`.

### Anti-Patterns to Avoid

- **Anti-pattern 1 — Importing MISSING_CHUNK_ID inside `_build_waypoint_hit` via a late import:** The design doc proposes `from llamaindex_runtime.tree.runtime import MISSING_CHUNK_ID` inside `_build_waypoint_hit`. This creates a circular import risk (`semantic_distribution.py` → `runtime.py` and `runtime.py` → `semantic_distribution.py`). **Instead:** import `MISSING_CHUNK_ID` at the top of `semantic_distribution.py` or define the constant directly. Verify import graph before adding.

- **Anti-pattern 2 — Assuming waypoints prevent the backend_hits=[] fallback:** `_map_query_hits_to_backend_hits` filters out `MISSING_CHUNK_ID` hits (line 512). A waypoint-only result still triggers the fallback. Evidence hits (from children with real chunk_ids) are what prevent the fallback.

- **Anti-pattern 3 — Building child lookup by iterating all `node_by_id` values:** The design doc's child collection (`for child_id in node_by_id if node_by_id[child_id].get("parent_node_id") == hotspot_node_id`) is O(N) over all nodes per hotspot. For large trees this is acceptable but worth documenting. The existing `_traverse_from_node` uses the same pattern at lines 1769-1773, confirming it is established convention here.

- **Anti-pattern 4 — Calling `evaluate_children` when there are no child_stats_with_similarity:** Guard with `if hasattr(policy, "evaluate_children") and child_stats_with_similarity:` (matching the pattern at line 1784).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Similarity computation | Custom dot-product | `_cosine_similarity(query_embedding, prototype)` (line 1906) | Already handles empty vectors, matches existing traversal behavior |
| Evidence hit construction | Manual QueryHit assembly | `_build_hits_from_node(node_stats, ...)` (line 1930) | Handles multi-span chunk expansion and all provenance fields |
| Missing chunk sentinel | Any other UUID sentinel | `MISSING_CHUNK_ID = UUID(int=0)` (runtime.py:86) | Already referenced at runtime.py:512 filter |
| Children collection | Recursive subtree walk | Direct children only: `parent_node_id == hotspot_node_id` | Design specifies "one level" — do not recurse past direct children |

---

## Runtime State Inventory

> Omitted — greenfield additions, no rename/migration involved.

---

## Common Pitfalls

### Pitfall 1: Circular Import from `_build_waypoint_hit`

**What goes wrong:** Design doc proposes `from llamaindex_runtime.tree.runtime import MISSING_CHUNK_ID` inside `_build_waypoint_hit`. `runtime.py` already imports from `semantic_distribution.py`. Adding the reverse import creates a circular dependency.

**Why it happens:** `MISSING_CHUNK_ID` is defined in `runtime.py:86`, but the new helper lives in `semantic_distribution.py`.

**How to avoid:** Define `MISSING_CHUNK_ID` as a module-level constant in `semantic_distribution.py` (duplicate the `UUID(int=0)` definition), or move it to a shared `_constants.py`. Do NOT add a top-level import of `runtime.py` in `semantic_distribution.py`.

**Warning signs:** `ImportError: cannot import name 'MISSING_CHUNK_ID'` or silent partial-import failures on module load.

### Pitfall 2: Waypoint Does Not Prevent Fallback for Route-Only Hotspots

**What goes wrong:** If the hotspot node's direct children are all route nodes (no direct chunk_ids themselves), `evidence_hits=[]`. The only result is the waypoint hit. `_map_query_hits_to_backend_hits` filters waypoints at line 512, leaving `backend_hits=[]`. The fallback is still triggered.

**Why it happens:** The design intends waypoints as navigation markers, and the mapper correctly skips them. Route-only children produce no `evidence_hits` from `_build_hits_from_node` because `chunk_ids=[]` for those children.

**How to avoid:** Accept this as correct behavior for the "route-only children" edge case. In this case, the Phase 5 fallback dict fix (adding `chunk_id=MISSING_CHUNK_ID` to the fallback dict) is what actually prevents the `chunk_id=null` symptom. Both fixes are necessary for complete coverage. Document the edge case in the new test: `test_hotspot_all_children_route_only_falls_to_fallback_backstop`.

**Warning signs:** Q18 still shows `chunk_id=null` after implementing only Phase 1-4 but not Phase 5.

### Pitfall 3: `_traverse_hotspot_with_children` Calls `_traverse_from_node` Recursively for Selected Child

**What goes wrong:** The further-drill step inside `_traverse_hotspot_with_children` calls `self._traverse_from_node(node=selected_child_node, ...)` with `current_depth=2`. This re-enters the standard traversal path where `node_stats=None` can again cause early return `[]` if the selected child is also a route node without stats.

**Why it happens:** The recursive call is passed to `_traverse_from_node`, which checks `node_stats` at line 1716-1721. If the child has `node_stats` (most leaf nodes do), this works. If the child is another route-like parent without stats, it returns `[]` again — but this only affects the further-drill, not the one-level evidence already collected.

**How to avoid:** The one-level evidence collection does not depend on `node_stats` — it uses `node_by_id` directly. Only the optional further-drill step calls `_traverse_from_node`. The basic Q18 fix still works even if the further-drill returns `[]`.

**Warning signs:** Test `test_hotspot_traversal_with_hiro_policy_drills_into_child` failing when child selected by `evaluate_children` is itself a route node.

### Pitfall 4: `BaselineTreeBranchDecisionPolicy` is a Frozen Dataclass

**What goes wrong:** Attempting to add `evaluate_children` to a `@dataclass(frozen=True)` causes confusion about mutability. The method itself is fine as a pure computation, but the dataclass restriction on `__setattr__` could confuse reviewers.

**Why it happens:** `frozen=True` prevents attribute mutation but does not prevent adding regular methods. This is a non-issue in practice.

**How to avoid:** Simply add the method. No structural change to the dataclass is needed. The method must only read `self.dispersion_threshold`, `self.entropy_threshold`, and `self.min_support_threshold` — no writes.

### Pitfall 5: prototype_embedding vs centroid Key Fallback

**What goes wrong:** Child stat lookup for similarity uses `child_node_stats.get("prototype_embedding") or child_node_stats.get("centroid", [])`. If neither key is present (stats from a very old schema), `child_prototype=[]` → `_cosine_similarity` logs a warning and returns 0.0. That child gets `similarity=0.0`, `query_distance=1.0`, and may be selected by Baseline policy as the worst candidate.

**Why it happens:** `_cosine_similarity` handles empty vectors gracefully (line 1908-1913) but returns 0.0, which is silent data corruption.

**How to avoid:** Skip children where `not child_prototype` — do not add them to `child_stats_with_similarity`. This matches the implicit behavior in `_traverse_from_node` at line 1790-1793.

---

## Code Examples

### Verified: _build_hits_from_node signature

```python
# [VERIFIED: read semantic_distribution.py:1930-1940]
def _build_hits_from_node(
    *,
    node_stats: dict[str, Any],
    version_id: UUID,
    doc_id: UUID,
    similarity: float,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    hotspot_node_id: UUID | None,
    navigation_node_ids: tuple[UUID, ...],
    drill_depth: int,
) -> list[QueryHit]:
```

### Verified: HIROEnhancedTreeBranchDecisionPolicy.evaluate_children return shape

```python
# [VERIFIED: read hiro_decision_policy.py:110-157]
# Returns one of:
{"decision": "drill_down",  "selected_child_id": <UUID>, "child_decisions": {...}}
{"decision": "keep_parent", "selected_child_id": None,   "child_decisions": {...}}
{"decision": "prune",       "selected_child_id": None,   "child_decisions": {...}}
```

### Verified: _map_query_hits_to_backend_hits already filters MISSING_CHUNK_ID

```python
# [VERIFIED: read runtime.py:511-513]
for hit in query_hits:
    if hit.chunk_id == MISSING_CHUNK_ID or hit.chunk_id in seen_chunks:
        continue
```

### Verified: existing hotspot traversal wiring (runtime.py:340-353)

```python
# [VERIFIED: read runtime.py:340-353]
for hotspot in hotspots:
    query_hits.extend(
        runner.traverse_tree_for_query(
            version_id=version_id,
            query_embedding=query_embedding,
            registry=registry,
            policy=policy,
            adapter=adapter,
            start_node_id=hotspot.node_id,
            hotspot_node_id=hotspot.node_id,
        )
    )
```

Both `start_node_id` and `hotspot_node_id` are set to `hotspot.node_id` — the detection condition `hotspot_node_id == start_node_id` is always true in the hotspot traversal path. No change to `runtime.py` calling code is required for the detection to work.

---

## Design-Doc vs Live Code Drift Check

The approved design doc (`TRAVERSE-LOGIC-REDESIGN-PLAN.md`, created 2026-06-24) was validated against commits `d7f7725` and `3296fdb` (Phase 12 final state). Line-by-line comparison:

| Design Doc Claim | Live Code Verification | Status |
|-----------------|----------------------|--------|
| `traverse_tree_for_query` at Line 1627-1690 | Confirmed: lines 1627-1690 [VERIFIED: read] | ACCURATE |
| `BaselineTreeBranchDecisionPolicy` at lines 70-106 | Confirmed: lines 70-106 [VERIFIED: read] | ACCURATE |
| `MISSING_CHUNK_ID = UUID(int=0)` at runtime.py:86 | Confirmed: line 86 [VERIFIED: read] | ACCURATE |
| `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children` at hiro_decision_policy.py:110-157 | Confirmed: lines 110-157 [VERIFIED: read] | ACCURATE |
| `_build_hits_from_node` insertion point "Line 1971 after" | `_build_waypoint_hit` new function goes after `_build_hits_from_node` ends at line 1971. New function at 1972+. Confirmed. | ACCURATE |
| Fallback dict at runtime.py:487-494 (no chunk_id key) | Confirmed: lines 486-494 show dict without chunk_id [VERIFIED: read] | ACCURATE |
| QueryHit schema at semantic_distribution.py:487: `chunk_id: UUID` | Confirmed at line 487 [VERIFIED: read] | ACCURATE |
| Design doc says `_traverse_from_node` exists and is callable | Confirmed: lines 1692+ [VERIFIED: read] | ACCURATE |
| `node_stats filter: if not vectors: continue` at lines 243-244 | Confirmed: line 243 `if not vectors: continue` [VERIFIED: read] | ACCURATE |
| `start_node_id` passed as both `start_node_id` and `hotspot_node_id` in runtime.py:340-353 | Confirmed at runtime.py:350-351 [VERIFIED: read] | ACCURATE |

**Drift verdict: None detected.** The design doc is accurate against the post-Phase-12 codebase.

**One additional finding not in the design doc:** `_map_query_hits_to_backend_hits` at `runtime.py:512` already filters `MISSING_CHUNK_ID` hits. The design doc does not mention this existing filter. Consequence: the waypoint hit is silently dropped before reaching backend output. This is architecturally correct but means:
1. The waypoint hit alone cannot prevent the `backend_hits=[]` fallback trigger.
2. Only real child evidence hits can prevent the fallback.
3. The Phase 5 fallback backstop (adding `chunk_id=MISSING_CHUNK_ID` to the fallback dict) is needed for the "route-only children" edge case even after Phase 1-4 are implemented.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (discovered: `tests/llamaindex_runtime/`) |
| Config file | `pytest.ini` or implicit discovery |
| Quick run command | `python -m pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q` |
| Full suite command | `python -m pytest tests/llamaindex_runtime/test_tree_traversal.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py tests/llamaindex_runtime/test_hiro_traversal_integration.py tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q` |
| Estimated runtime | ~35 seconds (35 existing tests pass in ~29 s) |

### Phase 13 Requirements → Test Map

The 5 implementation areas map to the following testable behaviors:

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| P13-01 | `traverse_tree_for_query` dispatches to `_traverse_hotspot_with_children` when `hotspot_node_id == start_node_id` | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotTraversalDispatch -q` | Wave 0 |
| P13-02 | Hotspot with evidence-bearing children returns waypoint hit (chunk_id=MISSING_CHUNK_ID, drill_depth=0) + real evidence hits | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotWithChildren -q` | Wave 0 |
| P13-03 | Waypoint hit has drill_depth=0, evidence hits have drill_depth=1 | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestWaypointShape -q` | Wave 0 |
| P13-04 | Evidence hits carry real chunk_id (not MISSING_CHUNK_ID) from child node_stats | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestEvidenceHitShape -q` | Wave 0 |
| P13-05 | Hotspot with no children returns waypoint-only list (not empty) | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotNoChildren -q` | Wave 0 |
| P13-06 | Hotspot children that are all route-only (no chunk_ids) produce waypoint only (evidence_hits=[]) | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestHotspotRouteOnlyChildren -q` | Wave 0 |
| P13-07 | `BaselineTreeBranchDecisionPolicy.evaluate_children` returns correct shape matching HIRO protocol | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildren -q` | Wave 0 |
| P13-08 | Baseline `evaluate_children` selects child with highest similarity when best decision is drill_down | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildrenDrillDown -q` | Wave 0 |
| P13-09 | Baseline `evaluate_children` returns keep_parent when best child decision is keep_parent | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestBaselineEvaluateChildrenKeepParent -q` | Wave 0 |
| P13-10 | `_traverse_hotspot_with_children` calls `policy.evaluate_children` on child stats when available | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestPolicyEvaluateChildrenCalledOnChildStats -q` | Wave 0 |
| P13-11 | HIRO `evaluate_children` on children (existing test) still passes after Phase 13 changes | regression | `pytest tests/llamaindex_runtime/test_hiro_traversal_integration.py -q` | Exists |
| P13-12 | Fallback dict now contains chunk_id field (MISSING_CHUNK_ID) when traversal returns empty | unit | `pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py::TestFallbackDictChunkId -q` | Wave 0 |
| P13-13 | p6 DNA regression: existing p6 tests remain green after Phase 13 changes | regression | `pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py::TestClusterHotspotSelector::test_p6_ai_product_manager_core_dna_routes_to_product_characteristics -q` | Exists |
| P13-14 | Non-hotspot root traversal is unaffected (root start_node_id without matching hotspot_node_id takes original path) | regression | `pytest tests/llamaindex_runtime/test_tree_traversal.py tests/llamaindex_runtime/test_tree_semantic_hotspot.py -q` | Exists |
| P13-15 | `_map_query_hits_to_backend_hits` skips waypoint hits (chunk_id=MISSING_CHUNK_ID) | regression | `pytest tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py -q` | Exists |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/llamaindex_runtime/test_hotspot_traversal_logic.py -q`
- **Per wave merge:** Full suite command (see above, ~35 s)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/llamaindex_runtime/test_hotspot_traversal_logic.py` — must be created in Wave 0; covers P13-01 through P13-12 (12 new test cases)

Existing infrastructure covers all regression tests (P13-11, P13-13, P13-14, P13-15).

---

## Open Questions (RESOLVED)

1. **Circular import: MISSING_CHUNK_ID location**
   - What we know: `MISSING_CHUNK_ID` is defined in `runtime.py:86`; `semantic_distribution.py` does not currently import from `runtime.py`; `runtime.py` imports from `semantic_distribution.py`.
   - What's unclear: Can we safely add a top-level import in the opposite direction, or will it cause a circular import at module load?
   - Recommendation: Do not add a runtime.py top-level import to semantic_distribution.py. Instead, define `_MISSING_CHUNK_ID = UUID(int=0)` directly inside `_build_waypoint_hit` or as a module-level constant in `semantic_distribution.py`. The planner should designate one sub-task to verify and resolve this before `_build_waypoint_hit` is written.
   - **RESOLVED:** Define `_MISSING_CHUNK_ID = UUID(int=0)` as a module-level constant in `semantic_distribution.py` (no `runtime.py` import). Plans implement this in 13-01-PLAN Task 3 (constant + `_build_waypoint_hit`), with a parity assertion `_MISSING_CHUNK_ID == runtime.MISSING_CHUNK_ID` in the Task 3 acceptance criteria.

2. **Q18 re-validation path**
   - What we know: The verification script is `verification/real-document-validation-2026-06-23/run_validation.py`. Q18 required a live DB run in the original analysis.
   - What's unclear: The local environment does not have `DATABASE_URL` set for DB-backed re-validation. The `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` may serve as a closer fixture-based proxy.
   - Recommendation: Include a fixture-based E2E test in the new test file that verifies the full pipeline from `traverse_tree_for_query(hotspot_node_id=X, start_node_id=X)` to backend hit shape (no `chunk_id=null`). DB-backed Q18 re-validation is a manual verification step.
   - **RESOLVED:** Fixture-based integration coverage is added to `tests/llamaindex_runtime/test_hotspot_traversal_logic.py` (the Wave 0 file created in 13-01-PLAN Task 2, exercised end-to-end across Plans 02-03). DB-backed Q18 re-validation is documented as manual-only in 13-VALIDATION.md ("Manual-Only Verifications" table).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | Test execution | Yes | (via `python -m pytest`) | — |
| Python 3.11 | Runtime | Yes | 3.11 | — |
| Database (PostgreSQL) | Q18 E2E re-validation | Unknown | — | Fixture-based integration test |

**Missing dependencies with no fallback:** None blocking the implementation or unit tests.

**Missing dependencies with fallback:** DB-backed Q18 validation requires running Docker/PostgreSQL. Fixture-based integration test provides partial coverage.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Root-only traversal | `start_node_id`-scoped hotspot traversal | Phase 10 | Enables starting from hotspot node |
| Single decision at hotspot parent | Decision on children via `evaluate_children` | Phase 13 (NEW) | Separates hotspot return from drill-down decision |
| No waypoint concept | Waypoint hit (MISSING_CHUNK_ID, drill_depth=0) | Phase 13 (NEW) | Enables navigation provenance for route-only hotspot nodes |
| No Baseline `evaluate_children` | Baseline gets `evaluate_children` parity with HIRO | Phase 13 (NEW) | Unifies decision interface across policies |
| Fallback dict without `chunk_id` | Fallback dict with `chunk_id=MISSING_CHUNK_ID` | Phase 13 (NEW) | Eliminates `chunk_id=null` from all fallback paths |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Adding `_traverse_hotspot_with_children` as an instance method on `RecursiveTreeTraversalRunner` will not conflict with the `TreeSemanticTraversalRunner` Protocol | Architecture Patterns | Would require adjusting the Protocol or adding to it |
| A2 | `_build_waypoint_hit` as a module-level function (not a method) is the correct placement | Standard Stack | Wrong placement could cause scoping issues |
| A3 | The detection condition `hotspot_node_id == start_node_id` never fires during normal root traversal (where `hotspot_node_id` is None or differs from `start_node_id`) | Architecture Patterns | If it fires unexpectedly for root traversal, behavior would change for non-hotspot queries |

All other claims in this research are HIGH confidence, verified against the live codebase.

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: read semantic_distribution.py:60-268]` — Baseline policy, node_stats construction, vector filter
- `[VERIFIED: read semantic_distribution.py:470-510]` — QueryHit schema, SubtreeHotspot, TreeBranchDecisionPolicy protocol
- `[VERIFIED: read semantic_distribution.py:1620-1903]` — traverse_tree_for_query, _traverse_from_node, node_stats lookup
- `[VERIFIED: read semantic_distribution.py:1906-1996]` — _cosine_similarity, _build_hits_from_node, get_hotspot_selector
- `[VERIFIED: read runtime.py:80-115]` — MISSING_CHUNK_ID definition
- `[VERIFIED: read runtime.py:320-380]` — hotspot traversal wiring, fallback trigger
- `[VERIFIED: read runtime.py:470-565]` — _score_tree_nodes_with_fallback, _map_query_hits_to_backend_hits
- `[VERIFIED: read hiro_decision_policy.py:1-157]` — HIROEnhancedTreeBranchDecisionPolicy.evaluate_children full implementation
- `[VERIFIED: read BUG_ANALYSIS_Q18_TRAVERSE_LOGIC.md]` — 7-step evidence chain
- `[VERIFIED: read TRAVERSE-LOGIC-REDESIGN-PLAN.md]` — approved design doc
- `[VERIFIED: bash: pytest 35-test suite runs green in ~29 s]` — baseline test health
- `[VERIFIED: read tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py:656-908]` — p6 DNA regression test names and fixtures

### Secondary (MEDIUM confidence)
- `[VERIFIED: bash: pytest --collect-only]` — 35 tests collected across the 5 regression files

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all line numbers and signatures confirmed by reading live code
- Architecture: HIGH — data flow verified end-to-end from runtime.py to semantic_distribution.py
- Pitfalls: HIGH — circular import risk confirmed by checking import graph; waypoint-filter behavior confirmed by reading line 512
- Design-doc drift: HIGH — zero drift detected; all 10 claims verified against post-Phase-12 code

**Research date:** 2026-06-25
**Valid until:** 2026-07-25 (stable internal codebase, no fast-moving external deps)
