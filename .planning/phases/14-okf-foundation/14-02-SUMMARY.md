---
phase: 14-okf-foundation
plan: 02
subsystem: database
tags: [postgresql, migrations, okf, pytest]
requires:
  - phase: 05-kg-extension
    provides: entities, relations, and canonical span schema
provides:
  - OKF sync/rebuild bookkeeping tables
  - Empty Phase 16 entity-mention tables
  - Relation qualifier persistence columns
  - Fresh/existing/re-apply migration integration coverage
affects: [14-03, 14-04, 15-okf-ingestion-pipeline, 16-raw-corpus-entity-layer]
tech-stack:
  added: []
  patterns: [zero-padded idempotent PostgreSQL migrations, isolated-schema integration tests]
key-files:
  created:
    - llamaindex_runtime/registry/migrations/015_okf_sync_state.sql
    - llamaindex_runtime/registry/migrations/016_entity_mentions.sql
    - llamaindex_runtime/registry/migrations/017_relation_qualifiers.sql
    - tests/llamaindex_runtime/okf/test_okf_migrations.py
  modified:
    - run_migrations.py
key-decisions:
  - "entity_mentions.entity_id remains nullable for pending mentions, retaining its entities foreign key when resolved."
  - "The PageIndex retrieval migration list remains unchanged because that workflow does not read OKF tables."
  - "The root migration list includes 005 before 015-017 so the general-purpose runner creates their direct entities/relations prerequisites."
patterns-established:
  - "Use a random temporary PostgreSQL schema per migration scenario to test fresh, upgrade, and re-apply paths."
requirements-completed: []
duration: "2026-07-13..2026-07-14 execution and verification"
completed: 2026-07-14
---

# Phase 14 Plan 02: OKF Migration Schema Summary

**OKF bookkeeping, pending-aware entity mentions, and relation qualifier migrations with isolated-schema regression coverage.**

## Current-state amendment (2026-07-17)

This summary preserves its Wave 1 execution record. Subsequent Task31/Task32 work changes neither its historical migration acceptance result nor Phase 14 closure status.

- `run_migrations.py` is a **curated general-purpose runner**, not an all-migrations executor and not the Task34 disposable acceptance CLI. Its current ordered sequence is `001,002,003,004,005,007,015,016,017,018`; `005` deliberately precedes the OKF migrations because it supplies `entities`/`relations` prerequisites. Do not infer the root runner has Task31's fixed `search_path` or timeout hardening.
- The direct PageIndex workflow has a separate, deliberately exact tuple: `001,002,003,004,007`. It excludes `005` and `015`–`018`; its Task31 acceptance is `61 collected/passed` with `88%` script branch coverage (282 statements, 64 branches). This does not make the direct workflow an OKF migration path.
- **Superseded current-status overlay (2026-07-17):** This Wave 1 summary remains a historical execution record. Phase 14/E1 is now **BOUNDED CLOSED/PASS** under [artifact 13](../../../verification/phase14-okf-foundation/13-final-authority-evidence-closure-review.md), verdict **APPROVE_FOR_FORMAL_CLOSURE** with no CRITICAL/HIGH findings. Gates A–E have PASS execution evidence and APPROVE independent reviews; Gate F is PASS only within declared Phase 14 non-goal scope, with an APPROVE independent review. Artifacts 04–07 retain tracked-diff-only/HIGH-CRITICAL targeted-impact/non-exhaustive-untracked limitations, so this is not a clean-worktree, intended-commit-scope, security, production, or full-derived-database-rebuild PASS. E1 remains limited to admitted raw-sidecar-to-`canonical_spans` reconciliation for registered/protected parents. Canonical-path ratification remains complete. **Historical/as-of this Wave 1 record:** Phase 15/E2a was unstarted and its separate explicit Gate 3 authorization was unsatisfied. **Current routing (later):** the interactive selection `授权规划和实施（推荐）` satisfies Gate 3; Phase 15 is authorized/planned/execution-unstarted pending approved plan execution. This routing grants no later-phase, Git, production, or disposable-acceptance authority. GitNexus is current at `9c1922c`. See [`verification/phase14-okf-foundation/README.md`](../../../verification/phase14-okf-foundation/README.md).

## Accomplishments

- Added zero-padded migrations 015–017 for OKF sync/rebuild state, Phase 16 entity mentions, and relation qualifiers.
- Added migration coverage for fresh initialization, existing-schema upgrade, idempotent re-application, character-coordinate constraints, nullable pending mentions, and runner safety.
- Hardened the integration suite with an explicit `OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1` opt-in so a configured URL alone cannot authorize database-global extension DDL.
- Added 005 and 015–017 to the general-purpose root migration runner; the URL is environment-only and migration paths resolve relative to the script.
- Completed real disposable PostgreSQL validation for the complete OKF suite and a second fresh-database root-runner proof.

## TDD and Verification Evidence

- **Initial RED:** the migration-presence test failed before implementation because lexicographic migrations ended at 014.
- **Coordinate-constraint RED:** a live negative-offset insert was accepted before `char_start >= 0` was added; after remediation PostgreSQL raises `CheckViolation` as required.
- **Complete non-live OKF suite:** `72 passed, 4 deselected, 2 warnings`.
- **Complete live disposable PostgreSQL OKF suite:** `76 passed, 2 warnings`, covering fresh, existing, re-apply, and character-range behavior.
- **Fresh root-runner proof on a second disposable database:** applied `001`, `002`, `003`, `005`, `007`, `015`, `016`, and `017` in order and produced 18 tables; required `okf_sync_state`, `entity_mentions`, and `relations` objects were present.
- **Static checks:** isolated mypy passed for the Wave 1 modules; Ruff passed; compileall passed; `git diff --check` passed.
- The disposable container used a process-local random password, bound only to `127.0.0.1`, passed internal and host readiness checks, and was automatically removed. No URL or credential was printed or persisted.

