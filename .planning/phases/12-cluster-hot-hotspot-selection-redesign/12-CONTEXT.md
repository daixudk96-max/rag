# Phase 12: Cluster-Hot Hotspot Selection Redesign - Context

**Gathered:** 2026-06-22
**Status:** Ready for planning
**Source:** Exploration E1–E7 (`.planning/hotspot-cluster-redesign-EXPLORATION/00-SUMMARY.md`) + user-approved design decisions

<domain>
## Phase Boundary

**What this phase delivers:** Replace the post-Phase-11 `HybridClusterHotspotSelector`'s single-node Top-K fusion with true *cluster-hot* selection. A parent node becomes a hotspot only when a coherent group of its direct children are hot, where "hot" requires BOTH vector similarity AND keyword match (dual-hot). This corrects the gap confirmed in exploration: the current selector ranks individual nodes by a fusion score and takes Top-K, so a single high-scoring node becomes a hotspot even when its siblings/line are cold.

**In scope:**
- `HybridClusterHotspotSelector.select_hotspots()` selection logic (`llamaindex_runtime/tree/semantic_distribution.py`).
- `HotspotSelectionContext` extension to carry a direct-child denominator.
- Runtime construction of that denominator in `llamaindex_runtime/tree/runtime.py` (hybrid_cluster branch).
- Test rewrite for distribution/coverage scoring; preservation of existing contract tests.

**Out of scope (do NOT touch):**
- The traversal layer interface `RecursiveTreeTraversalRunner.traverse_tree_for_query(start_node_id=...)` — selection-layer-only change.
- `SubtreeHotspotSelector` (route_subtree) and `ClusterHotspotSelector` (cluster) — kept intact as rollback paths.
- Closed Phase 11 artifacts — this is new Phase 12 scope, not a Phase 11 reopen.

</domain>

<decisions>
## Implementation Decisions

### Cluster-Hot Definition
- **D-01 [LOCKED] Definition A — direct-child coverage.** A parent node `P` is a hotspot iff `coverage(P) = |{c ∈ direct_children(P) : child_hot(c)}| / |direct_children(P)| ≥ θ` AND `|{c : child_hot(c)}| ≥ min_support`. Path-all-hot (definition B) and subtree-density (definition C) are NOT the first-version rule; B may be added later only as a tie-breaker.

### Dual-Hot Gate
- **D-02 [LOCKED] Dual-hot child.** `child_hot(c) = vector_hot(c) AND keyword_hot(c)`. A child that is vector-hot only, or keyword-hot only, does NOT count toward coverage. This is the core correction — the current `_compute_child_distribution_score` counts any candidate-node hit (union of vector OR keyword), not the intersection.

### Hotness Thresholds (Claude's Discretion — pick concrete defaults during planning)
- **D-03 Vector-hot criterion.** Define `vector_hot(c)` from the normalized vector-candidate score (e.g. above a normalized-similarity threshold, or membership in the vector candidate Top-N). Planner must specify a concrete, configurable default and justify it against the p6 tree.
- **D-04 Keyword-hot criterion.** Define `keyword_hot(c)` from keyword-hit term coverage (e.g. ≥1 matched query term against `heading_path`, reusing the existing jieba `_extract_keywords_from_query` path). Planner must specify a concrete, configurable default.

### Coverage Threshold and Fallback
- **D-05 [LOCKED] Configurable θ, never fixed at 1.0.** p6 internal sections mostly have 2–3 direct children (histogram: child-count 0×34, 2×5, 3×6, 5×1, 13×1), so θ=1.0 over-prunes focused queries. θ is a configurable parameter with a sensible default (planner picks, e.g. 0.5).
- **D-06 [LOCKED] Leaf fallback preserved.** Focused exact-leaf queries (e.g. `数据清洗标注的具体方法是什么？`) MUST still return their original position even when no parent meets coverage. A strong dual-hot leaf remains a valid hotspot/result. The root and very-broad top-level nodes must not be promoted by coverage alone (reuse existing root-avoidance pattern).

### Context Data
- **D-07 [LOCKED] Add child denominator to selection context.** `HotspotSelectionContext` cannot compute true coverage today — it only sees `node_stats` (vector/subtree-bearing nodes), not the complete direct-child set. Add `parent_to_children` (or `direct_child_count`) sourced from the complete tree. Reuse `_build_parent_to_children()` in `semantic_distribution.py`. Runtime must populate it in the hybrid_cluster branch.

