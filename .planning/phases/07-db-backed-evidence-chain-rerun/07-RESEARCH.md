---
phase: 7
slug: db-backed-evidence-chain-rerun
status: complete
generated: 2026-06-08
---

# Phase 7 Research — DB-Backed Evidence-Chain Rerun

## Research Question

How should Phase 7 prove or explain DB-backed evidence-chain readiness without leaking secrets, advancing the Level baseline, or collecting judgments too early?

## Current State

Phase 5 delivered these utilities:

- `verification/phase5-evidence-chain-verification/verify_active_version_counts.py`
  - Supports `--version-id`.
  - Supports `--output`.
  - Writes active-version-scoped counts.
  - Returns non-zero when DB is unavailable or no data is available.
- `verification/phase5-evidence-chain-verification/invoke_vector_loader.py`
  - Supports `--version-id`.
  - Writes `vector_loader_materialization.json` in the Phase 5 directory.
  - Returns non-zero when `DATABASE_URL` is missing or DB connection fails.
- `verification/phase5-evidence-chain-verification/validation_integrity_gate.py`
  - Consumes active-version counts and blocks human judgment / metric calculation unless evidence-chain and retrieval/judgment artifacts are consistent.

Current local `active_version_counts.json`:

```json
{
  "active_version_id": null,
  "database_url_configured": false,
  "data_available": false,
  "stats": {},
  "classification": "missing_canonical_spans"
}
```

## Key Planning Implications

### 1. Phase 7 starts with environment readiness

Before materialization, executor must know whether DB access exists. The check must write a sanitized artifact and must never expose raw `DATABASE_URL`.

Recommended artifact:

- `verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json`

Required fields:

- `database_url_configured`: boolean
- `connection_status`: `not_configured | connected | connection_failed`
- `active_version_id`: string or null
- `tables_checked`: list of registry/evidence-chain tables checked
- `ready_for_materialization`: boolean
- `blocking_reasons`: list of strings

### 2. Before/after counts are mandatory

Phase 7 should run:

```text
verify_active_version_counts.py --output active_version_counts.before.json
invoke_vector_loader.py
verify_active_version_counts.py --output active_version_counts.after.json
```

If DB is unavailable, the before artifact should still exist and classify the blocker. Materialization should be skipped or recorded as blocked.

### 3. Evidence-chain delta is the proof artifact

Recommended artifact:

- `verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`

It should compare before/after:

- `canonical_spans`
- `vector_chunks`
- `vector_chunks_with_node_id`
- `mapped_chunks_rate`
- `vector_chunk_spans`
- `tree_node_spans`
- `heading_path_rate`
- `classification`

Final classification:

- `DB_EVIDENCE_READY`
- `DB_EVIDENCE_BLOCKED`

### 4. Phase 7 must not collect judgments

Even if DB evidence is ready, human judgment collection belongs to Phase 8. Phase 7 routes to Phase 8 only after evidence-chain state is ready or explicitly explainable.

### 5. Level 2 remains authoritative

Phase 7 cannot write a new `level_assessment.json`. It can only produce DB/evidence-chain proof artifacts and a verification summary.

## Validation Architecture

### Automated checks

- `rtk grep "database_url_configured" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json`
- `rtk grep "classification" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json`
- `rtk grep "final_classification" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`
- `rtk grep "Level 2 remains authoritative" .planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md`

### Manual checks

- If `DATABASE_URL` is not configured, user must configure it outside the plan with session-safe secret handling.
- If materialization remains blocked after DB access, inspect `evidence_chain_delta.json` and `vector_loader_materialization.json`.

## Recommended Plan Structure

1. `07-PLAN-01`: DB readiness and active version target.
2. `07-PLAN-02`: Before/after diagnostics around materialization.
3. `07-PLAN-03`: Verification summary and routing.

## Risks

| Risk | Mitigation |
|------|------------|
| Raw DB secret leakage | Only write booleans/status, never connection string. |
| Wrong active version | Require `active_version_id` artifact and allow explicit `--version-id`. |
| False readiness | Use `classification` from `verify_active_version_counts.py`; do not override blockers. |
| Premature judgments | Phase 7 summary must say Phase 8 owns judgment collection. |
| Level drift | Repeat that Level 2 remains authoritative. |