## Files Created/Modified

- `llamaindex_runtime/registry/migrations/015_okf_sync_state.sql` — `okf_sync_state` and `okf_rebuild_log`.
- `llamaindex_runtime/registry/migrations/016_entity_mentions.sql` — empty aliases, mentions, and merge-log tables; `entity_mentions.entity_id` is nullable and has an `entities(entity_id)` foreign key.
- `llamaindex_runtime/registry/migrations/017_relation_qualifiers.sql` — idempotent `relations` columns for negation, condition, direction, confidence, and JSONB qualifiers.
- `tests/llamaindex_runtime/okf/test_okf_migrations.py` — temporary-schema fresh, existing, and re-apply integration scenarios.
- `run_migrations.py` — released additions of 005 and migrations 015–017 to `key_migrations`; 005 provides the direct `entities` and `relations` prerequisites.

## Migration List Reconciliation

| Hardcoded list | Decision | Reason | Impact analysis |
| --- | --- | --- | --- |
| `scripts/run_pageindex_real_retrieval_workflow.py::MIGRATION_FILES` | NOT ADD | The PageIndex retrieval workflow does not read OKF tables. Revisit in Phase 15 when ingestion moves to OKF. | `apply_migrations` LOW risk: one direct caller (`main`); no edit made. |
| `run_migrations.py::key_migrations` | ADD — implemented | It is the general-purpose manual migration runner. Migration 005 is included before 015–017 because it creates their direct `entities` and `relations` prerequisites; 001 provides `canonical_spans`. | `key_migrations` LOW risk: zero upstream impact; 005 and 015–017 added. |

## Issues Encountered

### Disposable PostgreSQL startup and safety

Docker/PostgreSQL initially required a two-layer readiness gate: `pg_isready` inside the container and a host-side psycopg `SELECT 1`. The integration suite also now refuses to run when `DATABASE_URL` is set without `OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1`, preventing accidental execution against a shared database.

### Independent database review disposition

The final database review returned **APPROVE** with no CRITICAL/HIGH findings and declared the database acceptance gate met. It identified:

- **MEDIUM, non-blocking performance optimization:** add an index on `entity_aliases(entity_id)` before Phase 16 populates aliases.
- **LOW test enhancement:** add behavioral coverage for `entity_mentions.entity_id ON DELETE SET NULL`.

Both are explicitly deferred to **Phase 16 pre-population schema hardening**, before these tables receive production data. Multiple Opus implementation agents failed before startup with a transient `503 auth_unavailable` and made zero edits; the coordinator did not bypass the user’s Opus-only implementation constraint. The deferral does not alter Wave 1 correctness, idempotency, or live acceptance evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Contract correction] Kept unresolved entity mentions valid**
- **Found during:** Task 1
- **Issue:** Older plan shorthand described a mandatory entity foreign key, which contradicts the frozen Phase 16 forward contract for pending mention resolution.
- **Fix:** Made `entity_mentions.entity_id` nullable with `ON DELETE SET NULL`, while preserving the foreign key for populated values; added assertions for both nullability and FK presence.
- **Files modified:** `016_entity_mentions.sql`, `test_okf_migrations.py`
- **Verification:** Structural test covers the contract; live assertion runs when `DATABASE_URL` is available.

**Total deviations:** 1 auto-fixed contract correction.

## Known Stubs

None. Entity-layer tables are intentionally empty until Phase 16; no UI or application behavior depends on them in this plan.

## Threat Flags

None open for Wave 1. Database credentials are environment-only and never logged. Current Phase 14 closeout/verification artifacts contain no credential values; protected variables were isolated as recorded. This does not make a repository-wide claim about historical planning artifacts. Integration execution requires explicit disposable-database opt-in.

## Next Phase Readiness

- Plan 14-02 acceptance is closed: migrations 015–017 passed fresh/existing/re-apply verification on disposable PostgreSQL.
- The general-purpose root runner passed on a separate fresh database with migration 005 before 015–017.
- Plan 14-03 may consume these contracts only after Navigator routing; this summary does not authorize parser/serializer execution by itself.
- Phase 16 must close the deferred alias-index and `ON DELETE SET NULL` behavioral-test enhancements before populating the entity tables.
- No commit was created, staged, or pushed.

## Independent Review Gate

- General code/plan compliance: **APPROVE**, 0 CRITICAL / 0 HIGH / 0 MEDIUM.
- Python correctness/test isolation: **APPROVE**, 0 CRITICAL / 0 HIGH; no blocking test-isolation defects.
- PostgreSQL migrations: **APPROVE**, 0 CRITICAL / 0 HIGH; database acceptance gate explicitly met; one MEDIUM performance enhancement and one LOW test enhancement deferred as documented above.
- Security: **APPROVE**, 0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW.

## Self-Check: PASSED

- The three migration files and test file exist at the paths listed above.
- No task or metadata commit was requested or created.
