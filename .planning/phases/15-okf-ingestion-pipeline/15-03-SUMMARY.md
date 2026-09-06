<!-- generated-by: gsd-doc-writer -->
# Phase 15-03 Summary — Caller Switchover and PageIndex Authority Retirement

**Status: DELIVERED.** Phase 15-03 made OKF admission and E2a reconciliation the sole normal ingestion writer path and retired PageIndex primary-tree authority, per [15-03-PLAN.md](15-03-PLAN.md). Its acceptance is closed by the durable integration boundary (Task #89) and the pure/static gate (Task #90). No live database was run by this planning summary.

## Objective

Enforce the SSOT ingress boundary without silently retaining direct persistence: one-conversion normal route, pure comparator-only direct derivation, consumer-only PageIndex, and an exhaustive caller-boundary record.

## Deliverables

### 1. Sole normal ingress route

**File:** `llamaindex_runtime/ingestion/pipeline.py` and `llamaindex_runtime/ingestion/docling_ingestor.py`

- Normal ingress order: provenance parent registration -> exactly one Docling conversion -> `serialize_document` raw-triplet publication -> strict M-D-S-M raw-pair admission -> whole-corpus E2a reconciliation.
- `DoclingConversionResult` (frozen dataclass) added; `convert_for_okf` performs one reader and one node-parser invocation; the serializer receives the captured node tuple.
- Normal ingestion never calls legacy `write_spans`, a direct persistence mode, an automatic fallback, or an E2b callback. `RAG_INGESTION_PATH=direct` and a production compatibility feature are prohibited.

### 2. Pure direct comparator

- Direct derivation exists only as an injected pure comparator/test helper with no persistence imports, cursor, or database handle; it fills the comparator-parity measurement only.

### 3. PageIndex consumer-only boundary

**File:** `llamaindex_runtime/tree/pageindex_adapter.py` and `llamaindex_runtime/client/pageindex_client.py`

- PageIndex reads/caches canonical E2a tree IDs and mappings; it cannot use `registry.write_tree`, UUID4 tree identities, or empty node-span mappings on E2a routes.
- E2b callbacks remain structurally absent from E2a composition.

### 4. Caller inventory

**File:** `.planning/phases/15-okf-ingestion-pipeline/15-CALLER-INVENTORY.md`

- Fresh exhaustive GitNexus + source-search inventory classifying every production usage of the required writers (`write_spans`, `write_tree`, vector-chunk DML/`write_vector_chunks`, `write_entities`, `write_relations`, `write_evidence_links`, `write_chunk_entity_links`, `write_node_entity_links`), `VectorLoader`, PageIndex adapter/client, `IngestionPipeline`, `DoclingIngestor`, and `build_tree_entity_extraction_callback`, each row with source symbol/path, entry route/condition, owner, disposition, and enforcement test.

### 5. Tests

**File:** `tests/llamaindex_runtime/okf/test_e2a_caller_switchover.py`

- Spy-based tests proving normal routing order, no legacy/direct/fallback/E2b invocation, pure non-persisting comparator, and PageIndex canonical-ID-only consumption.
- An executable deterministic caller-inventory completeness test fails when any required named persistence surface or callback lacks a row with its exact symbol/path, entry route/condition, owner, disposition, and enforcement test.

## Acceptance closure

- **Task #89 (durable integration boundary exact live selector):** PASS — 1 passed in 101.86s (exact authorized live selector, run once). This validates the durable ingress boundary: one conversion -> serializer -> strict admission -> reconciliation with no `write_spans`, direct persistence, fallback, or E2b callback, and PageIndex consuming canonical E2a tree state only.
- **Task #90 (pure/static gate):** PASS — 114 static/pure tests passed; Ruff clean; Black unchanged; default collection excludes live.

## Known non-blocking follow-up

- `_ingest_legacy` remains a dead/unreachable method in `llamaindex_runtime/ingestion/pipeline.py` (line 130); it is not called by any normal E2a route. Some historical verification scripts may still instantiate an old pipeline shape. This is follow-up cleanup only — NOT an acceptance blocker and NOT a reason to edit production now.

## Non-claims

- No quality or Level claim; Level 2 remains authoritative.
- No production readiness, no external database, no commit/push.
- External vector projection is excluded from E2a selected scope and requires a separate future design.
