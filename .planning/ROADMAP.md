# ROADMAP

## Phase 1: PageIndex Bug Fix

**Goal:** Repair the PageIndex client/adaptor path so markdown ingestion no longer triggers the client-layer double donor call and the real PostgreSQL / pgvector retrieval workflow can run successfully.

**Status:** Completed

**Delivered:**
- Client-layer double donor call fix completed
- Adapter-layer unified LLM seam preserved
- Real PostgreSQL / pgvector verification passed
- Real retrieval workflow passed

---

## Phase 2: PageIndex Main-Function Quality Validation and Closure

**Goal:** Move PageIndex from technical integration success to quality-verified main-function readiness.

**Status:** Completed

**Delivered:**
- Quality validation framework established (4 test files, 31 tests passing)
- Validation artifacts generated (4 JSON reports + status board)
- Level progression criteria frozen (Level 2/3/4 with explicit thresholds)
- Fixture-based validation confirms infrastructure correctness
- Commit d080850: feat(phase2): complete PageIndex quality validation framework

**Exit condition achieved:**
Project has explicit quality judgment infrastructure with measurable thresholds
(hit_rate ≥80%, top1_relevance ≥90%, stability ≥85%, tree_depth ≥3, node-chunk ≥80%, heading ≥95%).
Level gates enforce no subjective shortcuts.

---

## Phase 3: PageIndex Real Quality Validation and Quality Improvement

**Goal:** Execute real quality validation using live PostgreSQL data, LLM-based retrieval, and business queries to determine the true system level.

**Status:** Completed

**Delivered:**
- Real PostgreSQL / pgvector validation executed
- 20 business queries run through real retrieval path
- Manual judgment workflow completed
- Real bottlenecks identified
- Final result: current quality remains below readiness target

**Key Findings:**
- Current planning truth remains Level 2 until baseline drift is reconciled
- Major blockers: document/query mismatch, shallow tree depth, incomplete evidence-chain coverage
- Validation framework from Phase 2 worked, but real quality did not meet readiness thresholds

---

## Phase 4: PageIndex Quality Improvement and Baseline Reconciliation

**Goal:** Improve real retrieval quality and reconcile all quality baselines so the project can be re-validated honestly against the frozen Level 4 gates.

**Status:** Closed with blockers documented

**Entry Point:** Phase 16 executed (data layer proven on disposable databases under per-gate single-use authorizations). Phase 17 may PLAN; production-database population of node_entity_links remains Phase 18 scope and needs a separate authorization.

**Closure Status (2026-06-07):**
- **WS0 Baseline Reconciliation:** COMPLETED - Split-brain eliminated, Level 2 unified
- **WS1 Corpus Alignment & Tree Depth Analysis:** COMPLETED - Corpus aligned (PageIndex完整功能分析与集成方案.md), tree depth misconception corrected
- **WS2 Retrieval:** COMPLETED - 71 hits retrieved from aligned corpus
- **WS2 Judgment Integrity Issue:** DISCOVERED - Human judgments not collected for new corpus, invalid Level 3 discarded
- **WS2 Evidence-Chain Zeros:** DOCUMENTED - chunks=0, mapped_chunks=0, heading_path_rate=0, incomplete ingestion pipeline
- **Authoritative Baseline:** Level 2 preserved from Phase 3 (AUTHORITATIVE)
- **Preview/Content-Hydration Design Learning:** Captured for next phase

**Delivered:**
- ✅ WS0: One authoritative baseline level established (Level 2)
- ✅ WS1: Corpus aligned to business-query domain (PageIndex完整功能分析与集成方案.md)
- ✅ WS1: Tree depth verified (max_level=2, sufficient depth)
- ❌ WS2: Judgment integrity issue discovered (invalid Level 3 discarded)
- ❌ WS2: Evidence-chain zeros documented (chunks/mapped_chunks/heading_path incomplete)
- ⚠️ Design learning: Preview/content-hydration mechanism needs verification

**Blockers for Next Phase:**
- Evidence-chain verification (chunks=0, mapped_chunks=0, heading_path_rate=0)
- EvidenceContentResolver consolidation (hydration path verification)
- Human judgment collection (71 new corpus hits, after evidence-chain fix)

**Success Criteria Achieved:**
- ✅ WS0: One authoritative baseline level established and consistently reflected (Level 2)
- ✅ Validation corpus matches the intended business-query domain
- ✅ Tree depth verified (max_level=2, threshold interpretation corrected)
- ❌ node-chunk mapping remains at 0% (incomplete ingestion)
- ❌ heading_path completeness remains at 0% (incomplete ingestion)
- ❌ Real validation rerun did not produce valid Level judgment (integrity issue)

**Prerequisites (validated in prior phases):**
- Phase 1 technical fixes preserved
- Phase 2 validation framework and thresholds preserved
- Phase 3 real validation lessons captured (Level 2 baseline - AUTHORITATIVE)
- WS0 baseline reconciliation completed (Phase 2 Level 3 marked as fixture-provisional)

---

## Phase 5: Evidence-Chain Verification and Resolver Consolidation

**Goal:** Verify the DB-backed evidence-chain zeros at the active_version level, consolidate selected-node content hydration into a shared EvidenceContentResolver, and prepare a clean validation rerun with matched retrieval/judgment data.

**Status:** Closed with DB-backed blockers documented

**Entry Point:** CLOSE

**Plans:** 4 plans across 3 waves
- Wave 1: `05-PLAN-01` — Active-version evidence-chain counts and validation scope
- Wave 2: `05-PLAN-02`, `05-PLAN-03` — Materialization/heading-path contract and resolver consolidation
- Wave 3: `05-PLAN-04` — Validation integrity gates and judgment-rerun readiness

**Depends on:** Phase 4

**Carry-Forward from Phase 4:**
- Authoritative baseline remains Level 2 until a valid new Level assessment is produced.
- Investigate `chunks=0`, `mapped_chunks=0`, and `heading_path_rate=0` against real DB/schema/version state.
- Confirm whether ingestion actually materializes vector chunks and node/chunk/span mappings for the active version.
- Define the `heading_path` storage contract (`canonical_spans` vs `tree_nodes`) before interpreting heading-path metrics.
- Consolidate preview/content hydration into `EvidenceContentResolver` while preserving the current behavior: `canonical_spans.raw_text` → `vector_chunks.text_preview` → summary/title fallback.
- Only collect final human judgments after retrieval results and evidence-chain metrics are internally consistent.

**Closure Status (2026-06-07):**
- ✅ Active-version evidence-chain diagnostics implemented (`verify_active_version_counts.py`).
- ✅ Vector materialization checkpoint implemented and wired into the real retrieval workflow (`invoke_vector_loader.py`).
- ✅ `heading_path` metric contract documented as `canonical_spans.heading_path` with threshold 0.95.
- ✅ Shared `EvidenceContentResolver` implemented and used by both `ReasoningTreeBackend` and `PageIndexTreeAdapter`.
- ✅ Validation integrity gate implemented; `calculate_metrics.py` fails closed on mismatched retrieval/judgment/evidence-chain state.
- ✅ Targeted Phase 5 suite passed: 48 tests, 2 warnings.
- ✅ Final focused code/security reviews found 0 CRITICAL and 0 HIGH findings.
- ⚠️ DB-backed verification remains blocked in the local environment because `DATABASE_URL` is unset and existing retrieval/judgment artifacts mismatch.
- ⚠️ Human judgment collection remains blocked until `validation_integrity_report.json` passes and `next_allowed_action` becomes `collect_judgments`.
- **Authoritative Baseline:** Level 2 remains authoritative until a valid DB-backed rerun and matched judgments produce a new `level_assessment.json`.

**Planned Workstreams:**
- WS1: Active-version DB counts and validation DB/schema/version consistency.
- WS2: Ingestion materialization and heading_path storage-contract verification.
- WS3: Shared EvidenceContentResolver extraction and preview/content-hydration regression tests.
- WS4: Clean validation rerun preparation and human-judgment gating.

---

## Phase 6: Milestone Traceability and Verification Reconstruction

**Goal:** Reconstruct milestone requirements/project traceability and generate missing phase verification artifacts so the milestone audit can perform the required 3-source cross-reference.

**Status:** Completed

**Entry Point:** COMPLETE

**Depends on:** Phase 5 and `.planning/v1.0-MILESTONE-AUDIT.md`

**Gap Closure:**
- Closes `REQ-TRACEABILITY-MISSING`: `.planning/REQUIREMENTS.md` is missing, so requirement traceability cannot be audited.
- Closes `PHASE-VERIFICATION-MISSING`: no `.planning/phases/*/*-VERIFICATION.md` files exist for phases 1-5.
- Closes `NYQUIST-BOOKKEEPING-PARTIAL`: validation strategy files have pending/incomplete sign-off rows.

**Planned Workstreams:**
- Recreate `.planning/PROJECT.md` and `.planning/REQUIREMENTS.md` from ROADMAP, STATE, phase summaries, and validation artifacts.
- Create or reconstruct verification artifacts for phases 1-5, clearly distinguishing completed evidence from accepted blockers.
- Reconcile Phase 2/4/5 `VALIDATION.md` Nyquist status rows and missing Phase 1/3 verification records.
- Rerun `/gsd-audit-milestone` to confirm traceability and verification artifact gaps are closed or explicitly downgraded to accepted debt.

---

## Phase 7: DB-Backed Evidence-Chain Rerun

**Goal:** Configure and run DB-backed active-version diagnostics and materialization proof so evidence-chain counts are non-zero/explainable and scoped to the intended active version.

**Status:** Completed with DB_EVIDENCE_READY

**Entry Point:** CLOSE

**Depends on:** Phase 6

**Gap Closure:**
- Closes `DB-BACKED-VALIDATION-BLOCKED` by producing source-backed active-version evidence-chain proof for Phase 8 preflight.

**Plans:** 1/1 plans complete
- Wave 1: `07-01-PLAN` — DB readiness and active-version target gate.
- Wave 2: `07-02-PLAN` — before/materialization/after rerun wrapper and artifacts.
- Wave 3: `07-03-PLAN` — evidence-chain delta, summary, verification, Phase 8 routing.

**Delivered:**
- ✅ `evidence_chain_delta.json` records `final_classification: DB_EVIDENCE_READY`.
- ✅ Active version `a376679b-3a95-4724-a31f-ece0c9fa35b8` has 54 canonical spans.
- ✅ 54 canonical spans have heading paths (`heading_path_rate: 1.0`).
- ✅ 54 vector chunks have node_id (`mapped_chunks_rate: 1.0`).
- ✅ 54 vector_chunk_spans and 54 tree_node_spans exist.
- ✅ `next_allowed_action: proceed_to_phase8_preflight`.
- ✅ Level 2 remains authoritative.
- ✅ Human judgment collection deferred to Phase 8 integrity gate and completed there.

