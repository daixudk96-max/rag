# Phase 15 Caller Inventory — Execution Record

## Execution Context

**Wave**: 0 (Inventory Capture)
**Date**: 2026-07-27
**Executor**: Wave 0 Implementation Owner
**Status**: Execution record with GitNexus graph evidence captured from tool output (not source search speculation)

**Critical Methodology Note**: This inventory was generated from GitNexus tool outputs at execution time. HIGH/CRITICAL risk symbols must be reported to the user before edits proceed; they do NOT create automatic impact approval. Any scope expansion requires user decision.

---

## Mandatory Pre-Edit Scope Warning

**CRITICAL symbols (MUST NOT be modified in Wave 1)**:
- `IngestionPipeline.ingest` - CRITICAL (147 upstream, 103 direct, 2 processes)
- `write_tree` - CRITICAL (68 upstream, 54 direct, 6 processes)
- `PageIndexTreeAdapter._flatten_embedded_tree` - CRITICAL (35 upstream, 13 direct, 5 processes)

**HIGH symbols (Report blast radius before editing)**:
- `PostgresRegistryWriter.write_spans` - HIGH (11 upstream, 6 direct, 4 processes)
- `PageIndexTreeAdapter.index_tree` - HIGH (22 upstream, 15 direct, 4 processes)
- `EnhancedPageIndexClient.index` - HIGH (13 upstream, 9 direct, 3 processes)

---

## Execution Inventory (GitNexus Tool Evidence)

### Production Persistence Surfaces

| UID | Path/Symbol | Entry Condition | Owner | Disposition | Direct Callers | Processes | Risk | Enforcement Test Surface |
|-----|-------------|-----------------|-------|-------------|----------------|-----------|------|--------------------------|
| `Method:llamaindex_runtime/ingestion/pipeline.py:IngestionPipeline.ingest#2` | `IngestionPipeline.ingest` | Normal binary ingress after parent registration | E2a | Migrate to one conversion, serializer, strict corpus admitter, repository; no Wave 1 edit; test real E2a ingress in Wave 2 | 103 direct | 2 processes | CRITICAL | One-conversion call-order spy and no-legacy-writer test |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_spans#2` | `PostgresRegistryWriter.write_spans` | Pipeline and legacy callers | legacy | Forbidden from E2a; generic API not edited; only reject legacy normal ingress | 6 direct | 4 processes | HIGH | Static/spy negative call test |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_tree#3` | `PostgresRegistryWriter.write_tree` | Legacy tree persistence | legacy | Forbidden from E2a; generic writer must not be modified/removed; Track B removes only PageIndex calls | 54 direct | 6 processes | CRITICAL | Static/spy negative call test |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_vector_chunks#2` | `PostgresRegistryWriter.write_vector_chunks` | Legacy vector persistence | legacy | Do not edit shared writer | 14 direct | 0 processes | MEDIUM | No-import/no-call route test |
| `Method:llamaindex_runtime/registry/tree_generator.py:TreeGenerator.generate_tree#2` | `TreeGenerator.generate_tree` | Canonical local tree generator | E2a | Preserve as canonical producer; migrate to ordering shuffle-invariant | 6 direct | 0 processes | MEDIUM | Canonical authority preservation test |
| `Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter.index_tree#3` | `PageIndexTreeAdapter.index_tree` | PDF/Markdown PageIndex tree indexing | cache/legacy | No primary tree write on E2a routes; Track B narrow caller implementation boundary only | 15 direct | 4 processes | HIGH | Canonical tree consumer test |
| `Method:llamaindex_runtime/tree/pageindex_adapter.py:PageIndexTreeAdapter._flatten_embedded_tree#4` | `PageIndexTreeAdapter._flatten_embedded_tree` | Tree flattening with UUID4 ID generation | cache/legacy | Track B removes UUID4 canonical authoring without modifying generic APIs | 13 direct | 5 processes | CRITICAL | No UUID4/write_tree/empty-map test |
| `Method:llamaindex_runtime/client/pageindex_client.py:EnhancedPageIndexClient.index#4` | `EnhancedPageIndexClient.index` | PDF and Markdown PageIndex client routes | cache/legacy | Remove E2a registry writer authority; Track B updates consumer semantics while preserving user-facing API | 9 direct | 3 processes | HIGH | No UUID4/write_tree/empty-map test |
| `Function:llamaindex_runtime/cli/run_pageindex.py:main` | `CLI main` | CLI entry point | E2a | Track B updates help/behavior | 1 direct | 0 processes | LOW | CLI contract test |
| `Method:llamaindex_runtime/okf/e2a_reconciler.py:E2aReconciler.reconcile#2` | `E2aReconciler.reconcile` | E2a reconciliation execution | E2a | Real Wave 2 acceptance executor; must not be replaced with fake | 3 direct | 0 processes | LOW | Real acceptance executor test |
| `Function:llamaindex_runtime/processing/callbacks.py:build_tree_entity_extraction_callback` | `build_tree_entity_extraction_callback` | E2b extraction callback | E2b | E2b-only; no Phase 15 callback composition | 4 direct | 0 processes | LOW | Negative call graph test per E2a route |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_chunk_entity_links#2` | `write_chunk_entity_links` | Extraction association routes | E2b | Structurally absent from E2a; E2b-owned forbid E2a DML | 0 direct | 0 processes | LOW | E2a negative composition test |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_node_entity_links#2` | `write_node_entity_links` | Extraction association routes | E2b | Structurally absent from E2a; E2b-owned forbid E2a DML | 0 direct | 0 processes | LOW | E2a negative composition test |
| `Method:llamaindex_runtime/vector/loader.py:VectorLoader.load#2` | `VectorLoader.load` | Legacy vector pipeline, may project backend | legacy/cache | **UNRESOLVED/PARTIAL**: GitNexus impact queries failed with read-only pool error returning partial:true; context shows only tests and verification/p6_validation, no processes. This is an unresolved partial tool result, NOT a verified zero-impact assertion. Fresh impact analysis mandatory before edit. Disposition: no Wave 1 modification; Wave 2 asserts no external backend projection. | UNRESOLVED (partial:true from tool error) | 0 processes (from context, not impact) | UNRESOLVED | No-import/no-call route test with mandatory fresh impact caveat |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_entities#1` | `PostgresRegistryWriter.write_entities` | Manual or extraction callers | split E2a/E2b | E2a uses cursor repository; allowed manual-E2a state, preserve | 0 direct | 0 processes | LOW | Inventory completeness and denylist DML test |
| `Method:llamaindex_runtime/registry/postgres_adapter.py:PostgresRegistryWriter.write_evidence_links#2` | `PostgresRegistryWriter.write_evidence_links` | Manual or extraction callers | split E2a/E2b | E2a uses cursor repository; allowed manual-E2a state, preserve | 0 direct | 0 processes | LOW | Inventory completeness and denylist DML test |

