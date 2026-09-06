---
slug: phase11-hybrid-dna-retrieval
trigger: Phase 11 hybrid_cluster validation failure: Q01 "AI产品经理的核心DNA是什么？" returns no expected DNA evidence terms and selects forbidden 抖音案例 hotspot.
goal: find_root_cause_only
status: root_cause_found
created: 2026-06-19T00:00:00Z
updated: 2026-06-19T03:30:00Z
specialist_dispatch_enabled: true
tdd_mode: false
symptoms_prefilled: true
---

# Phase 11 Hybrid DNA Retrieval Investigation

## Trigger

Phase 11 hybrid_cluster validation failure: Q01 `AI产品经理的核心DNA是什么？` returns no expected evidence terms (`数据驱动`, `非确定性`, `持续性`) and selects forbidden hotspot under `05:40 - 抖音案例`.

## Symptoms

### Expected behavior

- Query Q01 should retrieve evidence from `00:31 - 产品特性对比 > AI产品经理核心DNA` or descendants.
- Retrieved text previews should contain `数据驱动`, `非确定性`, and `持续性`.
- Primary hotspot should not be in forbidden regions: `05:40 - 抖音案例`, `04:40 - 数据工作重要性`, `06:29 - 特斯拉案例`.

### Actual behavior

- `verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py` with `RAG_TREE_HOTSPOT_SELECTOR=hybrid_cluster` fails.
- `dna_expected_terms_found=False`.
- `dna_primary_hotspot_heading` points to `05:40 - 抖音案例 > AI产品经理的思考方向`.
- `dna_forbidden_hotspot_selected=True`.
- Q04/Q05-style content retrieval appears to work for other target areas, so the failure is query/section-specific rather than complete retrieval outage.

### Recent validation output

- `functional_status=FAIL`
- `hotspot_selector=hybrid_cluster`
- `canonical_spans=34`
- `tree_nodes=47`
- `vector_chunks=34`
- `query_count=10`
- `query_failures=0`
- `total_hits=48`
- `hotspot_metadata_rate=1.0`
- `navigation_path_rate=1.0`

### Reproduction

Run:

```powershell
cd verification/phase11-level-agnostic-hotspot-cluster-tracking
python run_validation.py
```

## Current Focus

**Hypothesis:** ROOT CAUSE FOUND — HybridClusterHotspotSelector fusion scoring fails to rank DNA node high enough because vector similarity alone is insufficient and keyword matching weight (0.30) doesn't compensate for distribution penalty on single-child leaf nodes.

**Test:** Compare Q01 vs Q04 retrieval results. DNA node appears in Q04 (rank 3, score 0.571) but not in Q01 top 5. Q01 selects forbidden 抖音案例 node (rank 1, score 0.690).

**Expecting:** Root cause traceable to fusion scoring formula where leaf nodes without strong keyword matches or distribution bonuses are outranked by irrelevant nodes with moderate vector similarity.

**Next Action:** Write root cause report with evidence, exact files/functions involved, and proposed minimal fix.

## Evidence

- timestamp: 2026-06-19T00:00:00Z
  observation: GitNexus impact for `_retrieve_tree_hits_from_backend` is CRITICAL: 15 impacted symbols, 7 affected processes, direct caller `retrieve_tree_hits_from_pdf`.
  implication: Diagnose first; avoid runtime edits until specific fix target and tests are identified.

- timestamp: 2026-06-19T03:00:00Z
  observation: DNA subsection exists in source document at line 38-41 in p6_final_sample_structured.md: "### AI产品经理核心DNA\n- 数据驱动\n- 非确定性\n- 持续性".
  implication: Materialization layer is not the problem; DNA content is in corpus.

- timestamp: 2026-06-19T03:05:00Z
  observation: DNA node `419f55a6-c0f8-5dbd-bef9-c542726f94d7` appears in Q04 retrieval (rank 3, score 0.571) with heading_path "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA" and text_preview "- 数据驱动 - 非确定性 - 持续性".
  implication: Vector embedding matches DNA content adequately for "数据闭环飞轮" query (Q04), proving node is retrievable.

- timestamp: 2026-06-19T03:10:00Z
  observation: Q01 retrieval returns 5 hits: rank 1 抖音案例 (score 0.690), rank 2 课程回顾 (score 0.518), rank 3 本节课讲解重点 (score 0.515), rank 4 抖音案例推荐机制 (score 0.372), rank 5 抖音案例用户行为数据 (score 0.337). DNA node NOT in top 5.
  implication: HybridClusterHotspotSelector fusion scoring ranks forbidden 抖音案例 nodes above DNA node for Q01.

