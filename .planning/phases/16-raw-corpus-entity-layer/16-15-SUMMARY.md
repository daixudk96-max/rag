---
phase: 16-raw-corpus-entity-layer
plan: 15
status: COMPLETE
completed: 2026-08-31
---

# 16-15-SUMMARY — Full-Corpus E2b Acceptance Runner (future gate 4)

## Result

**executed** — live acceptance matrix passed in full on a disposable local PostgreSQL (2026-08-31).

## Deliverables (Task 1, TDD via sole implementer a8362ef5)

- `verification/phase16-raw-corpus-entity-layer/run_e2b_full_corpus_acceptance.py` (1517 lines): env gate `OKF_MIGRATION_TEST_DATABASE_DISPOSABLE=1` + `OKF_REBUILD_EXPECTED_DATABASE` + `OKF_E2B_DISPOSABLE_TEST_AUTHORIZED=1` else exactly `blocked_not_executed` with zero connection (exit 1); `main(argv, *, target_uri)` — programmatic target only, never argv/env; redacted single-line-JSON evidence (`e2b_full_corpus_acceptance_evidence.md`, allowlist-validated); 8-transition matrix (first_materialization, equivalent_rerun, changed_set_convergence, manual_legacy_preservation, invalid_document_isolation, changed_set_failure_rollback, e2b_vs_e2b_serialization, e2a_vs_e2b_serialization); `executed_failed` = exit 3 fail-closed with evidence written.
- `tests/llamaindex_runtime/okf/test_e2b_full_corpus_acceptance_runner.py` (1622 lines): 62 tests, seam-driven fakes, never a real DB.

## Task 2 (decision): authorized by user (2026-08-31)

User instruction: '解除数字数据库禁令，然后继续吧' — recorded in `.planning/phases/16-raw-corpus-entity-layer/16-15-REPLAN-DB-AUTHORIZATION-2026-08-31.md` (disposable local PostgreSQL only; Docker as one-shot container supply mechanism; still forbidden: production DB/real credentials, RaNER/C2 live, model download, commit/push).

## Live gate execution history (coordinator-run, 5 rounds, pgvector/pgvector:pg16 local image)

- R1: fixture UNIQUE collision `idx_documents_source_uri` (same source_uri) → distinct per-doc source_uri.
- R2: status=executed but all 8 transitions rolled_back_failure (empty semantics) — root cause: psycopg default tuple_row makes `isinstance(row, Mapping)` False in `_acquire_locks`. **FINDING A** = connection factory must use `row_factory=psycopg.rows.dict_row`; **FINDING B** = proof-transition failures must yield executed_failed (exit 3) with evidence written, never executed. Archived: `e2b_full_corpus_acceptance_evidence_round2_rolledback_2026-08-31.md` (sha 4dbaf5495cd3a314d01af201b20caf04c6f252b31c3366d4fdecb0ebfabea16d).
- R3: transitions 1-3 passed real DB; transition 4 crashed zero-evidence: `_E2bLinkProofError: desired link (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa, dddddddd-dddd-4ddd-8ddd-dddddddddddd) is not derivable from any resolved mention span mapping`. **FINDING C** = desired links must derive from desired mention span mapping (repository caller contract, re-raises by design) + matrix-level unexpected exceptions must record `transition_error` so the gate fails closed WITH evidence.
- R4: executed_failed (exit 3, honest) — sole failing assertion `e2b_vs_e2b_serialization: second_outcome='changed'`. Root cause: matrix-order dependence (transition 3 leaves shrunk state; the overlap's single background reconcile converges shrunk→full = changed). Repository was correct. **FINDING D** = serialization transitions pre-converge before the overlap; strict `second_outcome == 'no_op'` kept. Round-4 evidence sha a6b769308f6b6b0ab87583e147a6e62179be844367ffa61f7ec673a3ea69d850 (archive later overwritten by R5 archive; sha recorded here).
- **R5 (final): status=executed, exit 0.** Evidence sha256 `53ae99b6e4f85223ccbfe99910a13a711d12d033670db4a408eb532068a412e3`, archived `e2b_full_corpus_acceptance_evidence_executed_SUCCESS_2026-08-31.md`. All 8 transitions pass: first_materialization changed (2 mentions/2 ledger/2 node_entity_links/2 ownership, bridge_count 2, chunk_entity_links 0); equivalent_rerun no_op (0 DML, no churn); changed_set_convergence changed (stale mention 1, ownership 1, bridge deletion 1, fail-closed preserved 0); manual_legacy_preservation changed (bridges preserved 1, mentions preserved 1, claimed 0, deleted 0, new bridge 1); invalid_document_isolation rolled_back_failure (audit written, scope_writes 0); changed_set_failure_rollback rolled_back_failure (rollback confirmed, old state restored, audit written); e2b_vs_e2b + e2a_vs_e2b serialization (serialized true, overlap blocked on shared `okf:e2a:parent:{doc}:{ver}` advisory lock, second_outcome no_op, duplicate_rows 0, pre_converge_outcome changed/no_op). No connection string/credential/corpus text in evidence.

## Verification (independently re-run by coordinator, env-stripped)

- `tests/llamaindex_runtime/okf/test_e2b_full_corpus_acceptance_runner.py`: 62 passed.
- Full okf suite: 3069 passed / 5 failed / 31 skipped — the 5 are the pre-existing set unchanged (3x `test_e2b_migration_gate_runner.py` evidence-leftover from the 16-14 authorized run, `test_e2a_wave1_eighth_db.py` migration-019 drift, `test_phase15_e2a_harness_blocked_import_proof.py` venv).
- black/ruff/py_compile clean; mypy 0 errors in the 2 files (93 pre-existing baseline in imported modules); blocked path exact (`blocked_not_executed`, exit 1, no evidence, zero connection).
- TDD: RED→GREEN per finding (47→49→55→60→62 tests); `_validate_matrix_outcomes` never weakened.

## Next

16-17 (static pieces: migration 021 + config + skipped_not_entered) → 16-18 verification orchestrator consuming real measurements → Phase 16 close-out (Windows-only; WSL measurement waived by user 2026-08-31).