---

## Graph Evidence Caveats

### VectorLoader.load — Unresolved Partial Tool Result

**Tool Output**: GitNexus `impact` queries failed internally with read-only pool error returning `partial: true`.
**Context Query**: Shows only tests and `verification/p6_validation`, no production processes.
**Assertion Status**: This is an unresolved partial tool result, NOT a verified zero-impact assertion. Fresh impact analysis is mandatory before any edit.
**Disposition**: No Wave 1 modification; Wave 2 must assert no external backend projection.

---

## Caller Classification Notes

**Production Callers** (from graph evidence):
- Direct callers enumerated from GitNexus upstream impact results
- Processes enumerated from GitNexus process queries
- Risk classification from GitNexus (CRITICAL > HIGH > MEDIUM > LOW)

**Test/Diagnostic Callers** (explicitly non-production):
- Tests under `tests/llamaindex_runtime/`
- Verification fixtures under `verification/`
- Diagnostic scripts in repository root

**Classification Logic**:
- E2a: Primary migration target, must be migrated/adapted
- E2b: Phase 16 entity layer, structurally unreachable from E2a
- legacy: Forbidden from E2a flow
- cache/legacy: Retain only consumer behavior, no registry authority
- split E2a/E2b: Context-dependent ownership

---

## Completeness Gate

Before any source edit:
1. Execute GitNexus upstream impact for every symbol above (or note unresolved partial results)
2. Use `gitnexus_query` for ingestion, PageIndex, tree, vector, and callback flows
3. Compare each result with repository-wide symbol references
4. Record direct callers, affected processes, risk, revision/index freshness, and final disposition
5. A HIGH/CRITICAL result must be surfaced before edits continue
6. Any unresolved partial tool results must be clearly marked and re-run before edit

---

## Required Normal Ingestion Order (Track A)

1. Register or resolve provenance parent
2. Execute exactly one Docling conversion
3. Capture serializer-compatible nodes and conversion metadata
4. Call `serialize_document(nodes, doc_id, version_id, source_checksum, docling_version, bundle_root, name)`
5. Strictly admit the M-D-S-M raw pair
6. Perform whole-corpus E2a reconciliation

Spy tests must prove this order and prove no normal call to `write_spans`, direct persistence fallback, or E2b callback.

---

## Wave 0 Execution Summary

**Inventory Status**: Complete execution record with GitNexus tool evidence
**CRITICAL Symbols**: 3 (IngestionPipeline.ingest, write_tree, PageIndexTreeAdapter._flatten_embedded_tree)
**HIGH Symbols**: 3 (PostgresRegistryWriter.write_spans, PageIndexTreeAdapter.index_tree, EnhancedPageIndexClient.index)
**Unresolved Partial Results**: 1 (VectorLoader.load - requires fresh impact before edit)
**Phase 15 Status**: Open (this inventory is Wave 0 capture, not Phase closure)

**Enforcement Test**: `tests/llamaindex_runtime/okf/test_phase15_caller_inventory_enforcement.py`