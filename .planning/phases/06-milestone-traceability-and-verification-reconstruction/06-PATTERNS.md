# Phase 6 Patterns — Traceability and Verification Reconstruction

## Source Analog Map

| Target artifact | Closest existing analog | Pattern to reuse |
|-----------------|-------------------------|------------------|
| `.planning/PROJECT.md` | `.planning/STATE.md`, `.planning/ROADMAP.md` | Brownfield current-state summary; preserve core value and current blockers. |
| `.planning/REQUIREMENTS.md` | `.planning/v1.0-MILESTONE-AUDIT.md`, ROADMAP phase goals | Traceability table keyed by REQ IDs, phase, status, evidence. |
| `01-VERIFICATION.md` | ROADMAP Phase 1 + recent commits | Reconstructed verification with source attribution. |
| `02-VERIFICATION.md` | `02-SUMMARY.md`, `02-VALIDATION.md` | Completed validation framework with fixture-provisional caveat. |
| `03-VERIFICATION.md` | STATE baseline history + `verification/phase3-real-validation/*` | Authoritative Level 2 real validation record. |
| `04-VERIFICATION.md` | `04-SUMMARY.md`, `04-LEARNINGS.md`, phase4 validation artifacts | Closed-with-blockers report preserving invalid Level 3 discard. |
| `05-VERIFICATION.md` | `05-SUMMARY.md`, `05-LEARNINGS.md`, phase5 artifacts | Closed-with-DB-blockers report preserving fail-closed gates. |
| `06-VALIDATION.md` | GSD VALIDATION template + Phase 5 validation style | Planning-doc verification strategy with grep-based checks. |

## Recommended File Patterns

### PROJECT.md

Use sections:

```markdown
# PROJECT — PageIndex Quality-Verified Main-Function Readiness

## What This Is
...

## Core Value
...

## Current State
...

## Requirements
### Validated
### Active / Blocked
### Out of Scope

## Key Decisions
| Date | Decision | Outcome |
```

Keep it concise and current. Do not archive all phase details; link to ROADMAP/STATE/audit.

### REQUIREMENTS.md

Use a traceability table:

```markdown
| ID | Requirement | Priority | Phase | Status | Evidence | Notes |
|----|-------------|----------|-------|--------|----------|-------|
| REQ-P2-VALIDATION-FRAMEWORK | ... | must | 2 | Complete | `02-SUMMARY.md` | ... |
```

Use statuses:

- `Complete`
- `Closed with blockers`
- `Pending`

Add a coverage summary at top:

```markdown
Coverage: 6 complete / 3 closed with blockers / 3 pending
```

### VERIFICATION.md

Use consistent sections:

```markdown
# Phase N Verification — Name

**Status:** Passed | Closed with blockers | Reconstructed from evidence
**Verification date:** YYYY-MM-DD
**Source basis:** list of source files

## Requirements Coverage
| Requirement | Status | Evidence |

## Evidence Reviewed
...

## Gaps / Blockers
...

## Audit Implication
...
```

Every reconstructed report should include `Reconstructed from evidence` if no original verification existed.

### VALIDATION.md reconciliation

Only change status rows from pending to green when a summary or artifact records the exact command/result. If evidence is incomplete, set status to `⚠️ partial` rather than `✅ green`.

## Data Flow

```text
ROADMAP + STATE + summaries + validation artifacts
  -> PROJECT.md current state
  -> REQUIREMENTS.md traceability
  -> per-phase VERIFICATION.md
  -> rerun /gsd-audit-milestone
```

## Anti-Patterns

- Do not mark Phase 4 or Phase 5 as clean pass.
- Do not mark Level 3/4 authoritative.
- Do not invent Phase 1/3 implementation details beyond ROADMAP/STATE/commit evidence.
- Do not delete old artifacts during reconstruction.
- Do not commit/tag during Phase 6.