### Boundary and Output Shape
- **D-08 [LOCKED] Selection-layer-only; preserve output contract.** Keep emitting `SubtreeHotspot(node_id=..., score=..., reason=..., support_count=..., dispersion=..., entropy=...)`. Do NOT change `traverse_tree_for_query`'s single-`start_node_id` interface. Each emitted hotspot flows into traversal exactly as today.

### Rollback and Safety
- **D-09 [LOCKED] Switch-gated, no deletions.** New behavior stays behind `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster`. `route_subtree` and `cluster` selectors remain unmodified rollback paths. No selector is deleted in this phase. CRITICAL runtime-path edits stay incremental.

### Test Strategy
- **D-10 [LOCKED] Rewrite distribution-scoring tests; preserve contract tests.** Rewrite `_compute_child_distribution_score`-style tests to assert coverage-ratio + dual-hot semantics (1/3, 2/3, 3/3 cases; vector-only and keyword-only children excluded). Preserve: selector registration/rollback, `HotspotSelectionContext` contract, score normalization, default-off reranker seam, cross-domain anti-hardcode, jieba keyword extraction, and the p6 DNA regression.

### Claude's Discretion
- Exact numeric defaults for θ, `vector_hot`, `keyword_hot`, and `min_support` (pick and justify).
- Whether to reuse `ClusterCandidate` / `_build_ancestor_clusters` machinery or add a focused coverage helper.
- Internal function decomposition, naming, and where the coverage helper lives.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Exploration (the research deliverable)
- `.planning/hotspot-cluster-redesign-EXPLORATION/00-SUMMARY.md` — full E1–E7 findings with code anchors: data flow, context-data availability gate, existing cluster code inventory, definition A/B/C comparison, selection-vs-traversal boundary, test regression surface, p6 tree reality.

### Selection layer (primary edit target)
- `llamaindex_runtime/tree/semantic_distribution.py` — `HybridClusterHotspotSelector.select_hotspots` (~835–1013), `_compute_child_distribution_score` (~1161–1226), `_compute_fusion_score` (~1229–1261), `HotspotSelectionContext`/`NodeSemanticHit`/`KeywordSpanHit` (~500–544), `_build_parent_to_children` (~313), existing cluster analog `_build_ancestor_clusters`/`ClusterCandidate` (~547, ~1054), `get_hotspot_selector` (~1694–1715).
- `llamaindex_runtime/tree/runtime.py` — hybrid_cluster context construction (vector_candidates, keyword_hits, `HotspotSelectionContext`) (~248–340) and traversal connection (~341–352).

### Tests (rewrite + preserve)
- `tests/llamaindex_runtime/test_tree_hybrid_hotspot_selector.py` — distribution scoring, fusion, registration, context, jieba extraction, anti-hardcode.
- `tests/llamaindex_runtime/test_tree_semantic_cluster_hotspot.py` — cluster densest-ancestor, root-avoidance, p6 DNA regression.

### Validation corpus / ground truth
- `verification/p6_validation/p6_final_sample_structured.md` — p6 tree (47 nodes; depth H1=1, H2=13, H3=33). DNA region `00:31 - 产品特性对比 > AI产品经理核心DNA` evidence `数据驱动 / 非确定性 / 持续性`.

</canonical_refs>

<specifics>
## Specific Ideas

- The bug shape (E1): `candidate_node_ids = set(vector_by_node) | set(keyword_by_node)` is a UNION; coverage must use the INTERSECTION (dual-hot) over the *complete* direct-child set.
- The data gap (E2): `HotspotSelectionContext.node_stats` skips no-vector nodes, so coverage denominator must come from the full tree via `parent_to_children`, not from `node_stats`.
- p6 coverage cases to test: parent with 3 children and 1 dual-hot child → coverage 1/3 (below θ=0.5, not a hotspot); 2 dual-hot → 2/3 (hotspot); 3 dual-hot → 1.0 (strongest).
- Regression anchor: DNA query must still return `数据驱动 / 非确定性 / 持续性` from the `产品特性对比` region; must NOT select `抖音案例` or `特斯拉案例`.

</specifics>

<deferred>
## Deferred Ideas

- Definition B (path-all-hot) as a tie-breaker — later phase, not v1.
- Definition C (subtree-density) full implementation — close to existing `ClusterHotspotSelector`; not v1.
- "Ancestor + member-set constrained recall" requiring a traversal-interface change — out of scope (D-08).

</deferred>

---

*Phase: 12-cluster-hot-hotspot-selection-redesign*
*Context gathered: 2026-06-22 from exploration E1–E7 and user-approved decisions*