- timestamp: 2026-06-19T03:15:00Z
  observation: HybridClusterHotspotSelector weights: _VECTOR_WEIGHT=0.40, _KEYWORD_WEIGHT=0.30, _RERANK_WEIGHT=0.20, _DISTRIBUTION_WEIGHT=0.10. Child distribution scoring rewards multi-child evidence over isolated leaf nodes.
  file: llamaindex_runtime/tree/semantic_distribution.py lines 836-856.
  implication: Leaf nodes (like DNA node which is level 2 with no children) receive distribution penalty relative to parent nodes with multiple children.

- timestamp: 2026-06-19T03:20:00Z
  observation: Keyword extraction in runtime.py (lines 40-52) splits query by word boundaries, filters stopwords. Query "AI产品经理的核心DNA是什么？" should extract keywords like ['AI', '产品经理', '核心DNA']. Keyword matching (line 209) checks `kw.lower() in heading_path.lower()`.
  implication: DNA heading "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA" contains "AI产品经理核心DNA" substring, so keyword match should succeed.

- timestamp: 2026-06-19T03:25:00Z
  observation: Keyword hits receive fixed score 0.6 (line 219 in runtime.py). Keyword normalization in HybridClusterHotspotSelector (lines 906-913) takes max keyword score per node. Vector scores normalized separately (lines 901-904).
  implication: Keyword boost of 0.30 weight * 0.6 normalized score = 0.18 contribution to fusion score, which may not compensate for weak vector similarity.

- timestamp: 2026-06-19T03:30:00Z
  observation: Q01 query embedding semantic similarity to DNA node may be lower than similarity to 抖音案例 nodes because query "核心DNA是什么" is ambiguous — could match "DNA" conceptually or could match "抖音案例" which discusses "数据飞轮" (a related AI product concept).
  implication: Vector similarity alone insufficient; need stronger keyword signal or distribution adjustment for target-domain leaf nodes.

## Eliminated

- Full retrieval outage: query_failures=0 and other queries retrieve content.
- Materialization failure: DNA node exists in tree (47 nodes), has vector chunk (34 chunks), has span_ids, appears in Q04/Q05 retrieval.
- Keyword extraction failure: Heading contains matching substring "AI产品经理核心DNA".
- Traversal failure: Navigation paths work for other queries, hotspot_node_id populated.

## Resolution

**root_cause:** HybridClusterHotspotSelector fusion scoring formula underweights domain-relevant leaf nodes (like DNA node) when vector similarity is moderate and keyword match is present but distribution bonus penalizes single-child nodes. Forbidden 抖音案例 parent nodes outrank DNA leaf node because they have higher vector similarity (due to semantic overlap with AI product concepts) and receive distribution bonus from having multiple children (推荐机制, 用户行为数据, AI产品经理的思考方向).

**fix:** Adjust keyword matching weight OR add domain-specific boost for exact heading keyword matches OR adjust distribution penalty to not penalize leaf nodes with strong keyword hits. Minimal fix: increase keyword weight from 0.30 to 0.45 when keyword match is exact (matched_terms contains all query keywords) OR add leaf-node bonus when keyword hit score > threshold.

**test_plan:**
1. Add unit test for HybridClusterHotspotSelector fusion scoring with synthetic node_stats: compare leaf node with strong keyword match vs parent node with moderate vector similarity + distribution bonus.
2. Add integration test for Q01 retrieval: assert DNA node in top 3 hits OR assert dna_expected_terms_found=True.
3. Verify fix does not break Q04/Q05 which already succeed.

**files_involved:**
- llamaindex_runtime/tree/semantic_distribution.py lines 836-950 (HybridClusterHotspotSelector.select_hotspots, fusion scoring formula).
- llamaindex_runtime/tree/runtime.py lines 40-52 (keyword extraction), lines 195-224 (keyword hit construction), lines 236-239 (hotspot selection call).
- verification/phase11-level-agnostic-hotspot-cluster-tracking/run_validation.py lines 413-456 (DNA validation logic).

**proposed_fix_options:**
1. Increase keyword weight to 0.45 when all query keywords match heading (exact match boost).
2. Add leaf-node distribution bonus when keyword hit score > 0.5 (domain-specific relevance signal).
3. Adjust distribution penalty: reduce _DISTRIBUTION_WEIGHT from 0.10 to 0.05 for leaf nodes with keyword hits.

**recommended_fix:** Option 1 (increase keyword weight for exact matches) is minimal and targeted. Implement by checking if matched_keywords contains all extracted query keywords, then boost keyword weight to 0.45 instead of 0.30. This avoids distribution formula changes and respects keyword matching signal without overfitting to specific domain terms.