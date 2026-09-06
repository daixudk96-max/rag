# Phase 15 Context — OKF Ingestion Pipeline (E2a)

## Authorization and execution state

Phase 15 is **authorized, planned, and execution-unstarted**.

- User selection: `授权规划和实施（推荐）`
- Authorization source: `interactive Claude Code session`
- Limitation: this record is not an independent repository transport receipt. No date, receipt ID, or durable independent authorization evidence is asserted.

This authorization permits Phase 15 planning and source implementation only. It does not authorize Phase 16/E2b, Phases 19/20, production activity, Git operations, or disposable PostgreSQL/Docker acceptance. The latter requires separate active authority. Phase 14/E1 summaries and evidence remain historical and unchanged.

## Locked decisions

| ID | Decision |
|---|---|
| D-15-01 | OKF is the sole durable knowledge authority. PostgreSQL is a disposable, rebuildable derived materialization cache. |
| D-15-02 | E2a operates on one whole admitted corpus/scope, never independently persisted documents. |
| D-15-03 | E2a performs all primary materialization in one caller-owned PostgreSQL transaction. Validate, admit, normalize, derive desired state, and embed before locks; then commit all primary DML or roll it back. |
| D-15-04 | E2a primary scope is `canonical_spans`, `vector_chunks`, `vector_chunk_spans`, `tree_nodes`, `tree_node_spans`, manual OKF `entities`, `relations`, `evidence`, span-backed manual `evidence_links`, ownership ledger, and `okf_sync_state`. A failure audit uses a fresh connection only after rollback and primary connection close. |
| D-15-05 | Equivalent input has zero DML in every primary table, ownership ledger, and `okf_sync_state`; reconciliation removes stale E2a state in FK-safe order. |
| D-15-06 | Raw admission is the strict adjacent `.md`, `.spans.json`, `.pair.json` contract governed by `ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md`. Reuse `NormalizationContract.normalize` and frozen span UUID5 identity; never copy normalization logic. |
| D-15-07 | `TreeGenerator.generate_tree` is canonical. PageIndex is a non-authoritative consumer/cache and cannot persist tree authority. |
| D-15-08 | E2a manual facts are validated `entities/**/*.md`, `relations/**/*.md`, and `concepts/**/*.md`; templates, support, synthesis, and raw files are not facts. |
| D-15-09 | Manual evidence resolves uniquely to document/version/span and exactly one entity or relation target. Label/quote-only evidence is invalid. Deterministic identities are mandatory and relation qualifiers are preserved. |
| D-15-10 | Direct Docling derivation is allowed only as a pure, non-persisting test or disposable shadow comparator. `RAG_INGESTION_PATH=direct`, automatic fallback, and every ordinary second fact path are prohibited. |
| D-15-11 | E2a does not project to external vector backends in the acceptance path. `vector_chunks.embedding vector(16)` remains E2a; `node_embeddings.embedding_vector vector(384)` remains a distinct cache. External backends are non-authoritative and require a separate future design. |
| D-15-12 | Generation/promotion IDs are deferred to a separate ADR/schema initiative; the atomic PostgreSQL transaction provides primary reader visibility. |
| D-15-13 | An append-only function attestation validates observed catalog state without a `pg_proc` exclusion. Final same-transaction re-attestation is detection only, not a lock or race prevention: an authorized function owner or superuser can replace a function or trigger concurrently or after commit. It makes no hostile-superuser, tamper-evidence, or postcommit guarantee. Production ownership, least privilege, a cooperative migration lease, controlled DDL, and postdeployment attestation are separately authorized operational work. |

## E2a DML boundary

**Allowlist:** only the primary tables named by D-15-04, cache invalidation/deletion effects for `summaries`, `node_embeddings`, and `semantic_distribution`, bounded failure audit after rollback.

**Denylist:** `chunk_entity_links`, `node_entity_links`, `entity_mentions`, `entity_aliases`, `entity_merge_log`, all NER-derived material, E2b/R3/fusion state, D4 tuning, automatic writeback, production deployment, and Git operations. The DML recorder and measured result must report this boundary.

## Required implementation architecture

- Admission uses the accepted raw-pair ADR M-D-S-M protocol: manifest, markdown, sidecar, manifest again; three total attempts; fail closed with no legacy production fallback.
- Desired state is immutable. The primary repository is cursor-only, accepts a caller-owned cursor, and never commits, rolls back, changes autocommit, or opens a replacement transaction.
- Required contract direction:

```python
class E2aMaterializationRepository:
    def reconcile(
        self,
        cursor: Cursor,
        desired: E2aDesiredState,
        *,
        recorder: DmlRecorder,
    ) -> E2aReconciliationResult: ...
```

- Existing `PostgresRegistryWriter.write_*` APIs and `VectorLoader.load()` are not E2a transaction primitives.
- Obtain a transaction-scoped global E2a advisory lock, then sorted per-parent advisory locks (including new parents), then sorted existing-parent `FOR UPDATE` locks. Hold them to commit or rollback.
- Reconcile tree nodes parent-first; reconcile node-span links; repoint surviving chunks before deleting stale nodes; count/invalidate summaries, node embeddings, and semantic distribution; fail closed if stale nodes retain `node_entity_links`.
- Use `IS DISTINCT FROM`, finite confidence validation, canonical JSONB qualifier comparison, and no unconditional timestamp refresh. A true no-op has no durable success/no-op log.
- Tree input and normalized semantic domain keys are totally sorted. Shuffled equivalent spans must yield identical tree IDs/mappings/manifest and zero second-run primary DML.