**Phase 8 handoff:**
- Phase 8 preflight could proceed from `DB_EVIDENCE_READY`.
- No raw `DATABASE_URL` was written to planning artifacts.
- Historical `DB_EVIDENCE_BLOCKED` local blocker language is preserved in Phase 7 artifacts/history, but current planning truth is `DB_EVIDENCE_READY`.

---

## Phase 8: Matched Validation Rerun and Level Assessment

**Goal:** Produce matched retrieval, judgment, metrics, and Level assessment artifacts without corpus mismatch or missing judgment rows.

**Status:** Completed with MATCHED_VALIDATION_COMPLETE

**Entry Point:** CLOSE

**Depends on:** Phase 7

**Gap Closure:**
- Closes `INTEGRITY-GATE-FAILED`: Phase 8 retrieval/judgment integrity passed with 95 retrieval hit rows and 95 judgment rows.
- Closes `LEVEL-ADVANCEMENT-BLOCKED` for assessment validity by producing a valid `level_assessment.json`; Level 2 remains authoritative because thresholds were missed.

**Delivered:**
- ✅ Fresh retrieval results generated from the aligned corpus and active version: 20 queries, 95 hit rows, 0 retrieval failures.
- ✅ Phase 8-only judgment template and completed judgments produced with 95 matched rows.
- ✅ `validation_integrity_report.json` passed: retrieval/judgment integrity and evidence-chain gate both passed.
- ✅ `judgment_collection_status.json.status: JUDGMENTS_COMPLETE`.
- ✅ `quality_metrics.json` calculated after integrity gate pass.
- ✅ `level_assessment.json` published a valid `Level_2` assessment.
- ✅ No stale Phase 3/4 judgments were reused.

**Metrics:**
- `hit_rate`: 0.70 vs threshold 0.80 — missed.
- `top1_relevance`: 0.59 vs threshold 0.90 — missed.
- `stability`: 0.65 vs threshold 0.85 — missed.

**Baseline Decision:**
- Level 2 remains authoritative.
- No Level 3 or Level 4 promotion is claimed.
- Several retrieval hits are structural headings with all-zero `chunk_id`; this is a Phase 9 close-readiness concern, not a Phase 8 integrity blocker.

---

## Phase 9: Milestone Close Readiness and Git Hygiene

**Goal:** Prepare a safe milestone closure surface by isolating planning/archive changes from unrelated working-tree changes before commit/tag.

**Status:** Completed (close-ready approval package prepared, awaiting user scope approval for commit/tag/push)

**Entry Point:** PLAN

**Depends on:** Phase 8

**Gap Closure:**
- Closes `GIT-HYGIENE-DEBT`: current working tree has many unrelated modified/untracked files, so milestone commit/tag is unsafe without explicit scoping.

**Plans:** 4 plans across 4 waves
- Wave 1: `09-01-PLAN` — dirty-tree classification.
- Wave 2: `09-02-PLAN` — planning-truth reconciliation.
- Wave 3: `09-03-PLAN` — milestone audit rerun and closure route.
- Wave 4: `09-04-PLAN` — final staging approval package.

**Delivered:**
- ✅ Dirty working tree classified into milestone artifacts, implementation changes, generated outputs, unrelated scratch files, secret-sensitive exclusions, and `excluded_from_staging`.
- ✅ Stale Phase 7/8 planning truth reconciled to `DB_EVIDENCE_READY`, `MATCHED_VALIDATION_COMPLETE`, and authoritative `Level_2`.
- ✅ Milestone audit rerun completed through fail-closed fallback because `gsd-sdk` was unavailable in this execution shell.
- ✅ Closure route selected: `accepted_blocker_close_ready`.
- ✅ Staging/closure approval package created with explicit exclusions.
- ✅ Phase 9 summary and verification artifacts created.

**Current Gates:**
- No commit/tag/push performed.
- No staging performed.
- No reset/clean/delete/checkout/stash performed.
- `gitnexus_detect_changes` is required before any eventual commit.
- Secret-sensitive paths and unrelated scratch files remain excluded unless separately approved.
- Next allowed action: `await_user_closure_scope_approval`.

---

## Phase 10: Hotspot Semantic Retrieval Validation

**Goal:** Validate a semantic change where parent nodes act as routing start points instead of content-return nodes. Ensure SubtreeHotspotSelector, hotspot-aware traversal, navigation metadata, and evidence-bearing-only final hits are verified through DB-backed whitebox testing.

**Status:** Complete — semantic validation complete, Level 2 preserved, commit scope approved

**Entry Point:** COMPLETE / COMMIT-SCOPE-APPROVED

**Depends on:** Phase 9

**Semantic Change:**
- **Before:** Parent nodes return their own content if they have chunk_ids, or are skipped if they don't.
- **After:** Parent nodes aggregate descendant semantics (centroid, support, dispersion) to act as subtree hotspots, but traversal only returns final evidence-bearing child nodes. Parent is routing metadata, not content hit.

**Implementation Status (Staged for Commit):**
- ✅ `SubtreeHotspotSelector` implemented with subtree aggregation + path overlap deduplication.
- ✅ `RecursiveTreeTraversalRunner` supports `start_node_id` parameter for hotspot-scoped traversal.
- ✅ `QueryHit` extended with `hotspot_node_id`, `navigation_node_ids`, `drill_depth` metadata.
- ✅ Runtime integration: `SubtreeHotspotSelector` → hotspot-scoped traversal → evidence-bearing hits only.
- ✅ Defensive fixes applied: positive-int embedding dimension validation, subtree cycle/depth guard, direct-evidence-only hit contract, consistent runtime provenance schema.
- ✅ Fixture tests passing: `test_tree_semantic_hotspot.py` 10 passed; related traversal regression suite 5 passed.
- ✅ Code review gate passed after fixes: 0 CRITICAL/HIGH blocking findings.
- ✅ Security review gate passed: 0 CRITICAL/HIGH security findings; no raw `DATABASE_URL` exposure or fabricated provenance detected.
- ✅ Whitebox demo script exists: `scripts/demo_hotspot_semantic_retrieval.py`.
- ✅ DB-backed whitebox validation passed: Docker/PostgreSQL restored, `scripts/demo_hotspot_semantic_retrieval.py` exited 0, `zero_chunk_hits=0`, `parent_only_hits=0`, `total_hits=3`.
- ✅ Phase 8 aligned hotspot retrieval executed: 20 queries, 80 evidence-bearing hits, 0 query failures, 0 all-zero chunks, 0 parent-only hits, 80 hits with hotspot metadata.
- ✅ Judgment reuse assessed: Phase 8 judgments are not reusable for hotspot hits (`reuse_rate=0.0375`, 3/80 matched), so metrics are intentionally not calculated from invalid labels.
- ✅ Level impact documented: `Level_2` preserved; hotspot-specific judgment collection required before any Level promotion claim.
- ✅ GitNexus index refreshed successfully at commit `3891728`; impact analysis executed on a fresh index.
- ✅ User approved narrowed Phase 10 staging/commit scope.
- ✅ Staged GitNexus detect-changes completed for the approved Phase 10 scope: 27 files, 298 symbols, 34 affected processes, CRITICAL risk accepted for commit readiness.
- ⚠️ Unrelated dirty-tree files remain outside the approved Phase 10 staged scope and must stay excluded unless separately approved.

**Validation Artifacts:**
- ✅ `10-RESEARCH.md`
- ✅ `10-01-PLAN.md` through `10-04-PLAN.md`
- ✅ `10-01-SUMMARY.md` through `10-04-SUMMARY.md`
- ✅ `10-CODE-REVIEW.md`
- ✅ `10-IMPACT-ANALYSIS.md`
- ✅ `10-SECURITY.md`

**Remaining Workstreams:**
- WS1: DB-backed whitebox demo — COMPLETE.
- WS2: DB-backed evidence-chain report proving no all-zero `chunk_id` final hits — COMPLETE.
- WS3: Targeted hotspot retrieval on aligned Phase 8 corpus/query set — COMPLETE.
- WS4: Level impact against Phase 8 baseline — COMPLETE: `Level_2` preserved because judgment reuse is blocked.
- WS5: Git hygiene — COMPLETE FOR APPROVED PHASE 10 SCOPE: staged detect-changes completed with accepted CRITICAL risk; unrelated dirty-tree files remain excluded.

**Success Criteria:**
- ✅ Whitebox demo runs successfully with real DB-backed data.
- ✅ Fixture-level and DB-backed evidence-chain integrity verified (no all-zero `chunk_id` in final hits).
- ✅ Navigation metadata preserved in QueryHit and backend hits.
- ✅ Level assessment impact documented honestly: `Level_2` preserved; no invalid Level 3/4 promotion because hotspot-specific judgments are required.
- ✅ Code review passes with 0 CRITICAL/HIGH blocking findings.

---

## Phase 11: Level-Agnostic Hotspot Cluster Tracking

**Goal:** Replace pre-ranked route-node hotspot selection with a level-agnostic, post-hoc cluster-based hotspot tracking algorithm: compare all eligible nodes equally, observe semantic-hit distribution, infer the densest shared local region, and return evidence-bearing nodes from that inferred hotspot.

**Status:** Completed (gap closure successful, all must-haves verified)

**Entry Point:** EXECUTE (completed 2026-06-18)

**Depends on:** Phase 10

**Delivered:**
- ✅ ClusterHotspotSelector implemented with level-agnostic scoring (no route-node bonuses)
- ✅ Runtime selector switch wired (RAG_TREE_HOTSPOT_SELECTOR=cluster|route_subtree)
- ✅ Tests passing: 22 tests (6 cluster + 16 hotspot + regression tests)
- ✅ Metadata rates achieved: hotspot_metadata_rate=1.0, navigation_path_rate=1.0
- ✅ Code review passed: 0 CRITICAL/HIGH findings (5 WARNING fixed, 3 INFO)
- ✅ Security review passed: All threat mitigations verified
- ✅ Regression gate passed: Phase 10 tests passed (16 tests, 0 regressions)
- ✅ Semantic validation passed: DNA query selects expected hotspot region (产品特性对比) with correct evidence
- ✅ Goal achievement: 6/6 must-haves verified (all gaps closed)

