# V2.0 Milestone — Two Planning Gaps Supplement (Handoff Only)

> **Status: SUPPLEMENTARY / NON-AUTHORITATIVE**  
> **Drafted: 2026-07-12**  
> **Scope: Handoff supplement only — no code, no migration, no commit.**  
> **Target reader: Next Claude session responsible for integrating two confirmed gaps into the v2.0 plan.**

This document is a standalone handoff supplement to `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` and the three authority upstreams listed in that file's §0. It addresses **two planning gaps** identified during the v2.0 pre-execution planning review. These gaps were **confirmed as present** but deliberately left out of scope during the initial milestone definition to keep Phase 14-19 boundaries tight. This supplement does **not** authorize implementation; it provides insertion points, scope/non-goals, interface/contract requirements, acceptance criteria, decision gates, rollback/fallback paths, and dependency/order constraints so another session can integrate them cleanly.

---

## 1. Authority Chain and Relationship to Existing Plans

### 1.1 Upstream Authority (Priority Order)

When this supplement conflicts with any of the following, **the upstream authority wins**. The order is strict:

1. `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` (execution handoff, D1-D8 + stages A-F + T1-T9)
2. `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` (architecture master plan)
3. `.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` (T1-T9 ratified technical decisions)
4. `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` (milestone definition: R-OKF-01..08, phases 14-19 mapping, flows F1-F6)
5. `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` (Chinese entity/coreference upgrade roadmap, WS0-WS4)
6. This document (supplement only)

### 1.2 What This Document Is

- A **planning-only** handoff that names exact planned-document insertion points in the existing v2.0 phase structure.
- A declaration of **scope and non-goals** for each gap, with interfaces/data contracts/acceptance criteria sufficient for another session to write detailed wave plans.
- A statement of **dependencies and ordering** relative to Phases 14-19, plus rollback/fallback paths if a gate fails.

### 1.3 What This Document Is NOT

- It does **not** authorize code changes, database migrations, schema additions, or new file creation in `llamaindex_runtime/`, `scripts/`, `tests/`, or `verification/`.
- It does **not** override D4 evaluation freeze (see §3).
- It does **not** grant permission to commit, push, or modify git-tracked source outside `.planning/` artifacts.
- It does **not** retroactively alter Phase 14-19 boundaries defined in `v2.0-MILESTONE-OKF-MULTIROUTE.md` §3–§5.

---

## 2. The Two Confirmed Gaps

### Gap 1: Chinese Coreference Resolution and `coref_clusters` Ownership

**Source evidence:**
- `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` §2.1 table: `coref_clusters` marked "❌ 缺" (missing table); assigned to WS2 (Chinese coreference layer).
- `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` §WS2: "migration 017: `coref_clusters`; `relation_mentions(subject, predicate, object, qualifiers JSONB, ku_id)`".
- `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` §6.3: "`coref_clusters`、`relation_mentions`、关系 qualifiers 的完整查询逻辑 | C 后按需插入".
- `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` §7.2: Target schema lists `entity_merge_log` but omits `coref_clusters` and `relation_mentions`.

**Current ownership in v2.0 plan:**
- Phase 16 (交接书阶段 C, raw corpus entity layer) covers entity extraction, alias/merge, `entity_mentions`, `node_entity_links` — but **does not** include `coref_clusters` or cross-sentence anaphora resolution rules.
- Phase 17 (交接书阶段 D, graph recall R3) consumes `node_entity_links` but assumes entity data already exists; it does not produce coreference clusters.

**Gap statement:**
There is **no dedicated sub-phase or wave within Phase 16** that explicitly owns Chinese coreference resolution (`coref_clusters` table, rule-based pronoun resolution, paragraph-center entity inheritance). The LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN assigns this to WS2, which maps to "C 后按需插入" in the handoff book, but "按需插入" is not a phase boundary — it is a deferral without a gate. This creates ambiguity about when and how coreference data enters the pipeline.

### Gap 2: Stage 6 Pilot / Productionization Ownership (Post-Phase 19)

**Source evidence:**
- `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` §3 WS4: "产出成本-质量-延迟 Pareto 表，决定试点（阶段6）范围。" — Stage 6 pilot is mentioned but not mapped to any GSD Phase.
- `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` §3: Phase mapping ends at Phase 19 (交接书阶段 F, evaluation & tuning). No Phase 20+ is defined.
- `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` §8 Non-goals: Does not mention pilot deployment, production rollout, or user-facing integration testing beyond evaluation metrics.

