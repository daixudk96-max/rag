# Phase 7 Patterns — DB-Backed Evidence-Chain Rerun

## Source Analog Map

| Target artifact / behavior | Existing analog | Pattern to reuse |
|----------------------------|-----------------|------------------|
| `db_readiness.py` | `verify_active_version_counts.py` | Parse optional `--version-id`, read `DATABASE_URL` without printing it, catch `psycopg.Error`, write JSON artifact. |
| `db_readiness.json` | `active_version_counts.json` | Sanitized readiness report with booleans/status/classification. |
| Before/after diagnostics | `invoke_vector_loader.py` | Capture counts before/after materialization and write JSON. |
| Evidence-chain delta | `validation_integrity_report.json` | Machine-readable gate artifact with `passed`/blocking reasons/next action. |
| Phase summary | `05-SUMMARY.md`, `06-SUMMARY.md` | Explicit READY/BLOCKED handoff and next route. |

## Artifact Naming Pattern

Write all Phase 7 generated outputs under:

```text
verification/phase7-db-backed-evidence-chain-rerun/
```

Files:

- `db_readiness.py`
- `db_readiness.json`
- `active_version_counts.before.json`
- `vector_loader_materialization.json`
- `active_version_counts.after.json`
- `evidence_chain_delta.json`

## Classification Pattern

Use these statuses:

- `DB_EVIDENCE_READY`
  - DB configured and connected.
  - Active version resolved.
  - Post-materialization classification is `evidence_chain_ready`.
- `DB_EVIDENCE_BLOCKED`
  - DB missing or connection failed.
  - Active version missing.
  - Post-materialization classification is still one of `missing_canonical_spans`, `missing_vector_materialization`, `missing_node_chunk_mapping`, or `missing_heading_paths`.

## Secret Safety Pattern

Allowed:

```json
{
  "database_url_configured": true,
  "connection_status": "connected"
}
```

Forbidden:

```json
{
  "database_url": "postgresql://user:password@host/db"
}
```

## Execution Pattern

```text
1. Run DB readiness.
2. If DB unavailable, write blocked artifacts and stop materialization.
3. If DB available, run before counts.
4. Run vector materialization.
5. Run after counts.
6. Compare counts and write delta.
7. Summarize READY/BLOCKED route.
```

## Anti-Patterns

- Do not use global table counts as authoritative readiness proof.
- Do not print or write raw `DATABASE_URL`.
- Do not collect judgments in Phase 7.
- Do not update `level_assessment.json` in Phase 7.
- Do not treat `DATABASE_URL` missing as a code failure; it is an environment blocker with a fail-closed artifact.
