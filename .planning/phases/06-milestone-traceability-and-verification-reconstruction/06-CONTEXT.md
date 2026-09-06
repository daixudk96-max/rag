# Phase 6: Milestone Traceability and Verification Reconstruction — Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** Gap-closure planning from `.planning/v1.0-MILESTONE-AUDIT.md`

<domain>
## Phase Boundary

Phase 6 is a planning-artifact and verification-reconstruction phase. It does **not** advance PageIndex quality level and does **not** perform DB-backed validation. Its job is to restore the missing milestone-close inputs that caused the v1.0 audit to return `gaps_found`:

- `.planning/PROJECT.md` is missing.
- `.planning/REQUIREMENTS.md` is missing.
- No `.planning/phases/*/*-VERIFICATION.md` files exist for phases 1-5.
- Phase 1 and Phase 3 phase directories are missing from `.planning/phases/`.
- Phase 2/4/5 `VALIDATION.md` files have pending/incomplete status rows that conflict with later summary-level closure records.

The phase succeeds when a new milestone audit can perform the required 3-source cross-reference: requirements traceability, phase verification artifacts, and summary/completion evidence.
</domain>

<decisions>
## Implementation Decisions

### D-06-01: Restore traceability before DB rerun
Phase 6 must run before Phase 7 because Phase 7 depends on a clean audit surface and because `.planning/REQUIREMENTS.md` is currently missing.

### D-06-02: Verification reconstruction must be evidence-attributed
Phase verification reports may be reconstructed from ROADMAP, STATE, summaries, validation artifacts, and validation JSON files, but each claim must name its source. Do not invent completion evidence.

### D-06-03: Blockers are valid verification outcomes
Phase 4 and Phase 5 should not be rewritten as clean passes. Their verification artifacts must preserve the documented blockers: evidence-chain zeros, invalid Phase 4 Level 3 discarded, DB-backed verification blocked, and human judgment collection blocked.

### D-06-04: REQUIREMENTS.md must encode both satisfied and blocked requirements
The rebuilt requirements file must not mark final quality readiness as complete until DB-backed evidence-chain verification and matched validation rerun are complete. Level 2 remains authoritative.

### D-06-05: Nyquist reconciliation is bookkeeping, not retroactive test execution
Updating `VALIDATION.md` should reconcile status rows with actual recorded evidence and summaries. It must not claim tests were run unless the corresponding summary or artifact records the command/result.

### D-06-06: No milestone commit/tag during Phase 6
Because the working tree has many unrelated modifications, Phase 6 only prepares the audit surface. Phase 9 owns safe staging/commit/tag planning.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit and state
- `.planning/v1.0-MILESTONE-AUDIT.md` — authoritative list of audit gaps Phase 6 closes.
- `.planning/ROADMAP.md` — phase goals, statuses, and Phase 6 gap-closure scope.
- `.planning/STATE.md` — accumulated decisions, baseline history, and current routing.
- `.planning/workspace-memory.json` — navigator continuity and next recommendation.

### Existing phase evidence
- `.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md` — Phase 2 completion evidence.
- `.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VALIDATION.md` — Phase 2 Nyquist/validation strategy to reconcile.
- `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md` — Phase 4 closure evidence and blockers.
- `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VALIDATION.md` — Phase 4 validation strategy to reconcile.
- `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md` — Phase 5 closure evidence and blockers.
- `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VALIDATION.md` — Phase 5 validation strategy to reconcile.
- `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-LEARNINGS.md` — Phase 5 missing-artifact and fail-closed learnings.

### Validation artifacts
- `verification/phase4-quality-validation/level_assessment.json` — authoritative Level 2 preservation.
- `verification/phase5-evidence-chain-verification/active_version_counts.json` — local DB-backed diagnostics blocked state.
- `verification/phase5-evidence-chain-verification/validation_integrity_report.json` — current integrity gate blockers.
- `verification/phase4-quality-validation/db-backed-node-aware-rerun-20260607/validation_status.json` — DB-backed snapshot showing evidence-chain zeros.
</canonical_refs>

<specifics>
## Specific Ideas

- Create `.planning/REQUIREMENTS.md` with explicit REQ IDs that map the v1.0 milestone:
  - `REQ-P1-TECH-INTEGRATION`
  - `REQ-P2-VALIDATION-FRAMEWORK`
  - `REQ-P3-REAL-BASELINE`
  - `REQ-P4-BASELINE-RECONCILIATION`
  - `REQ-P4-CORPUS-ALIGNMENT`
  - `REQ-P4-EVIDENCE-CHAIN-BLOCKERS-DOCUMENTED`
  - `REQ-P5-ACTIVE-VERSION-DIAGNOSTICS`
  - `REQ-P5-RESOLVER-CONSOLIDATION`
  - `REQ-P5-INTEGRITY-GATE`
  - `REQ-P6-TRACEABILITY-RESTORED`
- Mark requirements as `Complete`, `Closed with blockers`, or `Pending`, not just checked/unchecked.
- Create `01-VERIFICATION.md` and `03-VERIFICATION.md` directories/reports from ROADMAP, STATE, commits, and validation artifacts; clearly mark them as reconstructed.
- Each reconstructed `*-VERIFICATION.md` should include status, evidence sources, requirements coverage, gaps, and audit implications.
</specifics>

<deferred>
## Deferred Ideas

- DB-backed evidence-chain materialization and rerun are deferred to Phase 7.
- Matched retrieval/judgment/Level assessment rerun is deferred to Phase 8.
- Dirty working tree cleanup, commit scoping, and milestone tag are deferred to Phase 9.
</deferred>

---

*Phase: 06-milestone-traceability-and-verification-reconstruction*
*Context gathered: 2026-06-08 via gap-closure planning*
