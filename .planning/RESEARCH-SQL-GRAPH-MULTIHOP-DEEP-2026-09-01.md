# RESEARCH: SQL Graph Multi-hop Deep Research (archived 2026-09-01)

Provenance: user ran external deep research (2026-09-01) with coordinator prompt `.tmp/deep_research_prompt_sql_multihop_projects.md`. This is the coordinator condensed archive; verbatim cite tokens dropped. Companion doc: `.planning/RESEARCH-ENTITY-NORMALIZATION-DEEP-2026-09-01.md`. Both feed the ONE integrated program (UIE wiring + normalization + graph recall, per user decision (h)).

## 1. Verdict
- Single-machine PG, read-heavy/batch-write, fixed 2-hop, fanout-capped, sub-second online: DIRECTION VALIDATED, with real open-source precedents.
- Do NOT make "recursive CTE" the goal. Recommended ONLINE main path: Python-controlled BFS, one BATCHED SQL per hop (2 round trips per request), per-node fanout via `unnest(bigint[]) + LATERAL top-K`; keep recursive CTE only as generic/experimental/debug path. (Note: our 17-BOUNDARY.md L33 defaults to recursive CTE - this report recommends the OTHER boundary-allowed option, batched app-layer multi-hop, for the online path. Phase 17 PLAN should adopt this.)
- The critical guard is not total graph size but "edges touched PER REQUEST". Five independent budgets: depth / per-hop fanout / total unique nodes / total edges / wall-clock timeout.
- Graph hits are NOT evidence: edge/node -> provenance -> source chunks -> existing reranker. Graph = recall/navigation only.

## 2. Project evidence table
| Project | Maturity/License | Evidence | Pattern | Copy-worthy |
|---|---|---|---|---|
| LightRAG PGTableGraphStorage | ~39k stars, MIT, v1.5.6 2026-08-06, active | official merge test ~8k nodes/40k edges: get_knowledge_graph p50 39ms vs AGE 1,099ms; batch load 3.0s vs 434s | plain tables lightrag_graph_nodes/edges, JSONB props + B-tree; official recommended PG graph backend; doc describes frontier-capped BFS capped by max_nodes (MAX_GRAPH_NODES=1000 default) | closest match to our RAG case: plain-table graph, batch API, global node budget, one PG hosting graph+vector+KV+doc-status |
| Cognee PG graph adapter | ~30k stars, Apache-2.0, active | no large benchmark; repo itself marks PG graph backend demo-grade | graph_node(id,name,type,properties), graph_edge(source_id,target_id,relationship_name) composite PK, FK+cascade; get_neighborhood WITH RECURSIVE | schema to copy: hot columns promoted from JSON, composite unique edges, explicit ::bigint[] casts |
| OpenFGA | 5.7k stars, Apache-2.0, v1.19 2026-08 | real MySQL tuple table 12,044,739 rows: wrong index path ~65s -> composite index ~0.2s | SQL tuples + app-layer resolver (not RCTE) | budgets as first-class: resolveNodeLimit 25, resolveNodeBreadthLimit 10, deadline 3s, result limits. Anti-pattern lesson: fine-grained per-node reads exhausted hundreds of PG connections |
| SpiceDB | ~7k stars, Apache-2.0 | no RAG-aligned benchmark | SQL datastore + app-layer dispatch | recursion max-depth error; memory-protection middleware (1.48+) rejects under pressure |
| GitLab namespace hierarchy | production-scale PG | traversal_ids in production 2026 | early recursive CTE -> materialized root path array `traversal_ids`; authz queries became linear array predicates | when to STOP using RCTE: true tree + hot ancestor/descendant queries -> materialized path (or ltree); depth cap 20 |
| staudenmeir/laravel-adjacency-list | MIT, maintained | no benchmark | CTE-based adjacency API | read for what a mature RCTE API exposes: depth, constraints, cycle detection, path |
| Small RAG/memory projects (Ogham MCP etc.) | samples only | none reliable | PG FTS + pgvector + memory_relationships recursive CTE in one DB | architecture-isomorphic: vector+lexical+graph all-PG fusion interface |