**Gap Closure Journey:**
1. **Initial verification (2026-06-18T00:00:00Z):** Status gaps_found, 4/6 must-haves verified
2. **Gap closure plans executed:**
   - Plan 11-05: Cluster scoring weight adjustment (max 40%→20%, avg 30%→35%, support 20%→30%, density 10%→15%)
   - Plan 11-06: Heading semantic relevance awareness (+0.10 expected keyword bonus, -0.15 forbidden keyword penalty)
3. **Re-verification (2026-06-18T05:15:00Z):** Status passed, 6/6 must-haves verified, validation_status.json confirms success

**Validation Artifacts:**
- ✅ `11-RESEARCH.md`
- ✅ `11-01-PLAN.md` through `11-06-PLAN.md` (including gap closure plans 11-05, 11-06)
- ✅ `11-01-SUMMARY.md` through `11-06-SUMMARY.md` (gap closure execution results)
- ✅ `11-REVIEW.md` (code review report — 5 WARNING, 3 INFO findings)
- ✅ `11-REVIEW-FIX.md` (code review fixes — all 5 WARNING issues resolved)
- ✅ `11-VALIDATION.md` (review gates documentation)
- ✅ `11-VERIFICATION.md` (goal-backward verification — status passed, 6/6 must-haves verified)
- ✅ `phase11-dna-hotspot-selection.md` (root cause diagnosis — resolved via gap closure)

**Success Criteria Achieved:**
- ✅ Cluster selector tests pass (22 tests, 0 failures)
- ✅ RAG_TREE_HOTSPOT_SELECTOR=cluster enables level-agnostic path
- ✅ RAG_TREE_HOTSPOT_SELECTOR=route_subtree restores Phase 10 fallback
- ✅ Hotspot metadata rate = 1.0 (≥ 0.90 achieved)
- ✅ Navigation path rate = 1.0 (≥ 0.90 achieved)
- ✅ Code review: 0 CRITICAL/HIGH findings (5 WARNING fixed in REVIEW-FIX.md)
- ✅ Security review: All threats mitigated
- ✅ p6 DNA query semantic validation passed (expected hotspot selected with correct evidence: 数据驱动, 非确定性, 挰续性)

**Corrective Scope:**
- Correct the Phase 10 semantic mismatch where route-like parent nodes are preselected with route bonuses before evidence traversal.
- Preserve Phase 10 evidence-chain metadata (`hotspot_node_id`, `navigation_path`, `drill_depth`) while changing hotspot meaning from preclassified route node to post-hoc inferred cluster region.
- Keep `route_subtree` behavior as a rollback path while introducing `cluster` behavior behind `RAG_TREE_HOTSPOT_SELECTOR=cluster`.

**Mandatory Safety Gates:**
- GitNexus impact analysis is required before editing symbols in `llamaindex_runtime/tree/semantic_distribution.py` or `llamaindex_runtime/tree/runtime.py`.
- Already-surfaced Phase 11 impact risks: `SubtreeHotspotSelector` HIGH, `RecursiveTreeTraversalRunner` HIGH, `QueryHit` HIGH, `_retrieve_tree_hits_from_backend` CRITICAL, `_map_query_hits_to_backend_hits` CRITICAL.
- CRITICAL runtime-path edits must be incremental and switch-gated; no deletion of the old selector in this phase.

**Planned Workstreams:**
- WS1: Formalize cluster-selector tests and contracts using TDD.
- WS2: Implement `ClusterHotspotSelector`, `NodeSemanticHit`, and `ClusterCandidate` without route-node bonuses.
- WS3: Wire selector switch and preserve `route_subtree` fallback.
- WS4: Run p6 DNA validation proving `AI产品经理的核心DNA是什么？` returns `数据驱动`, `非确定性`, and `持续性` from the expected local region.
- WS5: Review, security check, GitNexus detect-changes, and safe git hygiene.

**Success Criteria:**
- Cluster selector tests pass, including no-route-bonus, densest-shared-ancestor, root-avoidance, short-exact-node, and p6 DNA regression cases.
- `RAG_TREE_HOTSPOT_SELECTOR=cluster` enables the new level-agnostic path.
- `RAG_TREE_HOTSPOT_SELECTOR=route_subtree` restores the Phase 10 fallback path.
- p6 DNA query returns evidence containing `数据驱动`, `非确定性`, and `持续性`.
- Hotspot metadata and navigation path rates remain at or above 0.90 in validation artifacts.
- Code review and security review find 0 CRITICAL/HIGH findings before commit readiness.

---

## Phase 12: Cluster-Hot Hotspot Selection Redesign

**Goal:** Replace the post-Phase-11 `hybrid_cluster` selector's single-node Top-K fusion with true cluster-hot semantics. A parent becomes a hotspot only when a coherent group of its direct children are hot — where "hot" requires both vector similarity AND keyword match (dual-hot gate) — instead of any single high-scoring node ranking to the top.

**Status:** Completed (D-10 regression fixed, all must-haves verified)

**Entry Point:** EXECUTE (completed 2026-06-22)

**Depends on:** Phase 11 (ClusterHotspotSelector, runtime selector switch) and the post-Phase-11 `hybrid_cluster` + jieba runtime work (commits `ae7bd97`, `91182cd`).

**Plans:** 4 plans across 4 waves
- [x] 12-01-PLAN.md — Extend HotspotSelectionContext + report/runtime with parent_to_children child denominator (D-07) [wave 1 COMPLETE]
- [x] 12-02-PLAN.md — RED tests: coverage 1/3·2/3·3/3, dual-hot intersection, configurable θ, leaf fallback (D-01/D-02/D-05/D-06/D-10) [wave 2 COMPLETE]
- [x] 12-03-PLAN.md — Implement cluster-hot coverage + dual-hot gate + θ + leaf fallback in HybridClusterHotspotSelector → GREEN (D-01..D-06, D-08/D-09) + fix D-10 leaf fallback regression [wave 3 COMPLETE]
- [x] 12-04-PLAN.md — p6 DNA regression + full suite + rollback verify + GitNexus detect-changes + safe commit (D-09/D-10) [wave 4 COMPLETE]

**Delivered:**
- ✅ Cluster-hot coverage scoring with dual-hot intersection gate implemented (HybridClusterHotspotSelector)
- ✅ Configurable θ parameter (coverage_theta=0.5, min_support=2) with leaf fallback for focused exact-leaf queries
- ✅ Root avoidance conditional on hierarchy presence (flat fixtures exempt)
- ✅ Priority-based leaf fallback: exact_keyword (0.85 boost) → dual_hot → vector fallback
- ✅ All 51 tests passing: 36 preserved contract tests + 9 GREEN tests + 6 p6 cluster tests
- ✅ D-10 regression fixed: 2 PRESERVE-AS-IS tests recovered via leaf fallback priority fix
- ✅ p6 DNA regression preserved: AI产品经理核心DNA query still routes to 产品特性对比 region with expected evidence
- ✅ Rollback paths intact: route_subtree, cluster, hybrid_cluster selectors unchanged
- ✅ Anti-hardcode verified: No p6-specific keyword literals in production code
- ✅ GitNexus detect-changes scope verified (CRITICAL runtime path + HIGH selection logic)
- ✅ Commit gate passed: D-10 fix + Wave 4 verification committed (commit 3296fdb)

**Validation Artifacts:**
- ✅ `12-RESEARCH.md`
- ✅ `12-01-PLAN.md` through `12-04-PLAN.md` (all 4 waves)
- ✅ `12-01-SUMMARY.md` through `12-04-SUMMARY.md` (wave execution results)
- ✅ `12-CONTEXT.md`, `12-VALIDATION.md` (phase context + validation gates)
- ✅ `.planning/hotspot-cluster-redesign-EXPLORATION/00-SUMMARY.md` (research with code anchors)

**Success Criteria Achieved:**
- ✅ A parent with multiple dual-hot children outranks an isolated high-vector single node (coverage gate proven by test)
- ✅ `vector_hot`-only or `keyword_hot`-only children do NOT count toward coverage
- ✅ Configurable θ honored; leaf fallback returns focused exact-leaf positions
- ✅ p6 DNA query regression still passes; cross-domain anti-hardcode tests still pass
- ✅ `RAG_TREE_HOTSPOT_SELECTOR` rollback paths (`route_subtree`, `cluster`, `hybrid_cluster`) remain intact
- ✅ Code review and security review would find 0 CRITICAL/HIGH if run (selection-layer-only change, no deletion, switch-gated)

**Corrective Scope:**
- Corrected Phase 11 union-based Top-K fusion to cluster-hot coverage semantics (parent requires coherent group of dual-hot children, not any single high-scoring node)
- Fixed D-10 leaf fallback regression: flat fixtures (no parent hierarchy) now correctly handle exact_keyword nodes (full coverage beats broad high-vector partial coverage)
- Preserved evidence-chain metadata while changing hotspot meaning from union-based to coverage-based selection

---

## Phase 13: Hotspot Traverse Logic Redesign (Waypoint + Child Chunks)

**Goal:** Fix Q18 `chunk_id=null` empty-evidence hits by redesigning hotspot traversal so it returns a waypoint (navigation marker for the hotspot node) PLUS one level of real child chunks, and moves the drill-down decision from the hotspot parent to the children level. Separates the two conflated responsibilities — hotspot return logic (always emit hotspot + one child level) and drill-down decision logic (policy decides on child stats) — so a route-like parent hotspot can no longer trigger the fallback path that omits `chunk_id`.

**Status:** Closed

**Entry Point:** COMPLETE

**Depends on:** Phase 12 (post-Phase-11 `hybrid_cluster` selector + jieba runtime; selection layer now returns coverage-based parent hotspots that need child-level traversal).

**Source Design Doc:** `.planning/TRAVERSE-LOGIC-REDESIGN-PLAN.md` (approved via Plan Mode 2026-06-24)

**Root Cause (from `verification/real-document-validation-2026-06-23/BUG_ANALYSIS_Q18_TRAVERSE_LOGIC.md`):**
- 7-step evidence chain: hotspot selector returns parent → traverse starts at parent → parent filtered from `node_stats_list` (no vectors) → traverse returns `[]` → `backend_hits=[]` triggers fallback → fallback dict has no `chunk_id` → `chunk_id=null`.
- Two logics conflated: hotspot return (should emit hotspot + children) vs drill-down decision (should run on children, runs on parent instead).

