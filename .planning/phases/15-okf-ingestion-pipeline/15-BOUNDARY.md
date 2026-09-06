<!-- generated-by: gsd-doc-writer -->
# Phase 15 (E2a): OKF Unified Ingestion Pipeline — Refined Boundary

## Active status and authorization

Phase 15 is **accepted and CLOSED** (dated 2026-08-05). Real acceptance passed through the chain **Task #88 (real disposable PostgreSQL transition matrix) -> Task #89 (durable integration boundary exact live selector) -> Task #90 (pure/static gate + exact authorized live selector)**, with **Task #54** as the goal-backward aggregate audit (**PASS_WITH_CLOSURE_UPDATES**, 10/10 must-haves, 0 acceptance blockers, 1 non-blocking warning).

- User selection: `授权规划和实施（推荐）`
- Authorization source: `interactive Claude Code session`
- Limitation: this is not an independent repository transport receipt. No date, receipt ID, or durable independent authorization evidence is claimed.

Original authorization history is preserved. All prior one-shot live authorizations were consumed by Tasks #88/#89/#90; no current live authorization exists and no further live execution is required for closure. The prior named local disposable Task #88 selector batches (sequential, once each, stop on first failure, no automatic retry) are complete. Closure does not authorize Phase 16/E2b, Phases 19/20, production, Git operations, or external database connections. Phase 14 summaries/evidence remain historical and unchanged. No commit/push is authorized and none was performed.

## Authority and precedence

1. The execution handoff governs Phase 15 scope and phase routing.
2. The unified OKF plan governs compatible architecture.
3. Accepted ADRs govern their explicit scope: `ADR-OKF-PHASE-A-TECH-DECISIONS-2026-07-12.md` governs Phase-A decisions and `ADR-OKF-RAW-PAIR-GENERATION-BINDING-2026-07-16.md` governs raw-pair publication/admission.
4. Milestone and roadmap documents map execution only.

Earlier wording that authorizes a persisted direct chain, `RAG_INGESTION_PATH=direct`, automatic fallback, a rollback direct writer, or a parallel direct/OKF fact path is historical and superseded for active Phase 15 routing.

## Goal

E2a makes OKF the unique durable knowledge authority and PostgreSQL a derived, disposable, rebuildable materialization cache. Normal binary ingress is exactly: provenance parent registration → one Docling conversion → `serialize_document` raw-triplet publication → strict raw-pair admission → whole-corpus E2a reconciliation. The transaction materializes canonical spans, vector chunks/mappings, canonical trees/mappings, manual OKF entities/relations/evidence/evidence-links, ownership, and sync state.

## In scope

- Strict raw triplet admission and frozen span identity reuse.
- One caller-owned PostgreSQL transaction with deterministic desired state, lock order, exact reconciliation, and post-rollback fresh-connection failure audit.
- Migration 019 materialization/ownership/evidence contract and a single root migration catalog.
- Deterministic tree reconciliation and only allowlisted cache invalidations.
- Normal-ingress caller switchover; PageIndex only as canonical-tree consumer/cache.
- Pure direct derivation only as a non-persisting unit-test/disposable shadow comparator.
- Measured typed-result verification specification; bounded local database acceptance verification was completed by Tasks #88/#89/#90 and closed.

## Explicit E2a data boundary

**Primary allowlist:** `canonical_spans`, `vector_chunks`, `vector_chunk_spans`, `tree_nodes`, `tree_node_spans`, manual OKF `entities`, `relations`, `evidence`, span-backed manual `evidence_links`, ownership ledger, and `okf_sync_state`.

**Permitted effects:** stale-node cache invalidation/counts for `summaries`, `node_embeddings`, `semantic_distribution`; bounded failure audit after primary rollback/close.

**Denied:** `chunk_entity_links`, `node_entity_links`, `entity_mentions`, `entity_aliases`, `entity_merge_log`, NER-generated facts, E2b/R3/fusion state, and D4 tuning. E2a must fail closed rather than cascade-null/delete E2b-owned rows.

## Control-plane trust boundary

An append-only function attestation validates observed catalog state, including `pg_proc` and trigger state; it has no `pg_proc` exclusion. An authorized function owner or superuser can replace an attested function or trigger concurrently or after commit. The final same-transaction re-attestation is detection only, not a control-plane lock or race prevention, and provides no hostile-superuser, tamper-evidence, or postcommit guarantee.

Role separation, a runner lease, system catalog locking, and production DDL governance are excluded from this Phase 15 boundary. The audit trigger constrains ordinary data mutation only; it does not establish those excluded controls. Production ownership, least privilege, a cooperative migration lease, controlled DDL, and postdeployment attestation are separately authorized operational work.

## Non-goals

No E2b NER/association work, E2a-to-E2b callback composition, dual persisted source paths, external vector projection, production action, Git operation, Level/quality claim, Phase 16 planning/execution, Phase 19/20, or unbounded/general disposable DB/Docker acceptance. The named local Task #88 selectors were the sole exception and are complete. External DB/production connections remain prohibited.

## Acceptance boundary

- Equivalent input has zero primary DML, including ownership and sync state; it does not refresh timestamps or write a no-op success record.
- A raw pair is validated M-D-S-M, at most three attempts, and fails closed without legacy fallback.
- All locking is transaction-scoped: global corpus advisory, sorted parent advisory, then sorted existing parent rows `FOR UPDATE`.
- Relation equality includes negation, condition, direction, finite confidence, and canonical JSONB qualifiers.
- Tree input/domain ordering is deterministic; shuffled equivalents preserve IDs/mappings/manifest and have zero second-run primary DML.
- Verification consumes `E2aReconciliationResult`; it cannot manufacture acceptance evidence.

## Plan registry

- `15-01-PLAN.md` — deterministic admission, ownership, migration 019, migration catalog. [summary: `15-01-SUMMARY.md`]
- `15-02-PLAN.md` — cursor-only exact reconciliation, locks, idempotence, trees, cache effects. [summary: `15-02-SUMMARY.md`]
- `15-03-PLAN.md` — one-conversion ingress switchover, pure comparator, PageIndex consumer boundary. [summary: `15-03-SUMMARY.md`]
- `15-04-PLAN.md` — measured-result verification and bounded acceptance verification handling. [summary: `15-04-SUMMARY.md`]


## Binding remediation

The exact corpus API, desired-state collections, ingress sequence, named 019 constraints/preflight, and destructive closure rules are defined in `15-CONTEXT.md` Binding remediation details and are mandatory plan inputs. External backend projection/outbox/status is removed from selected E2a scope. Existing external backends are non-authoritative; any synchronization requires a separate design.

## Migration 019 atomic file-size exception

The universal under-800-physical-lines guideline remains in force. The sole exception is governed by [ADR-PHASE15-MIGRATION019-ATOMIC-FILE-SIZE-EXCEPTION-2026-07-19.md](../../ADR-PHASE15-MIGRATION019-ATOMIC-FILE-SIZE-EXCEPTION-2026-07-19.md): 019 remains one fail-closed dynamic `DO` state machine, classified before DDL, catalogued and applied exactly once, without runtime fragment composition or helper database objects. Fresh/final/rerun checks and the completed disposable proof contract are mandatory compensating controls.
