---
phase: 07-db-backed-evidence-chain-rerun
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py
  - verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json
requirements:
  - REQ-P7-DB-EVIDENCE-CHAIN-PROOF
autonomous: true
---

<objective>
Create a sanitized Phase 7 DB readiness gate that proves whether the executor can safely run active-version evidence-chain diagnostics and materialization. Missing `DATABASE_URL` is an expected fail-closed blocker artifact, not a prompt to invent or print secrets.
</objective>

<must_haves>
  <truths>
    <truth>D-07-01: The raw `DATABASE_URL` is never printed, logged, or written to any artifact.</truth>
    <truth>D-07-02: Readiness is scoped to the intended `active_version_id`; global table presence alone is not enough.</truth>
    <truth>D-07-04: A blocked DB state is acceptable only when `db_readiness.json` records exact blocking reasons.</truth>
    <truth>REQ-P7-DB-EVIDENCE-CHAIN-PROOF starts with a machine-readable DB readiness artifact.</truth>
  </truths>
  <key_links>
    <link from="verification/phase5-evidence-chain-verification/verify_active_version_counts.py" to="verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py" via="reuse active-version UUID parsing and latest active-version resolution" pattern="parse_version_id|resolve_latest_active_version_id" />
    <link from=".planning/phases/07-db-backed-evidence-chain-rerun/07-CONTEXT.md" to="verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json" via="D-07-01 secret-safe DB gate" pattern="database_url_configured|connection_status|blocking_reasons" />
  </key_links>
</must_haves>

<threat_model>
  <threat id="T-07-01" severity="high" stride="Information Disclosure">
    A readiness script could leak the raw DB connection string through stdout, stderr, JSON artifacts, or exception messages.
    Mitigation: write only `database_url_configured: true/false`, sanitized `connection_status`, `active_version_id`, table names, and blocking reason codes. Never serialize `os.getenv("DATABASE_URL")`.
  </threat>
  <threat id="T-07-02" severity="medium" stride="Tampering">
    An invalid `--version-id` could reach SQL if validation is skipped.
    Mitigation: parse explicit version IDs with `uuid.UUID` before connecting or querying; return exit code 2 on invalid UUID.
  </threat>
</threat_model>

<tasks>
  <task type="auto">
    <name>Task 01-01: Create sanitized DB readiness utility</name>
    <read_first>
      - E:/github/rag/CLAUDE.md
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-CONTEXT.md
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-RESEARCH.md
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-PATTERNS.md
      - E:/github/rag/verification/phase5-evidence-chain-verification/verify_active_version_counts.py
      - E:/github/rag/llamaindex_runtime/registry/postgres_adapter.py
    </read_first>
    <action>
      Create `verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py` with type annotations on all functions.

      The utility must expose:
      - `PHASE7_DIR = Path(__file__).parent`
      - `OUTPUT_FILE = PHASE7_DIR / "db_readiness.json"`
      - `TABLES_CHECKED = ["document_versions", "canonical_spans", "vector_chunks", "vector_chunk_spans", "tree_node_spans"]`
      - `parse_version_id(value: str) -> uuid.UUID`
      - `build_db_readiness_report(version_id: uuid.UUID | None = None) -> dict[str, object]`
      - `main() -> int`

      Concrete report shape:
      - `database_url_configured`: boolean
      - `connection_status`: one of `not_configured`, `connected`, `connection_failed`, `invalid_version_id`, `no_active_version`
      - `active_version_id`: string or null
      - `tables_checked`: the exact `TABLES_CHECKED` list
      - `ready_for_materialization`: boolean
      - `blocking_reasons`: list of reason codes from `database_url_not_configured`, `connection_failed`, `invalid_version_id`, `active_version_missing`

      Behavior:
      - If `DATABASE_URL` is missing, write `db_readiness.json` with `database_url_configured: false`, `connection_status: "not_configured"`, `ready_for_materialization: false`, and `blocking_reasons: ["database_url_not_configured"]`; return exit code 1.
      - If `--version-id` is supplied, validate it with `uuid.UUID` before any DB query.
      - If DB connects, resolve explicit `version_id` or latest active version using the same ordering as Phase 5: `activated_at DESC NULLS LAST`, `registered_at DESC NULLS LAST`, `version_no DESC`.
      - If no active version exists, write `connection_status: "no_active_version"`, `ready_for_materialization: false`, and `blocking_reasons: ["active_version_missing"]`; return exit code 1.
      - If DB connects and an active version exists, write `connection_status: "connected"`, `ready_for_materialization: true`, `blocking_reasons: []`; return exit code 0.
      - Catch `psycopg.Error` and write `connection_status: "connection_failed"` plus `blocking_reasons: ["connection_failed"]`; do not include the exception string if it contains connection details.
    </action>
    <acceptance_criteria>
      - `verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py` exists.
      - File contains `TABLES_CHECKED = [`.
      - File contains `database_url_configured`.
      - File contains `ready_for_materialization`.
      - File contains `database_url_not_configured`.
      - File contains `uuid.UUID(value)`.
      - File does not contain `"DATABASE_URL":`.
      - File does not write `os.getenv("DATABASE_URL")` into a JSON object.
      - `$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py` exits 0.
    </acceptance_criteria>
    <verify>
      <automated>`$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py`</automated>
      <automated>`rtk grep "database_url_configured" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py`</automated>
      <automated>`rtk grep "DATABASE_URL\":" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py` must return no matches.</automated>
    </verify>
  </task>

  <task type="auto">
    <name>Task 01-02: Run readiness gate and write fail-closed artifact</name>
    <read_first>
      - E:/github/rag/verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py
      - E:/github/rag/.planning/phases/07-db-backed-evidence-chain-rerun/07-VALIDATION.md
    </read_first>
    <action>
      Run the readiness utility once. Treat exit code 1 as acceptable only if `db_readiness.json` exists and records a fail-closed blocker.

      Command:
      `$env:PYTHONPATH='E:/github/rag'; rtk proxy python verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py`

      If the command exits non-zero because `DATABASE_URL` is missing, do not request or store a secret. Confirm the artifact contains:
      - `"database_url_configured": false`
      - `"connection_status": "not_configured"`
      - `"ready_for_materialization": false`
      - `"database_url_not_configured"`
    </action>
    <acceptance_criteria>
      - `verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json` exists.
      - JSON contains `database_url_configured`.
      - JSON contains `connection_status`.
      - JSON contains `ready_for_materialization`.
      - JSON contains `blocking_reasons`.
      - JSON does not contain `postgresql://`.
      - JSON does not contain `password`.
    </acceptance_criteria>
    <verify>
      <automated>`rtk grep "database_url_configured" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json`</automated>
      <automated>`rtk grep "postgresql://" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json` must return no matches.</automated>
    </verify>
  </task>
</tasks>

<verification>
- `$env:PYTHONPATH='E:/github/rag'; rtk proxy python -m compileall -q verification/phase7-db-backed-evidence-chain-rerun/db_readiness.py`
- `rtk grep "database_url_configured" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json`
- `rtk grep "postgresql://" verification/phase7-db-backed-evidence-chain-rerun/db_readiness.json` must return no matches.
</verification>

<success_criteria>
- Phase 7 has a secret-safe DB readiness artifact.
- Missing DB access is represented as `DB_EVIDENCE_BLOCKED` input, not as an unhandled failure.
- A connected DB with active version can be passed to Plan 02 without relying on global counts.
</success_criteria>
