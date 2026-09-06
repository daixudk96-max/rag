# Phase 16-04 SUMMARY — C1 schema-gap migration 020 (provenance + owner scope + E2b audit + bridge ownership ledger)

**Status:** COMPLETE (static tests only; live migration gate **`blocked_not_executed`**)
**Wave:** 1 (macro W1) — **NON-LIVE only**
**Date:** 2026-08-06

## Scope

Implemented per `16-04-PLAN.md` using strict TDD (RED → GREEN → regression). Only the five allowlisted files were touched. No other dirty/untracked work was modified. Nothing was committed or pushed.

## Files changed (allowlist only)

1. `llamaindex_runtime/registry/migrations/020_ner_entity_mentions.sql` — **created** (schema-gap migration).
2. `llamaindex_runtime/registry/migration_catalog.py` — **modified**: appended exactly one `"020_ner_entity_mentions.sql"` immediately after `019_e2a_materialization_contract.sql` in `FULL_MIGRATION_CATALOG`. `PAGEINDEX_MIGRATIONS` is byte-for-byte unchanged and still excludes 020.
3. `tests/llamaindex_runtime/okf/test_e2b_migration_020_postgres.py` — **created** (non-DB static migration-spec/gate test).
4. `tests/llamaindex_runtime/okf/test_e2b_migration_catalog.py` — **created** (non-DB catalog placement test).
5. `.planning/phases/16-raw-corpus-entity-layer/16-04-SUMMARY.md` — **created** (this file).

Note: `llamaindex_runtime/registry/migration_catalog.py` is an already-untracked Phase 16 in-progress file in this worktree (never committed), so `git diff` cannot display the change; it was verified by reading the file (020 appended once after 019; PAGEINDEX identical).

## TDD: RED — genuine failure before implementation

Command (all DB/auth vars cleared in-process; see exact command below):

```
rtk env -u DATABASE_URL -u FORMAL_RUNTIME_DATABASE_URL -u OKF_MIGRATION_TEST_DATABASE_DISPOSABLE -u OKF_REBUILD_EXPECTED_DATABASE -u OKF_FAILURE_AUDIT_ACCEPTANCE -u OKF_REBUILD_DOCKER_ACCEPTANCE -u OKF_E2A_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_DISPOSABLE_TEST_AUTHORIZED -u OKF_E2B_MIGRATION_TEST_AUTHORIZED -u OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED -u OKF_E2B_RANER_SMOKE_AUTHORIZED -u OKF_E2B_C2_ENTRY_AUTHORIZED pytest tests/llamaindex_runtime/okf/test_e2b_migration_020_postgres.py tests/llamaindex_runtime/okf/test_e2b_migration_catalog.py -q
```

Result (RED): **14 failed, 1 passed in 5.15s**

- 11 tests in `test_e2b_migration_020_postgres.py` failed with `FileNotFoundError: ...\020_ner_entity_mentions.sql` (genuine missing migration behavior).
- 3 tests in `test_e2b_migration_catalog.py` failed (`AssertionError`: 020 absent from `FULL_MIGRATION_CATALOG` / not the final entry / not in `KEY_MIGRATIONS`).
- 1 passed: `test_pageindex_curated_workflow_excludes_020` (PAGEINDEX already excludes 020).

The RED failure was recorded before any production SQL/catalog edit. No production file existed at that point.

## TDD: GREEN — minimal correct implementation

After creating `020_ner_entity_mentions.sql` and appending the catalog entry, two refinement rounds corrected static-test/SQL alignment:

1. First GREEN run: **9 passed, 6 failed** — failures were (a) multi-line `CHECK ( ... )` bodies producing `CHECK ( expr )` after whitespace normalization while tests asserted `CHECK (expr)`, and (b) comments containing prohibited reference tokens (`node_entity_links`, `okf_rebuild_failure_audit`).
2. Fix: inlined all CHECK constraint bodies (valid SQL, consistent with 018 style) and made the test's `_normalize` strip `--` / `/* */` comments so assertions check **executable SQL only** (this also correctly restricts the forbidden-reference checks to actual DDL/DML, not prose comments).
3. Final GREEN run: **15 passed in 1.95s**.

## Regression (non-live, no DB)

| Selector | Result |
|---|---|
| `test_e2a_migration_catalog.py` + `test_e2a_migration_019_postgres.py` | **9 passed in 2.08s** |
| `test_okf_migrations.py` (module; DB integration tests skip without `DATABASE_URL`) | **10 passed, 10 skipped in 1.43s** |
| Combined focused + e2a regressions | **24 passed in 2.14s** |

