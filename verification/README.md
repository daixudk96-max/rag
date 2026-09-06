# Verification Runtime

This directory contains the executable verification/runtime implementation for the provenance-centric multi-view RAG system.

> Important: this is the **verification line**, not the final LlamaIndex-first target implementation line.
> It exists to validate architecture ideas, provide test baselines, and preserve behavior examples.

## Current implemented capabilities

### Core data foundation
- PostgreSQL registry / mapping / provenance / versioning
- Canonical spans with page / heading / offset metadata
- Versioned writes and active version switching

### Retrieval paths
- Keyword path
- Vector path (pgvector)
- Tree formal rollup
- Hit distribution analyzer
- Deep Hybrid path
- Lightweight reranker

### External interfaces
- `GET /health`
- `GET /query/keyword`
- `GET /query/vector`
- `GET /query/analyze`
- `POST /query`
- `POST /query/hybrid`

## Test status

Latest full regression result:
- **102 passed** (graph path retired 2026-09-05; 6 graph-runtime tests removed with it)


## Local test setup

### Bring up all backends

Before startup, set the required credentials:

```bash
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="change-me-postgres"
export POSTGRES_DB="rag_registry"
export MINIO_ACCESS_KEY="change-me-minio-user"
export MINIO_SECRET_KEY="change-me-minio-secret"
```

Then start the stack:

```bash
docker compose -f verification/docker-compose.yml up -d
```

This launches:
- PostgreSQL / pgvector on `postgresql://postgres:postgres@localhost:5432/rag_registry`
- Qdrant on `http://localhost:6333`
- Milvus on `http://localhost:19530`

### PostgreSQL

Set `FORMAL_RUNTIME_DATABASE_URL` before running the formal-runtime live tests.

Example:

```bash
export FORMAL_RUNTIME_DATABASE_URL="postgresql://postgres:${POSTGRES_PASSWORD}@localhost:5432/rag_registry"
python -m pytest tests -q
```

> For local throwaway verification, the compose file defaults to `postgres/postgres`.
> Replace it with stronger values via environment variables if you keep the stack running.

### Optional backend routing

To exercise the formal runtime with a specific vector backend, set:

```bash
export VECTOR_BACKEND="qdrant"      # or "milvus" / "pgvector"
export QDRANT_URL="http://localhost:6333"
export MILVUS_URL="http://localhost:19530"
```

## What this directory is for

Use this directory when you want to:
- run the real system against a real document
- validate end-to-end behavior
- inspect the implementation without all the planning artifacts

Planning, research, architecture notes, and roadmap materials are kept under:
- `../docs/`
