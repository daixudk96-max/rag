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

**Entry Point:** EXECUTE (WS0 baseline reconciliation completed 2026-05-31)

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

**Status:** Planned

**Entry Point:** PLAN

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

**Plans:** 3 plans across 3 waves
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

**Status:** Close-ready pending approval

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

**Status:** EXECUTE (wave 2 complete, proceeding to wave 3)

**Entry Point:** EXECUTE

**Depends on:** Phase 11 (ClusterHotspotSelector, runtime selector switch) and the post-Phase-11 `hybrid_cluster` + jieba runtime work (commits `ae7bd97`, `91182cd`).

**Plans:** 4 plans across 4 waves
- [x] 12-01-PLAN.md — Extend HotspotSelectionContext + report/runtime with parent_to_children child denominator (D-07) [wave 1 COMPLETE]
- [x] 12-02-PLAN.md — RED tests: coverage 1/3·2/3·3/3, dual-hot intersection, configurable θ, leaf fallback (D-01/D-02/D-05/D-06/D-10) [wave 2 COMPLETE]
- [ ] 12-03-PLAN.md — Implement cluster-hot coverage + dual-hot gate + θ + leaf fallback in HybridClusterHotspotSelector → GREEN (D-01..D-06, D-08/D-09) [wave 3]
- [ ] 12-03-PLAN.md — Implement cluster-hot coverage + dual-hot gate + θ + leaf fallback in HybridClusterHotspotSelector → GREEN (D-01..D-06, D-08/D-09) [wave 3]
- [ ] 12-04-PLAN.md — p6 DNA regression + full suite + rollback verify + GitNexus detect-changes + safe commit (D-09/D-10) [wave 4]

**Research:** Complete — `.planning/hotspot-cluster-redesign-EXPLORATION/00-SUMMARY.md` (E1–E7) with code anchors and the p6 tree reality check.

**Locked Design Decisions (from exploration, user-approved 2026-06-22):**
- **D1 — Definition A:** parent hotspot ⇔ `coverage(P) = |{c ∈ direct_children(P) : child_hot(c)}| / |direct_children(P)| ≥ θ`, where `child_hot(c) = vector_hot(c) AND keyword_hot(c)`. Path-all-hot (B) is a later tie-breaker, not the first-version rule.
- **D2 — Context data:** add a child denominator (`parent_to_children` / `direct_child_count`) to `HotspotSelectionContext`; today the selector only sees `node_stats` and cannot compute true coverage. Reuse `_build_parent_to_children()`.
- **D3 — Boundary:** selection-layer-only change. Keep emitting `SubtreeHotspot(node_id=...)`; do NOT change the traversal interface (`traverse_tree_for_query(start_node_id=...)`).
- **D4 — Threshold:** θ is configurable, NOT fixed at 1.0 (p6 internals mostly have 2–3 children; θ=1.0 over-prunes). Preserve a leaf fallback so focused exact-leaf queries (e.g. `数据清洗标注的具体方法是什么？`) still return their position.
- **D5 — Scope:** new Phase 12; do not reopen closed Phase 11.

**Mandatory Safety Gates:**
- GitNexus impact analysis required before editing symbols in `llamaindex_runtime/tree/semantic_distribution.py` (`HybridClusterHotspotSelector`, `_compute_child_distribution_score`, `_compute_fusion_score`, `HotspotSelectionContext`) and `llamaindex_runtime/tree/runtime.py` (hybrid_cluster context construction).
- CRITICAL runtime-path edits stay incremental and switch-gated behind `RAG_TREE_HOTSPOT_SELECTOR`; keep `route_subtree` and `cluster` selectors as rollback paths. No deletion of existing selectors in this phase.
- `gitnexus_detect_changes()` required before any commit.

**Planned Workstreams (subject to /gsd-plan-phase):**
- WS1: Extend `HotspotSelectionContext` with child denominator; wire `parent_to_children` from runtime/distribution report (TDD first).
- WS2: Implement cluster-hot coverage scoring with dual-hot gate, configurable θ, and leaf fallback in `HybridClusterHotspotSelector`.
- WS3: Rewrite distribution-scoring tests to coverage-ratio + dual-hot semantics; preserve registration, context, rerank-off, anti-hardcode, jieba-extraction, and p6 DNA regression tests.
- WS4: p6 validation across A's coverage cases (1/3, 2/3, 3/3) and leaf-query fallback; confirm DNA query still returns `数据驱动`, `非确定性`, `持续性`.
- WS5: Code review, security review, GitNexus detect-changes, safe git hygiene.

**Success Criteria:**
- A parent with multiple dual-hot children outranks an isolated high-vector single node (coverage gate proven by test).
- `vector_hot`-only or `keyword_hot`-only children do NOT count toward coverage.
- Configurable θ honored; leaf fallback returns focused exact-leaf positions.
- p6 DNA query regression still passes; cross-domain anti-hardcode tests still pass.
- `RAG_TREE_HOTSPOT_SELECTOR` rollback paths (`route_subtree`, `cluster`) remain intact.
- Code review and security review find 0 CRITICAL/HIGH before commit readiness.

---
