# Real End-to-End Validation Report

**Date**: 2026-05-12 23:45:32
**Document**: `[21]--【进阶版RAG】Query路由.MP_原文.docx`
**Result**: 31/31 passed, 0 failed

## Infrastructure

- **PostgreSQL**: `postgresql://postgres:postgres@localhost:5432/rag_registry`
- **Neo4j**: `bolt://localhost:17688` (临时测试实例，认证已省略)
- **Parser**: Docling (via DoclingWrapper)

## Step-by-Step Results

| Step | Status | Detail |
|------|--------|--------|
| 1a_parse_docx | PASS | 72 items parsed |
| 1b_generate_spans | PASS | 72 spans generated |
| 1c_sample_content | PASS | First spans: ['[21]--【进阶版RAG】Query路由.MP_原文', '2026年03月09日 17:40', '发言人 00:00'] |
| 2a_migrations | PASS | Schema applied |
| 2b_clean_slate | PASS | Tables truncated |
| 2c_create_document | PASS | doc_id=e760dafe-bfd0-4869-903c-b8329fe87a34 |
| 2d_create_contract | PASS | contract_id=526dca73-89ef-41f5-b17b-1df1f6db6d61 |
| 2e_create_version | PASS | version_id=fe6f4abb-2b44-4a61-82ac-7f381a81a497 |
| 2f_write_spans | PASS | 72 spans written |
| 2g_activate_version | PASS | version_id=fe6f4abb-2b44-4a61-82ac-7f381a81a497 activated |
| 3a_vector_chunks | PASS | 72 chunks with embeddings |
| 3b_tree_generate | PASS | 1 tree nodes generated |
| 3c_tree_load | PASS | 1 nodes, 72 node_spans loaded |
| 4a_anchor_terms | PASS | 5 anchor terms extracted |
| 4b_neo4j_clean | PASS | Neo4j cleaned |
| 4c_entities_created | PASS | 5 entities with evidence_links |
| 4d_relation_created | PASS | relation between first two entities |
| 5a_keyword | PASS | query='Query路由', hits=2, match_type=exact |
| 5b_vector | PASS | query='Query路由', hits=5, top3_scores=[0.9901, 0.9899, 0.9899] |
| 5c_graph | PASS | entity_id=fd9f3ae9-9e8c-5f68-bc39-1d87201585af, neighbors=1, evidence=1 |
| 5d_analyze | PASS | cv=0.000, entropy=0.000, decision=high_dispersion, hit_count=10, suggested_nodes=1 |
| 5e_hybrid | PASS | paths=[('keyword', 2, True), ('vector', 10, True), ('graph', 1, True)], total_hits=72, decision=high_dispersion, expanded_count=60, evidence_count=72 |
| 5f_unified_RAG | PASS | query='RAG', route=keyword, answer_len=27, evidence_count=7 |
| 5f_unified_Query路由的 | PASS | query='Query路由的原理是什么', route=vector, answer_len=206, evidence_count=10 |
| 6a_health_endpoint | PASS | status=200, body={'status': 'ok'} |
| 6b_keyword_endpoint | PASS | status=200, hits=2 |
| 6c_vector_endpoint | PASS | status=200, hits=5 |
| 6d_graph_endpoint | PASS | status=200, neighbors=1 |
| 6e_analyze_endpoint | PASS | status=200, body_keys=['cv', 'entropy', 'decision', 'reason', 'hit_count', 'suggested_node_ids'] |
| 6f_hybrid_endpoint | PASS | status=200, decision=high_dispersion |
| 6g_unified_endpoint | PASS | status=200, route=keyword |

## Detailed Failure Output

No failures detected.

## Document Content Summary

- **Total spans**: 72
- **Unique heading paths**: 1

### Heading Paths (first 20)

- `(root)`

### Graph Anchor Entities

1. **[21]--【进阶版RAG】Query路由.MP_原文** (heading: `(root)`)
2. **2026年03月09日 17:40** (heading: `(root)`)
3. **发言人 00:00** (heading: `(root)`)
4. **然后我们那天背景课的时候跟大家讲陆游对吧？好，我看看有多少人** (heading: `(root)`)
5. **发言人 00:41** (heading: `(root)`)

## Caveats and Limitations

- **Embedder**: Uses `DeterministicEmbedder` (hash-based, dim=16), not a real LLM embedding model. Vector similarity is approximate and not semantically meaningful.
- **Query classifier**: Uses simple heuristic rules (digit/symbol check, length threshold), not an ML classifier.
- **Graph entities**: Only 5 manually extracted anchor terms projected. A production system would use NER for automatic entity extraction.
- **Tree structure**: Built from heading_path only; no summary text generated for tree nodes.
- **Reranker**: Uses reciprocal rank fusion, not a cross-encoder model.

---
*Report generated at 2026-05-12 23:45:32*