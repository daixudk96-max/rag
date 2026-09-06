# Phase 9: Milestone Close Readiness and Git Hygiene - Research

**Researched:** 2026-06-08
**Domain:** Milestone closure, git hygiene, working tree classification, GSD state reconciliation
**Confidence:** HIGH

## Summary

Phase 9 must prepare a safe milestone closure surface by isolating planning/archive changes from unrelated working-tree changes before any commit/tag/push action. The working tree has **~150+ untracked files** and **~25 modified files** spanning implementation changes, verification artifacts, planning documents, scratch scripts, and unrelated work-in-progress. The planner must classify these into explicit categories, prepare a staging plan that respects user approval boundaries, and rerun the milestone audit to determine whether a clean close or accepted-blocker close is appropriate.

**Primary recommendation:** Use GSD-owned mechanisms (STATE.md, ROADMAP.md, `/gsd-audit-milestone`, plan phases) to reconcile stale planning text rather than ad hoc edits. Classify dirty-tree scope into four explicit categories: (1) milestone artifacts, (2) implementation changes, (3) generated outputs, (4) unrelated scratch files. Gate commit/tag/push behind explicit user approval at Phase 9 execution time.

<user_constraints>
## User Constraints (from CONTEXT.md)

Phase 9 has no CONTEXT.md yet (this is research phase). Constraints come from objective:

- **Do not commit, tag, push, checkout, reset, clean, delete, or modify code** [VERIFIED: objective]
- **Do not print or store raw DATABASE_URL** [VERIFIED: objective]
- **Phase 8 is complete but Level_2 remains authoritative** [VERIFIED: 08-SUMMARY.md, 08-VERIFICATION.md]
- **Phase 9 must close GIT-HYGIENE-DEBT by classifying dirty worktree scope and preparing explicit user approval boundaries** [VERIFIED: objective]
- **The plan must support workflow/chunked execution** [VERIFIED: objective]
- **It must account for stale planning text in STATE.md / ROADMAP.md without uncontrolled edits** [VERIFIED: objective]

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-P9-SAFE-MILESTONE-CLOSE | Isolate dirty working tree and prepare safe milestone close/commit/tag scope. | Dirty tree classification patterns, git hygiene practices, GSD state reconciliation mechanisms, approval gate patterns |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Working tree classification | Git CLI / GSD planning | — | Classification uses git status + planner reasoning, not code execution |
| Stale text reconciliation | GSD state mechanisms | Git commit | STATE.md/ROADMAP.md updates via GSD-owned commands, not ad hoc file edits |
| Milestone audit | GSD audit command | — | `/gsd-audit-milestone` owns the audit, planner prepares scope |
| Commit/tag/push gates | User approval | GSD execution | Actions gated behind explicit approval, not automatic |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| git | 2.47.1 | Working tree classification, staging, commit, tag | Only safe mechanism for milestone closure |
| GSD workflow | — | Chunked execution, STATE/ROADMAP mechanisms, audit | Project uses GSD for phase planning, prevents ad hoc edits |
| gh CLI | 2.85.0 | Remote repository operations (if needed) | GitHub CLI for PRs, releases, remote checks |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PowerShell | Windows 11 | Shell commands | Git operations, file checks |
| Python 3.x | — | Artifact generation scripts | Verification scripts, classification helpers |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Git stash for WIP isolation | Checkpoint commits + rebase | Stash is reversible; checkpoint commits require history rewriting |
| Ad hoc STATE.md edits | GSD mechanisms | Ad hoc edits violate GSD architecture; use `/gsd:complete-milestone` or plan-phase |

**Installation:**
Already installed: git 2.47.1, gh CLI 2.85.0, PowerShell, Python.

**Version verification:**
```
git version 2.47.1.windows.2 [VERIFIED: git --version]
gh version 2.85.0 (2026-01-14) [VERIFIED: gh --version]
```

## Architecture Patterns

### System Architecture Diagram

