# Identity Contract (v1)

## Locked IDs

- `doc_id`: logical document identity, stable across versions
- `version_id`: document version identity, changes on content or normalization changes
- `span_id`: canonical evidence identity, stable only within a given `version_id`
- `chunk_id`: vector-view identity, derived from one version and never used as global truth

## Hard rules

1. `chunk_id` must never be treated as global primary identity.
2. All query results must be traceable back to `span_id`.
3. Active document state is represented by `doc_id + active version_id`.
4. Derived views may change; base document and version identities must not.
