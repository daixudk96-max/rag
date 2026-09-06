---
phase: 16-raw-corpus-entity-layer
plan: 17
type: execute
status: COMPLETE
completed: 2026-08-31
---

# 16-17 Summary — C2 Rule-Engine Coref Layer (entry gate + static assets)

## What was built

1. **Task 1 (static assets, TDD, implementer 314718ec)**: 7 files.
   - NEW `llamaindex_runtime/registry/migrations/021_ner_coref_clusters.sql` (49 lines): normalized membership tables `coref_clusters` + `coref_cluster_mentions`, `tombstone BOOLEAN`; no merge table.
   - EDIT `llamaindex_runtime/registry/migration_catalog.py` (+021 entry).
   - EDIT `llamaindex_runtime/config.py`: `VALID_COREF_RESOLVERS = {off, rules}`, `rag_coref_resolver='off'` default, fail-closed `__post_init__`, `RAG_COREF_RESOLVER` env.
   - Tests: `tests/llamaindex_runtime/test_runtime_settings_phase16.py` +21 tests; contract pin updates in `test_e2b_migration_catalog.py` (final entry 020→021), `test_e2b_migration_gate_runner.py` (`_CATALOG_TAIL`→(020, 021)), `run_e2b_migration_gate.py` tail pin.
   - GitNexus impact: `RuntimeSettings` and `FULL_MIGRATION_CATALOG` upstream 0 direct (UNKNOWN library nodes); manual risk assessment LOW.

2. **Task 2 (user decision)**: user chose **enter** (2026-08-31, original message "1") — authorized one C2 entry live acceptance run (future gate 5). Context recorded: C2 live = disposable PostgreSQL + 021 + coref rules on a real database (deterministic rules only, no model inference); R-OKF-09 readiness gate; net benefit lands in Phase 19 G3.

3. **Task 3 (entry gate, TDD, implementers 91debdb6 → 66b081dc successor)**: 2 files (+3 live-parity tests in fix round).
   - NEW `verification/phase16-raw-corpus-entity-layer/run_c2_entry_acceptance.py`: default `skipped_not_entered` (zero connection, redacted reason, exit 1); authorized only when `OKF_E2B_C2_ENTRY_AUTHORIZED=1` AND disposable gate (same as 16-15) AND C1 CLOSED proven via archived evidence sha256 anchor `53ae99b6e4f85223ccbfe99910a13a711d12d033670db4a408eb532068a412e3` (candidates: SUCCESS-named archive first, plain executed archive second; contradiction → immediate fail-closed; all absent → c1_not_closed).
   - Proof chain `_run_proof_steps` (:753-828): apply catalog (21 migrations, tail includes 021) → fixture state → read resolved mentions → default-off parity (0 rows) → build clusters (on) → insert → verify membership → tombstone → verify tombstone state. Proof failure ⇒ `executed_failed` exit 3 WITH evidence, never silent.
   - `_c2_connection_factory` binds dict_row (:838-840).
   - NEW `tests/llamaindex_runtime/okf/test_c2_entry_acceptance_runner.py` (96 + 3 = 99 tests).

## Gate 5 live record (authorized single entry, rounds R1–R2)

- **R1 (2026-08-31)**: `executed_failed` exit 3 — fail-closed honesty preserved. C1 anchor verified (hash_matched=true, matrix_keys 8). Proof STEP3 `_read_resolved_mentions` raised `ValueError: input_id must be a Unicode scalar string` (`e2a_contract_primitives.py:50` / `:103 _uuid` / `entity/contracts.py:229` / `run_c2_entry_acceptance.py:588`). Root cause: psycopg3 dict_row returns uuid columns as `uuid.UUID`; fakes used str so only the live path exposed it. Evidence archived (`_failed_round1` copy, sha `815533994d73a458f7223229d41687ed567ce74d1a39cf1b7109aaf469f4145c`).
- **FINDING A fix (66b081dc, TDD)**: RED = 3 live-parity tests with uuid-typed fake rows (first failure traceback identical to live R1); GREEN = `str()` normalization of all UUID columns at 3 sites (`run_c2_entry_acceptance.py:592` span_id, :625-626 document_id/version_id + segment_id/entity_id non-None, :711 membership tuple, :752 tombstone set). GitNexus index lacks the runner symbol (risk UNKNOWN); manual blast radius LOW (same-file callers only).
- **R2 (2026-08-31)**: **executed, exit 0**. Evidence sha `91656cd4eb0e1c3902fd25db27e497e94c01cb2ae3a03520c2e25292d825c869` (archived `c2_entry_evidence_executed_2026-08-31.md`): catalog 21 migrations tail_includes_021=true; default_off_parity 0/0/0 DML; rules_materialization cluster_count=1 membership_count=2 deterministic_ids_verified=true; tombstone 1/1, membership_preserved=2. Container destroyed + credentials purged after run.

## Coordinator independent verification (claims untrusted until verified)

- Focused live-parity: 3 passed, 96 deselected; full C2 file: 99 passed.
- Full `tests/llamaindex_runtime/okf`: 3169 passed / 5 failed / 31 skipped — the 5 are exactly the pre-existing constant set (3× `test_e2b_migration_gate_runner.py` evidence-leftover; `test_e2a_wave1_eighth_db.py` 019-drift; `test_phase15_e2a_harness_blocked_import_proof.py` venv). No new failures.
- R2 live re-run by coordinator directly (rtk proxy python, PYTHONPATH repo root; URI via .tmp file; env gates set in-process; no argv credential route; container --rm + stop + credential file deletion verified).

## Disciplined notes

- C1 anchor archive restore lesson: PowerShell Copy-Item had silently failed once; hash verification MUST be python (`.tmp/restore_anchor.py`, byte-copy + sha assert). A blank `Get-FileHash` output = failure signal.
- docker `--env-file` must use LF (`\n`) line endings: CR leaked into POSTGRES_PASSWORD on the first R1 container start attempt.
- Live evidence archive overwrite risk: round-1 archive copied to the `_failed_round1` name before R2 overwrote the canonical name.

## Next

- 16-18 orchestrator (consumes real 16-15/16-17 measurements) → Phase 16 close-out.
