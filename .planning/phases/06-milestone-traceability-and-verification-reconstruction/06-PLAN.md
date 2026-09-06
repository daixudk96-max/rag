---
phase: 06-milestone-traceability-and-verification-reconstruction
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/PROJECT.md
  - .planning/REQUIREMENTS.md
  - .planning/phases/01-pageindex-bug-fix/01-VALIDATION.md
  - .planning/phases/01-pageindex-bug-fix/01-VERIFICATION.md
  - .planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VALIDATION.md
  - .planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VERIFICATION.md
  - .planning/phases/03-pageindex-real-quality-validation-and-quality-improvement/03-VALIDATION.md
  - .planning/phases/03-pageindex-real-quality-validation-and-quality-improvement/03-VERIFICATION.md
  - .planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VALIDATION.md
  - .planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VERIFICATION.md
  - .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VALIDATION.md
  - .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md
  - .planning/phases/06-milestone-traceability-and-verification-reconstruction/06-SUMMARY.md
requirements:
  - REQ-TRACEABILITY-MISSING
  - PHASE-VERIFICATION-MISSING
  - NYQUIST-BOOKKEEPING-PARTIAL
  - AUDIT-RERUN-READY
autonomous: true
---

<objective>
Restore the milestone planning and verification surface required by `/gsd-audit-milestone`: recreate PROJECT/REQUIREMENTS traceability, reconstruct phases 1-5 verification artifacts with source attribution, reconcile validation/Nyquist bookkeeping, and prepare the milestone for a meaningful re-audit without changing PageIndex runtime behavior or advancing the authoritative Level 2 baseline.
</objective>

<must_haves>
  <truths>
    <truth>`.planning/PROJECT.md` exists and describes the brownfield PageIndex quality-readiness program, current Level 2 baseline, and Phases 6-9 gap-closure roadmap.</truth>
    <truth>`.planning/REQUIREMENTS.md` exists and contains explicit REQ IDs, phase assignments, status, evidence, and notes for v1.0 traceability.</truth>
    <truth>Each phase 1-5 has a `*-VERIFICATION.md` artifact with source-attributed evidence and explicit status.</truth>
    <truth>Phase 4 and Phase 5 verification reports preserve blockers; they are not rewritten as clean passes.</truth>
    <truth>Level 2 remains authoritative until Phase 8 produces matched DB-backed validation and a valid `level_assessment.json`.</truth>
    <truth>Phase 6 does not commit, tag, or clean the dirty working tree; Phase 9 owns git hygiene.</truth>
  </truths>
  <key_links>
    <link from=".planning/v1.0-MILESTONE-AUDIT.md" to=".planning/REQUIREMENTS.md" via="audit gaps become explicit traceability rows" pattern="REQ-TRACEABILITY-MISSING|PHASE-VERIFICATION-MISSING|DB-BACKED-VALIDATION-BLOCKED" />
    <link from=".planning/ROADMAP.md" to=".planning/phases/*/*-VERIFICATION.md" via="phase goals/statuses become verification scope and audit implications" pattern="Phase 1|Phase 2|Phase 3|Phase 4|Phase 5" />
    <link from="verification/phase5-evidence-chain-verification/validation_integrity_report.json" to=".planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md" via="fail-closed integrity blocker evidence" pattern="unknown_hit|missing_judgment_rows|corpus_mismatch|missing_canonical_spans" />
  </key_links>
</must_haves>

<threat_model>
  <threat id="T-06-01" severity="high" stride="Tampering">
    Reconstructed planning artifacts could falsely mark blocked requirements as complete, causing a future milestone audit or close to pass without DB-backed validation.
    Mitigation: use explicit statuses `Complete`, `Closed with blockers`, and `Pending`; require evidence source paths in every requirement and verification report; grep for `Level 2 remains authoritative` across reconstructed artifacts.
  </threat>
  <threat id="T-06-02" severity="medium" stride="Repudiation">
    Future reviewers may not know which verification claims were reconstructed after the fact.
    Mitigation: every reconstructed `*-VERIFICATION.md` must include `Source basis:` and must state `Reconstructed from evidence` where no original verification report existed.
  </threat>
  <threat id="T-06-03" severity="medium" stride="Information Disclosure">
    Verification artifacts could leak raw database URLs or sensitive environment values while documenting DB blockers.
    Mitigation: artifacts may mention `DATABASE_URL configured/unset` but must not include raw connection strings.
  </threat>
