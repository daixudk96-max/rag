# Compatibility Tech-Debt Program — Frozen Interfaces

## Inherited Frozen Contracts

Do not change the meaning of:
- `doc_id`
- `version_id`
- `span_id`
- `chunk_id`
- `node_id`
- `entity_id`
- `relation_id`
- `evidence_id`
- `QueryHit`

## Allowed Edit Surfaces

- `scripts/run_sonarlint_ls_probe.py`
- `tests/test_run_sonarlint_ls_probe.py`
- `verification/phase8_comparison.py`
- `tests/llamaindex_runtime/test_phase8_promotion.py`
- root pytest configuration only when required for verifier clarity

## Verifier Output Contracts

### SonarLint probe
The verifier must distinguish:
- language server started
- analysis dispatched
- diagnostics received (strong mode)
- smoke-only fallback (weak mode, must be labeled as weak)

### Phase 8 comparison
The verifier must not claim donor success unless:
- credential gate passed
- donor execution actually happened
- stub/fallback state is explicitly classified

Allowed classification buckets:
- credential block
- provider / auth / model-access block
- runtime bug
- document / parsing issue
- success

## Integration Rule

Debt work may harden verifiers and small adapter behavior, but may not rewrite retrieval architecture, change donor priority, or change final provenance ownership.
