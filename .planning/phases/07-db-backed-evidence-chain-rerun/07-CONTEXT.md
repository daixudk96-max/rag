# Phase 7: DB-Backed Evidence-Chain Rerun — Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** ROADMAP Phase 7 + v1.0 milestone audit after Phase 6

<domain>
## Phase Boundary

Phase 7 closes `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`: configure and run DB-backed active-version diagnostics and materialization proof so evidence-chain counts are non-zero/explainable and scoped to the intended active version.

This phase does **not** collect human judgments and does **not** produce a final Level assessment. Those belong to Phase 8.

Phase 7 may end in either:

1. `DB_EVIDENCE_READY` — active-version evidence-chain counts are non-zero/explainable and gate is ready for Phase 8.
2. `DB_EVIDENCE_BLOCKED` — DB is unavailable or materialization still leaves gaps, but the blocker is exact and source-backed.
</domain>

<decisions>
## Implementation Decisions

### D-07-01: DATABASE_URL presence is a gate, not a secret to print
Diagnostics may record `database_url_configured: true/false`, but must never print or write the raw connection string.

### D-07-02: Active version scope is mandatory
All counts must be scoped to the intended `active_version_id`; global table counts are not authoritative for Phase 7.

### D-07-03: Before/after materialization comparison is required
Phase 7 must capture diagnostics before materialization, run the materialization path, then capture diagnostics after materialization.

### D-07-04: Explainable zero is better than false pass
If `chunks`, `mapped_chunks`, or `heading_path_rate` remain zero, Phase 7 must classify why and preserve the blocker for Phase 8/next remediation.

### D-07-05: No judgment collection in Phase 7
Phase 7 can prepare evidence-chain readiness only. Human judgment collection begins only when the integrity gate allows `collect_judgments`, owned by Phase 8.

### D-07-06: Level 2 remains authoritative
Phase 7 must not update Level baseline or publish a new `level_assessment.json`.
</decisions>

<canonical_refs>
## Canonical References

### Phase 7 scope and audit
- `.planning/ROADMAP.md` — Phase 7 goal and workstreams.
- `.planning/v1.0-MILESTONE-AUDIT.md` — current audit gap for `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`.
- `.planning/REQUIREMENTS.md` — requirement row for Phase 7.
- `.planning/STATE.md` — current route and Level 2 baseline.

### Phase 5 diagnostics and gates
- `.planning/phases/05-evidence-chain-verification-and-resolver-consolidation/05-SUMMARY.md` — DB-backed rerun sequence and current blockers.
- `verification/phase5-evidence-chain-verification/verify_active_version_counts.py` — active-version evidence-chain diagnostic utility.
- `verification/phase5-evidence-chain-verification/invoke_vector_loader.py` — materialization checkpoint utility.
- `verification/phase5-evidence-chain-verification/validation_integrity_gate.py` — integrity gate that consumes counts.
- `verification/phase5-evidence-chain-verification/active_version_counts.json` — current local fail-closed artifact.
- `verification/phase5-evidence-chain-verification/heading_path_contract.json` — heading-path metric source contract.

### Existing DB-backed evidence
- `verification/phase4-quality-validation/db-backed-node-aware-rerun-20260607/validation_status.json` — prior DB-backed snapshot with evidence-chain zeros.
</canonical_refs>

<specifics>
## Specific Ideas

- Write Phase 7 artifacts under `verification/phase7-db-backed-evidence-chain-rerun/`.
- Use separate before/after files:
  - `db_readiness.json`
  - `active_version_counts.before.json`
  - `materialization_result.json`
  - `active_version_counts.after.json`
  - `evidence_chain_delta.json`
- `db_readiness.json` should include `database_url_configured`, `connection_status`, `active_version_id`, and table availability, but never raw `DATABASE_URL`.
- `evidence_chain_delta.json` should classify `DB_EVIDENCE_READY` or `DB_EVIDENCE_BLOCKED`.
</specifics>

<deferred>
## Deferred Ideas

- Matched retrieval/judgment generation is deferred to Phase 8.
- Human judgment collection is deferred to Phase 8.
- Milestone close/git/tag is deferred to Phase 9.
</deferred>

---

*Phase: 07-db-backed-evidence-chain-rerun*
*Context gathered: 2026-06-08 via Navigator-guided planning*
