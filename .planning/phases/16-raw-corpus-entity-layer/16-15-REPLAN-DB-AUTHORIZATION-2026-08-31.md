# 16-15+16-17+16-18 REPLAN — database ban lifted (authorization record)

## User authorization (2026-08-31, verbatim)
'解除数字数据库禁令，然后继续吧' — lifts the '禁止 Docker/PostgreSQL、外部数据库' boundary for the remaining Phase 16 verification work (Option B from the presented menu).

## Scope granted (coordinator interpretation, recorded)
- Disposable LOCAL PostgreSQL only, following the already-established disposable-gate pattern of Plan 16-14 (single-use env authorization: OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1 + OKF_REBUILD_EXPECTED_DATABASE disposable loopback target + plan-specific authorize env; redacted evidence per 16-14 convention; cleanup verified).
- Ephemeral Docker containers are included as the PG provisioning mechanism ONLY (docker daemon + postgres:16 image already present on host; container removed after evidence pass). Loopback-only, throwaway credentials, disposable database/schema.
- NEVER: production/external database, DATABASE_URL or real credentials, data exfiltration to any external host.

## Still NOT authorized (unchanged)
- RaNER live inference / real Gate 3 attempt (user skip decision 2026-08-31 stands).
- C2 live entry live run (R-OKF-09 single-use) — 16-17 records skipped_not_entered branch; only its STATIC artifacts are built.
- Model downloads, commit/push.

## Package routing
- P1: Plan 16-15 Task 1 (TDD): verification/phase16-raw-corpus-entity-layer/run_e2b_full_corpus_acceptance.py + tests/llamaindex_runtime/okf/test_e2b_full_corpus_acceptance_runner.py. Default blocked_not_executed with zero connection; authorized path = deterministic FIXTURE path (16-15 truth #20: evidence must record fixture path since 16-13 measured smoke skipped).
- P2: coordinator fresh verification; then user-granted live gate execution vs disposable PG (docker, ephemeral), redacted evidence e2b_full_corpus_acceptance_evidence.md, cleanup_ok=true.
- P2: Plan 16-17 static artifacts (021 migration SQL + catalog entry + config switch rag_coref_resolver default off + run_c2_entry_acceptance.py default blocked) with C2 skipped_not_entered branch recorded.
- P3: Plan 16-18 verification orchestrator consuming MEASURED results only (gate 1 executed 2026-08-09; gate 3 skipped by user decision; C2 skipped_not_entered; 16-15 outcome from P2) -> 16-VERIFICATION.md.
- P4: T4 housekeeping (engine worktrees cleanup) + phase closure assessment.

Discipline: single implementer per package (subagent), coordinator routes/verifies only, GitNexus impact before editing existing symbols, tests never weakened, black/ruff/mypy clean, no commits.