</threat_model>

<tasks>
  <task type="auto">
    <name>Task 01-01: Recreate PROJECT and REQUIREMENTS traceability</name>
    <read_first>
      - E:/github/rag/.planning/v1.0-MILESTONE-AUDIT.md
      - E:/github/rag/.planning/ROADMAP.md
      - E:/github/rag/.planning/STATE.md
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-CONTEXT.md
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-RESEARCH.md
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-PATTERNS.md
    </read_first>
    <action>
      Create `.planning/PROJECT.md` with these exact top-level sections:
      - `# PROJECT — PageIndex Quality-Verified Main-Function Readiness`
      - `## What This Is`
      - `## Core Value`
      - `## Current State`
      - `## Requirements`
      - `## Key Decisions`
      - `## Known Blockers`
      - `## Next Milestone / Gap-Closure Route`

      The `## Core Value` section must contain the exact sentence: `Raise PageIndex from technical integration to quality-verified main-function readiness.`

      The `## Current State` section must contain:
      - `Authoritative baseline: Level 2`
      - `Level 2 remains authoritative until matched DB-backed validation produces a valid level_assessment.json.`
      - `Current route: Phase 6 -> Phase 7 -> Phase 8 -> Phase 9`

      Create `.planning/REQUIREMENTS.md` with these exact top-level sections:
      - `# REQUIREMENTS — v1.0 PageIndex Quality-Verified Main-Function Readiness`
      - `## Coverage Summary`
      - `## Traceability Table`
      - `## Requirement Outcomes`
      - `## Audit Notes`

      The `## Traceability Table` must include columns exactly:
      `| ID | Requirement | Priority | Phase | Status | Evidence | Notes |`

      Add these requirement rows with these IDs and statuses:
      - `REQ-P1-TECH-INTEGRATION` — Phase 1 — `Complete`
      - `REQ-P2-VALIDATION-FRAMEWORK` — Phase 2 — `Complete`
      - `REQ-P3-REAL-BASELINE` — Phase 3 — `Complete`
      - `REQ-P4-BASELINE-RECONCILIATION` — Phase 4 — `Complete`
      - `REQ-P4-CORPUS-ALIGNMENT` — Phase 4 — `Complete`
      - `REQ-P4-EVIDENCE-CHAIN-BLOCKERS-DOCUMENTED` — Phase 4 — `Closed with blockers`
      - `REQ-P5-ACTIVE-VERSION-DIAGNOSTICS` — Phase 5 — `Complete`
      - `REQ-P5-RESOLVER-CONSOLIDATION` — Phase 5 — `Complete`
      - `REQ-P5-INTEGRITY-GATE` — Phase 5 — `Complete`
      - `REQ-P7-DB-EVIDENCE-CHAIN-PROOF` — Phase 7 — `Pending`
      - `REQ-P8-MATCHED-VALIDATION-RERUN` — Phase 8 — `Pending`
      - `REQ-P9-SAFE-MILESTONE-CLOSE` — Phase 9 — `Pending`

      The coverage summary must include the exact line: `Coverage: 7 Complete / 1 Closed with blockers / 4 Pending`.
      The audit notes must state that `.planning/REQUIREMENTS.md` was reconstructed during Phase 6 from ROADMAP, STATE, audit, summaries, and validation artifacts.
    </action>
    <acceptance_criteria>
      - `.planning/PROJECT.md` exists.
      - `.planning/PROJECT.md` contains `Raise PageIndex from technical integration to quality-verified main-function readiness.`
      - `.planning/PROJECT.md` contains `Authoritative baseline: Level 2`.
      - `.planning/PROJECT.md` contains `Current route: Phase 6 -> Phase 7 -> Phase 8 -> Phase 9`.
      - `.planning/REQUIREMENTS.md` exists.
      - `.planning/REQUIREMENTS.md` contains `Coverage: 7 Complete / 1 Closed with blockers / 4 Pending`.
      - `.planning/REQUIREMENTS.md` contains all 12 `REQ-P` IDs listed in this task.
      - `.planning/REQUIREMENTS.md` contains `REQ-P7-DB-EVIDENCE-CHAIN-PROOF` and `Pending` on the same row.
      - `.planning/REQUIREMENTS.md` contains `REQ-P8-MATCHED-VALIDATION-RERUN` and `Pending` on the same row.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "Authoritative baseline: Level 2" .planning/PROJECT.md`</automated>
      <automated>`rtk grep "Coverage: 7 Complete / 1 Closed with blockers / 4 Pending" .planning/REQUIREMENTS.md`</automated>
      <automated>`rtk grep "REQ-P8-MATCHED-VALIDATION-RERUN" .planning/REQUIREMENTS.md`</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 01-02: Reconstruct phases 1-5 verification artifacts</name>
    <read_first>
      - E:/github/rag/.planning/ROADMAP.md
      - E:/github/rag/.planning/STATE.md
      - E:/github/rag/.planning/REQUIREMENTS.md
      - E:/github/rag/.planning/v1.0-MILESTONE-AUDIT.md
      - E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md
      - E:/github/rag/.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md
      - E:/github/rag/.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md
      - E:/github/rag/verification/phase4-quality-validation/level_assessment.json
      - E:/github/rag/verification/phase5-evidence-chain-verification/validation_integrity_report.json
    </read_first>
    <action>
      Create missing directories if needed:
      - `.planning/phases/01-pageindex-bug-fix/`
      - `.planning/phases/03-pageindex-real-quality-validation-and-quality-improvement/`

      Create these verification files:
      - `.planning/phases/01-pageindex-bug-fix/01-VERIFICATION.md`
      - `.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VERIFICATION.md`
      - `.planning/phases/03-pageindex-real-quality-validation-and-quality-improvement/03-VERIFICATION.md`
      - `.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VERIFICATION.md`
      - `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md`

      Every verification file must include these exact section headings:
      - `# Phase N Verification — {phase name}`
      - `## Verification Status`
      - `## Source Basis`
      - `## Requirements Coverage`
      - `## Evidence Reviewed`
      - `## Gaps / Blockers`
      - `## Audit Implication`

      Set statuses exactly:
      - Phase 1: `Status: Passed (reconstructed from evidence)`
      - Phase 2: `Status: Passed for validation framework; quality level remains non-authoritative fixture result`
      - Phase 3: `Status: Passed for real baseline discovery; quality readiness not achieved`
      - Phase 4: `Status: Closed with blockers`
      - Phase 5: `Status: Closed with DB-backed blockers documented`

      Requirements coverage must map:
      - Phase 1 -> `REQ-P1-TECH-INTEGRATION`
      - Phase 2 -> `REQ-P2-VALIDATION-FRAMEWORK`
      - Phase 3 -> `REQ-P3-REAL-BASELINE`
      - Phase 4 -> `REQ-P4-BASELINE-RECONCILIATION`, `REQ-P4-CORPUS-ALIGNMENT`, `REQ-P4-EVIDENCE-CHAIN-BLOCKERS-DOCUMENTED`
      - Phase 5 -> `REQ-P5-ACTIVE-VERSION-DIAGNOSTICS`, `REQ-P5-RESOLVER-CONSOLIDATION`, `REQ-P5-INTEGRITY-GATE`

      Phase 4 `## Gaps / Blockers` must contain exact strings:
      - `chunks=0`
      - `mapped_chunks=0`
      - `heading_path_rate=0`
      - `invalid Level 3 discarded`

      Phase 5 `## Gaps / Blockers` must contain exact strings:
      - `DATABASE_URL is unset`
      - `unknown_hit`
      - `missing_judgment_rows`
      - `corpus_mismatch`
      - `missing_canonical_spans`

      Each file's `## Audit Implication` must state whether it supports audit pass, audit pass with blockers, or pending follow-up.
    </action>
    <acceptance_criteria>
      - All five `*-VERIFICATION.md` files exist.
      - `01-VERIFICATION.md` contains `REQ-P1-TECH-INTEGRATION`.
      - `02-VERIFICATION.md` contains `REQ-P2-VALIDATION-FRAMEWORK`.
      - `03-VERIFICATION.md` contains `REQ-P3-REAL-BASELINE` and `Level 2`.
      - `04-VERIFICATION.md` contains `Closed with blockers`.
      - `04-VERIFICATION.md` contains `invalid Level 3 discarded`.
      - `05-VERIFICATION.md` contains `Closed with DB-backed blockers documented`.
      - `05-VERIFICATION.md` contains `missing_canonical_spans`.
      - `rtk grep "## Requirements Coverage" .planning/phases/*/*-VERIFICATION.md` returns matches for five verification files.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "## Requirements Coverage" .planning/phases/*/*-VERIFICATION.md`</automated>
      <automated>`rtk grep "invalid Level 3 discarded" .planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VERIFICATION.md`</automated>
      <automated>`rtk grep "missing_canonical_spans" .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md`</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 01-03: Reconcile validation and Nyquist bookkeeping</name>
    <read_first>
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-VALIDATION.md
      - E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VALIDATION.md
      - E:/github/rag/.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VALIDATION.md
      - E:/github/rag/.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VALIDATION.md
      - E:/github/rag/.planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-SUMMARY.md
      - E:/github/rag/.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md
      - E:/github/rag/.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md
    </read_first>
    <action>
      Create `.planning/phases/01-pageindex-bug-fix/01-VALIDATION.md` and `.planning/phases/03-pageindex-real-quality-validation-and-quality-improvement/03-VALIDATION.md` using the Phase 6 validation pattern.

      The Phase 1 validation file must include:
      - frontmatter `phase: 1`
      - frontmatter `nyquist_compliant: true`
      - section `## Validation Sign-Off`
      - line `**Approval:** reconstructed from Phase 1 completion evidence`

      The Phase 3 validation file must include:
      - frontmatter `phase: 3`
      - frontmatter `nyquist_compliant: true`
      - section `## Validation Sign-Off`
      - line `**Approval:** reconstructed from Phase 3 real-validation evidence`

      Update Phase 2/4/5 validation files without claiming unrecorded test runs:
      - In `02-VALIDATION.md`, change `**Approval:** pending` to `**Approval:** reconstructed from 02-SUMMARY.md; 31 tests passing recorded`.
      - In `04-VALIDATION.md`, change `**Approval:** pending` to `**Approval:** partial; Phase 4 closed with blockers documented`.
      - In `05-VALIDATION.md`, change `wave_0_complete: false` to `wave_0_complete: true` only if the referenced Wave 0 test files exist; otherwise keep false and add `Wave 0 remains partial`.
      - In `05-VALIDATION.md`, change `**Approval:** pending` to `**Approval:** partial; Phase 5 targeted suite passed but DB-backed proof remains blocked`.

      Do not change `nyquist_compliant: true` to false for phases with existing frontmatter unless the source evidence explicitly contradicts it.
    </action>
    <acceptance_criteria>
      - `01-VALIDATION.md` exists and contains `reconstructed from Phase 1 completion evidence`.
      - `03-VALIDATION.md` exists and contains `reconstructed from Phase 3 real-validation evidence`.
      - `02-VALIDATION.md` contains `31 tests passing recorded`.
      - `04-VALIDATION.md` contains `Phase 4 closed with blockers documented`.
      - `05-VALIDATION.md` contains `Phase 5 targeted suite passed but DB-backed proof remains blocked`.
      - `rtk grep "Approval:" .planning/phases/*/*-VALIDATION.md` returns approval lines for phases 1, 2, 3, 4, 5, and 6.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "Approval:" .planning/phases/*/*-VALIDATION.md`</automated>
      <automated>`rtk grep "31 tests passing recorded" .planning/phases/02-pageindex-main-function-quality-validation-and-closure/02-VALIDATION.md`</automated>
      <automated>`rtk grep "DB-backed proof remains blocked" .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VALIDATION.md`</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 01-04: Run audit-readiness checks and write Phase 6 summary</name>
    <read_first>
      - E:/github/rag/.planning/PROJECT.md
      - E:/github/rag/.planning/REQUIREMENTS.md
      - E:/github/rag/.planning/v1.0-MILESTONE-AUDIT.md
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-PLAN.md
      - E:/github/rag/.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-VALIDATION.md
    </read_first>
    <action>
      Run these audit-readiness checks and record their results in `06-SUMMARY.md`:
      - `rtk grep "REQ-P" .planning/REQUIREMENTS.md`
      - `rtk grep "## Requirements Coverage" .planning/phases/*/*-VERIFICATION.md`
      - `rtk grep "Level 2 remains authoritative" .planning/PROJECT.md .planning/REQUIREMENTS.md .planning/phases/*/*-VERIFICATION.md`
      - `rtk grep "Closed with blockers" .planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-VERIFICATION.md`
      - `rtk grep "Closed with DB-backed blockers documented" .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md`

      Create `.planning/phases/06-milestone-traceability-and-verification-reconstruction/06-SUMMARY.md` with these sections:
      - `# Phase 6 Summary — Milestone Traceability and Verification Reconstruction`
      - `## Completion Status`
      - `## Artifacts Created`
      - `## Requirements Restored`
      - `## Verification Reconstruction`
      - `## Validation/Nyquist Reconciliation`
      - `## Audit Readiness Checks`
      - `## Remaining Blockers Deferred to Later Phases`
      - `## Next Route`

      The `## Next Route` section must contain exactly:
      `Next recommended command: /gsd-audit-milestone`

      The remaining blockers section must list:
      - `Phase 7: DB-backed evidence-chain rerun`
      - `Phase 8: matched validation rerun and Level assessment`
      - `Phase 9: milestone close readiness and git hygiene`
    </action>
    <acceptance_criteria>
      - `06-SUMMARY.md` exists.
      - `06-SUMMARY.md` contains `Next recommended command: /gsd-audit-milestone`.
      - `06-SUMMARY.md` contains `Phase 7: DB-backed evidence-chain rerun`.
      - `06-SUMMARY.md` contains `Phase 8: matched validation rerun and Level assessment`.
      - `06-SUMMARY.md` contains `Phase 9: milestone close readiness and git hygiene`.
      - All audit-readiness checks listed in the action return at least one match.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "Next recommended command: /gsd-audit-milestone" .planning/phases/06-milestone-traceability-and-verification-reconstruction/06-SUMMARY.md`</automated>
      <automated>`rtk grep "Level 2 remains authoritative" .planning/PROJECT.md .planning/REQUIREMENTS.md .planning/phases/*/*-VERIFICATION.md`</automated>
      <automated>`rtk grep "Closed with DB-backed blockers documented" .planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-VERIFICATION.md`</automated>
    </verify>
  </task>
</tasks>

<verification>
- Run `rtk grep "REQ-P" .planning/REQUIREMENTS.md`.
- Run `rtk grep "## Requirements Coverage" .planning/phases/*/*-VERIFICATION.md`.
- Run `rtk grep "Level 2 remains authoritative" .planning/PROJECT.md .planning/REQUIREMENTS.md .planning/phases/*/*-VERIFICATION.md`.
- Run `rtk grep "Approval:" .planning/phases/*/*-VALIDATION.md`.
- Run `rtk grep "Next recommended command: /gsd-audit-milestone" .planning/phases/06-milestone-traceability-and-verification-reconstruction/06-SUMMARY.md`.
</verification>

<success_criteria>
- `/gsd-audit-milestone` no longer fails merely because `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, or phase verification files are missing.
- Requirements traceability includes explicit complete/blocked/pending statuses for v1.0 and follow-up Phases 7-9.
- Phase 4 and Phase 5 blockers remain visible and are not converted into false passes.
- Level 2 remains authoritative until Phase 8 produces a valid matched assessment.
- Phase 6 summary routes to `/gsd-audit-milestone` before Phase 7 execution.
</success_criteria>
