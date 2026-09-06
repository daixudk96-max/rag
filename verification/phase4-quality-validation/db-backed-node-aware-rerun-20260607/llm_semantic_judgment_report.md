# LLM Semantic Judgment Report

## Summary

- **review_type**: LLM semantic judgment from archived DB-backed retrieval snippets
- **source_archive**: `verification/phase4-quality-validation/db-backed-node-aware-rerun-20260607`
- **query_count**: 20
- **verdict**: `ROOT_BIAS_IMPROVED_BUT_SEMANTIC_RELEVANCE_NOT_PASS`
- **top1_full_relevance_rate_score_ge_0_8**: 0.30
- **top1_relevance_rate_score_ge_0_5**: 0.55
- **top1_average_relevance_score**: 0.55
- **best_top3_average_relevance_score**: 0.61
- **category_counts**:
  - fully_relevant: 6
  - mostly_relevant: 3
  - partially_relevant: 3
  - marginally_relevant: 4
  - not_relevant: 4

## Important interpretation

This is a semantic content judgment, not just a retrieval-hit or root-bias score.

The node-aware change materially improves root-bias: the archived retrieval has 20/20 queries with hits and only 1/20 top1 root hits. However, semantic relevance still does not meet the Phase quality target. Several top1 hits are structurally plausible but do not actually answer the query.

Major blockers:

1. Some validation queries ask for content absent from the source document, especially case-study, error-handling, invalid-input handling, chunking details, and explicit vector-threshold questions.
2. Several top1 hits land on adjacent implementation/integration sections rather than answer-specific evidence.
3. Evidence chain is still incomplete in `validation_status.json`: `chunks=0`, `mapped_chunks=0`, `heading_path_rate=0`.

## Per-query judgments

| Query | Score | Category | Top1 pass | Best rank | Judgment |
|---|---:|---|---|---:|---|
| Q01 | 0.45 | partially_relevant | false | 1 | Top1 is root title and only shows the document start plus the first major section. It does not list all first-level headings. Rank2/3 add partial structure but still do not answer the full structure request. |
| Q02 | 0.75 | mostly_relevant | false | 1 | Top1 hits “聚类功能已经实现了” and shows `_detect_semantic_cluster`, which is a real algorithm-related section. It is relevant, but not a clear comprehensive “核心算法原理” section. |
| Q03 | 0.05 | not_relevant | false | 3 | Source search found no case-study/case chapter. Top hits are Agent Workflow, feature list, and root title. They do not answer whether a case-study chapter exists or where it is. |
| Q04 | 0.65 | partially_relevant | false | 1 | Top1 Token 消耗对比 is one technical metric area, and rank2 functional matrix is also metric-like. But the query asks for all key technical indicators; retrieval does not surface a complete indicator list. |
| Q05 | 0.35 | marginally_relevant | false | 2 | Top hits discuss user intent and integration architecture. They mention input/retrieval/output, but do not actually explain how to use the system for data processing. |
| Q06 | 0.80 | fully_relevant | true | 1 | Top1 Token 消耗对比 is directly about performance optimization. Rank2/3 add hybrid retrieval and integration strategy, so the result can answer optimization methods. |
| Q07 | 0.80 | fully_relevant | true | 2 | Top1/2 hit recommended integration architecture. They support the design principles: preserve PageIndex, enhance retrieval, keep BackendHit output/contracts. |
| Q08 | 0.05 | not_relevant | false | 1 | Source search found no real error-handling mechanism. Top hits are Client/CLI/Agent Workflow feature sections and do not answer error handling. |
| Q09 | 0.85 | fully_relevant | true | 1 | Top1 clearly describes the chain: `get_document_structure` → LLM reasoning → `get_page_content` → final answer. This matches the requested complete flow. |
| Q10 | 0.65 | partially_relevant | false | 3 | Top1 is a comparison section; rank3 Token 消耗对比 directly supports performance/cost tradeoff. The answer is possible from top3, but top1 itself is only partial. |
| Q11 | 0.75 | mostly_relevant | false | 2 | Top1 summary recommends a technical approach; rank2/3 recommended integration scheme explain reasons. Comparison evidence exists elsewhere, but top1 is not the best evidence. |
| Q12 | 0.90 | fully_relevant | true | 1 | Top1 hits “下一步”, directly answering future work. It also fits the limitation/pending-work aspect of the question. |
| Q13 | 0.10 | not_relevant | false | 1 | Source search found no invalid-input or input-format error handling content. Top hits are Client/CLI/matrix sections and do not answer the query. |
| Q14 | 0.75 | mostly_relevant | false | 1 | Top1 Token 消耗对比 and rank2/3 functional matrix surface constraints such as token cost and missing features. Relevant but not a complete constraints list. |
| Q15 | 0.35 | marginally_relevant | false | 1 | Top1 hits retrieval backend enhancement and embedding clustering, but does not provide the vector retrieval threshold. Nearby source has config thresholds, but they are not in top3. |
| Q16 | 0.10 | not_relevant | false | 3 | Query asks for tree depth limit. Top hits are Client/CLI/matrix sections, not depth or tree-thinning threshold sections. |
| Q17 | 0.25 | marginally_relevant | false | 2 | Rank2 token comparison is weakly related to token limits, but top results do not describe chunking strategy. |
| Q18 | 0.40 | marginally_relevant | false | 1 | Top1 mentions embedding-based clustering, but does not explain model selection basis or list concrete embedding models. |
| Q19 | 0.85 | fully_relevant | true | 2 | Top1/2 PageIndex vs current implementation and functional matrix directly answer technical-scheme comparison. Rank3 token comparison adds tradeoff evidence. |
| Q20 | 0.90 | fully_relevant | true | 1 | Top1 recommended integration scheme directly answers integration with other systems: PageIndexClient, retrieval enhancement, and BackendHit output integration. |

## Bottom line

The fix is a real improvement for root-bias and retrieval coverage, but not a semantic quality pass.

- Before fix / historical artifact: root-bias was very high.
- After node-aware DB-backed rerun: top1 root-bias is about 5%.
- But semantic top1 full relevance is only about 30%; relaxed top1 relevance is about 55%.

So the next bottleneck is no longer root-first mapping. The next bottleneck is query/content alignment and evidence richness: the source document does not contain several requested answers, and retrieval has only heading/summary-style node text with no chunk evidence chain.