**Current ownership in v2.0 plan:**
- Phase 19 (交接书阶段 F) is the last defined phase. Its flow F6 is "固定查询集 → 四路/消融矩阵运行 → 人工判定 → 指标 vs 冻结阈值 → 权重/开关决策". This is an **evaluation** phase, not a **pilot deployment** or **production integration** phase.

**Gap statement:**
There is **no phase or boundary doc after Phase 19** that owns pilot deployment, production integration, user-facing A/B testing, or operational monitoring of the OKF SSOT + four-route retrieval system in a real user workflow. The LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN mentions "阶段6" (Stage 6 pilot) but does not map it to a GSD Phase number or define its entry gate.

---

## 3. D4 Evaluation Freeze Preservation

**D4 freeze status (from handoff book §6.3 / v2.0 milestone §6):**
> "质量评估、消融、热点权重重分配全部推迟到 F；此前不以图谱层解释/修复 Level 2 基线。"

**This supplement does NOT lift or modify D4 freeze.** Specifically:

- Neither Gap 1 nor Gap 2 authorizes changing fusion weights, enabling node summaries, adjusting hotspot parameters, or making Level 3/4 quality claims before Phase 19 closes.
- Coreference resolution (Gap 1) is a **data-production** concern (producing `coref_clusters` rows), not a **quality-tuning** concern. Its acceptance criteria are about data completeness and merge-log reversibility, not about hit_rate/top1/stability deltas.
- Stage 6 pilot (Gap 2) is a **deployment/integration** concern, not a **quality-tuning** concern. Its acceptance criteria are about operational readiness, user feedback loops, and rollback safety, not about metric thresholds.

**Any session working on these gaps must respect D4 freeze until Phase 18 closes and the user explicitly lifts it.**

---

## 4. Gap 1 Integration Plan: Chinese Coreference Resolution

### 4.1 Insertion Point

**Planned location:** Within Phase 16 (raw corpus entity layer), as a **new sub-phase or wave**:

- Option A (sub-phase): Create `.planning/phases/16-raw-corpus-entity-layer/16-04-PLAN.md` (if 16-01..16-03 exist at PLAN time) or renumber existing waves to insert a coreference wave.
- Option B (boundary extension): Amend `.planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md` to explicitly list coreference as in-scope for Phase 16, with its own entry/exit gates.

**Decision criterion:** If Phase 16 has not yet been planned to wave depth, use Option A (dedicated wave). If Phase 16 wave plans already exist, use Option B (boundary amendment) and defer detailed wave planning to the Phase 16 execution owner.

### 4.2 Scope

**In-scope:**
1. **Migration for `coref_clusters` table** (numbering continues from Phase 14 migrations; e.g., 018 or later depending on what Phase 14/16 already claimed):
   ```sql
   CREATE TABLE coref_clusters (
     cluster_id TEXT PRIMARY KEY,        -- deterministic hash or UUID
     entity_id TEXT REFERENCES entities(entity_id),
     cluster_type TEXT NOT NULL,         -- 'pronoun' | 'alias' | 'zero_anaphora'
     rule_source TEXT NOT NULL,          -- 'paragraph_center' | 'explicit_pronoun' | 'hanlp_model'
     confidence NUMERIC(5,4),            -- 0-1, threshold-gated
     span_id TEXT REFERENCES canonical_spans(span_id),
     char_start INTEGER,
     char_end INTEGER,
     mention_text TEXT,
     resolved_at TIMESTAMPTZ DEFAULT NOW(),
     reversible BOOLEAN DEFAULT TRUE
   );
   ```
2. **Rule-based coreference resolver module** in `llamaindex_runtime/entity/coref_resolver.py` (new file, pluggable interface):
   - Layer 1: Paragraph-center entity inheritance (default subject for subsequent sentences).
   - Layer 2: Explicit pronoun dictionary ("该X", "其", "上述", "主体", "本院", "本项目") + regex patterns.
   - Layer 3: HanLP coreference model (optional, low-confidence merges are logged but not applied automatically).
3. **`relation_mentions` table** (for relation-level qualifiers that OKF frontmatter already carries):
   ```sql
   CREATE TABLE relation_mentions (
     mention_id TEXT PRIMARY KEY,
     relation_key TEXT REFERENCES relations(relation_key),
     subject_entity_id TEXT REFERENCES entities(entity_id),
     predicate TEXT NOT NULL,
     object_entity_id TEXT REFERENCES entities(entity_id),
     qualifiers JSONB,                   -- negation, condition, direction, time
     ku_id TEXT,                         -- knowledge unit / span grouping
     confidence NUMERIC(5,4),
     extracted_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```
