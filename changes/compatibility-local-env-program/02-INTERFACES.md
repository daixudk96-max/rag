# Compatibility Local Env Program — Frozen Interfaces

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

## Target Configuration Surfaces

### Existing central settings seam
- `llamaindex_runtime/config.py`
- `RuntimeSettings`

### Existing direct-read seam to eliminate
- `llamaindex_runtime/llm/__init__.py`
- current direct `OPENAI_API_KEY` read path

## Planned Local Env Variables

Required / high-priority:
- `OPENAI_API_KEY`
- `LLM_MODEL`
- `LLM_TEMPERATURE`

Optional / provider-routing support:
- `OPENAI_BASE_URL`

Existing runtime values that the local template should keep visible:
- `DATABASE_URL`
- `VECTOR_BACKEND`
- `TREE_STRATEGY`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_MODEL_NAME`
- `QDRANT_URL`
- `MILVUS_URL`

Validation-helper values allowed in the local template:
- `REAL_VALIDATION_DOCUMENT_PATH`
- `REAL_VALIDATION_QUERY`

## Secret-Handling Contract

- tracked file: `.env.example`
- local-only file: `.env`
- real secret values must never be committed
- real secret values must never be printed into logs, prompts, markdown, or artifacts

## Integration Rule

This package may improve configuration loading and template hygiene, but may not change donor priority, retrieval architecture, or provenance ownership.
