# Phase 5 Summary — Evidence-Chain Verification and Resolver Consolidation

## Evidence-Chain Verification Result

Phase 5 now has active-version-scoped diagnostics in `verification/phase5-evidence-chain-verification/verify_active_version_counts.py`.

Current local artifact result:

- `active_version_id`: `null`
- `canonical_spans`: unavailable in local run (`DATABASE_URL` not configured)
- `vector_chunks`: unavailable in local run (`DATABASE_URL` not configured)
- `vector_chunks_with_node_id`: unavailable in local run (`DATABASE_URL` not configured)
- `vector_chunk_spans`: unavailable in local run (`DATABASE_URL` not configured)
- `tree_node_spans`: unavailable in local run (`DATABASE_URL` not configured)
- `heading_path_rate`: unavailable in local run (`DATABASE_URL` not configured)
- `classification`: `missing_canonical_spans`

Interpretation: the gate is fail-closed in this local environment because no `DATABASE_URL` is configured. A DB-backed rerun must execute `verify_active_version_counts.py`, then `invoke_vector_loader.py`, then `verify_active_version_counts.py` again against the active version.

## Resolver Consolidation Result

`EvidenceContentResolver` is implemented in `llamaindex_runtime/tree/evidence_content_resolver.py`.

It is used by both retrieval paths:

- `ReasoningTreeBackend` calls `EvidenceContentResolver().build_text_preview(...)` after LLM node selection.
- `PageIndexTreeAdapter` calls `EvidenceContentResolver().build_text_preview(...)` while constructing `BackendHit` evidence payloads.

Fallback order is preserved and test-backed:

1. `canonical_spans.raw_text`
2. `vector_chunks.text_preview`
3. summary/title fallback

The resolver only hydrates `text_preview`; it does not participate in ranking, LLM node selection, sorting, or retrieval limit behavior.

## Validation Integrity Gate

`verification/phase5-evidence-chain-verification/validation_integrity_gate.py` now writes `validation_integrity_report.json` and blocks invalid metric calculation.

Current local gate result:

- `passed`: `false`
- `blocking_reasons`:
  - `unknown_hit`
  - `missing_judgment_rows`
  - `corpus_mismatch`
  - `missing_canonical_spans`
- `next_allowed_action`: `fix_evidence_chain`

The gate confirms the Phase 4 invalid assessment cannot silently recur: existing retrieval and judgment artifacts are internally inconsistent, and evidence-chain diagnostics are not ready.

## Human Judgment Handoff

Status: `BLOCKED`

Human judgment collection must not start yet. Exact blockers:

1. Evidence-chain gate is not ready: `missing_canonical_spans` in the current local artifact.
2. Retrieval/judgment integrity fails: `unknown_hit`, `missing_judgment_rows`, and `corpus_mismatch`.
3. A clean DB-backed rerun must generate matched retrieval results and a fresh judgment template before manual judgment collection.

When the gate passes, the handoff target remains:

- `verification/phase3-real-validation/judgment_template.csv`

## Authoritative Baseline

Level 2 remains authoritative until a valid new `level_assessment.json` is produced from matched retrieval/judgment data.

The discarded Phase 4 Level 3 remains non-authoritative because its metrics mixed new-corpus retrieval with old-corpus judgments.

## Verification Commands Run

- `PYTHONPATH=E:/github/rag rtk proxy python -m compileall -q verification/phase5-evidence-chain-verification/verify_active_version_counts.py verification/phase3-real-validation/run_validation.py`
- `PYTHONPATH=E:/github/rag rtk proxy pytest tests/verification/test_validation_integrity.py -q` — 4 passed during Wave 1
- `PYTHONPATH=E:/github/rag rtk proxy pytest tests/verification/test_validation_integrity.py tests/llamaindex_runtime/test_evidence_chain_completeness.py -q` — 12 passed during Wave 1
- `PYTHONPATH=E:/github/rag rtk proxy python -m compileall -q verification/phase5-evidence-chain-verification/invoke_vector_loader.py verification/phase5-evidence-chain-verification/verify_heading_path_contract.py llamaindex_runtime/tree/evidence_content_resolver.py llamaindex_runtime/tree/reasoning_backend.py llamaindex_runtime/tree/pageindex_adapter.py scripts/run_pageindex_real_retrieval_workflow.py`
- `PYTHONPATH=E:/github/rag rtk proxy pytest tests/llamaindex_runtime/test_evidence_content_resolver.py tests/llamaindex_runtime/test_vector_loader.py tests/llamaindex_runtime/test_query_quality_validation.py tests/llamaindex_runtime/test_evidence_chain_completeness.py tests/verification/test_validation_integrity.py -q` — 33 passed during Wave 2
- `PYTHONPATH=E:/github/rag rtk proxy python -m compileall -q verification/phase5-evidence-chain-verification/validation_integrity_gate.py verification/phase3-real-validation/calculate_metrics.py`
- `PYTHONPATH=E:/github/rag rtk proxy pytest tests/verification/test_validation_integrity.py -q` — 9 passed during Wave 3
- `PYTHONPATH=E:/github/rag rtk proxy python verification/phase5-evidence-chain-verification/verify_active_version_counts.py || true` — wrote fail-closed local artifact
- `PYTHONPATH=E:/github/rag rtk proxy python verification/phase5-evidence-chain-verification/verify_heading_path_contract.py || true` — wrote heading-path contract artifact
- `PYTHONPATH=E:/github/rag rtk proxy python verification/phase5-evidence-chain-verification/validation_integrity_gate.py || true` — wrote fail-closed integrity report
