# Phase 12 Research — Cluster-Hot Hotspot Selection Redesign

**Source:** Consolidated from exploration E1–E7 (`.planning/hotspot-cluster-redesign-EXPLORATION/00-SUMMARY.md`). The exploration was a read-only, code-anchored fact-finding pass; this document formalizes it as the phase research input. No re-research agent was run because the investigation was already complete and user-confirmed ("调研内容出来").

---

## 1. Problem (confirmed by code, not speculation)

The active `hybrid_cluster` selector is single-node Top-K fusion, NOT cluster-hot:

- `HybridClusterHotspotSelector.select_hotspots()` builds `candidate_node_ids = set(vector_by_node) | set(keyword_by_node)` (UNION), computes a per-node `fusion = vector·0.40 + keyword·0.30 + distribution·0.10 (+rerank)`, sorts, and returns `fusion_scores[:limit]`. Anchor: `llamaindex_runtime/tree/semantic_distribution.py:954`, `:968`, `:993`.
- Child structure enters fusion ONLY through `distribution_score` at weight 0.10. `_compute_child_distribution_score()` rewards count/breadth of child/sibling hits but never checks full-child coverage and never requires dual-hot. Anchor: `:1161`–`:1226`.
- Result: an isolated high-scoring node becomes a hotspot even when its siblings/line are cold — the exact failure the user described.

## 2. Existing assets to reuse (E3)

- `ClusterHotspotSelector` already implements ancestor-cluster aggregation: `_build_path_to_root` (`:1016`), `_build_ancestor_clusters` (`:1054`), `ClusterCandidate` (`:547`), density via `_count_subtree_candidates`. It consumes vector similarity only — no keyword, no dual-hot. It is a structural analog, not a drop-in.
- `_build_parent_to_children(tree_nodes)` (`:313`) already produces the complete parent→children map. This is the denominator source for coverage.
- `get_hotspot_selector` (`:1694`) routes `route_subtree | cluster | hybrid_cluster`. Rollback paths exist and must stay intact.

## 3. Data availability gate (E2 — the one real prerequisite)

- `HotspotSelectionContext` carries `node_stats: dict[UUID, dict]` keyed only by nodes that have direct/subtree vectors (`_build_node_stats` does `if not vectors: continue`, `:240`). It does NOT carry the complete `tree_nodes` or a `parent_to_children` map.
- Therefore true direct-child coverage cannot be computed from `node_stats` alone. The selector context MUST be extended with a child denominator (`parent_to_children` or per-node `direct_child_count`), populated by runtime from the full tree (reuse `_build_parent_to_children`).
- Each `node_stats` entry already has `parent_node_id` and `level_no` (`:253`–`:256`), so child membership for analyzed nodes is inferable; the missing piece is the *complete* child set including no-vector children.

## 4. Selection vs traversal boundary (E5)

- Selection emits `SubtreeHotspot(node_id, score, reason, support_count, dispersion, entropy)`. Traversal takes a single `start_node_id` (`:1412`). Runtime sets `start_node_id = hotspot_node_id = hotspot.node_id` (`runtime.py:349`–`350`).
- If cluster-hot still emits a representative `node_id`, the traversal interface needs NO change (D-08). Risks to design around: duplicate recall (ancestor + member both traversed), dead branch (route leaf drills with no children), missed recall (keep_parent skips children).

## 5. p6 tree reality (E7)

- `verification/p6_validation/p6_final_sample_structured.md`: 47 nodes; depth H1=1, H2=13, H3=33; direct-child-count histogram `{0:34, 2:5, 3:6, 5:1, 13:1}`.
- Implication: θ=1.0 over-prunes (most internal sections have 2–3 children; a focused query hits one). A configurable θ (<1.0) is meaningful and discriminating. Root (13 children) must be excluded/penalized. Leaf fallback required for focused exact-leaf queries.

---

## Validation Architecture

> This section drives the Nyquist VALIDATION.md per-task verification map.

### Test infrastructure
- **Framework:** pytest (existing `tests/llamaindex_runtime/`).
- **Quick command:** `python -m pytest tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py -q`
- **Cluster/regression command:** `python -m pytest tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py -q`
- **Full selector suite:** `python -m pytest tests/llamaindex_runtime/ -q`

### Validation dimensions

1. **Coverage gate (D-01).** Synthetic parent with 3 children:
   - 1 dual-hot child → coverage 1/3 < θ(0.5) → parent NOT selected.
   - 2 dual-hot children → coverage 2/3 ≥ θ → parent selected.
   - 3 dual-hot children → coverage 1.0 → parent selected, outranks isolated high-vector single node.
2. **Dual-hot gate (D-02).** vector-hot-only child and keyword-hot-only child each do NOT count toward coverage (assert excluded).
3. **Context denominator (D-07).** `HotspotSelectionContext` exposes the complete direct-child set; coverage denominator includes a no-vector child (present in tree, absent from `node_stats`).
4. **Configurable θ + leaf fallback (D-05/D-06).** With no parent meeting θ, a strong dual-hot leaf is still returned (focused exact-leaf query keeps its position); root not promoted by coverage alone.
5. **Boundary preserved (D-08).** Output remains `SubtreeHotspot(node_id=...)`; traversal signature unchanged (no edits to `traverse_tree_for_query`).
6. **Rollback intact (D-09).** `RAG_TREE_HOTSPOT_SELECTOR=route_subtree` and `=cluster` still route to unmodified selectors.
7. **Regression (D-10).** p6 DNA query returns `数据驱动 / 非确定性 / 持续性` from `产品特性对比`; rejects `抖音案例` / `特斯拉案例`. Preserve registration, context, normalization, rerker-off, anti-hardcode, jieba extraction tests.

### Manual-only verifications
- DB-backed live retrieval on p6 corpus (Docker/PostgreSQL) confirming deeper-level hotspots still return `span_ids` / `navigation_path` / `drill_depth` — optional manual gate, not required for unit-level pass.

---

## Open questions for the planner (Claude's Discretion)
- Concrete defaults for θ, `vector_hot`, `keyword_hot`, `min_support` — pick and justify against the p6 child-count histogram.
- Reuse `_build_ancestor_clusters`/`ClusterCandidate` vs add a focused coverage helper.
- Exact location and signature of the coverage helper and the context-denominator field.

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Research consolidated 2026-06-22 from exploration E1–E7.*
