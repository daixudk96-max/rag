# Phase 15 Focused Research Record

## Reuse decision

Use the repository’s existing strict raw triplet admission, `NormalizationContract`, frozen span UUID5 v1 identity, `TreeGenerator.generate_tree`, deterministic 16-dimensional chunk embedding path, and Phase 14 rollback-audit structure. Replace method-local insert/no-op behavior with an E2a-owned exact-reconciliation service; do not convert existing component writers into a hidden per-method transaction boundary.

OpenKB/VectifyAI `MutationSnapshot` and `HashRegistry` are reference-only examples for rollback journals and SHA-256 state. The locally recorded upstream assessment identifies Apache-2.0 licensing. Any copied or substantially adapted code requires file-level attribution and license review; no wholesale pipeline adoption is approved.

## Primary-document constraints for implementation

1. Confirm the installed psycopg version’s transaction/connection-close semantics in its official documentation before writing the caller-owned transaction and post-rollback audit flow.
2. Confirm PostgreSQL lock and FK/cascade behavior from PostgreSQL documentation before selecting lock statements and scoped delete queries.
3. Confirm the Python pgvector package/adapter import and registration behavior from its primary project documentation before changing dependencies. The current project dependency declaration does not visibly list `pgvector`; create a recorded reproducibility decision rather than assuming an undeclared transitive dependency.
4. Preserve the existing database vector contracts: `vector_chunks.embedding vector(16)` for deterministic/local chunk embeddings and `node_embeddings.embedding_vector VECTOR(384)` for node prototypes. These are not interchangeable.

## Rejected alternatives

- Broad generation/promotion schema: deferred until a distinct ADR plus schema and query-visibility migration.
- Independent PageIndex tree persistence: rejected because it creates UUID4 node identities and no authoritative node-span mapping.
- External vector projection in the primary transaction: rejected because it makes an external service authoritative for database acceptance.
- Paragraph-label-only manual evidence: rejected because it cannot uniquely resolve to an admitted span.