All commands ran with the 12 DB/auth variables unset in-process. No Docker, PostgreSQL, network, package install, model, ModelScope, live gate, C2, commit, or push occurred. No `DATABASE_URL` or credential was read, printed, or persisted.

## What migration 020 does (schema decisions)

1. **`entity_mentions` additive nullable provenance columns** — all 20 via `ADD COLUMN IF NOT EXISTS`, typed (NOT compact JSONB) per the recorded storage decision: `input_id UUID`, `input_kind TEXT`, `input_revision TEXT`, `extractor_id TEXT`, `extractor_version TEXT`, `model_id TEXT`, `model_revision TEXT`, `artifact_digest CHAR(64)`, `schema_version TEXT`, `normalization_version TEXT`, `segmentation_version TEXT`, `label_map_digest CHAR(64)`, `runtime_compatibility_id TEXT`, `document_char_start INTEGER`, `document_char_end INTEGER`, `segment_id UUID`, `raw_label TEXT`, `entity_type TEXT`, `confidence_kind TEXT`, `e2b_owner_scope TEXT`. No backfill: NULL `e2b_owner_scope` means legacy/manual/unowned and is structurally preserved.
2. **Guarded idempotent named constraints** — because PostgreSQL has no `ADD CONSTRAINT IF NOT EXISTS`, all 6 `chk_okf_e2b_mentions_*` constraints are added inside a `DO $$ ... pg_constraint ... ALTER TABLE ... ADD CONSTRAINT ... $$` guard: input-kind allowed set, confidence-kind allowed set, artifact_digest / label_map_digest `^[0-9a-f]{64}$`, document coordinates both-NULL-or-both with `start >= 0 AND end > start`, and owner scope.
3. **Stable owner scope** — `chk_okf_e2b_mentions_owner_scope` is `e2b_owner_scope IS NULL OR e2b_owner_scope ~ '^okf:e2b:{8-4-4-4-12 lowercase hex}:{8-4-4-4-12 lowercase hex}$'` (exact canonical UUID groups, never the weak `[0-9a-fA-F-]{32,36}` class). The scope identity depends only on the two UUID slots (document_id + version_id), never on extractor/merger/model versions, so re-runs converge on the same owner scope.
4. **`okf_e2b_failure_audit` (append-only)** — distinct E2b objects throughout: `pk_okf_e2b_failure_audit`, `uq_okf_e2b_failure_audit_run`, 6 `chk_okf_e2b_failure_audit_*` (rollback confirmed, scope_count >= 1, scope_manifest object, sha256 `^[0-9a-f]{64}$`, failing doc/version both-NULL-or-both, diagnostic object), `prevent_okf_e2b_failure_audit_mutation()`, `trg_okf_e2b_failure_audit_append_only` (BEFORE UPDATE OR DELETE, FOR EACH ROW), `trg_okf_e2b_failure_audit_no_truncate` (BEFORE TRUNCATE, FOR EACH STATEMENT), `idx_okf_e2b_failure_audit_occurred_at` / `idx_okf_e2b_failure_audit_scope`. Never touches `okf_rebuild_failure_audit` or `prevent_okf_rebuild_failure_audit_mutation`.
5. **`okf_e2b_node_link_ownership` (typed bridge ownership ledger)** — `node_entity_link_owner_id` PK (`pk_okf_e2b_node_link_ownership`), FKs to `tree_nodes`/`entities`/`document_versions` ON DELETE CASCADE (`fk_okf_e2b_node_link_ownership_*`), `uq_okf_e2b_node_link_ownership UNIQUE (node_id, entity_id, version_id)`, and an **exact** key check `node_entity_link_key = node_id::text || ':' || entity_id::text` (not a broad regex). Indexes `idx_okf_e2b_node_link_ownership_node (node_id, entity_id)` and `idx_okf_e2b_node_link_ownership_version (version_id)`. It is a typed ownership/provenance record for persisted E2b-created bridges only — never a raw candidate audit.
6. **Node/version containment trigger** — independent FKs do NOT prove node/version consistency, so `validate_okf_e2b_node_link_ownership_version()` (distinct E2b name; count-based `SELECT count(*) FROM tree_nodes WHERE node_id = NEW.node_id AND version_id = NEW.version_id`) runs as `trg_okf_e2b_node_link_ownership_version` (BEFORE INSERT OR UPDATE, FOR EACH ROW) and rejects rows unless `tree_nodes` contains `NEW.node_id` with `NEW.version_id`. Trigger creation is idempotent via `DROP TRIGGER IF EXISTS` before `CREATE TRIGGER`.
7. **Boundary preservation** — `node_entity_links` PK stays `(node_id, entity_id)` (no ALTER/rekey; the migration never even references the table in executable SQL); no `chunk_entity_links` DDL; no `entity_merge_log` write target; no destructive row DML (`DELETE FROM`, `TRUNCATE TABLE`, `UPDATE ... SET`) and no ownership backfill/claim of legacy rows. The `BEFORE UPDATE OR DELETE` / `BEFORE TRUNCATE` trigger grammar is the expected append-only grammar, not destructive migration DML. No 019-managed table/function/trigger/constraint is modified.