## 3. LightRAG specifics
- Evolution: PGGraphStorage+Apache AGE -> PGTableGraphStorage plain tables (2026). Migration motives: AGE hard to deploy on RDS/Cloud SQL/Supabase/Neon; Cypher wrapper latency; AGE 1.8.0 graphid incompatibility could SIGSEGV PG backend (crash recovery) -> LightRAG added fail-closed version gate. Strong evidence AGAINST adding AGE for us.
- DO NOT COPY its undirected canonicalization: LightRAG treats (A,B)/(B,A) as same canonical pair (sorts entity IDs for edge-pair dedup). OUR relations are DIRECTED - keep UNIQUE(workspace,src,dst,relation_type) allowing both directions as distinct rows.
- Migration tool handles dup nodes/edges, rebuilds composite PK, clears orphan edges before endpoint FK; refuses lossless-impossible reciprocal-edge cases.

## 4. Cognee asyncpg pitfall (team rule)
`SELECT unnest(:seeds), 0` fails on PG16+asyncpg (bind param becomes `unknown`, cannot resolve unnest(unknown)). Fix/rule: ALWAYS explicit cast: `SELECT unnest($1::bigint[])`. Also: entity IDs, src/dst, frontier arrays, CTE paths all bigint from day one (GitLab hit integer/bigint array mismatch).

## 5. Schema (adapted for directed + evidence)
- kg_edge: edge_id identity PK, workspace_id, src_entity_id, dst_entity_id, relation_type smallint (FK dict), confidence, weight, props JSONB cold-only, created_at/updated_at; UNIQUE(workspace_id,src_entity_id,dst_entity_id,relation_type); FKs to entity.
- Two access indexes: (workspace_id,src_entity_id,dst_entity_id) INCLUDE(edge_id,relation_type,confidence,weight) and mirrored (workspace_id,dst_entity_id,src_entity_id); optional (workspace,src,relation_type,dst) per real query pattern; leading-column equality is what PG multicolumn B-tree rewards.
- kg_edge_evidence(edge_id FK CASCADE, chunk_id FK CASCADE, support_score, PK(edge_id,chunk_id)) + (chunk_id,edge_id) index. Never stuff chunk ids into an unbounded JSONB array.

## 6. Online query pattern (recommended main path)
- Fixed 2-hop: Python issues TWO batched SQLs (hop1, hop2), each: frontier = unnest($1::bigint[]), CROSS JOIN LATERAL per-node top-K (fanout) over outgoing UNION ALL incoming branches (direction flag +1/-1 preserved; edge rows never rewritten), excluding visited array, ORDER BY confidence DESC, edge_id, per-node LIMIT fanout; outer LIMIT = per-hop edge budget. Two round trips total, no N+1.
- Do NOT pre-canonicalize directed edges to (min,max) - that is LightRAG undirected behavior.
- Python control flow keeps: visited set, frontier list, hit_edges, budgets; breaks on budget exhaustion; next_frontier built from unseen nodes under node_budget.
- DB-side fuse: `BEGIN; SET LOCAL statement_timeout = 180ms; <expansion SQL>; COMMIT;` (request-local, not global postgresql.conf).
- Recursive CTE fallback (generic depth API): WITH RECURSIVE walk with path bigint[] cycle-guard, per-parent LATERAL fanout DURING recursion, depth < max in WHERE; DISTINCT ON entity for best path. NEVER rely on outer LIMIT to stop recursion (PG docs: early termination only when executor consumes lazily; sort/join can force full evaluation).
- Evidence step: hit_edge_ids JOIN kg_edge_evidence -> group by chunk_id, score = max(path_score * support_score) -> chunks (20-40) go to fusion/rerank. Can also use existing entity_mention(entity_id,chunk_id) for node evidence. No new evidence store needed.