4. **Integration with entity extractor pipeline**: After entity extraction (jieba/HanLP), run coreference resolver; write `coref_clusters` rows; update `entity_mentions` if a mention is resolved to a different entity via coreference.
5. **Reversibility**: All automatic merges logged to `entity_merge_log` (already in Phase 14 migration 017); coreference-based merges must include `rule_source` and `confidence` for audit.

**Out-of-scope (non-goals for this gap):**
- LLM-based coreference resolution (violates D7 zero-token constraint).
- Cross-document coreference (Phase 16 is intra-document only; cross-doc is a later concern).
- Changing `evidence_links` or `chunk_entity_links` schema (coreference adds a parallel table, does not rewrite existing links).
- Quality tuning (do not measure hit_rate improvement from coreference until Phase 19; D4 freeze applies).

### 4.3 Interface / Data Contract

**Input contracts:**
- OKF parser output: `entity_mentions` rows (from Phase 14/16 entity extraction) with `span_id`, `char_start`, `char_end`, `mention_text`.
- OKF relation frontmatter: Already-parsed relation dicts with `type`, `target`, `negation`, `condition`, `direction`, `confidence`.

**Output contracts:**
- `coref_clusters` rows: One per resolved pronoun/anaphora instance, with `cluster_id` deterministically derived from `(doc_id, paragraph_id, rule_source, mention_text)`.
- `relation_mentions` rows: One per OKF relation frontmatter entry, carrying qualifiers as JSONB.
- No modification to `entities`, `relations`, or `entity_aliases` tables (coreference is additive).

**Pluggable interface:**
```python
class CorefResolver(Protocol):
    def resolve(self, mentions: list[EntityMention], context: dict) -> list[CorefCluster]:
        """Return coreference clusters for a batch of entity mentions."""
        ...
```
Default implementation: `RuleBasedCorefResolver` (dictionary + regex). Optional upgrade: `HanLPCorefResolver`.

### 4.4 Acceptance Criteria

1. **Schema**: Migration applies cleanly on fresh initdb and on existing 001-017 database; no naming conflict with Phase 14 migrations.
2. **Data**: For a fixture document with known pronouns (e.g., "该院" referring to "内蒙古自治区卫健委"), `coref_clusters` contains ≥1 row with correct `entity_id` linkage and `rule_source = 'explicit_pronoun'`.
3. **Reversibility**: Every auto-merge via coreference is logged to `entity_merge_log` with `prior_target`, `current_target`, `rule_source`, `confidence`; a rollback script can undo the merge.
4. **No silent drops**: Relation frontmatter qualifiers (negation/condition/direction) are written to `relation_mentions.qualifiers` JSONB, not silently discarded.
5. **Zero LLM tokens**: Default path uses no LLM calls; HanLP model is optional and gated by config.
6. **Test coverage**: Unit tests for resolver rules (pronoun dictionary, regex patterns, paragraph-center inheritance); integration test for end-to-end `mentions → coref_clusters` flow.

### 4.5 Decision Gates

| Gate ID | Condition | Action if Failed |
|---------|-----------|------------------|
| G-COREF-1 | Migration applies without conflict on target DB | Defer to DBA; do not proceed with resolver implementation |
| G-COREF-2 | Fixture document yields ≥1 `coref_clusters` row with correct linkage | Review rule dictionary; expand pronoun list or fix regex |
| G-COREF-3 | All auto-merges logged to `entity_merge_log` with required fields | Fix logging before enabling resolver in pipeline |
| G-COREF-4 | Zero LLM calls in default path (verified via mock/profiler) | Enforce config gate; disable HanLP fallback |

### 4.6 Rollback / Fallback

- **If G-COREF-2 fails repeatedly**: Disable coreference resolver in pipeline config; fall back to plain entity extraction without pronoun resolution. R3 recall will miss anaphora-linked entities, but this is acceptable until Phase 19 ablation decides whether coreference is worth the complexity.
- **If G-COREF-3 fails**: Block all auto-merges; require manual review for every coreference candidate (effectively turning resolver into a proposal-only tool).
- **Rollback script**: Provided with migration; deletes `coref_clusters` and `relation_mentions` rows for a given `doc_id` or `version_id`.

