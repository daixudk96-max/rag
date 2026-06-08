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
