# Phase 7 Summary — DB-Backed Evidence-Chain Rerun

## Requirement

`REQ-P7-DB-EVIDENCE-CHAIN-PROOF`

## Result

`DB_EVIDENCE_READY`

Phase 7 now has a DB-backed active-version evidence chain for version `a376679b-3a95-4724-a31f-ece0c9fa35b8`.

The original blocker sequence was resolved in order:

1. `database_url_not_configured` — fixed by loading the repo-root `.env` in Phase 7 scripts.
2. `connection_failed` — fixed by starting the existing `rag_registry_postgres` Docker container.
3. `missing_canonical_spans` — fixed by completing parsing for the registered active version and writing canonical spans.
4. `missing_node_chunk_mapping` — fixed by reconstructing `tree_node_spans` from existing canonical spans and tree nodes, then rerunning vector-node linking.

## Final Evidence Counts

| Metric | Value |
|--------|-------|
| `canonical_spans` | 54 |
| `canonical_spans_with_heading_path` | 54 |
| `heading_path_rate` | 1.0 |
| `vector_chunks` | 54 |
| `vector_chunks_with_node_id` | 54 |
| `mapped_chunks_rate` | 1.0 |
| `vector_chunk_spans` | 54 |
| `tree_node_spans` | 54 |
| `classification` | `evidence_chain_ready` |

## Artifacts

| Artifact | Status | Meaning |
|----------|--------|---------|
| `verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json` | ready | DB readiness gate connected to PostgreSQL and resolved the active version. |
| `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json` | ready | Before-counts classify the active version as `evidence_chain_ready`. |
| `verification/phase7-db-backed-evidence-chain-rerun/vector_loader_materialization.json` | complete | VectorLoader completed for 54 chunks. |
| `verification/phase7-db-backed-evidence-chain-rerun/tree_node_span_repair.json` | complete | 54 tree-node span mappings generated and inserted; all 54 vector chunks linked to nodes. |
| `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json` | ready | After-counts classify the active version as `evidence_chain_ready`. |
| `verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` | complete | Final classification is `DB_EVIDENCE_READY`. |

## Interpretation

Level 2 remains authoritative until Phase 8 completes matched retrieval, integrity-gated judgment collection, metric calculation, and valid Level assessment publication.

Human judgment collection is still deferred to Phase 8 and must remain gated by `validation_integrity_report.json.next_allowed_action == "collect_judgments"`.

Phase 7 did not publish a new `level_assessment.json` and did not update the quality baseline.

## Next Route

Next route: `/gsd-execute-phase 8`

Phase 8 may now run its preflight. It must still enforce its own gates before retrieval, judgment collection, metrics, or baseline update.