### 4.7 Dependencies / Ordering

- **Blocks:** None (coreference is additive; R3 fusion in Phase 17 can proceed without it, though R3 recall quality may be lower).
- **Blocked by:** Phase 14 migration 016 (`entity_mentions` table) and Phase 16 entity extractor interface (need `EntityMention` data type).
- **Parallel with:** Phase 16 entity extraction waves (can develop resolver in isolation, integrate after base extractor lands).

---

## 5. Gap 2 Integration Plan: Stage 6 Pilot / Productionization

### 5.1 Insertion Point

**Planned location:** After Phase 19 (交接书阶段 F), as **Phase 20** (or rename "Stage 6" to "Phase 20" for consistency with GSD numbering):

- Create `.planning/phases/20-stage-6-pilot-productionization/20-BOUNDARY.md` (boundary doc).
- When Phase 19 closes and user lifts D4 freeze, `/gsd-plan-phase` will expand this into wave plans (20-01..20-NN).

**Rationale:** The LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN mentions "阶段6" (Stage 6 pilot) but does not assign it a GSD Phase number. Mapping it to Phase 20 keeps the A-F → 14-19 mapping intact while giving Stage 6 its own phase identity.

### 5.2 Scope

**In-scope:**
1. **Pilot deployment environment**: Define a staging/prod-like environment where the full OKF SSOT + four-route retrieval system runs with real user queries (not just fixed eval sets).
2. **User-facing integration**: Wire the retrieval API (existing query endpoint) into a real user interface or agent workflow that exercises R1/R2a/R2b/R3 fusion in realistic scenarios.
3. **Operational monitoring**: Instrument latency, throughput, error rates, and resource usage (PostgreSQL query time, vector search cost, entity resolution overhead).
4. **Feedback loop**: Collect user judgments on retrieval quality (thumbs up/down, relevance labels) and feed them back into `retrieval_logs` or a new `user_feedback` table.
5. **A/B testing framework**: Allow toggling R3 on/off, adjusting fusion weights (within bounds set in Phase 19), and comparing variants side-by-side.
6. **Rollback safety**: Ensure pilot can fall back to pre-v2.0 retrieval (R1 + R2a/R2b only) if R3 causes unacceptable degradation.

**Out-of-scope (non-goals for this gap):**
- Changing core architecture (no new tables, no schema migrations beyond monitoring/feedback).
- Quality tuning (Phase 19 owns weight decisions; Phase 20 only observes and collects feedback).
- User training or documentation (pilot is for internal validation, not public launch).
- Performance optimization (observe but do not optimize; optimization comes after pilot data is collected).

### 5.3 Interface / Data Contract

**Input contracts:**
- Phase 19 output: Finalized fusion weights, R3 enable/disable switch, ablation results showing which route combinations are worth piloting.
- User queries: Natural language questions from real users (not curated eval sets).

**Output contracts:**
- Retrieval hits: Same `QueryHit` format as existing API, with added `route_labels` indicating which routes contributed (R1, R2a, R2b, R3).
- Feedback records: `(query_id, user_id, relevance_label, timestamp)` stored in `user_feedback` table or JSON files.
- Monitoring metrics: `(timestamp, latency_ms, db_query_time_ms, entity_resolution_ms, fusion_time_ms, total_tokens)` exported to a time-series store or log file.

**New components (if any):**
- `llamaindex_runtime/pilot/feedback_collector.py` (new module, optional): Store user feedback with provenance.
- `llamaindex_runtime/pilot/monitoring.py` (new module, optional): Wrap retrieval call with timing instrumentation.
- Config flags: `ENABLE_R3_PILOT` (bool), `PILOT_FUSION_WEIGHTS` (dict), `FEEDBACK_STORAGE_PATH` (str).

### 5.4 Acceptance Criteria

1. **Environment**: Pilot environment is provisioned with OKF bundle ingested, all migrations applied, and retrieval API reachable.
2. **Integration**: At least one real user workflow (CLI, web UI, or agent) can submit queries and receive fused retrieval results with R3 enabled.
3. **Monitoring**: Latency and resource usage metrics are captured for every pilot query; p50/p95/p99 latencies are computable.
4. **Feedback**: User feedback is stored with query provenance and is queryable for later analysis.
5. **Rollback**: Disabling `ENABLE_R3_PILOT` reverts to pre-v2.0 retrieval behavior with no code changes (feature flag only).
6. **Safety**: Pilot does not write to OKF `raw/` or modify entity/relation tables (read-only access to derived DB).

