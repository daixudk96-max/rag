# DECISION: RAG backend adopts LightRAG (graph + vector unified) - 2026-09-01

Decision authority: USER, 2026-09-01 (this session). Status: FORMAL architecture decision.

## Decision (user words, intent preserved)
- 全面引入 LightRAG 作为 RAG 后端（成熟、有人维护），在其基础上加/改少量部件。
- **图谱与向量不再作为两条独立召回通道**：两者默认合成一路（LightRAG 承担），加我们既有的 BM25 + 重排通道做融合。
- 归一化（别名/消歧）层仍由我们实现，接在 LightRAG 之上/之前。
- 理由（用户）: LightRAG 成熟、维护好；自建维护困难；借鉴重搞工作量大于直接用+小改；AGE 插件非生产级 -> 用其生产级 PG plain-table 后端（PGTableGraphStorage）。

## Integration scope (the 'small changes')
1. Feeding mode (OPEN, research v3 Q1): feed our PRE-BUILT, normalized KG into LightRAG (custom KG insertion, e.g. insert_custom_kg) vs let LightRAG LLM-extract entities itself. Preference: feed our own graph (keeps Phase 16 deterministic pipeline as upstream, avoids LLM extraction cost/nondeterminism).
2. Normalization/alias layer: stays OURS (Phase 17), upstream of or replacing LightRAG's name-keyed merge.
3. BM25 + rerank: our existing path; fusion point with LightRAG channel to be designed in Phase 17 PLAN.
4. Query-time LLM usage: LightRAG graph query modes may require LLM keyword extraction at query time - conflicts with the Phase-16-ratified zero-generative-LLM entity-pipeline contract; needs explicit user decision + contract amendment at Phase 17 PLAN (retrieval-path LLM is a different scope than entity-materialization LLM, but must be explicit).
5. workspace/scope filtering + evidence-to-chunk provenance alignment with existing okf_e2b/node_entity_links schema.

## Impact on existing planning docs (deferred to Phase 17 PLAN, not edited now)
- 17-BOUNDARY.md L33 'no new store' still holds: LightRAG PGTableGraphStorage uses plain PostgreSQL tables (no AGE, no new engine). L19 switch matrix semantics (R3 route, RAG_ENTITY_EXTRACTOR) and L33 default query path need amendment when Phase 17 planning starts.
- Phase 16 assets (entity pipeline, materialization, coref, verification orchestrators) are RETAINED as the upstream producer of the graph LightRAG will serve.

## Research inputs
- .planning/RESEARCH-ENTITY-NORMALIZATION-DEEP-2026-09-01.md
- .planning/RESEARCH-SQL-GRAPH-MULTIHOP-DEEP-2026-09-01.md (LightRAG PGTableGraphStorage 39ms p50 vs AGE 1099ms; budgeted BFS pattern; directed-edge warning)
- Deep research v3 (integration paths): .tmp/deep_research_prompt_lightrag_integration_v3.md (issued 2026-09-01, user runs externally)
- v2 projects-panorama report arrived 2026-09-01 and archived: `.planning/RESEARCH-NORMALIZATION-PROJECTS-PANORAMA-2026-09-01.md`. Confirms: LightRAG merge = exact-name (maintainer-confirmed) with `merge_entities` API in `lightrag/operate.py`/`utils_graph.py` (post-decision executor, copyable); PG canonical tables = source of truth, LightRAG indexes derived/rebuildable; normalization layer (Splink scoring + dedupe active learning + RapidFuzz + USCC hard anchors) remains OURS per decision. Answers research-v3 Q2; Q1/Q3/Q4/Q5 still pending v3 run.

---

## Addendum: R8 embedding backend decision (2026-09-02)

Decision (user: interim online now, local bge-m3 before W7):

- Embedding adapter is PLUGGABLE (online + local dual channel, interface-level swap, no schema change).
- Interim (now): Aliyun DashScope `text-embedding-v3`, 1024 dims, OpenAI-compatible endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1`.
  - Connectivity VERIFIED 2026-09-02: HTTP 200, model echoed, dimension 1024 (usage 4 tokens). Key stored in `E:/github/rag/.env` under `DASHSCOPE_API_KEY` (local-only file, never committed).
- Final (before W7 acceptance): local `bge-m3` (1024 dims) via repo-local wheelhouse; same dimension -> no re-index/rebuild needed at switchover.
- Constraints honored: key never printed/logged; no key in repo code; evidence redacted.
- Note: local relay (127.0.0.1:8317) serves chat/image LLMs only - POST /v1/embeddings returns 404, so it cannot supply embeddings.

Rationale: interim online avoids blocking W6 on a local model deploy; pluggable adapter keeps the W7 local-bge-m3 switchover a config change, not a schema migration.

### R8 update: upgraded interim model to text-embedding-v4 (2026-09-02)

User asked for the newest embedding model and higher dimensionality. Probed live with the stored key:

- text-embedding-v4: OK; default 1024 dims; accepts dimensions up to 2048 (verified 2048).
- text-embedding-v3: hard caps at 1024 (HTTP 400: dimension range [64, 128, 256, 512, 768, 1024]).

Amended decision: interim online model = text-embedding-v4 pinned at dimensions=1024.
Rationale: model generation is the quality lever, not dimension count; pinning 1024 keeps future local bge-m3 (1024) switchover schema-compatible with zero re-index. 2048 dims would break that compatibility path.
Config: E:/github/rag/.env now has DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4 + DASHSCOPE_EMBEDDING_DIMENSIONS=1024 (adapter must send the explicit dimensions parameter, never rely on provider defaults).