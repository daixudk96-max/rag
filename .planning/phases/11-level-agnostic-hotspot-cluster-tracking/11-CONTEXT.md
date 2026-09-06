# Phase 11: Level-Agnostic Hotspot Cluster Tracking - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning
**Source:** User design correction + Phase 11 corrective design artifact (`11-01-PLAN.md`)

<domain>
## Phase Boundary

Phase 11 corrects the hotspot-tracking semantics implemented in Phase 10. Phase 10 proved that hotspot metadata, navigation paths, drill depth, evidence-bearing chunks, and subtree traversal metadata can flow through the runtime. It did not satisfy the intended product semantics because it preselects route-like parent nodes and applies route-node bonuses before evidence traversal.

This phase must replace that pre-ranked route-node hotspot selection with a level-agnostic, post-hoc cluster-based hotspot selector:

```text
query embedding
→ compare against all eligible nodes equally
→ collect top semantic hits across the tree
→ analyze where those hits cluster structurally
→ infer the densest shared parent/local subtree after the fact
→ read from that inferred hotspot area
```

Out of scope: Level promotion, human judgment collection, UI work, broad ingestion redesign, global embedding model replacement, deletion of the old selector, unrelated dirty-tree cleanup.
</domain>

<decisions>
## Implementation Decisions

### D-01 — Level-agnostic first-pass similarity
All eligible tree nodes must compete equally by cosine similarity before hotspot inference. Initial node scoring must not apply route-node bonus, depth bonus, parent preference, direct/indirect chunk preference, or predeclared hotspot/evidence roles.

### D-02 — Post-hoc cluster inference
`hotspot_node_id` in the cluster path means "shared region where semantic hits clustered", not "node preclassified as hotspot". The selected hotspot may be a local parent region or the exact evidence node if that is the densest meaningful region.

### D-03 — Candidate breadth
The selector must inspect a broader candidate set than final `similarity_top_k`, starting with `candidate_top_n = max(limit * 4, 20)` unless tests prove a safer value is needed.

### D-04 — Ancestor grouping
Candidate semantic hits must be grouped by ancestors/local subtrees. Cluster scoring should include max score, average score, normalized support count, and density. Root must be excluded or penalized unless no local region exists.

### D-05 — Evidence-bearing final hits
Runtime output must still return concrete evidence-bearing hits inside the inferred hotspot region. Metadata must preserve `hotspot_node_id`, `navigation_path`, `drill_depth`, and evidence-chain provenance.

### D-06 — Rollback selector switch
The old `SubtreeHotspotSelector` route-subtree behavior must remain available as `RAG_TREE_HOTSPOT_SELECTOR=route_subtree`. The new behavior must be enabled by `RAG_TREE_HOTSPOT_SELECTOR=cluster`. Do not delete the old selector in this phase.

### D-07 — Mandatory p6 DNA regression
For query `AI产品经理的核心DNA是什么？`, validation must return evidence containing `数据驱动`, `非确定性`, and `持续性`. The primary hotspot must be `00:31 - 产品特性对比` or `AI产品经理核心DNA` itself, not unrelated regions such as `05:40 - 抖音案例`, `04:40 - 数据工作重要性`, or `06:29 - 特斯拉案例`.

### D-08 — GitNexus risk acceptance boundary
Impact analysis has already surfaced HIGH risk for `SubtreeHotspotSelector`, `RecursiveTreeTraversalRunner`, and tree `QueryHit`, plus CRITICAL risk for `_retrieve_tree_hits_from_backend` and `_map_query_hits_to_backend_hits`. Plans must keep runtime edits incremental, switch-gated, and reversible. `gitnexus detect-changes` is required before commit readiness.

### Claude's Discretion
Implementation may choose exact dataclass field names and private helper decomposition as long as the public behavior and metadata contracts above are preserved.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 11 design contract
- `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-DESIGN.md` — original corrective design, required algorithm, TDD tests, validation plan, non-goals.
- `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-RESEARCH.md` — research findings, architecture recommendations, validation architecture, risks.
- `.planning/phases/11-level-agnostic-hotspot-cluster-tracking/11-VALIDATION.md` — validation contract and required commands.

### Existing implementation
- `llamaindex_runtime/tree/semantic_distribution.py` — current `SubtreeHotspotSelector`, `RecursiveTreeTraversalRunner`, `QueryHit`, cosine similarity helpers, provenance patterns.
- `llamaindex_runtime/tree/runtime.py` — current runtime selector integration and backend-hit mapping path.
- `tests/llamaindex_runtime/test_tree_semantic_hotspot.py` — current hotspot selector/traversal/provenance regression patterns.
- `tests/llamaindex_runtime/test_tree_runtime_traversal_integration.py` — runtime integration tests for traversal and mapping.

### Validation corpus
- `verification/p6_validation/p6_final_sample_structured.md` — p6 structured validation corpus containing `AI产品经理核心DNA` evidence.
- `verification/phase10-real-docx-retrieval-validation/run_validation.py` — existing validation-runner pattern to adapt or copy for Phase 11.
</canonical_refs>

<specifics>
## Specific Ideas

Suggested data shapes:

```python
NodeSemanticHit(node_id, similarity, heading_path, parent_node_id, path_to_root)
ClusterCandidate(ancestor_node_id, member_node_ids, member_scores, max_score, avg_score, support_count, subtree_candidate_count, density)
```

Recommended cluster score:

```python
cluster_score = (
    max_score * 0.40
    + avg_score * 0.30
    + normalized_support_count * 0.20
    + density * 0.10
)
```

Required test names:
- `test_cluster_hotspot_selector_scores_all_nodes_without_route_bonus`
- `test_cluster_hotspot_selector_selects_densest_shared_ancestor`
- `test_cluster_hotspot_selector_avoids_root_when_local_cluster_exists`
- `test_short_exact_heading_node_survives_long_related_text`
- `test_p6_ai_product_manager_core_dna_routes_to_product_characteristics`
</specifics>

<deferred>
## Deferred Ideas

- Heading-path text augmentation.
- BM25 + vector hybrid retrieval.
- Cross-encoder reranking.
- LLM rerank over candidate clusters.
- Full quality Level promotion.
- Human judgment collection.
</deferred>

---

*Phase: 11-level-agnostic-hotspot-cluster-tracking*
*Context gathered: 2026-06-17 via Phase 11 corrective design conversion*