```
Dirty Working Tree
       │
       ├─► Classification (Git Status + Planner Reasoning)
       │        │
       │        ├─► Milestone Artifacts (.planning/, verification/phase8-*, RESEARCH.md)
       │        ├─► Implementation Changes (llamaindex_runtime/*, tests/*)
       │        ├─► Generated Outputs (verification/phase4-quality-validation/db-backed-node-aware-rerun-20260607/*)
       │        ├─► Unrelated Scratch Files (*.py scratch scripts, .autod/, .claude-plugin/, etc.)
       │        │
       │        └─► Classification Report
       │
       ├─► Stale Text Reconciliation
       │        │
       │        ├─► STATE.md updates (via GSD mechanisms, not ad hoc)
       │        ├─► ROADMAP.md updates (via GSD mechanisms)
       │        ├─► Milestone audit rerun (/gsd-audit-milestone)
       │        │
       │        └─► Reconciliation Status Report
       │
       ├─► Milestone Audit Rerun
       │        │
       │        ├─► REQ-P8-MATCHED-VALIDATION-RERUN verification
       │        ├─► REQ-P9-SAFE-MILESTONE-CLOSE check
       │        ├─► Gap closure status
       │        │
       │        └─► Audit Decision: clean close OR accepted-blocker close
       │
       └─► Staging Plan Preparation
                │
                ├─► Milestone artifact staging list
                ├─► Implementation change staging list (optional, user choice)
                ├─► Generated output staging list (optional)
                ├─│ Unrelated files: EXPLICITLY EXCLUDED from staging
                │
                └─► Approval Gate: User must approve final staging scope before commit
```

### Recommended Project Structure

Phase 9 artifacts should be created under:
```
.planning/phases/09-milestone-close-readiness-and-git-hygiene/
├── 09-RESEARCH.md (this file)
├── 09-PLAN-*.md (generated by planner)
├── 09-SUMMARY.md (after execution)
├── 09-VERIFICATION.md (after execution)
└── classification_report.json (execution artifact)
```

Execution artifacts may also be written to:
```
verification/phase9-milestone-close/
├── classification_report.json
├── stale_text_reconciliation.json
├── audit_rerun_status.json
├── staging_plan.json
└── final_closure_decision.json
```

### Pattern 1: Working Tree Classification

**What:** Categorize dirty working tree into four buckets: milestone artifacts, implementation changes, generated outputs, unrelated scratch files.

**When to use:** Before any staging/commit action in milestone closure phases.

**Example:**
```bash
# Classification approach (planner reasoning + git status)
git status --short  # produces modified/untracked file list

# Planner categorizes each file/dir:
# 1. Milestone artifacts: .planning/phases/*-RESEARCH.md, *-PLAN.md, *-SUMMARY.md, *-VERIFICATION.md
# 2. Implementation changes: llamaindex_runtime/*, tests/* (if Phase 8 execution modified these)
# 3. Generated outputs: verification/phase*/ artifacts produced during execution
# 4. Unrelated scratch: *.py scratch scripts, .autod/, .claude-plugin/, temp files
```

