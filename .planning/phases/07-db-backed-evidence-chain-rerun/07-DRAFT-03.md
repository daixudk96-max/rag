---
phase: 07-db-backed-evidence-chain-rerun
plan: 03
type: execute
wave: 3
depends_on:
  - 07-PLAN-02
files_modified:
  - verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json
  - .planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md
  - .planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md
requirements:
  - REQ-P7-DB-EVIDENCE-CHAIN-PROOF
autonomous: true
---

<objective>
Compare Phase 7 before/after evidence-chain artifacts, publish a machine-readable `DB_EVIDENCE_READY` or `DB_EVIDENCE_BLOCKED` delta, and write the Phase 7 summary/verification handoff that routes safely into Phase 8 without collecting judgments or changing the authoritative Level 2 baseline.
</objective>

<must_haves>
  <truths>
    <truth>D-07-03: The evidence proof is based on before/after materialization artifacts.</truth>
    <truth>D-07-04: Zero or blocked evidence-chain state is classified and preserved, not hidden.</truth>
    <truth>D-07-05: Phase 7 summary explicitly says human judgment collection is deferred to Phase 8.</truth>
    <truth>D-07-06: Phase 7 summary explicitly says Level 2 remains authoritative.</truth>
    <truth>REQ-P7-DB-EVIDENCE-CHAIN-PROOF is closed only as ready or blocked with exact DB evidence.</truth>
  </truths>
  <key_links>
    <link from="verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json" to="verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json" via="before stats" pattern="stats|classification|status" />
    <link from="verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json" to="verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json" via="after stats and final classification" pattern="final_classification|DB_EVIDENCE_READY|DB_EVIDENCE_BLOCKED" />
    <link from="verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json" to=".planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md" via="routing decision" pattern="Phase 8|Level 2 remains authoritative|judgment collection deferred" />
  </key_links>
</must_haves>

<threat_model>
  <threat id="T-07-05" severity="medium" stride="Information Disclosure">
    Summary or delta files could copy sensitive DB connection details from lower-level artifacts.
    Mitigation: delta and summary may cite only sanitized booleans, statuses, active version IDs, classifications, counts, and blocking reason codes.
  </threat>
  <threat id="T-07-06" severity="high" stride="Tampering">
    A blocked or partial Phase 7 result could be misrepresented as quality readiness, causing premature Phase 8 judgment collection or invalid Level advancement.
    Mitigation: `evidence_chain_delta.json` uses `DB_EVIDENCE_READY` only when after classification is `evidence_chain_ready`; otherwise it uses `DB_EVIDENCE_BLOCKED` and summary keeps Level 2 authoritative.
  </threat>
</threat_model>

<tasks>
  <task type="auto">
    <name>Task 03-01: Build evidence-chain delta artifact</name>
    <read_first>
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/vector_loader_materialization.json
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-RESEARCH.md
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-PATTERNS.md
    </read_first>
    <action>
      Create `verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` by comparing before/materialization/after artifacts.

      Required JSON fields:
      - `requirement_id`: `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`
      - `active_version_id`: string or null
      - `before_classification`: value from before artifact `classification`, or null when blocked
      - `after_classification`: value from after artifact `classification`, or null when blocked
      - `materialization_status`: `completed` or `blocked`
      - `stats_delta`: object with keys `canonical_spans`, `vector_chunks`, `vector_chunks_with_node_id`, `vector_chunk_spans`, `tree_node_spans`, `heading_path_rate`, and `mapped_chunks_rate`; values are numeric deltas when stats exist, otherwise null
      - `final_classification`: `DB_EVIDENCE_READY` only when `after_classification == "evidence_chain_ready"`; otherwise `DB_EVIDENCE_BLOCKED`
      - `blocking_reasons`: copied from blocked artifacts or derived from `after_classification` when not ready
      - `next_allowed_action`: `phase8_matched_validation_rerun` when ready; otherwise `fix_evidence_chain_before_phase8`
      - `level_baseline`: `Level 2 remains authoritative`
      - `judgment_collection`: `deferred_to_phase8`

      If no helper script is created, generate the JSON deterministically from the three existing artifacts during execution. If a helper script is created, name it `build_evidence_chain_delta.py`, include type annotations, and compile it.
    </action>
    <acceptance_criteria>
      - `verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` exists.
      - JSON contains `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`.
      - JSON contains `final_classification`.
      - JSON contains either `DB_EVIDENCE_READY` or `DB_EVIDENCE_BLOCKED`.
      - JSON contains `Level 2 remains authoritative`.
      - JSON contains `deferred_to_phase8`.
      - JSON does not contain `postgresql://`.
      - JSON does not contain `password`.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "final_classification" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`</automated>
      <automated>`rtk grep "Level 2 remains authoritative" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`</automated>
      <automated>`rtk grep "postgresql://" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` must return no matches.</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 03-02: Write Phase 7 summary and verification handoff</name>
    <read_first>
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json
      - E:/github/rag/.planning/ROADMAP.md
      - E:/github/rag/.planning/STATE.md
      - E:/github/rag/.planning/REQUIREMENTS.md
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-VALIDATION.md
    </read_first>
    <action>
      Create `.planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md` and `.planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md`.

      `07-SUMMARY.md` must contain these exact strings:
      - `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`
      - `DB_EVIDENCE_READY` or `DB_EVIDENCE_BLOCKED`
      - `Level 2 remains authoritative`
      - `Human judgment collection is deferred to Phase 8`
      - `Next route: /gsd-plan-phase 8`

      `07-VERIFICATION.md` must contain:
      - `db_readiness.json`
      - `active_version_counts.before.json`
      - `vector_loader_materialization.json`
      - `active_version_counts.after.json`
      - `evidence_chain_delta.json`
      - `No raw DATABASE_URL was written`
      - `No level_assessment.json update was performed`
      - `No human judgments were collected`

      Do not edit `.planning/STATE.md` or `.planning/ROADMAP.md` inside this task unless execute-phase routing explicitly does it after all plans pass.
    </action>
    <acceptance_criteria>
      - `.planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md` exists.
      - Summary contains `REQ-P7-DB-EVIDENCE-CHAIN-PROOF`.
      - Summary contains `Level 2 remains authoritative`.
      - Summary contains `Human judgment collection is deferred to Phase 8`.
      - Summary contains `Next route: /gsd-plan-phase 8`.
      - `.planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md` exists.
      - Verification contains `No raw DATABASE_URL was written`.
      - Verification contains `No level_assessment.json update was performed`.
      - Verification contains `No human judgments were collected`.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "Level 2 remains authoritative" .planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md`</automated>
      <automated>`rtk grep "No raw DATABASE_URL was written" .planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md`</automated>
    </verify>
  </task>
</tasks>

<verification>
- `rtk grep "final_classification" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json`
- `rtk grep "Level 2 remains authoritative" .planning/phases/07-db-backed-evidence-chain-rerun/07-SUMMARY.md`
- `rtk grep "No raw DATABASE_URL was written" .planning/phases/07-db-backed-evidence-chain-rerun/07-VERIFICATION.md`
- `rtk grep "level_assessment.json" verification/phase7-db-backed-evidence-chain-rerun/evidence_chain_delta.json` must return no matches.
</verification>

<success_criteria>
- Phase 7 has a machine-readable final evidence-chain readiness/blocker classification.
- The human-readable summary routes to Phase 8 only for matched validation and judgment collection.
- Level 2 remains the authoritative baseline until Phase 8 produces a valid matched Level assessment.
- The phase verification artifact proves no secret leakage, no premature judgments, and no Level drift.
</success_criteria>