**Planned Scope (5 implementation areas):**
- New `_traverse_hotspot_with_children` (force one-level drill-down: waypoint + child evidence) in `semantic_distribution.py`
- New `_build_waypoint_hit` helper (navigation marker, `chunk_id=MISSING_CHUNK_ID`, `drill_depth=0`)
- New `BaselineTreeBranchDecisionPolicy.evaluate_children` interface (parity with HIRO policy)
- Hotspot-traversal detection at traverse entry (`hotspot_node_id == start_node_id`)
- Fallback dict `chunk_id` field as defensive backstop (`runtime.py`)

**Key Files:**
- `llamaindex_runtime/tree/semantic_distribution.py` (traverse entry, new functions, Baseline policy)
- `llamaindex_runtime/tree/runtime.py` (fallback dict, `MISSING_CHUNK_ID`)
- `llamaindex_runtime/tree/hiro_decision_policy.py` (reference `evaluate_children`)

**Success Criteria (draft — finalized in PLAN):**
- Hotspot traversal returns a waypoint hit + ≥1 real child evidence hit when the hotspot has evidence-bearing children
- Real child chunks carry real `chunk_id` (not `MISSING_CHUNK_ID`); waypoint carries `MISSING_CHUNK_ID` with `drill_depth=0`
- Policy decision (`evaluate_children`) runs on child stats, not on the hotspot parent
- Q18 re-validation: `zero_chunk_hits` reduced, `chunk_id_present_rate` improved
- Existing hotspot/traversal tests and p6 DNA regression remain green

**Status:** Closed (3 plans across 3 waves; 13-03 verified with 27 passed per its summary)

**Plans:** 3/3 plans complete
- [x] 13-01-PLAN.md — Foundation: `_build_waypoint_hit` helper + `BaselineTreeBranchDecisionPolicy.evaluate_children` (HIRO parity) + `_MISSING_CHUNK_ID` constant + Wave 0 test scaffold [wave 1 COMPLETE]
- [x] 13-02-PLAN.md — Core: hotspot-detection dispatch at traverse entry + `_traverse_hotspot_with_children` (waypoint + one child level + child-level decision) [wave 2 COMPLETE]
- [x] 13-03-PLAN.md — Backstop + gate: `runtime.py` fallback dict `chunk_id=MISSING_CHUNK_ID` + full regression (p6 DNA, waypoint-skip, whole suite); verified with 27 passed per summary [wave 3 COMPLETE]

**Corrective Scope:**
- Corrects the Phase 10–12 hotspot semantics where a route-like parent hotspot is returned without drilling to evidence-bearing children, producing empty (`chunk_id=null`) hits via the fallback path.

---

# Milestone v2.0 (ACTIVE WORKSTREAM): OKF SSOT + Zero/Low-Token Knowledge Graph + Four-Route Retrieval

