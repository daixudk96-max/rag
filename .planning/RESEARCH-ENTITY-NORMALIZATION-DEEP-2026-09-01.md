# RESEARCH: Entity Normalization Deep Research (archived 2026-09-01)

Provenance: user ran external deep-research tool (2026-09-01) with coordinator prompt `.tmp/deep_research_prompt_guiyi.md`; report pasted back and archived/condensed by coordinator. Verbatim cite tokens dropped; sources named inline. This document is a planning input for the ONE integrated program (UIE wiring + normalization, per user decision (h) in 16-13-GATE3-OPEN-FOLLOWUPS-2026-09-01.md).

## 0. Coverage caveat (coordinator + user, 2026-09-01)
User review: the tool/project inventory in this report is TOO THIN (only 4 tools + 4 data resources; partly caused by the original prompt capping at 3-5 candidates). A supplementary wide-enumeration research prompt was issued: `.tmp/deep_research_prompt_normalization_projects_v2.md` (target 15-25 concrete projects across 6 categories incl. Chinese-specific, framework merge-implementation details, and authoritative anchor data sources). Coordinator supplementary candidate list (from own knowledge, UNVERIFIED, to be validated by the v2 research): recordlinkage / py_entitymatching / febrl (ER libs); BLINK / GENRE / REL / spaCy EntityLinker (NEL); DeepKE / CCKS entity-linking tasks / bootool-CnDBpedia ecosystem (Chinese); LightRAG / nano-graphrag / cognee / Microsoft GraphRAG / LlamaIndex PropertyGraphIndex (framework entity-merge code to copy); RapidFuzz / jellyfish (fuzzy); GLEIF / OpenCorporates / CN commercial registry APIs + USCC check-digit (authority anchors).

## 1. Core verdict
- Do NOT build normalization as `normalize_name -> lookup -> merge`.
- Needed: incremental, open-world, ingestion-time entity resolution. Every new mention gets exactly one of THREE outcomes: AUTO-LINK/MERGE (high confidence) | HUMAN REVIEW (gray zone) | CREATE NEW provisional entity (no credible candidate).
- Pipeline skeleton (consistent across Wikidata / enterprise MDM / academic EL, e.g. BLINK): candidate generation -> scoring -> decision -> merge/link/new -> audit & feedback.
- PRECISION-FIRST: wrong MERGE is catastrophic (transitive closure can silently chain entities into wrong mega-clusters); wrong SPLIT is recoverable later. Precision is fixed by HARD VETO rules, not by one threshold; recall is fixed by more diverse candidate retrieval. These must be tuned separately.
- Candidate generation and match decision must be evaluated SEPARATELY (a missed candidate can never be fixed by a better scorer).
- Priority order: (1) audit + hard veto + alias provenance + immutable entity IDs; (2) high candidate recall; (3) simple calibrated lightweight matcher; (4) LLM last.

## 2. Recommended pipeline (per-stage table)
| Stage | Implementation | Failure/degrade path |
|---|---|---|
| Raw fidelity | save mention.raw_text + offsets + context; never overwrite | any result replayable from raw |
| Chinese normalization | Unicode NFKC; OpenCC trad/simp -> generate VARIANTS (never overwrite canonical); company-name structural parse | conversions only produce search keys |
| Strong evidence link | full legal name, human-verified aliases, Wikidata QID, USCC code, official domain, product model | conflicting IDs forbid auto-merge |
| Candidate generation | union: exact alias + company structured fields + pg_trgm + pgvector/BGE + low-weight pinyin; type filter | no candidates -> provisional entity |
| Main scorer | rule features + char similarity + context embedding + type/location/relations; Fellegi-Sunter/logistic calibrated | degrade to deterministic evidence |
| Rerank | bge-reranker-v2-m3 cross-encoder, Top-K only | skip without harm |
| Decision | hard veto -> high-precision auto merge/link -> gray-zone human review -> low-score NEW | prefer wrong-split over wrong-merge |
| LLM | gray-zone assist + training-data teacher only; NEVER full hot path | system fully functional without |
| Audit | immutable IDs + resolution/merge events + evidence JSONB + rule/alias/model versions | merge redirect/rollback |
| Alias learning/backfill | alias lifecycle candidate/pending/verified; re-run ONLY affected historical mentions | no destructive full recompute |

## 3. Key principles
- Entity ID is identity; canonical name is just an attribute (Wikidata model). Aliases are provenance-carrying ASSETS, not identity keys.
- open-world linking: f(m) in E union {NEW, REVIEW} - NIL/NEW is a first-class result.
- Evidence tiers: STRONG = same USCC code, official former-name statements, verified external IDs, unique product model, explicit document pattern `X（以下简称Y）`; MEDIUM = normalized full-name match, high context similarity, same location/industry, repeated co-usage across independent docs; WEAK = shared trade name, edit distance, embedding, pinyin, mere co-occurrence. A single WEAK evidence must never auto-merge.
- Hard veto per entity type: ORG = different USCC, known subsidiary_of/parent_of/brand_of relations, conflicting legal structure; PRODUCT = model/SKU/version; PER = birth date/affiliation/geo/timeline conflicts.
- Cluster merge (A~B, B~C => A,B,C one cluster) forbidden as naive transitive closure; new edge must re-score against canonical cluster profile + verify hard constraints across both groups.
- Auto-merge threshold: choose smallest t on human gold set s.t. precision lower-confidence-bound at auto-merge band reaches target (e.g. 99.5-99.9%); NOT a hand-picked cosine number. 99.5/99.9 are engineering targets for this scenario, not industry constants.

