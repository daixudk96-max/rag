# Phase 13: Hotspot Traverse Logic Redesign - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 2 modified files (semantic_distribution.py, runtime.py) + 1 new test file
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified Symbol | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `traverse_tree_for_query` entry (hotspot detection block) | controller (dispatch gate) | request-response | `traverse_tree_for_query` lines 1661-1665 (start_node_id branch) | exact — same method, parallel branch |
| `RecursiveTreeTraversalRunner._traverse_hotspot_with_children` | service / traversal | tree walk + hit construction | `RecursiveTreeTraversalRunner._traverse_from_node` (lines 1692-1903) | exact — same class, same return type, same kwargs pattern |
| `_build_waypoint_hit` (module-level function) | utility / hit builder | transform | `_build_hits_from_node` (lines 1930-1971) | exact — same signature shape, same QueryHit construction |
| `BaselineTreeBranchDecisionPolicy.evaluate_children` | policy method | request-response | `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children` (hiro_decision_policy.py lines 110-157) | exact — must match identical protocol signature and return shape |
| `_score_tree_nodes_with_fallback` dict (add `chunk_id` field) | utility / fallback | transform | `_map_query_hits_to_backend_hits` hit_dict (runtime.py lines 544-562) | role-match — same dict-building context, adds parallel `chunk_id` key |
| `tests/llamaindex_runtime/test_hotspot_traversal_logic.py` | test | unit | `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` | role-match — same fixture/mock style, same import set |

---

## Pattern Assignments

### 1. Hotspot detection gate in `traverse_tree_for_query` (semantic_distribution.py lines 1661-1690)

**Analog:** `traverse_tree_for_query` lines 1661-1665 (existing `start_node_id` branch)

**Insertion point:** After line 1665 (`start_nodes` list resolved), before the loop at line 1668.

**Existing branch pattern to mirror** (lines 1661-1665):
```python
if start_node_id is not None:
    start_node = node_by_id.get(start_node_id)
    start_nodes = [start_node] if start_node is not None else []
else:
    start_nodes = [node for node in nodes if node.get("parent_node_id") is None]
```

**New block — copy this style exactly:**
```python
# Hotspot traversal: short-circuit to dedicated handler that enforces
# "waypoint + one-level child chunks" contract.
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

**Style notes from analog:**
- Keyword-only call to `self._traverse_from_node` at line 1671 shows the exact kwarg names this project uses
- Returns directly (no accumulation into `hits` list) — consistent with early-return branches

---

### 2. `RecursiveTreeTraversalRunner._traverse_hotspot_with_children` (NEW method)

**Analog:** `RecursiveTreeTraversalRunner._traverse_from_node` (semantic_distribution.py lines 1692-1903)

**Signature pattern** (lines 1692-1710):
```python
def _traverse_from_node(
    self,
    *,
    node: dict[str, Any],
    version_id: UUID,
    query_embedding: list[float],
    node_stats_list: list[dict[str, Any]],
    node_by_id: dict[UUID, dict[str, Any]],
    tree_signals: dict[str, Any],
    policy: TreeBranchDecisionPolicy,
    registry: SemanticDistributionRegistry,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    parent_query_distance: float | None,
    navigation_node_ids: tuple[UUID, ...],
    hotspot_node_id: UUID | None,
    current_depth: int,
    max_depth: int | None,
) -> list[QueryHit]:
```

**New method signature — drop `parent_query_distance`, `navigation_node_ids`, `current_depth`; rename `node` to `hotspot_node`:**
```python
def _traverse_hotspot_with_children(
    self,
    *,
    hotspot_node: dict[str, Any] | None,
    version_id: UUID,
    query_embedding: list[float],
    node_stats_list: list[dict[str, Any]],
    node_by_id: dict[UUID, dict[str, Any]],
    tree_signals: dict[str, Any],
    policy: TreeBranchDecisionPolicy,
    registry: SemanticDistributionRegistry,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    max_depth: int | None,
) -> list[QueryHit]:
```

**Child collection pattern** (lines 1769-1773 — copy verbatim):
```python
child_nodes = [
    node_by_id[child_id]
    for child_id in node_by_id
    if node_by_id[child_id].get("parent_node_id") == node_id
]
```

**Child stats + similarity enrichment pattern** (lines 1784-1803):
```python
if hasattr(policy, "evaluate_children"):
    child_stats = []
    for child_node in child_nodes:
        child_node_stats = child_stats_by_id.get(child_node["node_id"])
        if child_node_stats is None:
            continue
        child_prototype = child_node_stats.get(
            "prototype_embedding"
        ) or child_node_stats.get("centroid", [])
        child_similarity = _cosine_similarity(
            query_embedding, child_prototype
        )
        child_query_distance = 1.0 - child_similarity
        child_stats.append(
            {
                **child_node_stats,
                "query_distance": child_query_distance,
                "parent_query_distance": query_distance,
            }
        )
