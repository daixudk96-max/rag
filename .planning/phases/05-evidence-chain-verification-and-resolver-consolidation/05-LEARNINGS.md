---
phase: 5
phase_name: "evidence-chain-verification-and-resolver-consolidation"
project: "rag"
generated: "2026-06-07T12:00:00Z"
counts:
  decisions: 5
  lessons: 5
  patterns: 5
  surprises: 4
missing_artifacts:
  - "05-VERIFICATION.md"
  - "05-UAT.md"
---

# Phase 5 Learnings: Evidence-Chain Verification and Resolver Consolidation

## Decisions

### Active-Version Counts Are Authoritative
Phase 5 evidence-chain metrics are scoped to one `active_version_id`; global `COUNT(*) FROM vector_chunks` is no longer authoritative for diagnosing `chunks`, `mapped_chunks`, or `heading_path_rate`.

**Rationale:** Phase 4 showed evidence-chain zeros, but global counts could not distinguish missing materialization from wrong-version or wrong-scope metrics. Active-version diagnostics make the failure attributable.
**Source:** 05-PLAN-01.md; 05-SUMMARY.md

---

### Heading Path Completeness Uses `canonical_spans.heading_path`
`canonical_spans.heading_path` is the authoritative heading-path metric source, while `tree_nodes.heading_path` and `vector_chunks.heading_path` are derived sources.

**Rationale:** Metrics must measure the source evidence chain, not a derived display field. This prevents interpreting tree metadata as proof that the source spans were correctly populated.
**Source:** 05-PLAN-02.md; 05-SUMMARY.md

---

### Preview Hydration Belongs in `EvidenceContentResolver`
Selected-node `text_preview` hydration is centralized in `llamaindex_runtime/tree/evidence_content_resolver.py` and called by both `ReasoningTreeBackend` and `PageIndexTreeAdapter`.

**Rationale:** The same fallback order was needed in both retrieval paths: `canonical_spans.raw_text` → `vector_chunks.text_preview` → summary/title fallback. Centralizing avoids duplicate drift.
**Source:** 05-PLAN-03.md; 05-SUMMARY.md

---

### Validation Metrics Must Fail Closed
`calculate_metrics.py` must refuse to produce a Level assessment unless retrieval results, judgment rows, active-version diagnostics, and corpus evidence pass the integrity gate.

**Rationale:** Phase 4 produced an invalid Level 3 by mixing new-corpus retrieval results with old-corpus judgments. Fail-closed gating prevents that class of error from recurring silently.
**Source:** 05-PLAN-04.md; 05-SUMMARY.md; STATE.md

---

### Level 2 Remains Authoritative Until Matched DB-Backed Validation Completes
Phase 5 implementation can close with blockers documented, but quality level cannot advance until a DB-backed rerun and matched human judgments produce a valid `level_assessment.json`.

**Rationale:** Local artifacts are fail-closed because `DATABASE_URL` is unset and retrieval/judgment artifacts mismatch. Advancing the level without matched evidence would repeat the Phase 4 integrity failure.
**Source:** 05-SUMMARY.md; STATE.md

---

## Lessons

### Fail-Closed Artifacts Are Successful Guardrails, Not Implementation Failure
The local Phase 5 artifacts correctly report `missing_canonical_spans`, `corpus_mismatch`, `missing_judgment_rows`, and `unknown_hit` instead of allowing a misleading Level assessment.

**Context:** `active_version_counts.json` and `validation_integrity_report.json` are blocked because the local environment lacks `DATABASE_URL` and the existing judgment file belongs to the old corpus.
**Source:** 05-SUMMARY.md; STATE.md

---

### GSD Plan Discovery Can Miss Phase-Numbered Plan Files
`gsd-tools init execute-phase` returned `plan_count=0` even though `05-PLAN-01.md` through `05-PLAN-04.md` existed and were valid.

**Context:** Phase 5 had to be executed manually by reading the plan files, grouping waves, applying the tasks, and reconciling STATE/ROADMAP afterward. This created a navigator loop until bookkeeping was updated.
**Source:** STATE.md; 05-SUMMARY.md

---

### Review Findings Need Evidence Reconciliation
Some review findings were stale or false positives (for example missing resolver tests and missing package imports), while others were real high-value fixes (bounded LLM response parsing and narrower exception handling).