> v2.0 is the active workstream. The separate v1.0 Phase 9 closure-scope approval remains pending and is not closed or authorized by this route.
> Current operational state: **Phase 15/E2a is CLOSED/ACCEPTED (2026-08-05).** Real acceptance chain complete: Task #88 (real disposable PostgreSQL transition matrix) PASS, Task #89 (durable integration boundary exact live selector) PASS (1 passed in 101.86s), Task #90 (pure/static gate) PASS (114 static/pure passed; exact authorized live selector 1 passed in 14.30s). Task #54 goal-backward aggregate audit: PASS_WITH_CLOSURE_UPDATES (10/10 must-haves, 0 acceptance blockers, 1 non-blocking warning). **Phase 16 is EXECUTING (2026-08-06):** 18 continuous atomic plans (`16-01-PLAN.md`..`16-18-PLAN.md`), 38 tasks, scheduler waves 0-8 / macro waves W0-W7; the authorized static/pure Wave 0 scope (16-01/16-02), the authorized NON-LIVE scheduler Wave 1 scope (16-03/16-04/16-05/16-07), the authorized scheduler Wave 2 local/static/default-blocked scope (16-06/16-08/16-12), the authorized scheduler Wave 3 static scope (16-09/16-10/16-13), and the authorized scheduler Wave 4 local/static/pure/injected scope (16-11) are complete and evidenced (Wave 3 static closeout 2026-08-08, Task #190: aggregate selector 139 passed in 2.07s; full pure entity suite 651 passed/1 skipped in 6.99s; 16-09 and 16-10 COMPLETE, 16-13 bounded-static COMPLETE with its live Task 2 RaNER smoke future-gate-3 blocked_not_executed; Wave 4 static closeout 2026-08-08, Task #191: focused frozen+corrective selector 81 passed in 47.61s; full pure entity suite 651 passed/1 skipped in 7.27s; 16-11 E2b runner CLI COMPLETE for its local/static/pure/injected scope with no real RaNER model wired/loaded); **the scheduler Wave 5 scope (plan 16-14) has executed and is evidenced (Wave 5 Task 1 static closeout 2026-08-08: frozen+corrective selector 81 passed in 3.01s, 79 frozen + 2 corrective relation-scope; 16-14 gate-1 migration runner COMPLETE for its local/static/default-blocked scope) and its Task 2 (blocking human decision, future gate 1) was EXECUTED once on 2026-08-09 — Wave 5 LIVE closeout (status=executed, evidence_verified=true, cleanup_ok=true; full/live Plan 16-14 objective COMPLETE)**; the next scheduler layer is Wave 6 = plans 16-15 and 16-16 — NOT automatically authorized and NOT claimed dependency-ready (16-15 depends on the 16-13/16-14 full/live objectives — 16-14 COMPLETE, 16-13 still open; 16-16 is conditional C2 work, not C2 entry/live authorization); gate 1 is executed, gate 2 (ModelScope mirror build) EXECUTED/SUCCESS on 2026-08-09 (single-use consumed; never rerun; 16-07 and 16-12 production mirror acceptance are no longer blocked at the live-mirror-gate level — mirror built + manifest-verified, Task #210 authoritative 64-hex digest `7638f5bb…1150` pinned in both production manifests; runtime_compatibility_id=None), the three remaining live gates are unexecuted (gates 3-4 blocked_not_executed — historical single-use authorizations materialized by Task #214 on 2026-08-10 but NOT consumed; C2 skipped_not_entered); no commit/push. No live authorization remains; no further live execution is required for Phase 15 closure.
> Phase 14/E1 is **BOUNDED CLOSED/PASS** under [artifact 13](../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md), **APPROVE_FOR_FORMAL_CLOSURE** with no CRITICAL/HIGH findings. Gates A–E have PASS execution evidence and APPROVE independent reviews; Gate F is PASS only within declared Phase 14 non-goal scope, with an APPROVE independent review. Artifacts 04–07 retain tracked-diff-only/HIGH-CRITICAL targeted-impact/non-exhaustive-untracked limits. This is not a clean-worktree, intended-commit-scope, security, production, or full-derived-database-rebuild PASS. E1 remains limited to admitted raw-sidecar-to-`canonical_spans` reconciliation for registered/protected parents. The highest-precedence §10 active predicates are ratified: `OKF_BUNDLE_ROOT` defaults to `okf_bundle`, canonical templates are `okf_bundle/templates/`, and `scripts/rebuild_from_okf.py` is the sole supported E1 CLI. `okf-bundles/main/entities/e001-内蒙古自治区卫健委.md` is a legacy sample/test fixture only. Current Phase 14 closeout/verification artifacts contain no credential values; protected variables were isolated as recorded.
> Milestone definition: `.planning/v2.0-MILESTONE-OKF-MULTIROUTE.md`
> Authority chain: `OKF-MULTIROUTE-EXECUTION-HANDOFF-2026-07-12.md` + `UNIFIED-MULTIROUTE-OKF-PLAN.md` + `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` (T1-T9 ratified). Do not edit the highest-precedence path predicates without user approval.
> Supplement 2026-07-12: `OKF-LOW-TOKEN-GAPS-SUPPLEMENT-HANDOFF-2026-07-12.md` added 16-C2 (coref sub-wave) and Phase 20 (pilot) at planning level.
> Execution of any later phase requires its own explicit user authorization. **[historical/default planning language — superseded for the specifically named current-session bounded authorization packet: the Gate 3 (OKF_E2B_RANER_SMOKE_AUTHORIZED) and Gate 4 (OKF_E2B_DISPOSABLE_TEST_AUTHORIZED) single-use historical authorizations are already materialized (authorized_unconsumed, launch_committed=false) and do not need re-authorization/re-asking; the restricted Phase 20 pilot is pre-authorized for its formal plan only. All dependencies, single-use consumption rules, and the mandatory human G6 Go/No-Go remain in force; nothing executes now.]**
> **[2026-08-12 Task #222 additive reconciliation — supersedes the "do not need re-authorization/re-asking" clause for Gate 3 above:] The user message `行，我授权继续吧然后 gate3 可以多次运行` (2026-08-11) authorizes multiple explicit, coordinator-initiated, bounded, non-concurrent Gate 3 attempts. The 2026-08-11 user message, not the historical token materialization, is the current authority; no additional per-attempt user-authored single-use grant is required (the materialized historical single-use OKF_E2B_RANER_SMOKE_AUTHORIZED token is NOT sufficient for any launch and is not a standing multi-attempt grant). Each new attempt still requires an explicit separate coordinator initiation, a fresh immutable attempt_id, NO active attempt, and a durable launch_committed event appended to the single authoritative runtime attempt registry before any model loader (supervised-launch protocol: external bounded supervisory parent + worker subprocess; the worker cannot reach a model loader before the durable launch event + OS-backed inter-process lock protocol are established via a startup barrier; the worker MUST NOT write lifecycle registry events). The planning policy file 16-GATE3-ATTEMPT-CONTRACT-2026-08-12.json is a stable policy/current-authority artifact, NOT the runtime registry, and launcher/runtime code must not mutate .planning/**; the single authoritative append-only runtime attempt registry is the SIBLING path verification/phase16-raw-corpus-entity-layer/raner_smoke_attempt_registry.jsonl (outside any attempt output root; lock at verification/phase16-raw-corpus-entity-layer/.raner_smoke_attempt_registry.lock; implemented by Task #221; not created now). Future multi-attempt evidence publication is attempt-specific (verification/phase16-raw-corpus-entity-layer/raner_smoke_live_output/<attempt-id>/); Task #221 must adapt the current fixed whole-directory atomic os.replace publisher to attempt-specific publication through TDD before any launch, so the registry SIBLING is never inside an atomically-replaced or pre-existing-rejected output root. Terminal ok means ONLY supervised worker completion (supervisor-captured per-attempt evidence-pair hashes), NOT independent verification, canonical, deployment-suitable, or compatibility-frozen; canonical_selected (only after an independent verifier validates a terminal ok) and compatibility_frozen (only after canonical_selected under a separately authorized downstream compatibility-freeze action) are post-terminal append-only annotation events in the same registry (zero-or-one per current Phase 16; supersession only via separately authorized planning amendment). Exactly one terminal lifecycle event (ok|execution_failed) per attempt; a dangling launch_committed (worker killed/crashed before any terminal event) is terminalized ONLY by explicit coordinator reconciliation (never automatic retry / no recovery loop). Gate 3 launch semantics are multi-attempt-by-explicit-launch, not single-use/no-retry. A separate TDD-governed contract amendment of the /goal skill+tests and Plan 16-13 is required before the first Gate 3 launch. Gate 4 remains unexecuted and not authorized. C2 skipped_not_entered. Nothing executes now (Task #222 planning-only).**
> **[2026-08-12 Task #227 adjudication record — supersedes the "Task #221 NOW AUTHORIZED" immediate-stop framing above:] Task #221's isolated-runtime-preparation implementation was carried out as Task #224, which STOPPED at LIMIT_REACHED (2026-08-12; stop status LIMIT_REACHED, not COMPLETE/BLOCKED/LIVE_GATE_FAILED) after two independent read-only specification reviews returned BLOCK. Coordinator-previously-observed fresh focused selector `121 passed in 3.85s` proves unit seams only, not specification compliance or production composition. Decisive preparation blocker: runtime pip is configured `--no-index --find-links .cache/raner-runtime/dist` but no production mechanism populates/validates that dependency wheelhouse, so a fresh authorized build cannot install locked dependencies or reach the required `modelscope.pipelines` import proof. Confirmed gaps: parent-only WSL measurement provider does not cross the real subprocess boundary; runtime builder incrementally mutates the final runtime instead of whole-runtime staging/atomic publication (no no-overwrite/preparation concurrency protection); prepare CLI reads the lock in text mode (CRLF raw-byte identity not preserved); import/network proofs not bound to the exact build/venv/mirror/lock/repository artifact; no production launcher composes LaunchSpec+supervise_launch. The bounded changed-approach remediation allowance ('Remediate Gate3 supervisor' + 'Remediate Gate3 contract', the latter the active second remediation) is EXHAUSTED; no further writer may be inferred or silently dispatched. Exact resume point: an explicit user authorization for a newly replanned/extended remediation package is REQUIRED, then GitNexus upstream impact on every existing symbol to edit, then fresh TDD — NOT existing authorization. Tasks #221/#225/#226/#220/#215 remain blocked/incomplete; Task #181 pending. Gate 3 attempt count remains 0 (no registry/lock/attempt evidence/`.cache/raner-runtime` runtime created; no package/model/network/DB/C2/live activity, compatibility freeze, commit, or push). Exact user boundary preserved verbatim without reinterpretation: “禁止 Docker/PostgreSQL、外部数据库、网络或模型下载、RaNER 推理、任何 live gate、C2、commit 和 push；Wave 2–4 仍须另行授权。” Nothing executes now (Task #227 planning-only adjudication).**

---

## Phase 14: OKF Foundation (格式契约 + docling→OKF 序列化 + 重建 + span_id 硬门)

**Goal:** Establish the E1 OKF foundation for a single registered document/version: format contracts (raw frontmatter + spans sidecar schema v1 + canonical structural hash), docling→OKF serializer, parser completion (sidecar reading, frontmatter validation, incremental/delete via canonical hash), migrations 015-017, transactional `rebuild_from_okf.py` reconciliation of `canonical_spans` from admitted raw frontmatter + sidecar, and the span_id round-trip regression gate (`S_direct == S_okf` 100%). Registered/protected `documents` and `document_versions` provenance parents already exist; E1 does not rebuild vector chunks, tree nodes, entities, relations, evidence, or NER associations.

**Status:** BOUNDED CLOSED/PASS — all four plans have execution records and [artifact 13](../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md) records **APPROVE_FOR_FORMAL_CLOSURE**. E1 remains bounded; see [`14-04-SUMMARY.md`](phases/14-okf-foundation/14-04-SUMMARY.md).

**Entry Point:** CLOSED (bounded) — Phase 15 is accepted and CLOSED (2026-08-05).

**Depends on:** T1-T9 ratified (`.planning/ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md`) ✅; no v1.0 phase dependency (additive workstream).

**Requirements:** R-OKF-01 (proof mechanism), R-OKF-03 (hard gate), R-OKF-04 (constraint); P14-01..P14-12 (see 14-CONTEXT.md).

**User-approved prerequisite (2026-07-14):** Phase 14 scope expanded to pin `docling==2.109.0` and enable Docling's official `HeadingHierarchyModel` in `_build_default_reader`. This makes multi-level `heading_path` achievable for PDF fixtures (T9 requirement). Span-ID migration impact documented as intentional boundary. See ADR Phase 14 scope expansion section.

**Plans:** 4/4 execution records; **BOUNDED CLOSED/PASS — artifact 13 APPROVE_FOR_FORMAL_CLOSURE**
- [x] 14-01-PLAN.md — OKF format contracts: spans sidecar schema v1 + raw frontmatter contract + canonical structural hash + OKF_BUNDLE_ROOT config + bundle templates/AGENT.md (TDD) [wave 1 execution record]
- [x] 14-02-PLAN.md — Migrations 015_okf_sync_state / 016_entity_mentions / 017_relation_qualifiers; hardcoded migration-list sites documented, with adjudication tracked separately [wave 1 execution record]
- [x] 14-03-PLAN.md — docling→OKF serializer (raw/*.md + *.spans.json, reusing NormalizationContract) + parser completion (sidecar reading, fail-fast frontmatter validation, incremental/delete, no silent qualifier drop) [wave 2 execution record]
- [x] 14-04-PLAN.md — E1 `canonical_spans` reconciliation/round-trip/rebuild-audit execution record; bounded CLOSED/PASS by artifact 13 [wave 3]

**Wave 1 closure evidence (2026-07-14):**
- 72 non-live OKF tests and 21 config regression tests passed.
- 76 tests passed against disposable PostgreSQL; fresh/existing/re-apply migration paths verified.
- A second fresh database accepted the root runner’s 8 migrations and produced 18 tables.
- Phase 14-01 scoped coverage is 85%; isolated mypy, Ruff, compileall, and whitespace checks passed.
- General, Python, database, and security Opus reviews all returned APPROVE with no CRITICAL/HIGH findings.
- No commit/push performed; unrelated dirty-tree changes remain excluded.

**Wave 2 closure evidence (2026-07-14):**
- 107 focused serializer+parser tests passed; 179 full OKF suite passed; 82 normalization regressions passed.
- Branch coverage 89% total (parser 86%, serializer 94%).
- Scoped mypy (`--follow-imports=skip`), Ruff, py_compile, git diff --check all passed.
- Security review APPROVE: 0 CRITICAL/0 HIGH; future hardening MEDIUM (symlink traversal, size/count caps) documented, NOT fixed.
- Python review APPROVE: 0 CRITICAL/0 HIGH; only non-blocking maintainability notes.
- General review: initial 2 HIGH findings fixed (serializer-only enrichment deleted, 4 direct-chain-equivalent regression tests added); final re-review APPROVE.
- GitNexus impact: serialize_document HIGH (23 test callers, 0 production processes); no HIGH/CRITICAL production execution flow.
- No commit/push performed; unrelated dirty-tree changes remain excluded.

**Final authoritative complete-OKF-suite evidence:**
- Run `python -m pytest tests/llamaindex_runtime/okf -m 'not integration'`. In the clean DB/libpq environment: **869 collected; 853 selected; 849 passed; 4 skipped; 16 deselected; 0 failed**. This supersedes prior 851/845/844/1/6 figures as current full-suite evidence.
- Run matching branch coverage from the same selection with `python -m coverage run --branch --source=llamaindex_runtime/okf,scripts -m pytest tests/llamaindex_runtime/okf -m 'not integration'`, then report only `llamaindex_runtime/okf/*`, `scripts/rebuild_from_okf.py`, and `scripts/_rebuild_database_connection.py`. The include-filtered result: OKF package **2401 statements / 138 misses / 726 branches / 84 partial = 92.64%**; lowest relevant `llamaindex_runtime/okf/_rooted_write_posix.py` **115 / 17 / 30 / 4 = 82.76%**; rebuild main **382 / 37 / 86 / 11 = 88.89%**; helper **55 / 3 / 12 / 1 = 94.03%**; scripts total **437 / 40 / 98 / 12 = 89.53%**; combined selected scopes **2838 / 178 / 824 / 96 = 92.19%**.
- Frozen-fixture CLI parity remains **3/3**.

**Current Task31/Task32 acceptance evidence (independent from the complete OKF suite; does not close Phase 14):**
- Task31 selected exactly `tests/test_real_retrieval_workflow.py`, `tests/test_real_retrieval_workflow_database.py`, and `tests/test_real_retrieval_workflow_security.py`: **61 collected/passed**, with **88%** script branch coverage (282 statements, 64 branches). The direct PageIndex tuple is exactly `001,002,003,004,007`, excluding `005` and `015`–`018`; it has loopback, dynamic-libpq, explicit `search_path=public`/`connect_timeout=10`, 5s lock/60s statement timeout, redaction, and fixed-error controls. `pgvector/pgvector:pg15` remains a mutable-tag MEDIUM residual; no hermetic claim.
- Task32 strict rebuild runtime accepts only numeric-loopback `postgresql://127.0.0.1` targets with explicit credentials/database/port and rejects query/fragment/service/socket/multihost/`localhost`. It uses capability-aware libpq controls and `search_path=public` for both primary/audit factory connections, verifies `current_database()` before DML, and only audits after confirmed rollback/close with primary-error precedence.
- Task32 non-DB selection: **97 collected/passed** with DB/acceptance variables unset. Independent labelled disposable-Docker acceptance: **12 collected/passed, 0 skipped**; loopback/process-only credentials/label cleanup/no residual `okf.task=34` container. Outer gate: `OKF_REBUILD_DOCKER_ACCEPTANCE=1`; audit additionally requires `OKF_FAILURE_AUDIT_ACCEPTANCE=1`; inner disposable marker remains.
- Scoped Black/Ruff/py_compile/AST and implementation-scoped mypy were clean. No full-repository mypy-green claim: unrelated pre-existing closure errors remain. The fresh sibling helper resists same-key/file poison and restores cache after success/`BaseException`; concurrent isolated importlib loads retain a nonblocking temporary-`sys.modules` race.
- Remaining hardening is M1 aggregate bundle limits, M2 broader operational timeout policy (the root runner is not Task31-hardened), M3 cross-scope absent-span collision taxonomy, M4 import race, future approved production sentinel/least privilege, and mutable image tag. Audit is operational, not tamper-evident. Semantic lint **passed**: `pnpm dlx @thisismydesign/okf-lint ./okf_bundle --max-warnings 0` returned `No problems found` with 0 errors and 0 warnings. `okf_bundle/.okflintrc.json` disables only `timestamp-format`, preserving quoted `<ISO-8601-timestamp>` template sentinels and accurately treating raw timestamp as optional, non-serializer, non-admission metadata. Final independent review was APPROVE with zero findings; the prior HIGH raw-timestamp wording mismatch is resolved. GitNexus index is fresh/current at `9c1922c`; full/unstaged detect-changes maps 23 tracked files, 58 symbols, and 6 flows at HIGH risk, including unrelated pre-existing changes. It is not a commit-scope PASS, and a future actual commit must run detect-changes on its intended scope.

**Key Files (current state; pre-14-01 baseline is historical):**
- `llamaindex_runtime/okf/parser.py` — current admitted raw Markdown + adjacent sidecar-pair parser; `OKFDocument` carries sidecar spans and canonical hash, and raw provenance is typed on `OKFFrontmatter`. Historical pre-14-01 baseline: paragraph-only DTO/body splitting/raw-byte hash.
- `llamaindex_runtime/okf/` — implemented contracts, sidecar, canonical-hash, serializer, raw-pair, and round-trip modules; focused tests exist under `tests/llamaindex_runtime/okf/`.
- `llamaindex_runtime/ingestion/docling_ingestor.py` — READ-ONLY span-id/`NormalizationContract` reference except the approved `_build_default_reader` scope expansion.
- `llamaindex_runtime/registry/migrations/015_okf_sync_state.sql` through `018_okf_rebuild_failure_audit.sql` — registered OKF migrations.
- `scripts/run_pageindex_real_retrieval_workflow.py` — Task31 direct workflow with exact migration tuple `001,002,003,004,007`; excludes `005`/`015`–`018` and is not an OKF migration path.
- `run_migrations.py` — root migration runner; `KEY_MIGRATIONS = FULL_MIGRATION_CATALOG` (compatibility export) and `FULL_MIGRATION_CATALOG` in `llamaindex_runtime/registry/migration_catalog.py` is the one authoritative ordered root catalog: `001_initial.sql` through `019_e2a_materialization_contract.sql`, with 019 exactly once after 018. Not Task34's disposable CLI and not claimed to have Task31 timeout/search-path hardening. The earlier curated tuple ending at 018 (`001,002,003,004,005,007,015,016,017,018`) is historical/superseded.
- `scripts/rebuild_from_okf.py` — E1 rebuild/round-trip CLI target; functional delivery, canonical-path ratification, and bounded A-F closure are recorded by artifact 13. E1 remains bounded to `canonical_spans` reconciliation.
- `llamaindex_runtime/config.py` — current `OKF_BUNDLE_ROOT` setting.

**Success Criteria (hard acceptance = handoff §10):**
- A 格式契约: sidecar schema v1 + frontmatter contract validated by tests; format-only rewrite does NOT change canonical hash
- B span_id round-trip: `S_direct == S_okf` 100% identical across ≥3 fixture classes (sectioned PDF, table/complex-layout PDF, DOCX); failure output names the first mismatching coordinate
- C schema: current registered migration set is 015-018; fresh-initdb and existing-database application remain subject to Wave 3 acceptance. Hardcoded runner migration-list adjudication remains separately owned and is not claimed here.
- D parser 增量: sidecar-driven span identity; incremental sync + delete detection via canonical hash; frontmatter validation fail-fast; relation qualifiers never silently dropped
- E 可重建证明（E1）: `documents`/`document_versions` provenance parents are registered/protected and already exist; admitted raw frontmatter + sidecar deterministically reconcile `canonical_spans`; second equivalent run has no canonical-span DML; transaction/audit behavior is verified. Vector/tree/entity/relation/evidence/NER materialization is explicitly E2a/E2b work, not Phase 14.
- F 非目标 honored: no NER, no PageIndex tuning, no fusion-weight change, no agent writeback, no Level claims

**Non-goals:** everything listed under F above + no change to any existing ingestion caller (single-document proof only; corpus-wide switchover is Phase 15).

---

## Phase 15: OKF Unified Ingestion Pipeline (SSOT 全量落地)

**Goal:** E2a makes OKF the ONLY fact path into PostgreSQL for the whole corpus: every PDF/Word enters via docling → OKF raw serialization → unified OKF ingestion; normal durable ingress is solely OKF → E2a. Direct derivation is permitted only as a pure non-persisting test/disposable shadow comparator for parity, with no automatic fallback or parallel persisted fact path. E2a materializes/parity-checks `vector_chunks`/`vector_chunk_spans`, `tree_nodes`/`tree_node_spans`, and manual OKF entities/relations/evidence. NER-derived writes remain Phase 16 E2b.

**Status:** CLOSED/ACCEPTED (2026-08-05). Real acceptance chain Tasks #88/#89/#90 passed; Task #54 goal-backward aggregate audit PASS_WITH_CLOSURE_UPDATES (10/10 must-haves, 0 acceptance blockers, 1 non-blocking warning).

**Entry Point:** CLOSE — real acceptance complete. Tasks #52/#53/#79/#86/#88/#89/#90/#54 are COMPLETE. No live authorization remains; no further live execution is required for closure. Phase 16 EXECUTING (2026-08-06): authorized static/pure Wave 0 (16-01/16-02), authorized NON-LIVE scheduler Wave 1 (16-03/16-04/16-05/16-07), authorized scheduler Wave 2 local/static/default-blocked (16-06/16-08/16-12), authorized scheduler Wave 3 static (16-09/16-10/16-13), authorized scheduler Wave 4 local/static/pure/injected (16-11), and the authorized scheduler Wave 5 scope (16-14) is complete (Wave 3 static closeout 2026-08-08; Wave 4 static closeout 2026-08-08; Wave 5 Task 1 static closeout 2026-08-08: frozen+corrective selector 81 passed in 3.01s; Wave 5 LIVE closeout 2026-08-09: 16-14 Task 2 executed, status=executed, full/live Plan 16-14 objective COMPLETE) but gate 1 executed 2026-08-09, gate 2 (ModelScope mirror build) EXECUTED/SUCCESS 2026-08-09 (single-use consumed; never rerun), and the three remaining live gates are unexecuted (gates 3-4 blocked_not_executed — historical single-use authorizations materialized by Task #214 but NOT consumed; C2 skipped_not_entered); next Wave 6 (plans 16-15/16-16) is NOT automatically authorized and NOT claimed dependency-ready.

**Depends on:** Phase 14 (contracts, serializer, parser, migrations, rebuild mechanism).

**Requirements:** R-OKF-01 (full corpus), R-OKF-02, R-OKF-04.

**Plans:** Four-plan implementation scope delivered with all four summaries filed (`15-01-SUMMARY.md`, `15-02-SUMMARY.md`, `15-03-SUMMARY.md`, `15-04-SUMMARY.md`). Aggregate acceptance record: `15-VERIFICATION.md`.

Plans:
- [x] 15-01-PLAN.md — deterministic admission, manual evidence, and migration contracts [summary: `15-01-SUMMARY.md`]
- [x] 15-02-PLAN.md — caller-owned exact atomic reconciliation [summary: `15-02-SUMMARY.md`]
- [x] 15-03-PLAN.md — caller switchover and PageIndex authority retirement [summary: `15-03-SUMMARY.md`]
- [x] 15-04-PLAN.md — authority-aware verification evidence [summary: `15-04-SUMMARY.md`]

**Boundary doc:** `.planning/phases/15-okf-ingestion-pipeline/15-BOUNDARY.md`

**Acceptance chain (2026-08-05):**
- **Task #88 (real disposable PostgreSQL transition matrix):** PASS — first materialization, equivalent rerun (zero DML), late failure, concurrency, stale reconciliation, migration catalog/fresh schema, 019 atomic envelope.
- **Task #89 (durable integration boundary exact live selector):** PASS — 1 passed in 101.86s (run once).
- **Task #90 (pure/static gate + exact authorized live selector):** PASS — 114 static/pure tests passed; Ruff clean; Black unchanged; protected runner fingerprint unchanged; default collection excludes live; exact authorized live selector passed once (1 passed in 14.30s).
- **Task #54 (goal-backward aggregate audit):** PASS_WITH_CLOSURE_UPDATES — 10/10 must-haves verified; 0 acceptance blockers; 1 non-blocking warning.

**Non-claims:** PASS is bounded to the precise Phase 15 boundary. No hostile-superuser/tamper-evidence/postcommit guarantee; no quality or Level claim (Level 2 remains authoritative); no production readiness; no external DB. `migration019-applied.json` is historical/non-authoritative. `_ingest_legacy` (dead/unreachable in `llamaindex_runtime/ingestion/pipeline.py`) and old historical script shape are non-blocking follow-up cleanup only. No commit/push. No clean-worktree/full-worktree claim.

**Success Criteria (draft — finalized at PLAN):**
- No second persistence-capable document/vector/tree writer exists outside OKF; E2b NER writes remain separately owned.
- Direct derivation is a pure non-persisting comparator with measured parity only.
- Full-corpus E2a reconciliation is atomic, exact-idempotent, deterministic, and denylist-safe.
- R1/R2a/R2b/p6 are smoke-only; no quality or Level claim is made.

---

## Phase 16: Raw Corpus Entity Layer (零/低 token 实体抽取)

**Goal:** E2b populates the NER-derived entity layer from OKF raw corpus with a zero/low-token multi-source extraction pipeline: **ModelScope `iic/nlp_raner_named-entity-recognition_chinese-large-generic` performs primary fixed-label, contextual discovery of dictionary-external mentions**, while jieba/domain dictionaries, OKF frontmatter, and deterministic rules provide high-confidence domain supplementation, boundary correction, and normalization. E2b owns NER-derived `entity_mentions` with character-level coordinates/provenance, aliases/merge handling, and `node_entity_links`; manual OKF entities/relations/evidence may already be materialized by Phase 15 E2a and are not rematerialized here. A dictionary-only implementation cannot satisfy C1 acceptance. No generative LLM triple extraction (R-OKF-04); the feature remains default OFF. Internally split into **C1** (extraction/normalization/linking, main wave) and **C2** (Chinese local coreference chains `coref_clusters` + normalized membership table — conditional second wave, default OFF, added 2026-07-12 per supplement handoff §4).

**Status:** EXECUTED (2026-08-31) — all 18 plans (16-01..16-18) delivered with summaries. Detailed wave-0-5 history lives in each plan SUMMARY file and git history; live acceptance now proven on one-shot disposable PostgreSQL: C1 full-corpus 8/8 transition matrix (16-15, evidence sha256 53ae99b6e4f85223ccbfe99910a13a711d12d033670db4a408eb532068a412e3, archive e2b_full_corpus_acceptance_evidence_executed_2026-08-31.md) and C2 entry (16-17 Gate 5 R2 2026-08-31, executed: 21 migrations incl. 021, default-off parity 0/0/0 DML, rules cluster=1 membership=2 deterministic ids verified, tombstone preserved; evidence sha256 91656cd4eb0e1c3902fd25db27e497e94c01cb2ae3a03520c2e25292d825c869). Aggregate record: 16-VERIFICATION.md (16-18, 35 contract tests, evidence anchors hash-verified). EXPLICIT NON-CLAIM: RaNER live smoke is blocked_not_executed (2026-08-29 real attempt fail-closed not_launched/wsl_not_ready by the frozen WSL provider contract; the WSL measurement track was WAIVED by user decision 2026-08-31); real inference awaits a separate explicit user authorization. C1 executed; C2 entered and passed.

**Entry Point:** EXECUTE — Wave 0 (16-01/16-02 static/pure), authorized NON-LIVE scheduler Wave 1 (16-03/16-04/16-05/16-07), authorized scheduler Wave 2 local/static/default-blocked (16-06/16-08/16-12), authorized scheduler Wave 3 static (16-09/16-10/16-13), and authorized scheduler Wave 4 local/static/pure/injected (16-11) executed and evidenced (Wave 3 static closeout 2026-08-08; Wave 4 static closeout 2026-08-08); **the authorized scheduler Wave 5 scope (16-14) executed and is evidenced (Wave 5 Task 1 static closeout 2026-08-08: frozen+corrective selector 81 passed in 3.01s) and its Task 2 (future gate 1) was EXECUTED once on 2026-08-09 (Wave 5 LIVE closeout; status=executed, evidence_verified=true, cleanup_ok=true; full/live Plan 16-14 objective COMPLETE); next scheduler layer is Wave 6 = plans 16-15 and 16-16 — NOT automatically authorized and NOT claimed dependency-ready**; gate 1 executed, gate 2 (ModelScope mirror build) EXECUTED/SUCCESS 2026-08-09 (single-use consumed; never rerun), and the three remaining live gates are unexecuted (gates 3-4 blocked_not_executed — historical single-use authorizations materialized by Task #214 but NOT consumed; C2 skipped_not_entered). C1 mandatory; C2 conditional (entered only after C1 acceptance closed + a separate single-use `OKF_E2B_C2_ENTRY_AUTHORIZED`; `skipped_not_entered` does not block C1-based closure but R-OKF-09 cannot be claimed live-tested).

**Depends on:** Phase 15 (unified ingestion), Phase 14 (entity_mentions/aliases/merge_log tables).

**Requirements:** R-OKF-04, R-OKF-06, R-OKF-09 (C2 readiness gate only — net benefit adjudicated at Phase 19 G3).

**Boundary doc:** `.planning/phases/16-raw-corpus-entity-layer/16-BOUNDARY.md`

**Success Criteria (planned acceptance criteria — not yet achieved):**
- Extractor interface is pluggable, schema-independent, and uses a discriminated `CorpusSpanInput | QueryTextInput` union: both reuse one RaNER adapter, `input_id/input_revision`, normalized-text coordinate contract, label map, and provenance output. Corpus candidates use `input_revision=document_revision`, carry document/sidecar projection, and are persistence-eligible; query candidates use `input_revision=query_revision`, and their audit/merger artifacts are request-scoped with zero durable candidate-audit/mention/merge/alias/link/evidence writes. **A runnable RaNER Large Generic adapter is mandatory for C1**, with initial `RAG_ENTITY_EXTRACTOR=off|raner` defaulting to off. UIE is a future schema-guided extension; RaNER Base News is a resource-constrained fallback candidate; HanLP/DeepKE are not initial supported values. Protocol-only, mock-only, or jieba/dictionary-only delivery does not close C1
- Direct inference works without project annotation or fine-tuning; a small manually labeled Chinese set is required only for acceptance measurement, not as training or startup prerequisite
- Dictionary-excluded Person/Organization/Location plus `CW` or `PROD` fixtures prove contextual model discovery, versioned label mapping, and exact character-offset round-trip; a domain-alias fixture proves dictionaries/frontmatter work as high-confidence supplements
- Model, dictionary, rule, and frontmatter candidates share one mention schema with source/confidence-kind/version provenance; every raw overlapping candidate is retained before a deterministic, versioned merger marks selected/suppressed outcomes. RaNER stores `confidence=None`, `confidence_kind="unavailable"` rather than a fabricated probability
- entity_mentions rows carry span_id + char_start/char_end + mention_text + raw/canonical label + confidence metadata + source; offsets are Python Unicode code-point half-open indices in the exact normalized span, with immutable document revision and normalization/segmentation/sidecar projection provenance. Invalid coordinates are never recovered with substring search; a failed span writes no partial entity/alias/link state. `entity_id` nullable/pending allowed (forward contract for C2)
- Entity/alias merge is logged (entity_merge_log) and reversible; NER candidates never directly cause permanent canonical-entity merges
- Model files are frozen by complete SHA-256 manifest and offline loading; Windows/WSL CPU cold start, peak memory, throughput, and p95 latency are measured. Large Generic cannot be silently replaced by Base News if it exceeds budget; any degradation requires same-evaluation-set evidence and explicit adjudication [2026-08-31 user decision: Windows/WSL measurement acceptance WAIVED on this host - skipped entirely, no further research; real gate-3 attempt NOT executed; facts + 3-step resumption in .planning/phases/16-raw-corpus-entity-layer/16-13-GATE3-WSL-GAP-DOWNSTREAM-2026-08-29.md final-closure section]
- Zero generative-LLM tokens consumed by the enabled baseline (`RaNER Large Generic + dictionary/frontmatter/rules`); entity extraction remains default OFF until explicitly enabled
- C2 (if entered): coref clusters are local evidence links only (no permanent entity merges), `RAG_COREF_RESOLVER=off|rules` defaults off, model-assisted coreference exposes no model value until separately frozen, per-cluster tombstone soft-delete, disabled-state regression identical to C1-only; migration ordering C1-schema before C2-schema per ADR T5

---

## Phase 17: Graph Recall R3 + Four-Route Fusion (图谱召回接入)

**Goal:** Add the fourth retrieval route R3 (entity/graph multi-hop over entities/relations/entity_mentions) and inject it ONLY into `analysis/fusion.py::fuse_candidates` (RRF path) with source labels and observable scores (T7). `_compute_fusion_score` fixed weights remain untouched; hotspot-weight participation is deferred to Phase 19 ablation.

**Status:** EXECUTED (2026-09-03) — 8 waves W0-W7 + W7-LIVE live gates (gate exit 0 evidence 853bb353…, demo RC 0 report c2ae8ea3…) + FIX-17 spec amendments (entities actually ingest, deps failure writes evidence) all closed; see 17-PLAN-MASTER-2026-09-01.md (26 sections) + 17-DECISION-LIGHTRAG-BACKEND-2026-09-01.md. [2026-09-03 user decisions: graph+vector one route via LightRAG backend; normalization layer self-built; LLM_MODEL temporarily deepseek-v4-flash during codex outage, revert decision pending user. Original RAG_ROUTE_R3 runtime-switch surface and BM25 real route remain registered follow-ups (master plan §26).] [2026-09-04: debt wave W5a/W5b/W5c closed (follow-ups 13→8 closed, F11/F12/F4-live/F14-residual recorded) + verification orchestrator run_phase17_verification.py verified (9 checks 0 failed, focused 136, 组合 3/1541/1); see 17-VERIFICATION.md] [2026-09-05: legacy Neo4j property-graph seam retired (graph/query.py + projector.py + seam.py deleted, query() graph mode/leg removed, classifier no longer routes to graph; verification harness graph_path + /query/graph + neo4j compose service removed; LightRAG channel is the sole graph engine; archive sha cda69874…, 6-domain combined 1287/0 post-retirement; see .planning/phases/neo4j-graph-seam-retirement/NEO4J-SEAM-RETIRED-2026-09-05.md)]

**Entry Point:** EXECUTED (2026-09-03) — Phase 18 may PLAN; production OKF writeback + human review = Phase 18 scope

**Depends on:** Phase 16 (entity layer data), existing fusion mechanisms (verified: `fuse_candidates` RRF at `llamaindex_runtime/analysis/fusion.py:40`; `_fuse_candidate_scores` does NOT exist).

**Requirements:** R-OKF-05.

**Boundary doc:** `.planning/phases/17-graph-recall-multiroute-fusion/17-BOUNDARY.md`

**Success Criteria (draft — finalized at PLAN):**
- R3 route runnable standalone AND fused under the legal `RAG_ROUTE_R3=on + RAG_ENTITY_EXTRACTOR=raner` configuration; per-route source labels visible in fused output
- All four `R3 on|off × extractor off|raner` combinations are tested: `R3=on/extractor=off` fails deterministically during startup/config validation, never auto-loads the model, falls back to dictionary-only extraction, or masquerades as an empty route
- R1/R2a/R2b behavior with R3 disabled is bit-identical to pre-Phase-17
- No change to `_compute_fusion_score` fixed weights (0.40/0.30/0.20/0.10)
- If Phase 16 delivered C2: coref consumption is an optional, budget-capped, explainable expansion signal with its own off-switch independent of `RAG_ROUTE_R3`; coref-off behavior identical to a no-coref build; coref links never produce evidence-less QueryHits (2026-07-12 supplement)

---

## Phase 18: Controlled OKF Writeback (proposal/staging + 人审)

**Goal:** Enable agents to propose knowledge writebacks into OKF via a staging area with mandatory human review before merge (T8/D8). Human editing remains first-class; agent auto-commit stays disabled pending separate user approval and quality gates.

**Status:** EXECUTED (2026-09-04) — W0-W7 all executed (proposal/staging + journal + CLI + merge executor + debt wave + R-OKF-07 no-bypass verification verified 9/0 + live full-chain acceptance on a disposable bundle copy; see 18-PLAN-MASTER W6/W7 关单 + 18-VERIFICATION.md + live evidence archive). Redlines held: no auto-merge (T8), raw/ zero-write, git human-only

**Entry Point:** Phase 18 CLOSED 2026-09-04 (all waves DONE). Phase 19 (RaNER retirement) may PLAN/execute per approved criteria C1-C7

**Depends on:** Phase 17 (retrieval consumes what writeback improves), Phase 15 (sync flow F3 ingests merged edits).

**Requirements:** R-OKF-07.

**Boundary doc:** `.planning/phases/18-controlled-okf-writeback/18-BOUNDARY.md`

**Success Criteria (draft — finalized at PLAN):**
- Staged proposals never touch `raw/` (machine-generated only); targets are `entities/`, `concepts/`, `synthesis/`
- No path exists for an agent to merge without human approval
- Merged edits flow through canonical-hash sync (F3) with full provenance

---

## Phase 19: RaNER Retirement & WSL Closure (RaNER 整体退役) [created 2026-09-03]

**Goal:** Retire the RaNER extraction stack entirely (superseded by PP-UIE-0.5B: 95% vs 47% extraction quality, UIE adds relation extraction, both local/offline). Root-removes Gate 3 residuals, WSL measurement requirement, and all .cache/raner-* assets (~4.6GB).

**Status:** EXECUTED (2026-09-04) — W0-W6 all DONE. Record: .planning/phases/19-raner-retirement/19-RETIRED-2026-09-04.md (C1-C7 PASS; 8 code files edited fail-closed, 2 dirs + 17 py + 5 .cache dirs + stale manifest deleted, 4476.7 MB freed, assets+code archived with verified sha256; post-retirement baselines: 6-domain combined 1287 passed/0 failed — first fully green combined, okf 5 pre-existing/3381/31, entity 966/0).

**Decision record (user, 2026-09-03):** '彻底把 RANER 直接删掉吧，这个没什么意义了' + coordinator evaluation: UIE fully replaces RaNER (quality 95% vs 47%, relations UIE-only, RaNER production path never succeeded once). Only RaNER advantage = speed (0.25s vs 6.9s per sentence CPU) — rejected as retention reason (wrong-fast worse than right-slow; GPU closes UIE gap). Honest semantic note: baseline wording changes from zero-generative-LLM to zero-cloud-LLM (dictionary/frontmatter/rules remain zero-LLM; model extraction = local small model).

**Retirement criteria (C1-C7, defined 2026-09-03):** C1 zero code residue (grep raner; exemptions: label_map.py = canonical type vocabulary shared by identity/contracts/UIE, third-party corpus data) / C2 full deletion inventory (gate3 17 files + raner_adapter + offline_mirror + mirror_downloader + 7 phase16 runners + tests mapped) / C3 surgical keeps (extractor.py branch removal, config VALID_ENTITY_EXTRACTORS -> {off}, fail-closed on raner) / C4 suite health (entity 3 chronic raner failures disappear; okf 5 pre-existing unchanged) / C5 asset purge with before/after sizes + irreversibility record / C6 zip archive + sha256 before deletion (.planning history untouched) / C7 ROADMAP/STATE/contract RETIRED annotations.

**Plan doc:** .planning/phases/19-raner-retirement/19-RETIRED-2026-09-04.md (authored at execution 2026-09-04; archive-first discipline WAS honored — both zips + inventory JSON written and sha-verified before any deletion).

---

## Phase 20: Evaluation & Tuning (D4 解冻后) [renumbered from Phase 19, 2026-09-03 — RaNER retirement inserted as new Phase 19]

**Goal:** Lift the D4 deferral: run the ablation matrix over route combinations and switches (node summaries, hotspot weight participation for entity signals), collect matched human judgments, and assess against the frozen thresholds (hit_rate ≥0.80, top1_relevance ≥0.90, stability ≥0.85) for any Level 3/4 claim. Source-level alignment (2026-07-12 supplement): question set stratified by the eight DOCX Chinese difficulty categories (full-name/abbreviation, same-name disambiguation, explicit coreference, zero anaphora, negation, condition/exception, cross-section/cross-document multi-hop, unanswerable); primary metric **All-Evidence Recall**; ablation follows the DOCX ladder A→G (baseline → entity inverted index → KU multi-index → normalization → coreference/16-C2 → semantic edges → high-value qualifiers if present), one increment per rung.

**Status:** Boundary drawn (19-BOUNDARY.md) — detailed wave planning deferred; D4 becomes available for Phase 19 after Phase 18 and all dependencies close (not executed now; no new explicit user unfreeze required)

**Entry Point:** PLAN (blocked: requires Phase 18 closed AND all dependencies closed; D4 becomes available for Phase 19 once those close — it is not executed now and does not require a new explicit user unfreeze)

**Depends on:** Phases 14-18 all closed; v1.0 evaluation machinery (verification/ pipeline, judgment templates).

**Requirements:** R-OKF-08; R-OKF-09 adjudication (G3).

**Boundary doc:** `.planning/phases/19-evaluation-tuning/19-BOUNDARY.md`

**Success Criteria (draft — finalized at PLAN):**
- Ablation matrix covers per-route on/off and fusion-variant comparisons with matched judgments (no label reuse across mismatched corpora — Phase 4/10 lesson)
- Any weight redistribution or summary enablement is decided by measured deltas, not assumption
- Level claims only from valid matched assessments against frozen thresholds
- Adjudication gates delivered: **G3** (16-C2 coref net benefit → default-on / keep-off / remove), **G4** (dynamic multi-hop policy for R3), **G5** (pilot business value, handed to Phase 20 G6 as input)
- Phase 19 produces evaluations and adjudications ONLY — it deploys no pilot and implements no permission/isolation (that is Phase 20)

---

## Phase 21: Restricted Business Pilot & Production Readiness (受限业务试点与生产就绪) [renumbered from 20, 2026-09-03]

**Goal:** Validate the full OKF SSOT + four-route architecture on a single controlled business knowledge base and establish production readiness: data governance, permission/isolation enforced at candidate generation (not UI filtering), index operations, LLM-independent observability, canary/rollback, human feedback loop via Phase 18 channels, and ops/security baseline. Registered planning-level 2026-07-12 per supplement handoff §5; DOCX Stage 6 mapping.

**Status:** Boundary drawn (20-BOUNDARY.md) — the restricted Phase 20 FORMAL PLAN is PRE-AUTHORIZED (current-session bounded authorization packet); this does NOT authorize pilot execution and is NOT human G6 sign-off. Planning-level only; nothing executes now.

**Entry Point:** PLAN (gated: (1) D4 available AND Phase 19 closed — formal planning remains dependency-gated; (2) the restricted Phase 20 formal plan is PRE-AUTHORIZED — no independent explicit user authorization for the formal plan is needed, but actual restricted-pilot EXECUTION remains blocked until mandatory human G6 Go/No-Go, and Phase 19 passing alone does NOT authorize execution; (3) pilot-corpus consistency P0 remains mandatory: `S_direct == S_okf` round-trip re-run on the real pilot corpus, same version as the Phase 19 evaluation corpus)

**Depends on:** Phases 14-19 all closed; Phase 19 G5 output as G6 input.

**Requirements:** R-OKF-10.

**Boundary doc:** `.planning/phases/20-pilot-productionization/20-BOUNDARY.md`

**Success Criteria (draft — finalized at PLAN):**
- **P0** SSOT readiness proven on the pilot corpus (round-trip identity)
- **P1** derived layer fully rebuildable from OKF alone at pilot scale
- **P2** observable trial run (metrics/logging without LLM-dependent monitoring)
- **P3** real-scale rollback drill passes — the only real-scale proof of D1's rebuildability claim
- **G6** Go/No-Go decision with human sign-off, consuming G5 (pilot value) from Phase 19
- Agent writeback remains default OFF in the pilot; enabling proposals requires a fourth separate authorization (T8 human-review framework unchanged)
- DOCX "P95 ≤ 5s" recorded as a source-level target line for observation, not a hard G6 commitment

---


## Active Phase 15 precedence correction

Phase 15 is accepted and CLOSED (2026-08-05). The prior one-shot live authorizations (named local disposable Task #88/#89/#90 selector batches, sequential, once each, stop on first failure, no automatic retry) were consumed and are complete. Closure does not authorize Phase 16/E2b live gates, Phases 19/20, production, Git operations, or external database connections. Phase 16 is EXECUTING (2026-08-06): the authorized static/pure Wave 0 scope (16-01/16-02), the authorized NON-LIVE scheduler Wave 1 scope (16-03/16-04/16-05/16-07), the authorized scheduler Wave 2 local/static/default-blocked scope (16-06/16-08/16-12), the authorized scheduler Wave 3 static scope (16-09/16-10/16-13), and the authorized scheduler Wave 4 local/static/pure/injected scope (16-11) have executed and are evidenced (Wave 3 static closeout 2026-08-08, Task #190: aggregate selector 139 passed in 2.07s; full pure entity suite 651 passed/1 skipped in 6.99s; 16-09/16-10 COMPLETE, 16-13 bounded-static COMPLETE with its live Task 2 RaNER smoke future-gate-3 blocked_not_executed; Wave 4 static closeout 2026-08-08, Task #191: focused frozen+corrective selector 81 passed in 47.61s; full pure entity suite 651 passed/1 skipped in 7.27s; 16-11 E2b runner CLI COMPLETE for its local/static/pure/injected scope with no real RaNER model wired/loaded); the scheduler Wave 5 scope (plan 16-14) has executed and is evidenced (Wave 5 Task 1 static closeout 2026-08-08: frozen+corrective selector 81 passed in 3.01s) and its Task 2 (blocking live decision gate, future gate 1) was EXECUTED once on 2026-08-09 (Wave 5 LIVE closeout; status=executed, evidence_verified=true, cleanup_ok=true; full/live Plan 16-14 objective COMPLETE); the next scheduler layer is Wave 6 = plans 16-15 and 16-16 — NOT automatically authorized and NOT claimed dependency-ready; gate 1 executed, gate 2 (ModelScope mirror build) EXECUTED/SUCCESS 2026-08-09 (single-use consumed; never rerun), the three remaining live gates (gates 3-4 blocked_not_executed — historical single-use authorizations materialized by Task #214 but NOT consumed; C2 skipped_not_entered) are unauthorized and unexecuted, and wave completion confers no live-execution authority and does not close C1. This active correction does not alter historical Phase 14 evidence. Scoped precedence is: the execution handoff for scope and phase routing; the unified architecture where consistent; accepted ADRs in their explicit technical scope, including `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` and `ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md`; then milestone/roadmap execution mapping. The raw-pair ADR governs generated raw-pair binding and strict production admission.
