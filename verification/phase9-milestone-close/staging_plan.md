# Phase 9 Staging Plan

**Requirement:** `REQ-P9-SAFE-MILESTONE-CLOSE`  
**JSON plan:** `verification/phase9-milestone-close/staging_plan.json`  
**approval_required:** true

## Summary

This plan defines what can be staged only after explicit approval. It does not stage anything.

- No commit/tag/push performed.
- No raw DATABASE_URL was written.
- `gitnexus_detect_changes_required`: true.
- Commit/tag/push remain blocked until the user explicitly approves final closure scope.

## Recommended Staging Groups

### 1. Phase 9 close package

Recommended after explicit approval:

- `verification/phase9-milestone-close/classification_report.json`
- `verification/phase9-milestone-close/classification_report.md`
- `verification/phase9-milestone-close/state_reconciliation_report.json`
- `verification/phase9-milestone-close/state_reconciliation_report.md`
- `verification/phase9-milestone-close/audit_rerun_status.json`
- `verification/phase9-milestone-close/audit_rerun_status.md`
- `verification/phase9-milestone-close/staging_plan.json`
- `verification/phase9-milestone-close/staging_plan.md`
- `verification/phase9-milestone-close/final_closure_decision.json`
- `.planning/phases/09-milestone-close-readiness-and-git-hygiene/09-SUMMARY.md`
- `.planning/phases/09-milestone-close-readiness-and-git-hygiene/09-VERIFICATION.md`

### 2. Planning truth updates

Recommended after explicit approval:

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/v1.0-MILESTONE-AUDIT.md`
- `.planning/workspace-memory.json`

### 3. Implementation changes

Do not stage by default.

The classification report found 178 implementation/test paths. These require separate review and approval before they can enter milestone staging.

### 4. Generated outputs

Stage only if explicitly approved.

The classification report found 72 generated-output paths. The safe default is to stage only the Phase 9 close package and any specifically approved validation evidence.

## Explicit Exclusions

The full exclusion list is in `staging_plan.json.excluded_from_staging` and currently contains 481 paths.

Excluded categories include:

- secret-sensitive paths
- unrelated scratch directories
- `.autod/`
- `.claude-plugin/`
- compatibility adapter scratch docs
- broad generated outputs not selected for this approval package
- implementation/test changes not separately approved

## Secret-Sensitive Exclusions

The full secret-sensitive exclusion list is in `staging_plan.json.secret_sensitive_excluded`.

Current secret-sensitive exclusions:

- `.env.example`
- `test_token_measurement.py`

These are excluded from staging unless separately reviewed and approved without printing secret values.

## Required Checks Before Any Future Commit

1. Review `staging_plan.json` and `final_closure_decision.json`.
2. Run `gitnexus_detect_changes` or CLI equivalent before commit.
3. Run relevant tests for any implementation changes selected for staging.
4. Scan selected artifacts for raw connection strings and credential-like values.
5. Confirm final closure scope explicitly before commit/tag/push.

## Proposed Next Command Only After Approval

```text
rtk git add <approved files only>
rtk proxy npx gitnexus detect-changes --repo rag
rtk git commit -m "docs(phase9): prepare milestone close approval package"
```

Tag and push remain separately gated:

- `tag_policy`: `do_not_tag_without_explicit_user_approval`
- `push_policy`: `do_not_push_without_explicit_user_approval`