## 4. Alias table design (fact table with provenance, not TEXT[])
entity_alias: alias_id, entity_id, alias_raw, alias_norm, alias_type (legal_name/short_name/former_name/brand_name/transliteration/traditional_variant/typo_variant/generated_candidate), source_type, source_ref, evidence_span, confidence, status (candidate/verified/rejected/deprecated), valid_from, valid_to, alias_version, created_by, created_at.
Alias semantics: under WHAT source, type, time, and evidence may this string be interpreted as this entity.

## 5. Chinese-specific normalization
- Company names: parse into {admin_division, trade_name, industry, org_form}; fields feed candidate retrieval and scoring; NEVER merge after stripping suffixes (shared trade name != same legal person; 集团 vs 有限公司 are related but often distinct entities).
- `华为` should become a typed, sourced, short-name ALIAS of `华为技术有限公司` (from attested evidence spans), not the output of suffix-stripping rules.
- NFKC for search keys; raw always preserved. OpenCC (Apache-2.0) generates simplified/traditional VARIANTS. pypinyin (MIT) recall-only, low weight, never merge evidence.

## 6. External alias resources
- Wikidata: STRONGLY RECOMMENDED seed (CC0, zh/zh-hans/zh-hant labels+aliases+external IDs).
- CN-DBpedia: valuable Chinese encyclopedia entity/alias source but verify current license before production import.
- OpenKG: a discovery portal, NOT a blanket license - check per dataset.
- OwnThink: ~140M-row KG but no clear license -> exclude from production default.
- Do not chase a global coverage number; measure alias coverage on own gold mentions per type (PER/ORG/LOC/PRODUCT).

## 7. Alias mining priority
1. Evidence-pattern extraction: `（以下简称X）` / `简称X` / `原名` / `曾用名` - HIGH precision, alias and canonical co-occur in one evidence span, perfect for audit chains, very low cost. 2. Wikidata-sourced aliases with provenance. 3. Human-reviewed coref clusters learned as aliases. 4. Multi-doc repeated contexts + structured anchors. NOT: bare co-occurrence mining (mother/subsidiary co-occur BECAUSE they are related). LLM: constrained EXTRACTION from given spans only (must locate exact span, else candidate-only); free-form alias imagination forbidden.

## 8. Models: embeddings / reranker / LLM
- Candidates: BAAI/bge-base-zh-v1.5 (cheap) or BAAI/bge-m3 (multilingual, 8192 tokens, dense+sparse+multi-vector). Rerank Top-K: BAAI/bge-reranker-v2-m3. All from FlagEmbedding, one stack.
- Embed entity PROFILE (type/name/aliases/location/industry/description/key relations) and mention CONTEXT (surrounding sentence) - never embed bare strings; similarity != identity (subsidiary/brand/next-gen product are semantically close but must NOT merge).
- LLM-as-judge data: GPT-4 zero-shot ER F1 76.4-98.4 across 6 benchmarks; ~117 tokens/pair, ~2.19 s and ~0.47 US-cent per pair (2024 prices). 2026 teacher-student study: LLM labeling of 5 ER benchmarks cost ~USD 28-41 total; student matcher within 2 F1 of human-trained; Distil-style matcher 41.5-534x faster than LLM inference.
- => LLM = gray-zone judge + labeling teacher, not hot-path matcher. LLM explanations are NOT audit evidence; evidence = source spans + structured fields. LLM-extracted aliases without located span stay `candidate` forever.

## 9. Open-source tools
| Tool | Status 2026-09 | License | Verdict for us |
|---|---|---|---|
| Splink (moj-analytical-services) | very active (2026-08), Splink 4, PostgreSQL backend, Fellegi-Sunter, TF-adjust | MIT; OPEN ISSUE: igraph GPL dependency redistribution question (2026-08-25) - check before closed-source redistribution | learn from / optionally embed as scorer; not whole pipeline |
| dedupe | low activity (last surfaced commit 2025-07-29) | MIT | human-in-the-loop fits; ★★☆ maintenance risk |
| Zingg | active | AGPL-3.0 + Spark | NOT recommended: ops + license weight for 1-3 person team |
| LinkTransformer | moderate | GPL-3.0 | reference for semantic candidate generation only |
- Final tool stance: own the orchestrator + PG data model ourselves; pg_trgm + pgvector + BGE candidate layer; borrow Fellegi-Sunter thinking (Splink-style); build review UI ourselves.