```

**CRITICAL — skip children with empty prototype (Pitfall 5 in RESEARCH.md):**
Add `if not child_prototype: continue` immediately after the `child_prototype` assignment, mirroring the implicit skip in the existing pattern.

**evaluate_children call pattern** (lines 1805-1853 — copy structure):
```python
child_result = policy.evaluate_children(
    child_stats=child_stats,
    tree_signals=tree_signals,
)
aggregate_decision = child_result.get("decision")
selected_child_id = child_result.get("selected_child_id")

if aggregate_decision == "drill_down" and selected_child_id in node_by_id:
    hits.extend(
        self._traverse_from_node(
            node=node_by_id[selected_child_id],
            version_id=version_id,
            query_embedding=query_embedding,
            node_stats_list=node_stats_list,
            node_by_id=node_by_id,
            tree_signals=tree_signals,
            policy=policy,
            registry=registry,
            doc_id=doc_id,
            chunk_to_span_ids=chunk_to_span_ids,
            parent_query_distance=query_distance,
            navigation_node_ids=(
                *navigation_node_ids,
                selected_child_id,
            ),
            hotspot_node_id=hotspot_node_id,
            current_depth=current_depth + 1,
            max_depth=max_depth,
        )
    )
```

**_build_hits_from_node call pattern** (lines 1751-1762 — copy for evidence hits):
```python
hits.extend(
    _build_hits_from_node(
        node_stats=enriched_node_stats,
        version_id=version_id,
        doc_id=doc_id,
        similarity=similarity,
        chunk_to_span_ids=chunk_to_span_ids,
        hotspot_node_id=hotspot_node_id,
        navigation_node_ids=navigation_node_ids,
        drill_depth=current_depth,
    )
)
```

---

### 3. `_build_waypoint_hit` (module-level function, insert after line 1971)

**Analog:** `_build_hits_from_node` (semantic_distribution.py lines 1930-1971)

**Exact signature to mirror** (lines 1930-1940):
```python
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

**QueryHit construction pattern** (lines 1957-1969 — copy field names exactly):
```python
hits.append(
    QueryHit(
        doc_id=doc_id,
        version_id=version_id,
        span_id=span_id,
        chunk_id=chunk_id,
        node_id=node_id,
        similarity_score=similarity,
        hotspot_node_id=hotspot_node_id,
        navigation_node_ids=navigation_node_ids,
        drill_depth=drill_depth,
    )
)
```

**New function signature and body — adapt as:**
```python
def _build_waypoint_hit(
    *,
    node: dict[str, Any],
    version_id: UUID,
    doc_id: UUID,
    chunk_to_span_ids: dict[UUID, list[UUID]],
    hotspot_node_id: UUID | None,
    navigation_node_ids: tuple[UUID, ...],
) -> list[QueryHit]:
```

**MISSING_CHUNK_ID constant:** Do NOT import from `runtime.py` (circular import risk — RESEARCH.md Pitfall 1, Open Question 1). Define locally:
```python
_MISSING_CHUNK_ID = UUID(int=0)  # matches runtime.MISSING_CHUNK_ID at runtime.py:86
```
Place at module level near the other `_MAX_TRAVERSAL_DEPTH` constants (lines 60-66).

**QueryHit fields for waypoint:**
- `chunk_id=_MISSING_CHUNK_ID`
- `span_id=UUID(int=node_id.int & (2**63 - 1))` (synthetic, deterministic)
- `similarity_score=0.0`
- `drill_depth=0`
- `hotspot_node_id=hotspot_node_id`
- `navigation_node_ids=navigation_node_ids`

