---
phase: 07-db-backed-evidence-chain-rerun
plan: 02
type: execute
wave: 2
depends_on:
  - 07-PLAN-01
files_modified:
  - verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py
  - verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json
  - verification/phase7-db-backed-evidence-chain-rerun/vector_loader_materialization.json
  - verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json
requirements:
  - REQ-P7-DB-EVIDENCE-CHAIN-PROOF
autonomous: true
---

<objective>
Run active-version-scoped evidence-chain diagnostics before and after vector materialization, while respecting the DB readiness gate from Plan 01. If DB access is unavailable, write blocked before/materialization/after artifacts rather than silently skipping Phase 7 evidence.
</objective>

<must_haves>
  <truths>
    <truth>D-07-02: All diagnostic counts are scoped to one `active_version_id`.</truth>
    <truth>D-07-03: Phase 7 captures before counts, materialization result, and after counts.</truth>
    <truth>D-07-04: Persistent zeros must be classified through the Phase 5 evidence-chain classification contract.</truth>
    <truth>D-07-05: This plan does not generate retrieval results or collect human judgments.</truth>
    <truth>D-07-06: This plan does not update `level_assessment.json`; Level 2 remains authoritative.</truth>
  </truths>
  <key_links>
    <link from="verification/phase5-evidence-chain-verification/verify_active_version_counts.py" to="verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py" via="before/after active-version counts" pattern="compute_active_version_counts|classification" />
    <link from="verification/phase5-evidence-chain-verification/invoke_vector_loader.py" to="verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py" via="materialization checkpoint" pattern="materialize_chunks_for_version|VectorLoader" />
  </key_links>
</must_haves>

<threat_model>
  <threat id="T-07-03" severity="high" stride="Tampering">
    Materialization could run against the wrong active version if the wrapper ignores the readiness artifact or resolves a different version between before and after checks.
    Mitigation: use one explicit `active_version_id` for before counts, materialization, and after counts; write that same ID to all three artifacts.
  </threat>
  <threat id="T-07-04" severity="medium" stride="Repudiation">
    A failed DB run could leave no artifact, making Phase 8 routing ambiguous.
    Mitigation: write blocked JSON artifacts for before counts, materialization, and after counts whenever readiness is false or DB execution fails.
  </threat>
</threat_model>

<tasks>
  <task type="auto">
    <name>Task 02-01: Create Phase 7 DB-backed rerun wrapper</name>
    <read_first>
      - E:/github/rag/CLAUDE.md
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json
      - E:/github/rag/verification/phase5-evidence-chain-verification/verify_active_version_counts.py
      - E:/github/rag/verification/phase5-evidence-chain-verification/invoke_vector_loader.py
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-PATTERNS.md
    </read_first>
    <action>
      Create `verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py` with type annotations on all functions.

      The wrapper must expose:
      - `PHASE7_DIR = Path(__file__).parent`
      - `READINESS_FILE = PHASE7_DIR / "db_readiness.json"`
      - `BEFORE_FILE = PHASE7_DIR / "active_version_counts.before.json"`
      - `MATERIALIZATION_FILE = PHASE7_DIR / "vector_loader_materialization.json"`
      - `AFTER_FILE = PHASE7_DIR / "active_version_counts.after.json"`
      - `load_readiness(path: Path = READINESS_FILE) -> dict[str, object]`
      - `write_blocked_artifact(path: Path, readiness: dict[str, object], stage: str) -> dict[str, object]`
      - `run_rerun(version_id: uuid.UUID | None = None) -> dict[str, object]`
      - `main() -> int`

      Behavior when readiness is blocked:
      - If `db_readiness.json` is missing or has `ready_for_materialization: false`, write all three files with `status: "blocked"`, `stage`, `active_version_id` from readiness when present, and `blocking_reasons` copied from readiness.
      - Return exit code 1 after writing the blocked artifacts.

      Behavior when readiness is ready:
      - Use the same `active_version_id` from readiness unless `--version-id` is explicitly supplied and matches the intended rerun target.
      - Connect with `psycopg.connect(os.getenv("DATABASE_URL", ""), connect_timeout=10)` without printing the URL.
      - Import the Phase 5 count module and call `compute_active_version_counts(conn, version_id)` before materialization; write the result to `active_version_counts.before.json`.
      - Import or call the Phase 5 materialization path so `VectorLoader(embed_dim=16).load(conn, version_id)` runs exactly once for the same version.
      - Write `vector_loader_materialization.json` with `status: "completed"`, `active_version_id`, `loader_result`, and `changed`.
      - Call `compute_active_version_counts(conn, version_id)` again and write `active_version_counts.after.json`.
      - Return 0 only if after counts were written; do not require classification to be `evidence_chain_ready` in this plan.
    </action>
    <acceptance_criteria>
      - `verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py` exists.
      - File contains `active_version_counts.before.json`.
      - File contains `vector_loader_materialization.json`.
      - File contains `active_version_counts.after.json`.
      - File contains `ready_for_materialization`.
      - File contains `compute_active_version_counts`.
      - File contains `VectorLoader` or `materialize_chunks_for_version`.
      - File does not contain `level_assessment.json`.
      - File does not contain `judgment_template.csv`.
      - `$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py` exits 0.
    </acceptance_criteria>
    <verify>
      <automated>`$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py`</automated>
      <automated>`rtk grep "active_version_counts.before.json" verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py`</automated>
      <automated>`rtk grep "level_assessment.json" verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py` must return no matches.</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 02-02: Execute before/materialization/after rerun or blocked fallback</name>
    <read_first>
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-VALIDATION.md
    </read_first>
    <action>
      Run:
      `$env:PYTHONPATH='E:/github/rag'; rtk proxy python verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py`

      If `DATABASE_URL` is missing or readiness is false, the command may exit 1. That is acceptable only when these files still exist and contain `status: "blocked"`:
      - `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json`
      - `verification/phase7-db-backed-evidence-chain-rerun/vector_loader_materialization.json`
      - `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json`

      If DB is available, all three files must share the same non-null `active_version_id`, and the after file must contain a `classification` field from the Phase 5 classifier.
    </action>
    <acceptance_criteria>
      - `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json` exists.
      - `verification/phase7-db-backed-evidence-chain-rerun/vector_loader_materialization.json` exists.
      - `verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json` exists.
      - Before JSON contains either `classification` or `status`.
      - Materialization JSON contains `active_version_id` or `blocking_reasons`.
      - After JSON contains either `classification` or `status`.
      - None of the three artifacts contain `postgresql://`.
      - None of the three artifacts contain `password`.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "classification\|status" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json`</automated>
      <automated>`rtk grep "classification\|status" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json`</automated>
      <automated>`rtk grep "postgresql://" verification/phase7-db-backed-evidence-chain-rerun/*.json` must return no matches.</automated>
    </verify>
  </task>
</tasks>

<verification>
- `$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/run_db_backed_rerun.py`
- `rtk grep "classification\|status" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.before.json`
- `rtk grep "classification\|status" verification/phase7-db-backed-evidence-chain-rerun/active_version_counts.after.json`
- `rtk grep "postgresql://" verification/phase7-db-backed-evidence-chain-rerun/*.json` must return no matches.
</verification>

<success_criteria>
- Phase 7 has before, materialization, and after artifacts even when DB is blocked.
- If DB is available, all three artifacts are scoped to one active version.
- If evidence-chain counts remain zero, the after artifact preserves the classifier output for Plan 03.
- No human judgment or Level assessment artifacts are touched.
</success_criteria>