## 10. Evaluation (4 layers, all required)
- Candidate layer: Recall@K target >99% (high; scorer handles precision later).
- Pair layer: precision@auto-merge-threshold is THE production gate; F1 auxiliary; report review-band precision/recall.
- Cluster layer: B-cubed AND pairwise together.
- Ops layer: auto_merge_rate, new_entity_rate, review_rate, review_accept_rate, rollback_rate, alias_precision_by_source, candidate_miss_rate, mega_cluster_alerts, p95 ingestion latency, LLM calls/1000 mentions, reviewer minutes/1000 mentions.
- Gold set v1: ~1000-2000 targeted human judgments, NOT random: ~30% near auto-merge threshold, ~20% same-short-name hard negatives, ~20% known true aliases, ~15% candidate-boundary, ~10% random traffic, ~5% cluster-merge incidents; double-label 20-30% of riskiest.
- Label taxonomy MUST include RELATED_BUT_NOT_SAME (parent/subsidiary, brand/company, product/line) besides SAME/DIFFERENT/INSUFFICIENT.
- Slice reporting by entity type, surface form (exact/short/typo/trad-simp/pinyin), frequency, alias source, decision source, cluster size; specifically track false-merge rate of high-frequency short ORG aliases (华为/联想/中兴 class).
- Reviewer UI shows: mention + source context, candidate entity profile, positive evidence, veto checks, alias provenance span, model versions, choices [Same/Different/Related-but-distinct/Insufficient].

## 11. PostgreSQL schema sketch (v1)
- entities(entity_id PK, entity_type, canonical_name, status active/merged/provisional/retired, merged_into_id NULL, created_at, created_by_version) - ID never changes on rename; merge is LOGICAL (status=merged + merged_into_id redirect), never DELETE/UPDATE-all.
- mentions(mention_id PK, document_id, raw_text, norm_text, char_start, char_end, context_text, entity_type, created_at).
- entity_aliases(... per section 4 ...).
- mention_resolutions(resolution_id PK, mention_id, entity_id, candidate_rank, calibrated_score, decision auto/review/human/new, resolver_version, normalization_ver, alias_version, evidence JSONB, reviewer_id, created_at) - APPEND-ONLY versioned facts with supersedes chain; answers "why was this mention linked to X on date D".
- entity_merge_events(merge_event_id PK, source_entity_id, target_entity_id, decision_source, score, evidence JSONB, resolver_version, reviewer_id, rollback_of, created_at).
- do_not_merge(entity_id_a, entity_id_b, reason, evidence, PK(a,b)) - prevents re-review of human-rejected pairs after model upgrades.
- Backfill: reverse index alias_norm -> mention_ids and -> candidate entity_ids; when alias promoted candidate->verified, re-run ONLY affected mentions (unresolved / provisional / low-confidence / old resolver version / same surface), never full corpus.

## 12. resolve_mention algorithm (condensed)
A save raw -> B build search keys (nfkc/simplified/traditional/company_parts/pinyin) -> C exact verified-alias lookup; unique strong match + no veto = commit -> D union candidates (exact norm / structured fields / trigram / embedding / pinyin) + type filter; empty -> provisional -> E drop vetoed candidates -> F calibrated feature scoring -> G cross-encoder rerank Top-K only when needed -> H decision: auto-merge policy pass + cluster consistency check => commit; review band => optional LLM judge + enqueue human; else => provisional new entity. Each mention compares against tens of candidates, never 10^6 pairwise.

## 13. Not-recommended list (with reasons)
1. Strip `有限公司/集团/行政区划` then exact-merge (shared trade name != same legal person). 2. embedding cosine > X auto-merge (similarity != identity). 3. aliases as TEXT[] without provenance. 4. free-form LLM alias generation into verified table (hallucination -> systematic false merges). 5. LLM on every candidate pair (cost/latency; use teacher-student instead). 6. pair threshold + transitive closure clustering (one false edge -> mega-cluster). 7. one scorer/threshold for all entity types. 8. destructive full-corpus backfill after alias changes. 9. deleting loser entity ID on merge (breaks audit + refs; use redirect/tombstone). 10. co-occurrence as alias evidence. 11. pinyin match as merge evidence. 12. importing unclear-license Chinese KG dumps. 13. starting with Spark/Zingg/big cluster (PG trigram + pgvector suffices at 10^4-10^6).

## 14. Production v1 definition (report final line)
PostgreSQL as sole identity source -> NFKC/OpenCC/company-name structural parse -> verified-alias exact recall + pg_trgm + BGE/pgvector parallel candidates -> type-specific hard veto -> calibrated lightweight feature matcher -> BGE reranker gray-zone only -> human review -> minimal LLM assist -> event-sourced merge/alias/resolution history.

## Addendum 2026-09-01: v2 projects-panorama report archived
The supplementary wide-enumeration research (25 projects, 6 categories, framework merge-code locations, authority anchors) is archived at `.planning/RESEARCH-NORMALIZATION-PROJECTS-PANORAMA-2026-09-01.md`. It confirms the §14 production-v1 definition and adds: 25-project inventory, Splink/dedupe/LightRAG/cognee/RapidFuzz top-5 copy list, USCC hard-evidence policy, alias-provenance schema, framework identity anti-patterns (name-derived IDs).