---

### 4. `BaselineTreeBranchDecisionPolicy.evaluate_children` (NEW method)

**Analog:** `HIROEnhancedTreeBranchDecisionPolicy.evaluate_children` (hiro_decision_policy.py lines 110-157)

**Exact signature to copy verbatim** (lines 110-115):
```python
def evaluate_children(
    self,
    *,
    child_stats: list[dict[str, Any]],
    tree_signals: dict[str, Any],
) -> dict[str, Any]:
```

**Return shape — three valid dict shapes** (lines 141-157):
```python
# Shape 1: drill_down
{"decision": "drill_down",  "selected_child_id": <UUID>, "child_decisions": {<UUID>: "drill_down"}}
# Shape 2: keep_parent
{"decision": "keep_parent", "selected_child_id": None,   "child_decisions": {<UUID>: "keep_parent"}}
# Shape 3: prune
{"decision": "prune",       "selected_child_id": None,   "child_decisions": {<UUID>: "prune"}}
```

**HIRO iteration pattern** (lines 122-139 — Baseline uses same outer loop, different selection logic):
```python
child_decisions: dict[Any, str] = {}
selected_child_id: Any | None = None
saw_keep_parent = False

for child in child_stats:
    child_id = child.get("node_id")
    decision = self.decide_branch_action(
        node_stats=child,
        tree_signals=tree_signals,
    )
    child_decisions[child_id] = decision
    # ... selection logic differs for Baseline vs HIRO
```

**Baseline-specific selection:** Instead of HIRO's `query_distance > selected_child_score` (line 137), Baseline selects `min(child_stats, key=lambda c: c.get("query_distance", 1.0))` before the loop, then calls `decide_branch_action` on the single best child only.

**Frozen dataclass constraint (RESEARCH.md Pitfall 4):** `BaselineTreeBranchDecisionPolicy` is `@dataclass(frozen=True)` (line 69). The new method reads only `self.dispersion_threshold`, `self.entropy_threshold`, `self.min_support_threshold` — no writes, no issue.

---

### 5. `_score_tree_nodes_with_fallback` dict — add `chunk_id` field (runtime.py lines 486-494)

**Analog:** `_map_query_hits_to_backend_hits` hit_dict construction (runtime.py lines 544-562)

**Existing fallback dict** (lines 486-494) — currently missing `chunk_id`:
```python
scored_nodes.append(
    {
        "node_id": node["node_id"],
        "score": score,
        "text_preview": node.get("summary_text") or node.get("title") or "",
        "heading_path": node.get("heading_path"),
        "span_ids": span_ids_by_node.get(node["node_id"], []),
    }
)
```

**Reference dict that has `chunk_id`** (lines 544-562):
```python
hit_dict = {
    "node_id": hit.node_id,
    "chunk_id": hit.chunk_id,       # <-- this field is what the fallback dict lacks
    "chunk_id_missing": False,
    "score": hit.similarity_score,
    ...
}
```

**Minimal change — add one key using `MISSING_CHUNK_ID`** (already imported in runtime.py at line 86):
```python
scored_nodes.append(
    {
        "node_id": node["node_id"],
        "chunk_id": MISSING_CHUNK_ID,   # NEW: defensive backstop sentinel
        "score": score,
        "text_preview": node.get("summary_text") or node.get("title") or "",
        "heading_path": node.get("heading_path"),
        "span_ids": span_ids_by_node.get(node["node_id"], []),
    }
)
```

`MISSING_CHUNK_ID` is already in scope in `runtime.py` (line 86, module-level). No import needed.

---

### 6. `tests/llamaindex_runtime/test_hotspot_traversal_logic.py` (NEW test file)

**Analog:** `tests/llamaindex_runtime/test_tree_semantic_hotspot.py`

**Import block pattern** (lines 1-27 of test_tree_semantic_hotspot.py):
```python
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.runtime import _map_query_hits_to_backend_hits
from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    ClusterHotspotSelector,
    PersistedTreeSemanticDistributionAdapter,
    QueryHit,
    RecursiveTreeTraversalRunner,
    SubtreeHotspotSelector,
)
```