## 7. Guardrail initial values (engineering starting points, not laws)
max_seeds<=5 (query-side linker top-K); max_depth hard 2; hop1_fanout=24; hop2_fanout=12; max_unique_nodes=1000 (LightRAG MAX_GRAPH_NODES default same order); max_edges=1500-2500; statement_timeout=150-200ms; graph stage target p95<100ms, hard SLO p95<150-200ms; final evidence chunks 20-40. Fanout math: worst path tree ~1+F+F^2 nodes (F=16 -> 273; F=32 -> 1057; F=64 -> 4161); 3 seeds multiply.
- Hub suppression: degree_out/in stats or offline degree bucket; degree>1000: per-hop<=8; degree>10000: no expansion unless relation whitelist (e.g. down-weight 公司-属于-行业 hub relations).
- Response should report: depth_reached, nodes_visited, edges_visited, chunks_returned, truncated, truncate_reason, elapsed_ms (LightRAG exposes is_truncated similarly).
- Degradation ladder: normal -> near-budget: shrink hop2 fanout / stop new frontier -> timeout/node budget: keep completed hop1 + evidence -> PG pressure: turn graph channel OFF entirely (fallback to vector+BM25), never fail the whole RAG request.

## 8. Closure table / ltree decision table
- General cyclic typed KG default 2-hop: NO closure table; live edge table + bounded expansion.
- True single-parent tree (org/chapter/category): ltree or GitLab-style traversal_ids materialized path for that relation only.
- Rare-write stable DAG with frequent ancestor/descendant queries: consider closure table.
- Arbitrary relation-sequence KG: closure table not worth it.

## 9. Swap-to-graph-DB triggers (functional, NOT edge-count)
- Keep PG: 2-hop default, touched edges <5k, p95 <100-150ms. Even 10M-100M edges with selective queries + small budgets is NOT a trigger (OpenFGA 12M tuples).
- Architecture review: p95 >200ms or p99 >500ms sustained after index/fanout/N+1 fixes.
- Consider dedicated graph serving: typical request must touch >50k edges, or node budget must grow 1k -> >10k for recall.
- Strong signals: hub seeds degree >10k-100k un-prunable; requests evolve to 4+ hops with runtime-determined path lengths; product needs shortest path/all paths/variable-length patterns/online graph algorithms (shortest path, community, centrality); graph workload >30% of single PG CPU/IO degrading pgvector/BM25 p95 by >20%; timeout rate several percent unfixable; unbounded user-submitted graph queries.
- Principle: QUERY SHAPE is the architecture boundary, not row count.

## 10. Pitfalls (do-not list)
1. Per-node SQL from Python BFS (connection storm; batch per frontier). 2. depth-only limits without breadth (degree-100k seed fills everything on hop1). 3. Recursive CTE fully expanded + outer LIMIT as fuse. 4. src/dst/relation_type inside JSONB (kills B-tree adjacency access). 5. Copying LightRAG undirected canonicalization. 6. Implicit array param types (always $1::bigint[]). 7. Mixed integer/bigint IDs and path arrays. 8. Closure table over general KG. 9. Installing AGE just for Cypher syntax (LightRAG SIGSEGV/crash-recovery incident with AGE 1.8.0; deploy pain on managed PG). 10. Feeding graph edges directly into prompt instead of provenance chunks.

## 11. Final one-liner
Use PostgreSQL AS PostgreSQL, not disguised Neo4j: narrow directed edge table + bidirectional B-tree adjacency indexes + two batch-frontier SQL rounds + strict depth/fanout/node/edge/time budgets + land graph hits on provenance chunks. Aligns with LightRAG 2026 AGE->plain-tables move; absorbs OpenFGA budget philosophy, Cognee schema/cast pitfalls, GitLab hierarchy-only precomputation.