**Source:** [CITED: Git SCM - git status](https://git-scm.com/docs/git-status)

### Pattern 2: Git Stash for WIP Isolation

**What:** Stash unrelated WIP changes before milestone commit, restore after.

**When to use:** When dirty tree contains unrelated WIP that shouldn't be in milestone commit.

**Example:**
```bash
# Save WIP changes (excluding milestone artifacts)
git stash push -m "WIP: unrelated milestone work" -- <wip-files>

# Commit milestone artifacts
git add .planning/phases/09-*
git commit -m "docs(phase9): complete milestone close readiness research"

# Restore WIP
git stash pop
```

**Source:** [CITED: Git SCM - Stashing and Cleaning](https://git-scm.com/book/en/v2/Git-Tools-Stashing-and-Cleaning)

### Pattern 3: Partial Staging with git add -p

**What:** Interactively stage only milestone-related hunks/files.

**When to use:** When milestone artifacts are interleaved with unrelated changes in same files.

**Example:**
```bash
# Interactively review and stage only milestone-related changes
git add -p  # choose 'y' for milestone hunks, 'n' for unrelated

# Commit staged milestone changes
git commit -m "docs(phase9): milestone close readiness"
```

**Source:** [CITED: Git SCM - git add --patch](https://git-scm.com/docs/git-add)

### Pattern 4: GSD State Reconciliation

**What:** Use GSD-owned mechanisms (STATE.md, ROADMAP.md, `/gsd:complete-milestone`) to update stale planning text.

**When to use:** When STATE.md/ROADMAP.md contain outdated phase/blocker language after a phase completes.

**Mechanism:**
- `/gsd:plan-phase` generates plans that may update STATE.md through GSD workflow
- `/gsd:complete-milestone` performs final milestone closure including STATE/ROADMAP updates
- Planner should NOT directly edit STATE.md/ROADMAP.md — use GSD mechanisms instead

**Source:** [CITED: GSD USER-GUIDE.md](https://github.com/gsd-build/get-shit-done/blob/main/docs/USER-GUIDE.md)

### Pattern 5: Milestone Audit Gate

**What:** Rerun `/gsd-audit-milestone` after Phases 6-8 complete to verify gap closure.

**When to use:** Before final milestone close decision.

**Example:**
```bash
# Rerun audit
/gsd-audit-milestone

# Audit returns:
# - "passed" → proceed to clean close
# - "gaps_found" → proceed to accepted-blocker close with explicit debt documentation
```

**Source:** [CITED: GSD Milestone Audit](https://gsd-build-get-shit-done.mintlify.app/workflow/plan-phase)

### Anti-Patterns to Avoid

- **Ad hoc STATE.md edits:** Violates GSD architecture; STATE.md should be updated via GSD mechanisms (`/gsd:complete-milestone`, plan-phase execution).
  - **What to do instead:** Use GSD workflow commands to update state.
- **Commit/tag/push without user approval:** Violates Phase 9 objective; milestone closure requires explicit user approval.
  - **What to do instead:** Prepare staging plan, present to user, gate commit/tag/push behind approval.
- **Staging unrelated files in milestone commit:** Violates milestone scope; milestone commit should only contain milestone artifacts.
  - **What to do instead:** Explicitly exclude unrelated scratch files from staging list.
- **Raw DATABASE_URL in artifacts:** Violates security constraint.
  - **What to do instead:** Reference sanitized status (`database_url_not_configured`) only.
- **Clean milestone close with unresolved blockers:** Violates honest closure principle; if blockers exist, use accepted-blocker close.
  - **What to do instead:** Audit determines clean vs accepted-blocker close; planner follows audit decision.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Working tree classification script | Custom Python script to parse git status | Git CLI + planner reasoning | Git status is sufficient; planner reasoning handles categorization logic |
| Milestone audit rerun | Ad hoc REQUIREMENTS.md verification script | `/gsd-audit-milestone` command | GSD audit is authoritative; custom scripts duplicate logic |
| STATE.md reconciliation | Direct file edit with text replacement | `/gsd:complete-milestone` or plan-phase mechanisms | GSD owns state; ad hoc edits violate architecture |
| Staging plan generator | Custom script to generate git add commands | Planner-generated PLAN.md with staging lists | Planner understands scope; scripts don't |

**Key insight:** GSD workflow provides state management, audit, and completion mechanisms. Hand-rolling these violates architecture and duplicates functionality.

## Runtime State Inventory

> This phase is greenfield (milestone close preparation), not rename/refactor/migration. Omit Runtime State Inventory per template guidance.

## Common Pitfalls

### Pitfall 1: Ad Hoc STATE.md/ROADMAP.md Edits

**What goes wrong:** Planner directly edits STATE.md or ROADMAP.md to remove stale blocker text, violating GSD architecture.

**Why it happens:** Stale text (e.g., Phase 7 blockers in STATE.md when Phase 8 completed) is visible; planner attempts quick fix.

**How to avoid:** Use GSD mechanisms (`/gsd:complete-milestone`, plan-phase execution) to update state. Do NOT use file write/edit tools on STATE.md/ROADMAP.md.

**Warning signs:** Planner attempts to edit `.planning/STATE.md` or `.planning/ROADMAP.md` directly.

### Pitfall 2: Staging Unrelated Files

**What goes wrong:** Milestone commit includes unrelated scratch files (*.py temp scripts, .autod/, .claude-plugin/) because git status shows them and planner didn't explicitly exclude.

**Why it happens:** Dirty tree has many untracked files; planner assumes all should be staged.

**How to avoid:** Classification report must explicitly list "EXCLUDED from staging" category. Staging plan must only include milestone artifacts, implementation changes (optional), generated outputs (optional).

**Warning signs:** Staging list includes files like `_tmp_pageindex_quality_probe.py`, `.autod/`, `.claude-plugin/`.

### Pitfall 3: Commit/Tag/Push Without Approval Gate

**What goes wrong:** Planner executes `git commit`, `git tag v1.0`, or `git push` without user approval, violating Phase 9 objective.

**Why it happens:** Planner assumes milestone close implies automatic commit/tag/push.

**How to avoid:** PLAN.md must include explicit approval gate task: "Present staging plan to user; await approval before commit/tag/push actions."

**Warning signs:** Plan includes `git commit`, `git tag`, or `git push` commands without approval gate task.

### Pitfall 4: Clean Close with Unresolved Blockers

**What goes wrong:** Planner attempts clean milestone close when blockers remain (e.g., Level 2 not meeting Level 4 thresholds, evidence-chain zeros).

**Why it happens:** Planner interprets Phase 9 as "close milestone regardless."

**How to avoid:** Milestone audit rerun determines closure type. If audit returns `gaps_found` or blockers, use accepted-blocker close with explicit debt documentation.

**Warning signs:** Plan assumes clean close without audit rerun, or ignores Level 2 baseline status.

### Pitfall 5: Raw DATABASE_URL Leak

**What goes wrong:** Classification or staging plan artifacts include raw `DATABASE_URL` value.

**Why it happens:** Planner references environment variable values without sanitization.

**How to avoid:** Only reference sanitized status (`database_url_not_configured`). Do NOT print, store, or commit raw `DATABASE_URL`.

**Warning signs:** Artifact contains line like `DATABASE_URL=postgres://...`.

## Code Examples

Verified patterns from official sources:

### Working Tree Classification

```bash
# Source: https://git-scm.com/docs/git-status
# Get modified and untracked files
git status --short

# Output format:
# M .planning/ROADMAP.md
# ?? .autod/
# ?? verification/phase8-matched-validation-rerun/

# Planner categorizes each entry into:
# - Milestone artifacts (.planning/phases/09-*)
# - Implementation changes (llamaindex_runtime/*)
# - Generated outputs (verification/phase8-*)
# - Unrelated scratch (.autod/, temp scripts)
```

### Staging Specific Files

```bash
# Source: https://git-scm.com/docs/git-add
# Stage only milestone artifacts
git add .planning/phases/09-milestone-close-readiness-and-git-hygiene/09-RESEARCH.md
git add .planning/phases/09-milestone-close-readiness-and-git-hygiene/09-PLAN-*.md

# Commit milestone research/plans
git commit -m "docs(phase9): research milestone close readiness and git hygiene"
```

### Milestone Audit Rerun

```bash
# Source: https://gsd-build-get-shit-done.mintlify.app/workflow/plan-phase
# Rerun audit after phases 6-8 complete
/gsd-audit-milestone

# Audit returns JSON with:
# - status: "passed" | "gaps_found"
# - requirements coverage
# - phase verification coverage
# - integration check
# - nyquist coverage
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ad hoc STATE.md edits | GSD mechanisms (`/gsd:complete-milestone`) | GSD architecture introduced | State updates are now workflow-controlled, preventing split-brain |
| Manual milestone audit | `/gsd-audit-milestone` command | GSD architecture introduced | Audit is now automated, authoritative, cross-references REQUIREMENTS/phases/verification |
| Commit all dirty files | Selective staging, stash for WIP | Git workflow best practices established | Milestone commits are now atomic, clean, reversible |

**Deprecated/outdated:**
- `git commit -a` (stages all changes): Replaced by selective staging (`git add -p`, specific file staging) to keep commits atomic.
- Manual REQUIREMENTS.md verification: Replaced by `/gsd-audit-milestone` which cross-references requirements, phases, verification artifacts.

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `/gsd-audit-milestone` will rerun successfully after Phase 8 completion and produce updated gap status. | Pattern 5: Milestone Audit Gate | If audit fails or returns stale pre-Phase 8 status, planner may make incorrect closure decision. |
| A2 | User will provide explicit approval for commit/tag/push actions during Phase 9 execution. | Pattern: Approval Gates | If user expects automatic commit/tag, workflow will stall waiting for approval. |
| A3 | Dirty working tree classification can be performed via git status + planner reasoning without custom script. | Pattern 1: Working Tree Classification | If classification is ambiguous (e.g., implementation changes mixed with milestone artifacts in same file), planner may mis-categorize. |
| A4 | GSD mechanisms (`/gsd:complete-milestone`) will update STATE.md/ROADMAP.md correctly without planner intervention. | Pattern 4: GSD State Reconciliation | If GSD mechanisms don't update stale text, STATE.md will remain outdated, causing split-brain. |
| A5 | Level 2 remains authoritative baseline even after Phase 8 validation confirms same level. | User Constraints | If baseline should have been updated to Phase 8 Level 2 (same level but validated), STATE.md may need clarification. |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions (RESOLVED)

1. **Should Phase 8 implementation changes be included in milestone commit? — RESOLVED**
   - Resolution: Do not decide this automatically. Phase 9 classification separates Phase 8 implementation/test changes from planning and generated validation artifacts. `staging_plan.json` must mark implementation changes as `implementation_changes_optional`, requiring explicit user approval before staging.

2. **How should stale STATE.md/ROADMAP.md text be reconciled? — RESOLVED**
   - Resolution: Reconciliation must happen through Phase 9's GSD-owned execution plan, not ad hoc edits outside the workflow. Plan 09-02 creates a reconciliation evidence map first, then requires a manual checkpoint before any state-critical planning doc update. If later `/gsd:complete-milestone` supersedes these updates, it remains the final milestone owner.

3. **What is final closure decision (clean close vs accepted-blocker close)? — RESOLVED**
   - Resolution: Do not assume either route. Plan 09-03 reruns the milestone audit or writes a fail-closed fallback. `audit_rerun_status.json` must choose `clean_close_ready`, `accepted_blocker_close_ready`, or `blocked` from evidence. Since Phase 8 confirms Level_2, quality threshold misses remain explicit close-readiness concerns.

4. **Should unrelated scratch files be gitignored? — RESOLVED**
   - Resolution: Not automatically in Phase 9. Classification lists unrelated scratch files under `excluded_from_staging`. Any `.gitignore` change is a separate optional user-approved action, not part of the milestone close package unless explicitly approved.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| git | Working tree classification, staging, commit, tag | ✓ | 2.47.1.windows.2 | — |
| gh CLI | Remote repository operations (if needed) | ✓ | 2.85.0 | — |
| GSD workflow | Milestone audit, state reconciliation, chunked execution | ✓ | — (installed) | — |
| PowerShell | Shell commands | ✓ | Windows 11 built-in | — |
| Python 3.x | Artifact generation scripts (if needed) | ✓ | — (installed) | — |

**Missing dependencies with no fallback:**
None — all dependencies available.

**Missing dependencies with fallback:**
None — all dependencies available.

## Validation Architecture

> workflow.nyquist_validation not found in config.json (absent = enabled). Include this section.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (implied from tests/ directory structure) |
| Config file | pytest.ini (exists) |
| Quick run command | `pytest tests/ -q` (estimated <30s for quick subset) |
| Full suite command | `pytest tests/ --tb=short` (full suite) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-P9-SAFE-MILESTONE-CLOSE | Working tree classification produces categorized file list | unit (planner reasoning) | No automated test — planner reasoning task | ❌ Wave 0 |
| REQ-P9-SAFE-MILESTONE-CLOSE | Milestone audit rerun produces updated gap status | integration | `/gsd-audit-milestone` (CLI command) | ✅ (GSD command) |
| REQ-P9-SAFE-MILESTONE-CLOSE | Staging plan excludes unrelated scratch files | unit (plan verification) | No automated test — plan checker task | ❌ Wave 0 |
| REQ-P9-SAFE-MILESTONE-CLOSE | Approval gate prevents commit/tag/push without user OK | manual | Manual checkpoint in execution | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** No automated tests for classification/reconciliation tasks (planner reasoning).
- **Per wave merge:** Milestone audit rerun at final wave.
- **Phase gate:** Milestone audit + verification artifact generation.

### Wave 0 Gaps
- [ ] `tests/verification/test_phase9_milestone_close.py` — covers REQ-P9 classification/audit/reconciliation verification
- [ ] `verification/phase9-milestone-close/classification_report.json` — execution artifact, not pre-existing
- [ ] `verification/phase9-milestone-close/audit_rerun_status.json` — execution artifact

*(No existing test infrastructure for Phase 9 — this is a planning/preparation phase. Tests are not required for planner reasoning tasks. Milestone audit rerun is GSD command, not test file.)*

## Security Domain

> security_enforcement not found in config.json (absent = enabled). Include this section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (Phase 9 is planning/git hygiene, no auth changes) |
| V3 Session Management | no | — (no session changes) |
| V4 Access Control | no | — (no access control changes) |
| V5 Input Validation | no | — (no user input handling) |
| V6 Cryptography | no | — (no crypto changes) |

**Phase 9 is git hygiene/planning — no security-sensitive code changes. Security domain not applicable.**

### Known Threat Patterns for Git Workflow

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Raw DATABASE_URL leak | Information Disclosure | Sanitize all env var references; reference status only (`database_url_not_configured`) |
| Unrelated file staging | Tampering | Explicit classification report; exclude unrelated files from staging list |
| Commit without approval | Tampering | Approval gate in execution plan; user must approve commit/tag/push scope |

## Sources

### Primary (HIGH confidence)
- [Git SCM - git status documentation](https://git-scm.com/docs/git-status) - working tree classification reference
- [Git SCM - git add documentation](https://git-scm.com/docs/git-add) - partial staging reference
- [Git SCM - Stashing and Cleaning](https://git-scm.com/book/en/v2/Git-Tools-Stashing-and-Cleaning) - WIP isolation patterns
- [GSD USER-GUIDE.md](https://github.com/gsd-build/get-shit-done/blob/main/docs/USER-GUIDE.md) - GSD workflow mechanisms, chunked execution, STATE.md management
- [GSD Plan Phase Execution](https://gsd-build-get-shit-done.mintlify.app/workflow/plan-phase) - milestone audit, planning workflow
- [08-SUMMARY.md](E:/github/rag/.planning/phases/08-matched-validation-rerun-and-level-assessment/08-SUMMARY.md) - Phase 8 completion evidence
- [08-VERIFICATION.md](E:/github/rag/.planning/phases/08-matched-validation-rerun-and-level-assessment/08-VERIFICATION.md) - Phase 8 verification evidence
- [REQUIREMENTS.md](E:/github/rag/.planning/REQUIREMENTS.md) - REQ-P9-SAFE-MILESTONE-CLOSE definition
- [ROADMAP.md](E:/github/rag/.planning/ROADMAP.md) - Phase 9 goal/status
- [STATE.md](E:/github/rag/.planning/STATE.md) - Phase 8 baseline, Level 2 status
- [v1.0-MILESTONE-AUDIT.md](E:/github/rag/.planning/v1.0-MILESTONE-AUDIT.md) - pre-Phase 9 audit status

### Secondary (MEDIUM confidence)
- [Git Workflows - Apache DeltaSpike](https://deltaspike.apache.org/suggested-git-workflows.html) - git workflow patterns
- [Git Stash Tutorial - YouTube](https://www.youtube.com/watch?v=urSlkC-6lZE) - stash usage patterns
- [Partial Commits with Git - Abel Nu](https://coding.abel.nu/2014/10/partial-commits-with-git/) - git add -p patterns
- [GSD for Claude Code Deep Dive](https://www.codecentric.de/en/knowledge-hub/blog/the-anatomy-of-claude-code-workflows-turning-slash-commands-into-an-ai-development-system) - GSD architecture overview

### Tertiary (LOW confidence)
- [Reddit - Git workflow discussion](https://www.reddit.com/r/git/comments/1oq5jev/your_git_workflow_is_probably_optimized_for_the/) - community practices (verify with primary sources)
- [Medium - Git Stash for Newbies](https://medium.com/@noorfatimaafzalbutt/save-your-work-without-committing-by-mastering-git-stash-70ee23a9260e) - tutorial content (verify with Git SCM docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - git, GSD, gh CLI verified via tool calls
- Architecture: HIGH - patterns from official Git SCM docs, GSD USER-GUIDE
- Pitfalls: HIGH - derived from Git best practices, GSD architecture, Phase 9 constraints

**Research date:** 2026-06-08
**Valid until:** 30 days (stable domain - Git workflow, GSD architecture unlikely to change significantly)