<!-- generated-by: gsd-doc-writer -->
# Phase 15-02 Summary — Caller-Owned Exact Atomic Reconciliation

**Status: DELIVERED.** Phase 15-02 implemented exact, atomic primary E2a reconciliation over an already admitted whole corpus, per [15-02-PLAN.md](15-02-PLAN.md). Its acceptance is closed by the real disposable PostgreSQL transition matrix (Task #88) and the durable integration boundary (Task #89). No live database was run by this planning summary.

## Objective

Replace insert-if-absent and component-owned transactions with deterministic desired-state reconciliation: a cursor-only repository, one caller-owned transaction, concurrency-safe locking, exact idempotence, deterministic tree identity, and fail-closed E2b protection.

## Deliverables

### 1. Cursor-only exact E2a repository

**File:** `llamaindex_runtime/okf/e2a_materialization_repository.py`

- `E2aMaterializationRepository.reconcile(cursor, desired, *, recorder) -> E2aReconciliationResult`: exact upsert/diff with no unconditional conflict updates, per-table DML recording, and database cascade-effect recording.
- Never commits, rolls back, changes autocommit, or opens a connection. `PostgresRegistryWriter.write_*` and `VectorLoader.load()` are forbidden E2a primitives.

### 2. Caller-owned reconciliation orchestration

**File:** `llamaindex_runtime/okf/e2a_reconciler.py`

- One caller-owned transaction: derive desired state before locks, acquire the global transaction-scoped E2a advisory lock, sorted per-parent advisory locks including new parents, and sorted existing-parent `FOR UPDATE` locks.
- Parent-first tree nodes and node spans reconciled, chunks repointed, then stale nodes deleted after cache invalidation counts; fail closed on `node_entity_links`. Global manual entities/relations deleted only when ownership is gone and no non-E2a dependency remains.
- Failure audit runs solely via a fresh connection after rollback/primary close, in bounded phases with redacted diagnostics.

### 3. Deterministic tree reconciliation

**File:** `llamaindex_runtime/registry/tree_generator.py`

- Sorted normalized semantic domains before `TreeGenerator.generate_tree`; shuffled equivalents preserve tree IDs, mappings, and manifest.

### 4. Tests

**Files:** `tests/llamaindex_runtime/okf/test_e2a_desired_state.py`, `test_e2a_reconciliation.py`, `test_e2a_disposable_postgres.py`

- Fake-cursor RED-then-GREEN tests for ordered lock acquisition, allowlist-only DML, equivalent rerun zero DML (including `okf_sync_state` and ownership; no success/no-op audit row), late-failure rollback + fresh-connection bounded audit, stale span/chunk/node closure with zero mutation, shuffled-span tree identity, and denylist coverage including `chunk_entity_links`.
- `test_e2a_disposable_postgres.py` is an acceptance fixture that is inert unless separately authorized; ordinary selectors never connect to a database.

## Acceptance closure

- **Task #88 (real disposable PostgreSQL transition matrix):** PASS — first materialization, equivalent rerun (zero DML), late failure, concurrency (global/sorted advisory/row locks), and stale reconciliation were validated against a real disposable PostgreSQL/Docker target.
- **Task #89 (durable integration boundary exact live selector):** PASS — 1 passed in 101.86s (exact authorized live selector, run once).
- **Task #90 (pure/static gate):** PASS — 114 static/pure tests passed; protected runner fingerprint unchanged; default collection excludes live.

## Non-claims

- No quality or Level claim; Level 2 remains authoritative.
- No production readiness, no external database, no commit/push.
- Hostile-superuser, tamper-evidence, and postcommit guarantee are explicitly not claimed (control-plane attestation is detection only).