## Migration 019 contract

The required planned migration is `llamaindex_runtime/registry/migrations/019_e2a_materialization_contract.sql`. It must provide the minimal additive constraints/DDL for a manual-fact ownership ledger keyed by safe canonical relative OKF path, fact kind, and deterministic fact ID; source digest; nullable admitted doc/version scope; multi-owner global entities/relations; same-version composite uniqueness/FKs for spans, evidence, and E2a evidence links; exactly one target; required E2a evidence object; constrained source kind; deterministic dedup; bounded E2a failure phases extending 018. Migration 019 and E2a selected scope contain no projection outbox or external-projection status. A natural-key collision with different deterministic identity or incompatible ownership fails closed. Never cascade-null/delete E2b data.

## Known impacts and implementation checkpoints

Before modifying source, rerun GitNexus impact for every edited symbol and warn on HIGH/CRITICAL results. Existing recorded risks: `IngestionPipeline.ingest` CRITICAL; `PostgresRegistryWriter.write_spans` HIGH; `PostgresRegistryWriter.write_tree` CRITICAL; `PageIndexTreeAdapter.index_tree` HIGH; `EnhancedPageIndexClient.index` HIGH; `DoclingIngestor.ingest` MEDIUM; `TreeGenerator.generate_tree` MEDIUM. `VectorLoader.load` impact is incomplete/unknown and must be rerun.

## Non-goals

No Phase 16/E2b extraction, NER, aliases/merge provenance, `node_entity_links`, R3/fusion, D4 tuning, automatic writeback, production rollout, Git activity, or retrieval-quality/Level claim. R1/R2a/R2b/p6 are smoke-only.


## Binding remediation details

**Precedence.** The handoff governs scope and routing; the unified plan governs compatible architecture; accepted ADRs govern explicit technical scope, including `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` and raw-pair ADR `ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md`; milestone/roadmap map execution only. HIGH/CRITICAL GitNexus impact is warning/reporting, not undefined approval. A newly discovered scope expansion blocks for user decision.

**Normal ingress.** Add immutable `DoclingConversionResult(source_uri, source_sha256, docling_version, nodes)` and `DoclingIngestor.convert_for_okf(source_path)`. It invokes reader conversion and node parsing exactly once and does not build spans or persist. Normal ingress order is register parent, convert once, send the returned nodes to `serialize_document`, publish manifest last, open `BundleAuthority`, call `read_raw_pair(authority, ("raw", "<slug>.md"))`, call `admit_e2a_corpus(authority)`, and reconcile the complete corpus in one caller-owned transaction. The direct comparator accepts no connection, cursor, writer, or persistence import.

**Admission.** `admit_e2a_corpus(authority) -> E2aDesiredState` recursively discovers `raw/**/*.pair.json` and admits each raw document only through manifest-bound M-D-S-M `read_raw_pair`. It separately admits only `entities/**/*.md`, `relations/**/*.md`, and `concepts/**/*.md`; excludes templates, synthesis, AGENT files, index/log, raw triplet members, hidden/support/reserved files; requires safe POSIX paths; rejects unsupported or duplicate document-version/fact identities; validates all candidates before return; sorts `(kind, normalized_relative_path, stable_identity)`; emits canonical corpus JSON plus SHA-256; and fails closed on empty/invalid corpus without partial state.

**Desired state.** Immutable `E2aDesiredState` includes corpus manifest/hash, ordered parents, canonical spans, vector chunks and chunk-span links, tree nodes and node-span links, manual entities, relations, evidence objects, evidence links, ownership facts, sync rows, and validation/provenance metadata, all with deterministic natural keys. It deliberately omits E2b and external-projection state. `E2aReconciliationResult` outcomes are `changed`, `no_op`, `rolled_back_failure`, and `acceptance_blocked`, with allowed DML, denylist counts, comparator parity, stale/cache counts, and post-rollback audit status only.

**019 and closure.** Migration 019 preflights legacy `evidence_links` and aborts without rewrite for cross-version span/evidence mismatches or both/neither targets; it emits stable redacted runner errors; creates `UNIQUE(version_id, span_id)`, `UNIQUE(version_id, evidence_id)`, named composite evidence-link FKs, and `CHECK (num_nonnulls(entity_id, relation_id) = 1)`. Ownership has deterministic ID, safe path, constrained kind, fact ID, digests, nullable scope, duplicate prevention and multi-owner support. Legacy source-kind default remains; nullable ownership FK permits legacy rows; `manual_okf` requires ownership and evidence; E2a dedup uses a scoped partial unique index. Drop/recreate known names and reject unknown failure phases. The allowed phase set is target_validation, scope_lock, parent_reconciliation, span_reconciliation, tree_reconciliation, chunk_reconciliation, manual_fact_reconciliation, evidence_reconciliation, transaction_commit, and success_log_write only when retained. There is no outbox or external projection status.

For stale spans reject `entity_mentions` or non-E2a/legacy evidence. For chunks reject `chunk_entity_links`. For a tree recursively evaluate stale descendants, reject any `node_entity_links`, repoint surviving chunks, invalidate/count summaries, node_embeddings, semantic_distribution, then remove E2a links/nodes. Remove stale ownership before deleting a global fact; delete only with no remaining owner, mention, alias, node/chunk link, outside-scope relation, or non-E2a evidence. Recorder accounts for app DML and DB cascades; forbidden closure rolls back all primary work.
