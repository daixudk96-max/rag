# Phase 15/E2a Caller-Switchover Execution Summary (2026-07-21)

## Scope

Tasks #68–72 (caller-switchover subscope only). NOT a full Phase 15 closure.

## Execution Record

### Task #68 — Design legacy caller switchover
- Status: COMPLETE
- Design documented in execution record

### Task #69 — Write caller-switchover RED specs
- Status: COMPLETE
- File: `tests/llamaindex_runtime/okf/test_e2a_caller_switchover.py:1`
- 21 tests, 733 lines, frozen contract (15 points)
- Ruff/Black clean
- All 21 RED against legacy before GREEN

### Task #70 — Implement legacy caller switchover GREEN
- Status: COMPLETE
- File: `llamaindex_runtime/ingestion/pipeline.py:1`
- `IngestionPipeline.__init__` now keyword-only: `registry, ingestor=None, bundle_root=None, connection_factory=None, reconciler=None`
- `ingest()` validates source exists FIRST (`FileNotFoundError`), then validates E2a deps BEFORE registry registration (`ValueError("Missing E2a dependencies: ...")`), then unconditionally dispatches to `_ingest_e2a` (NO silent legacy fallback)
- `DoclingIngestor.convert_for_okf()` added
- `DoclingConversionResult` frozen dataclass (source_uri, source_sha256, docling_version, nodes)
- `IngestResult` gained `reconciliation_result` field (default None)
- 21/21 GREEN
- All edited files <800 lines, Ruff/Black clean

### Task #71 — Verify caller-switchover source gate (read-only audit)
- Status: COMPLETE, verdict PASS
- 11/11 contract points verified vs disk
- No legacy leak detected
- 21/21 GREEN
- 3078 collected + 1 pre-existing collection error (untracked tests/llamaindex_runtime/fixtures, not caused by Task #70)

### Task #72 — Migrate legacy caller tests
- Status: COMPLETE, audited PASS
- File: `tests/llamaindex_runtime/test_docling_ingestion.py:167`
- Migrated `test_ingestion_pipeline_registers_document_and_persists_spans` to `test_docling_ingestor_registers_document_and_persists_spans`
- Uses `DoclingIngestor.ingest()` directly + manual `register_document`/`write_spans`
- All 5 original assertions preserved
- 24 passed in file, 462 lines, Ruff/Black clean

## Remaining Gated Items

OUT OF current scope, require separate authorization:

- **~90 live-DB tests** across 14 files construct `IngestionPipeline(registry=live_pg)` without E2a kwargs
  - Stay SKIPPED when DATABASE_URL is unset (no DB authorized)
  - Will require E2a kwargs when Phase 15 live-PostgreSQL acceptance gate (Task #54) is separately authorized

- **8 verification scripts** in `verification/phase*/run_validation.py`
  - Production callers without E2a kwargs
  - CRITICAL blast radius
  - Gated behind Task #54 acceptance authorization

## Explicit Non-Claims

- NOT a full Phase 15 closure
- NOT a clean-worktree
- NOT a commit/full-database-rebuild PASS
- Caller-switchover subscope only (Tasks #68–72)

## Next Steps

- Continue Phase 15/E2a remaining plans (Tasks #52/#53)
- Phase 15 acceptance gate (Task #54, requires separate live-PostgreSQL authorization)
- Advance ROADMAP Phases 16-20 per /goal directive