**Context:** Targeted tests already passed, but final focused reviews still caught real hardening opportunities. The correct response was to verify each finding against code and tests rather than blindly accept or dismiss all findings.
**Source:** STATE.md; 05-SUMMARY.md

---

### DB-Backed Verification Is a Separate Gate From Code Completion
Phase 5 delivered the diagnostic utilities and gates, but DB-backed proof requires an environment with `DATABASE_URL` and an active version containing materialized spans/chunks.

**Context:** The implementation is test-backed and reviewed, yet the final evidence-chain status remains blocked until the live DB route is run.
**Source:** 05-SUMMARY.md

---

### Human Judgment Must Be Downstream of Evidence Integrity
Human judgment collection is useful only after retrieval artifacts and evidence-chain metrics are internally consistent.

**Context:** Phase 4 showed that collecting or reusing judgments against the wrong corpus invalidates metric calculation. Phase 5 gates now keep judgment collection blocked until artifacts match.
**Source:** 05-PLAN-04.md; 05-SUMMARY.md

---

## Patterns

### Active-Version Diagnostic Report Pattern
Build a standalone verification utility that resolves or accepts `active_version_id`, computes registry-backed counts, writes a JSON artifact, and classifies the readiness state.

**When to use:** Use when production quality depends on version-scoped persistence state and global DB counts can hide wrong-version or wrong-scope bugs.
**Source:** 05-PLAN-01.md; 05-SUMMARY.md

---

### Materialize-Then-Recheck Checkpoint Pattern
Run evidence-chain counts before materialization, invoke an idempotent loader, then rerun counts and persist before/after artifacts.

**When to use:** Use when an ingestion step may be skipped or partially completed and needs explicit repair/readiness proof before retrieval validation.
**Source:** 05-PLAN-02.md; 05-SUMMARY.md

---

### Shared Resolver With Fallback Order Pattern
Encapsulate evidence payload hydration in a shared resolver and keep it downstream of ranking/selection so presentation content cannot influence retrieval decisions.

**When to use:** Use when multiple retrieval backends need identical content hydration while preserving independent ranking and selection logic.
**Source:** 05-PLAN-03.md; 05-SUMMARY.md

---

### Fail-Closed Validation Gate Pattern
Before calculating metrics, validate retrieval/judgment row identity, corpus markers, evidence-chain classification, and required artifact presence; exit non-zero on mismatch.

**When to use:** Use whenever quality metrics combine artifacts produced at different times, from different corpora, or through human-in-the-loop judgment.
**Source:** 05-PLAN-04.md; 05-SUMMARY.md

---

### Navigator State Reconciliation Pattern
When execution is completed manually due orchestration/tooling failure, update STATE, ROADMAP, and workspace memory to the truthful next lifecycle position so navigator does not reopen completed work.

**When to use:** Use after manual fallback execution or partial automation failure where code/artifacts are complete but workflow metadata still points to an earlier stage.
**Source:** STATE.md

---

## Surprises

### Local Gate Blocked Before DB Investigation Could Run
The active-version diagnostics worked, but immediately classified local state as `missing_canonical_spans` because `DATABASE_URL` was not configured.

**Impact:** Phase 5 could close implementation, but live DB verification became an explicit follow-up blocker rather than a completed proof.
**Source:** 05-SUMMARY.md

---

### Existing Retrieval/Judgment Artifacts Had More Mismatch Than Expected
The integrity report found `unknown_hit`, `missing_judgment_rows`, and `corpus_mismatch` simultaneously.

**Impact:** The gate proved Phase 4's invalid assessment class was real and multi-causal, reinforcing that judgment collection must wait for fresh matched artifacts.
**Source:** 05-SUMMARY.md

---

### Review Agents Found Both False Positives and Real Security Hardening
Initial review output included stale findings that contradicted current files, but later focused review found real high-value issues in LLM response bounds and broad exception handling.

**Impact:** The workflow needed evidence-based triage. Final fixes increased security posture and test coverage without broad refactoring.
**Source:** STATE.md; 05-SUMMARY.md

---

### Planning Metadata Became the Workflow Bottleneck
After implementation and review passed, navigator still recommended `/gsd-execute-phase` because STATE and ROADMAP still said Phase 5 was ready to execute.

**Impact:** Closure required explicit state reconciliation. Without it, the navigator loop would keep sending the project back to already-completed execution.
**Source:** STATE.md