**Fixture/mock pattern** (lines 49-80):
```python
registry = MagicMock()
registry.query_tree_nodes_by_version.return_value = [
    {
        "node_id": parent_node_id,
        "heading_path": "...",
        "level_no": 0,
        "parent_node_id": None,
    },
    ...
]
```

**Test class naming:** Use `class TestHotspotTraversalDispatch:`, `class TestHotspotWithChildren:` etc. (PascalCase class per behavior group, matching the `TestSubtreeHotspotSelector` / `TestRecursiveTreeTraversalRunnerStartNodeId` convention in the analog).

**Additional imports needed for new test file:**
```python
from llamaindex_runtime.tree.hiro_decision_policy import HIROEnhancedTreeBranchDecisionPolicy
from llamaindex_runtime.tree.runtime import MISSING_CHUNK_ID
```

---

## Shared Patterns

### Keyword-Only Function Signatures

**Source:** All traversal helpers in `semantic_distribution.py` (e.g., `_build_hits_from_node` lines 1930-1939, `_traverse_from_node` lines 1692-1710)

**Apply to:** `_traverse_hotspot_with_children`, `_build_waypoint_hit`

All new functions must use `*` as the first parameter after `self` (or as sole separator for module-level functions). No positional args.

### `list[QueryHit]` Return Type

**Source:** `_build_hits_from_node` line 1940, `_traverse_from_node` line 1710

**Apply to:** `_traverse_hotspot_with_children`, `_build_waypoint_hit`

Both new functions return `list[QueryHit]`, never `None`.

### Child stat enrichment dict spread

**Source:** `_traverse_from_node` lines 1797-1802:
```python
child_stats.append(
    {
        **child_node_stats,
        "query_distance": child_query_distance,
        "parent_query_distance": query_distance,
    }
)
```

**Apply to:** `_traverse_hotspot_with_children` child stats building. Use `**spread` pattern, not field-by-field copy.

### Prototype embedding fallback

**Source:** `_traverse_from_node` lines 1790-1793:
```python
child_prototype = child_node_stats.get(
    "prototype_embedding"
) or child_node_stats.get("centroid", [])
```

**Apply to:** `_traverse_hotspot_with_children`. Also guard with `if not child_prototype: continue` to avoid 0.0 similarity silently corrupting ranking (RESEARCH.md Pitfall 5).

### `hasattr(policy, "evaluate_children")` guard

**Source:** `_traverse_from_node` line 1784:
```python
if hasattr(policy, "evaluate_children"):
```

**Apply to:** `_traverse_hotspot_with_children`. Guard must also check `and child_stats_with_similarity` to avoid calling with empty list (RESEARCH.md Anti-Pattern 4).

---

## No Analog Found

None. All 5 implementation areas have direct analogs in the codebase.

---

## Key Constraints Extracted from Live Code

| Constraint | Source | Line |
|------------|--------|------|
| `QueryHit.chunk_id: UUID` (not Optional) — must be MISSING_CHUNK_ID, not None | `semantic_distribution.py` | 487 |
| `_map_query_hits_to_backend_hits` skips `chunk_id == MISSING_CHUNK_ID` hits | `runtime.py` | 512 |
| `BaselineTreeBranchDecisionPolicy` is `@dataclass(frozen=True)` — new method must not write `self` | `semantic_distribution.py` | 69 |
| `MISSING_CHUNK_ID = UUID(int=0)` already defined in `runtime.py` — do not redefine there | `runtime.py` | 86 |
| Circular import: `semantic_distribution.py` does NOT import from `runtime.py` currently | Both files | — |
| Child lookup: O(N) scan over `node_by_id` is established convention | `semantic_distribution.py` | 1769-1773 |
| `evaluate_children` return dict must have keys: `decision`, `selected_child_id`, `child_decisions` | `hiro_decision_policy.py` | 141-157 |

---

## Metadata

**Analog search scope:** `llamaindex_runtime/tree/semantic_distribution.py`, `llamaindex_runtime/tree/runtime.py`, `llamaindex_runtime/tree/hiro_decision_policy.py`, `tests/llamaindex_runtime/test_tree_semantic_hotspot.py`
**Files scanned:** 4
**Pattern extraction date:** 2026-06-25