### 5.5 Decision Gates

| Gate ID | Condition | Action if Failed |
|---------|-----------|------------------|
| G-PILOT-1 | Pilot environment provisioned and reachable | Defer pilot start; troubleshoot infra |
| G-PILOT-2 | R3 toggle works (on/off produces different route labels in output) | Debug feature flag wiring |
| G-PILOT-3 | Feedback records are queryable and linked to original queries | Fix feedback storage schema |
| G-PILOT-4 | Rollback to pre-v2.0 retrieval succeeds within 5 minutes | Improve rollback automation before proceeding |

### 5.6 Rollback / Fallback

- **If G-PILOT-2 fails**: Disable R3 entirely; pilot runs with R1/R2a/R2b only. Collect baseline metrics for comparison once R3 is fixed.
- **If G-PILOT-4 fails**: Manual rollback procedure documented in `20-BOUNDARY.md`; involves reverting config flags and redeploying pre-v2.0 retrieval service.
- **Fallback position**: Pre-v2.0 retrieval (R1 + R2a/R2b) remains available throughout pilot; no data is lost if pilot is aborted.

### 5.7 Dependencies / Ordering

- **Blocks:** None (pilot is observational; does not block further development).
- **Blocked by:** Phase 19 closure (must have finalized weights and R3 enablement decision); D4 freeze lift (user must approve moving from evaluation to pilot).
- **Parallel with:** None (Phase 20 is sequential after Phase 19).

---

## 6. Summary of Insertion Points and Artifacts

| Gap | Insertion Point | New Artifact(s) | Modified Artifact(s) |
|-----|----------------|-----------------|----------------------|
| Gap 1 (Coreference) | Phase 16, as new wave or boundary extension | `16-04-PLAN.md` (or amend `16-BOUNDARY.md`), migration SQL, `coref_resolver.py`, tests | None (additive only) |
| Gap 2 (Pilot) | After Phase 19, as Phase 20 | `20-BOUNDARY.md`, wave plans (20-01..), optional `pilot/` modules | None (additive only) |

---

## 7. Checklist for Next Session

Before integrating these gaps into the plan, verify:

- [ ] Read all five upstream authority docs (§1.1 priority order).
- [ ] Confirm Phase 14-19 boundary docs exist and are consistent with this supplement.
- [ ] Check if Phase 16 wave plans already exist; if yes, amend boundary instead of adding a wave.
- [ ] Confirm D4 freeze is still active (user has not lifted it).
- [ ] Verify migration numbering (Phase 14 may have claimed 015-017; adjust Gap 1 migration numbers accordingly).
- [ ] Ensure no existing code implements `coref_clusters` or `relation_mentions` (search `llamaindex_runtime/` for these names).
- [ ] Do NOT commit, push, or modify any source file outside `.planning/` based on this supplement alone.
- [ ] Wait for explicit user approval before creating Phase 20 or executing any Gap 1 migration.

---

## 8. Source Evidence List

The following documents were read and analyzed to identify these gaps:

1. `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md` — Milestone definition, phase mapping, requirements R-OKF-01..08, flows F1-F6, non-goals.
2. `.planning/OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` — Execution handoff, D1-D8 decisions, T1-T9 open questions, §6.3 missing implementations list (explicitly names `coref_clusters`).
3. `.planning/UNIFIED-MULTIROUTE-OKF-PLAN.md` — Architecture master plan (referenced but not deeply analyzed in this supplement).
4. `.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` — T1-T9 ratified technical decisions (referenced for migration numbering and schema constraints).
5. `.planning/LOW-TOKEN-GRAPHRAG-UPGRADE-PLAN.md` — Chinese entity/coreference upgrade roadmap; WS0-WS4 work streams; §2.1 table (missing `coref_clusters`); §WS2 (coreference rules and migration 017); §WS4 (mentions "阶段6" pilot).
6. `.planning/ROADMAP.md` — Phase 14-19 registration under "Milestone v2.0 (PLANNED — DO NOT EXECUTE)"; confirms Phase 19 is last defined phase.
7. `.planning/STATE.md` — Project state; confirms Phase 13 CLOSED, Phase 14 PLANNED, D4 freeze active.

No code files were read or modified. No database schemas were created. No tests were written. This is a planning-only handoff document.
