<!-- generated-by: gsd-doc-writer -->
# Phase 15-01 Summary — Deterministic Admission, Ownership, Migration 019, and Migration Catalog

**Status: DELIVERED.** Phase 15-01 defined deterministic E2a admission and the schema contract that makes primary materialization safe, per [15-01-PLAN.md](15-01-PLAN.md). Its acceptance is closed by the real disposable PostgreSQL transition matrix (Task #88) and the pure/static gate (Task #90). No live database was run by this planning summary.

## Objective

Ensure only complete, validated OKF sources reach the single E2a reconciliation transaction: TDD-tested immutable contracts, strict M-D-S-M raw-pair admission, manual-fact desired state, migration 019, and one full ordered migration catalog.

## Deliverables

### 1. Immutable contracts

**File:** `llamaindex_runtime/okf/e2a_contracts.py`

- Frozen DTOs covering immutable admission, ownership, desired-state, and measured-result contracts (`E2aDesiredState`, `DmlRecorder`, `E2aReconciliationResult`).
- Manifest hash, per-table primary DML, transaction outcome, denylist counts, comparator parity, stale/cache counts, failure-audit outcome, and post-rollback failure-audit outcome are serializable from typed results only.
- Span identity is derived through the established `NormalizationContract.normalize`, not copied logic.

### 2. Strict raw-pair admission

**File:** `llamaindex_runtime/okf/e2a_admission.py`

- Whole-corpus admission `E2aCorpusAdmitter.admit_e2a_corpus(authority) -> E2aDesiredState`: recursive manifest-only `raw/**/*.pair.json` admission through `read_raw_pair`, fact discovery only below entities/relations/concepts, strict exclusions, safe POSIX paths, duplicate identity rejection, deterministic `(kind, path, identity)` ordering, and a canonical full-corpus manifest/SHA-256.
- Valid raw pairs and manual OKF facts admit into one deterministic immutable desired state; invalid pairs, ambiguous facts, evidence without a unique document/version/span, and ownership collisions fail before any primary DML.
- Accepted raw-pair ADR governs binding (`ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md`); no inferred sidecar convention and no legacy fallback.

### 3. Migration 019 materialization contract

**File:** `llamaindex_runtime/registry/migrations/019_e2a_materialization_contract.sql`

- E2a ownership ledger keyed by safe relative OKF path / fact kind / deterministic ID, source digest, nullable scope, multi-owner global facts, composite `(version_id, span_id)` and `(version_id, evidence_id)` integrity, exactly-one link target, required evidence, constrained source kind/dedup, and bounded E2a failure phases.
- Append-only initial and final same-transaction attestation of observed function source, OID, and trigger catalog state without a `pg_proc` exclusion; the final re-attestation is detection only, not a lock or race prevention. No projection outbox/status.
- Per [ADR-PHASE15-MIGRATION019-ATOMIC-FILE-SIZE-EXCEPTION-2026-07-19.md](../../ADR-PHASE15-MIGRATION019-ATOMIC-FILE-SIZE-EXCEPTION-2026-07-19.md), 019 remains one fail-closed dynamic `DO` state machine, classified before DDL, catalogued and applied exactly once.

### 4. Single full migration catalog

**File:** `llamaindex_runtime/registry/migration_catalog.py`

- Complete ordered root catalog with exactly-once 019 entry after 018; `run_migrations.py` remains its unchanged consumer.
- The PageIndex curated subset is explicitly non-applicable with a regression test.

### 5. Tests

**Files:** `tests/llamaindex_runtime/okf/test_e2a_admission.py`, `test_e2a_contracts.py`, `test_e2a_migration_019_postgres.py`

- RED-then-GREEN TDD across isolated temporary bundles against a no-DML spy.
- `test_e2a_migration_019_postgres.py` is a non-DB static migration-spec/gate test that validates migration SQL structure (single `DO`, pre-DDL classifier, one-entry catalog, one-`cursor.execute`/post-file-commit envelope); it is NOT a live PostgreSQL acceptance selector.

## Acceptance closure

- **Task #88 (real disposable PostgreSQL transition matrix):** PASS — migration catalog/fresh schema and the 019 atomic envelope were validated against a real disposable PostgreSQL/Docker target (fresh schema proves 019 constraints/indexes; 019 applies exactly once after 018; equivalent input has zero primary DML).
- **Task #90 (pure/static gate):** PASS — 114 static/pure tests passed; Ruff clean; Black unchanged; default collection excludes live.
- **Historical artifact reconciliation:** `verification/phase15-okf-ingestion-pipeline/migration019-applied.json` is historical and non-authoritative. It must NOT be represented as current Task #90 or aggregate Phase 15 acceptance evidence. It is a point-in-time delivery record, not a live acceptance record.

## Non-claims

- No quality or Level claim; Level 2 remains authoritative.
- No production readiness, no external database, no commit/push.
- Runner connection policy, timeouts, role assumption, DDL lease, and production execution remain excluded from this boundary.
