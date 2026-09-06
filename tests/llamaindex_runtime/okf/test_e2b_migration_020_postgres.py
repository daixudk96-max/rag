"""Non-DB static migration-spec/gate tests for Phase 16 C1 migration 020.

These tests read ``020_ner_entity_mentions.sql`` and assert the schema-gap
boundaries without touching PostgreSQL:
- explicit typed provenance columns via ``ADD COLUMN IF NOT EXISTS``
- a nullable, stable ``e2b_owner_scope`` with a strict ``okf:e2b:{doc}:{version}``
  regex (exact 8-4-4-4-12 lowercase hex groups, no extractor/model/merger tokens)
- ``okf_e2b_failure_audit`` (append-only, isolated E2b names)
- ``okf_e2b_node_link_ownership`` typed ledger with exact node/entity key equality
  and a node/version containment trigger
- no node_entity_links rekey, no chunk_entity_links DDL, no destructive DML,
  no legacy claim/backfill, no 019/018 reuse
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "020_ner_entity_mentions.sql"
)

EXPECTED_ENTITY_MENTIONS_COLUMNS = frozenset(
    {
        "input_id",
        "input_kind",
        "input_revision",
        "extractor_id",
        "extractor_version",
        "model_id",
        "model_revision",
        "artifact_digest",
        "schema_version",
        "normalization_version",
        "segmentation_version",
        "label_map_digest",
        "runtime_compatibility_id",
        "document_char_start",
        "document_char_end",
        "segment_id",
        "raw_label",
        "entity_type",
        "confidence_kind",
        "e2b_owner_scope",
    }
)

EXPECTED_OWNER_SCOPE_PATTERN = (
    "^okf:e2b:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:"
    "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_ADD_COLUMN_RE = re.compile(
    r"ADD COLUMN IF NOT EXISTS\s+([a-z_][a-z0-9_]*)\s+"
    r"([A-Z]+(?:\s*\(\s*\d+\s*\))?)",
    re.IGNORECASE,
)


def _migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Remove -- and /* */ comments so assertions check executable SQL only.

    Safe for this migration: no string literal contains a `--` or `/*` sequence.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", _strip_sql_comments(sql).strip())


def _constraint_names(normalized: str) -> set[str]:
    return set(
        re.findall(r"\bCONSTRAINT\s+([a-z][a-z0-9_]*)", normalized, re.IGNORECASE)
    )


def test_entity_mentions_gains_exact_provenance_columns_idempotently() -> None:
    sql = _migration_sql()
    added: dict[str, str] = {
        m.group(1): m.group(2) for m in _ADD_COLUMN_RE.finditer(sql)
    }
    assert set(added) == EXPECTED_ENTITY_MENTIONS_COLUMNS
    assert added["input_id"].upper() == "UUID"
    assert added["segment_id"].upper() == "UUID"
    assert added["artifact_digest"].upper() == "CHAR(64)"
    assert added["label_map_digest"].upper() == "CHAR(64)"
    assert added["document_char_start"].upper() == "INTEGER"
    assert added["document_char_end"].upper() == "INTEGER"
    assert added["e2b_owner_scope"].upper() == "TEXT"
    assert "ADD COLUMN IF NOT EXISTS e2b_owner_scope TEXT" in _normalize(sql)
    assert not re.search(
        r"ALTER TABLE entity_mentions\s+ADD COLUMN\s+(?!IF NOT EXISTS)",
        sql,
        re.IGNORECASE,
    )
    assert "DROP COLUMN" not in _normalize(sql)


def test_owner_scope_check_is_nullable_strict_and_version_stable() -> None:
    normalized = _normalize(_migration_sql())
    m = re.search(
        r"chk_okf_e2b_mentions_owner_scope CHECK \(e2b_owner_scope IS NULL OR "
        r"e2b_owner_scope ~ '([^']+)'\)",
        normalized,
    )
    assert m is not None, "owner-scope CHECK must accept NULL then validate format"
    assert m.group(1) == EXPECTED_OWNER_SCOPE_PATTERN
    assert "[0-9a-fA-F-]{32,36}" not in m.group(1)
    assert m.group(1).startswith("^") and m.group(1).endswith("$")
    for token in (
        "extractor",
        "model",
        "merger",
        "runtime",
        "schema",
        "normalization",
        "segmentation",
    ):
        assert token not in m.group(1)


def test_entity_mentions_value_checks_are_nullable_and_named() -> None:
    normalized = _normalize(_migration_sql())
    assert (
        "chk_okf_e2b_mentions_input_kind CHECK (input_kind IS NULL OR "
        "input_kind IN ('corpus_span', 'query_text'))" in normalized
    )
    assert (
        "chk_okf_e2b_mentions_confidence_kind CHECK (confidence_kind IS NULL OR "
        "confidence_kind IN ('frontmatter_declared', 'dictionary_exact', "
        "'rule_weight', 'model_probability', 'unavailable'))" in normalized
    )
    assert (
        "chk_okf_e2b_mentions_artifact_digest CHECK (artifact_digest IS NULL OR "
        "artifact_digest ~ '^[0-9a-f]{64}$')" in normalized
    )
    assert (
        "chk_okf_e2b_mentions_label_map_digest CHECK (label_map_digest IS NULL OR "
        "label_map_digest ~ '^[0-9a-f]{64}$')" in normalized
    )
    assert (
        "chk_okf_e2b_mentions_document_coordinates CHECK ((document_char_start "
        "IS NULL AND document_char_end IS NULL) OR (document_char_start IS NOT NULL "
        "AND document_char_end IS NOT NULL AND document_char_start >= 0 AND "
        "document_char_end > document_char_start))" in normalized
    )


def test_failure_audit_table_is_append_only_with_isolated_names() -> None:
    normalized = _normalize(_migration_sql())
    for required in (
        "CREATE TABLE IF NOT EXISTS okf_e2b_failure_audit (",
        "audit_id UUID NOT NULL",
        "e2b_run_id UUID NOT NULL",
        "occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "failure_phase TEXT NOT NULL",
        "failure_code TEXT NOT NULL",
        "rollback_confirmed BOOLEAN NOT NULL",
        "scope_count INTEGER NOT NULL",
        "scope_manifest JSONB NOT NULL",
        "scope_manifest_sha256 CHAR(64) NOT NULL",
        "failing_doc_id UUID",
        "failing_version_id UUID",
        "diagnostic JSONB NOT NULL",
        "CONSTRAINT pk_okf_e2b_failure_audit PRIMARY KEY (audit_id)",
        "CONSTRAINT uq_okf_e2b_failure_audit_run UNIQUE (e2b_run_id)",
        "CONSTRAINT chk_okf_e2b_failure_audit_rollback CHECK (rollback_confirmed)",
        "CONSTRAINT chk_okf_e2b_failure_audit_scope_count CHECK (scope_count >= 1)",
        "CONSTRAINT chk_okf_e2b_failure_audit_scope_manifest CHECK "
        "(jsonb_typeof(scope_manifest) = 'object')",
        "CONSTRAINT chk_okf_e2b_failure_audit_hash CHECK "
        "(scope_manifest_sha256 ~ '^[0-9a-f]{64}$')",
        "CONSTRAINT chk_okf_e2b_failure_audit_scope_pair CHECK ((failing_doc_id "
        "IS NULL AND failing_version_id IS NULL) OR (failing_doc_id IS NOT NULL "
        "AND failing_version_id IS NOT NULL))",
        "CONSTRAINT chk_okf_e2b_failure_audit_diagnostic CHECK "
        "(jsonb_typeof(diagnostic) = 'object')",
        "CREATE OR REPLACE FUNCTION prevent_okf_e2b_failure_audit_mutation()",
        "okf_e2b_failure_audit is append-only",
        "CREATE TRIGGER trg_okf_e2b_failure_audit_append_only",
        "BEFORE UPDATE OR DELETE ON okf_e2b_failure_audit",
        "CREATE TRIGGER trg_okf_e2b_failure_audit_no_truncate",
        "BEFORE TRUNCATE ON okf_e2b_failure_audit",
        "CREATE INDEX IF NOT EXISTS idx_okf_e2b_failure_audit_occurred_at "
        "ON okf_e2b_failure_audit (occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_okf_e2b_failure_audit_scope "
        "ON okf_e2b_failure_audit (failing_doc_id, failing_version_id)",
    ):
        assert required in normalized


def test_ledger_is_typed_ownership_not_candidate_audit() -> None:
    normalized = _normalize(_migration_sql())
    for required in (
        "CREATE TABLE IF NOT EXISTS okf_e2b_node_link_ownership (",
        "node_entity_link_owner_id UUID NOT NULL",
        "node_id UUID NOT NULL",
        "entity_id UUID NOT NULL",
        "version_id UUID NOT NULL",
        "node_entity_link_key TEXT NOT NULL",
        "e2b_run_id UUID NOT NULL",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "CONSTRAINT pk_okf_e2b_node_link_ownership PRIMARY KEY "
        "(node_entity_link_owner_id)",
        "CONSTRAINT fk_okf_e2b_node_link_ownership_node FOREIGN KEY (node_id) "
        "REFERENCES tree_nodes(node_id) ON DELETE CASCADE",
        "CONSTRAINT fk_okf_e2b_node_link_ownership_entity FOREIGN KEY (entity_id) "
        "REFERENCES entities(entity_id) ON DELETE CASCADE",
        "CONSTRAINT fk_okf_e2b_node_link_ownership_version FOREIGN KEY (version_id) "
        "REFERENCES document_versions(version_id) ON DELETE CASCADE",
        "CONSTRAINT uq_okf_e2b_node_link_ownership UNIQUE "
        "(node_id, entity_id, version_id)",
        "CONSTRAINT chk_okf_e2b_node_link_key CHECK (node_entity_link_key = "
        "node_id::text || ':' || entity_id::text)",
        "CREATE INDEX IF NOT EXISTS idx_okf_e2b_node_link_ownership_node "
        "ON okf_e2b_node_link_ownership (node_id, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_okf_e2b_node_link_ownership_version "
        "ON okf_e2b_node_link_ownership (version_id)",
    ):
        assert required in normalized
    assert "chk_okf_e2b_node_link_key CHECK (node_entity_link_key ~" not in normalized
    assert "~ '^[0-9a-fA-F-]+:[0-9a-fA-F-]+$'" not in normalized


def test_ledger_has_node_version_containment_trigger() -> None:
    normalized = _normalize(_migration_sql())
    assert (
        "CREATE OR REPLACE FUNCTION validate_okf_e2b_node_link_ownership_version()"
        in normalized
    )
    assert "FROM tree_nodes" in normalized
    assert "NEW.node_id" in normalized
    assert "NEW.version_id" in normalized
    assert "CREATE TRIGGER trg_okf_e2b_node_link_ownership_version" in normalized
    assert "BEFORE INSERT OR UPDATE ON okf_e2b_node_link_ownership" in normalized
    assert (
        "EXECUTE FUNCTION validate_okf_e2b_node_link_ownership_version()"
        in normalized
    )


def test_all_constraints_are_named_and_okf_e2b_isolated() -> None:
    normalized = _normalize(_migration_sql())
    constraint_names = _constraint_names(normalized)
    assert constraint_names, "migration must declare named constraints"
    for name in constraint_names:
        assert name.startswith(
            ("chk_okf_e2b_", "pk_okf_e2b_", "uq_okf_e2b_", "fk_okf_e2b_")
        ), name
    for keyword in ("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK"):
        named = len(
            re.findall(
                r"\bCONSTRAINT\s+[a-z][a-z0-9_]*\s+" + keyword + r"\b",
                normalized,
            )
        )
        total = len(re.findall(r"\b" + keyword + r"\b", normalized))
        assert named == total, f"unnamed {keyword} constraint present"


def test_all_indexes_triggers_functions_are_okf_e2b_isolated() -> None:
    normalized = _normalize(_migration_sql())
    indexes = set(
        re.findall(r"CREATE INDEX IF NOT EXISTS\s+([a-z][a-z0-9_]*)", normalized)
    )
    assert indexes == {
        "idx_okf_e2b_failure_audit_occurred_at",
        "idx_okf_e2b_failure_audit_scope",
        "idx_okf_e2b_node_link_ownership_node",
        "idx_okf_e2b_node_link_ownership_version",
    }
    for name in indexes:
        assert name.startswith("idx_okf_e2b_"), name

    triggers = set(
        re.findall(r"CREATE TRIGGER\s+([a-z][a-z0-9_]*)", normalized)
    )
    dropped_triggers = set(
        re.findall(r"DROP TRIGGER IF EXISTS\s+([a-z][a-z0-9_]*)", normalized)
    )
    assert triggers == dropped_triggers
    assert triggers == {
        "trg_okf_e2b_failure_audit_append_only",
        "trg_okf_e2b_failure_audit_no_truncate",
        "trg_okf_e2b_node_link_ownership_version",
    }
    for name in triggers:
        assert name.startswith("trg_okf_e2b_"), name

    functions = set(
        re.findall(r"CREATE OR REPLACE FUNCTION\s+([a-z][a-z0-9_]*)", normalized)
    )
    assert functions == {
        "prevent_okf_e2b_failure_audit_mutation",
        "validate_okf_e2b_node_link_ownership_version",
    }
    for name in functions:
        assert "okf_e2b" in name, name


def test_no_destructive_dml_no_legacy_claim_no_prohibited_references() -> None:
    normalized = _normalize(_migration_sql())
    assert not re.search(r"\bDELETE\s+FROM\b", normalized, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\s+TABLE\b", normalized, re.IGNORECASE)
    assert not re.search(
        r"\bUPDATE\s+(?:ONLY\s+)?[a-z_][a-z0-9_]*\s+SET\b",
        normalized,
        re.IGNORECASE,
    )
    assert "SET e2b_owner_scope" not in normalized
    assert "e2b_owner_scope =" not in normalized
    assert "BEFORE UPDATE OR DELETE ON okf_e2b_failure_audit" in normalized
    assert "BEFORE TRUNCATE ON okf_e2b_failure_audit" in normalized
    for forbidden in (
        "node_entity_links",
        "chunk_entity_links",
        "entity_merge_log",
        "okf_rebuild_failure_audit",
        "prevent_okf_rebuild_failure_audit_mutation",
        "trg_okf_rebuild_failure_audit",
        "evidence_links",
        "okf_manual_fact_ownership",
        "okf_manual_evidence_targets",
        "okf_sync_state",
        "candidate",
        "duplicate",
        "overlap",
    ):
        assert forbidden not in normalized, f"prohibited reference: {forbidden}"


def test_every_ddl_statement_is_guarded_idempotent() -> None:
    sql = _migration_sql()
    assert not re.search(r"CREATE TABLE\s+(?!IF NOT EXISTS)", sql, re.IGNORECASE)
    assert not re.search(r"CREATE INDEX\s+(?!IF NOT EXISTS)", sql, re.IGNORECASE)
    assert not re.search(
        r"ALTER TABLE entity_mentions\s+ADD COLUMN\s+(?!IF NOT EXISTS)",
        sql,
        re.IGNORECASE,
    )
    assert sql.count("IF NOT EXISTS (") == 6


def test_entity_mentions_pk_is_not_rekeyed() -> None:
    normalized = _normalize(_migration_sql())
    assert not re.search(
        r"ALTER TABLE entity_mentions[^;]*\bPRIMARY KEY\b", normalized, re.IGNORECASE
    )
    assert not re.search(
        r"ALTER TABLE entity_mentions[^;]*\bDROP\b", normalized, re.IGNORECASE
    )
    assert "PRIMARY KEY (mention_id)" not in normalized