## Static test coverage (substantive, not implementation-shaped)

`test_e2b_migration_020_postgres.py` pins, by reading and parsing the SQL:
- the exact 20-column `ADD COLUMN IF NOT EXISTS` set with exact types, and that no unconditional `ALTER TABLE ... ADD COLUMN` exists;
- the exact owner-scope regex (strict lowercase 8-4-4-4-12 groups, anchored, NULL-accepting, no extractor/model/merger/runtime/schema tokens embedded);
- the 6 nullable named `chk_okf_e2b_mentions_*` value/format/coordinate checks;
- the failure-audit table shape, named `pk/uq/chk_okf_e2b_*` constraints, append-only function and both trigger grammar forms, and the two `idx_okf_e2b_failure_audit_*` indexes;
- the ledger table shape, all named `pk/fk/uq/chk_okf_e2b_*` constraints, exact key equality (and rejection of the broad regex), and both `idx_okf_e2b_node_link_ownership_*` indexes;
- the node/version containment function + trigger (references `tree_nodes`, `NEW.node_id`, `NEW.version_id`);
- constraint/index/trigger/function name isolation (`chk_okf_e2b_` / `pk_okf_e2b_` / `uq_okf_e2b_` / `fk_okf_e2b_` / `idx_okf_e2b_` / `trg_okf_e2b_`) and that every constraint is named (no unnamed inline PK/UQ/FK/CHECK);
- no destructive DML / no legacy claim / no backfill (checked against executable SQL, comments stripped);
- no prohibited references (`node_entity_links`, `chunk_entity_links`, `entity_merge_log`, `okf_rebuild_failure_audit`, `prevent_okf_rebuild_failure_audit_mutation`, `trg_okf_rebuild_failure_audit`, `evidence_links`, `okf_manual_fact_ownership`, `okf_manual_evidence_targets`, `okf_sync_state`, `candidate`, `duplicate`, `overlap`);
- full idempotence guard inventory (every CREATE TABLE/INDEX uses `IF NOT EXISTS`, every `ALTER TABLE ... ADD COLUMN` uses `IF NOT EXISTS`, exactly 6 `IF NOT EXISTS (` constraint guards) and that `entity_mentions` PK is never rekeyed.

`test_e2b_migration_catalog.py` pins `FULL_MIGRATION_CATALOG` ends with exactly one `020_ner_entity_mentions.sql` immediately after 019, `KEY_MIGRATIONS is FULL_MIGRATION_CATALOG` and includes 020 as the final entry, and PAGEINDEX still excludes it.

## Verification minimum satisfied

- Focused new tests: **15 passed**.
- Existing `test_e2a_migration_catalog.py`: **passed**.
- Relevant non-live migration 019 static selector: `test_e2a_migration_019_postgres.py` **passed**; `test_okf_migrations.py` static subset **passed** (DB/integration tests skipped, no DB).
- Scoped whitespace/diff check: no trailing whitespace, no tabs in any allowlisted file; `migration_catalog.py` diff verified by reading (file is untracked in this worktree); PAGEINDEX byte-for-byte unchanged.

## Live gate — `blocked_not_executed`

Actual application of migration 020 to a disposable PostgreSQL is a separately authorized migration gate and was **NOT executed**. No Docker, PostgreSQL connection, network access, package installation, model/ModelScope use, C2 entry, commit, or push occurred. `DATABASE_URL` and all related variables were unset in every command process; no credential was read, printed, or persisted.

## Unresolved issues / notes

- The "no other owner remains, else fail closed" stale-bridge deletion rule is repository-layer logic (`llamaindex_runtime/entity/materialization_repository.py`, a later plan), not migration 020; this migration provides the schema-level ownership proof (ledger + UNIQUE + containment trigger) that the repository requires.
- SQL validity against a real PostgreSQL is asserted only statically here; real apply (including trigger/function semantics) is deferred to the separate migration gate.
- This is 16-04 only. Phase 16 as a whole is not claimed complete.
