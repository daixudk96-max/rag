# Compatibility Real-Validation Program — Frozen Interfaces

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

## Validation Entry Surfaces

Primary validation surfaces:
- `verification/phase8_comparison.py`
- `verification.phase8_comparison.compare_and_decide_promotion(pdf_path, query_text)`
- `llamaindex_runtime/tree/pageindex_adapter.py`

## Secret-Handling Contract

- `OPENAI_API_KEY` may be session-scoped only
- never print the secret value
- never commit the secret to the repo
- never write the secret into markdown, config, or artifact files

## Validation Artifact Contract

A fresh real-validation artifact must clearly report:
- credential status (`set` / `missing`)
- validation document path
- query text
- donor execution state
- stub / fallback status
- failure classification
- whether the parent package should keep `DEFER`

## Allowed Failure Classification

Use only explicit buckets:
- missing key
- invalid key / auth
- model access / provider block
- quota / billing
- network
- PageIndex runtime bug
- parsing / document-specific issue
- success

## Integration Rule

Real validation may expose bugs and justify minimal fixes, but it may not change donor priority, reopen paused branches, or rewrite provenance ownership.
