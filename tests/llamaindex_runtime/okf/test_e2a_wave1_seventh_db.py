"""Static and isolated catalog-contract regressions for Wave 1 seventh remediation.

These tests deliberately inspect migration/catalog contract text and pure acceptance
helpers only. They do not claim that PostgreSQL has parsed or executed the migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf import e2a_disposable_catalog as catalog

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def test_static_migration_locks_then_reresolves_before_classification_or_mutation() -> (
    None
):
    """Static guard only: this does not prove PostgreSQL lock semantics."""
    sql = _sql()
    preflight, ddl = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )

    lock_position = preflight.index("LOCK TABLE")
    classification_position = preflight.index(
        "-- Read-only base-table shape classification"
    )
    reresolve_position = preflight.index(
        "SELECT namespace_row.oid INTO final_schema_oid"
    )
    assert lock_position < reresolve_position < classification_position
    assert "ACCESS EXCLUSIVE MODE" in preflight
    assert "e2a_preflight_relation_changed" in preflight
    assert "e2a_preflight_missing_required_table" in preflight
    assert "ALTER TABLE" not in preflight
    assert "CREATE TABLE" not in preflight
    assert "CREATE INDEX" not in preflight
    assert "ALTER TABLE" in ddl


def test_static_migration_has_fresh_data_probes_before_any_ddl() -> None:
    """Static guard only: live query behavior requires separately authorized proof."""
    sql = _sql()
    preflight, _ = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )

    for stable_failure in (
        "e2a_preflight_exactly_one_target",
        "e2a_preflight_cross_version_span",
        "e2a_preflight_cross_version_evidence",
        "e2a_preflight_existing_manual_okf",
    ):
        assert stable_failure in preflight
    assert preflight.count("num_nonnulls(link.entity_id, link.relation_id) <> 1") == 1
    assert "span.version_id IS DISTINCT FROM link.version_id" in preflight
    assert "evidence.version_id IS DISTINCT FROM link.version_id" in preflight


def test_static_migration_final_row_drift_uses_boolean_exists_not_found_flag() -> None:
    sql = _sql()

    assert "final_row_drift boolean := false" in sql
    assert "pg_catalog.boolean" not in sql
    assert "SELECT EXISTS (" in sql
    assert ") INTO final_row_drift;" in sql
    assert "IF final_row_drift THEN" in sql
    assert "IF FOUND THEN" not in sql


def test_static_migration_uses_exact_check_bodies_and_rejects_true_drift() -> None:
    sql = _sql()

    assert "pg_catalog.pg_get_expr(" in sql
    assert "constraint_row.conbin" in sql
    assert "constraint_row.conrelid" in sql
    assert "e2a_normalize_expression" in sql
    assert "e2a_preflight_audit_check_drift" in sql
    assert "chk_evidence_links_exactly_one_target" in sql
    assert "chk_evidence_links_manual_projection" in sql
    assert "chk_evidence_links_manual_scope" in sql
    assert "CHECK (TRUE)" not in sql


def test_static_migration_preserves_extension_objects_but_identifies_only_five_legacy_shapes() -> (
    None
):
    sql = _sql()

    assert "legacy_cascade_oid" in sql
    assert "constraint_row.oid = legacy_cascade_oid" in sql
    assert "e2a_preflight_legacy_fk_changed" in sql
    assert (
        "FROM pg_catalog.pg_constraint AS constraint_row\n         WHERE constraint_row.conrelid = evidence_links_oid\n           AND constraint_row.contype = 'f') = 5"
        not in sql
    )
    for identity in (
        "(evidence_links_oid, document_versions_oid, ARRAY['version_id'], ARRAY['version_id'])",
        "(evidence_links_oid, canonical_spans_oid, ARRAY['span_id'], ARRAY['span_id'])",
        "(evidence_links_oid, evidence_oid, ARRAY['evidence_id'], ARRAY['evidence_id'])",
        "(evidence_links_oid, entities_oid, ARRAY['entity_id'], ARRAY['entity_id'])",
        "(evidence_links_oid, relations_oid, ARRAY['relation_id'], ARRAY['relation_id'])",
    ):
        assert identity in sql
    for metadata in (
        "constraint_row.convalidated",
        "constraint_row.confmatchtype",
        "constraint_row.confupdtype",
        "constraint_row.condeferrable",
        "constraint_row.condeferred",
    ):
        assert metadata in sql


def test_static_migration_structurally_validates_reused_indexes_and_audit_triggers() -> (
    None
):
    sql = _sql()

    for retained_index in (
        "idx_evidence_links_version",
        "idx_evidence_links_entity",
        "idx_evidence_links_relation",
        "idx_evidence_links_span",
        "idx_evidence_links_evidence",
        "idx_okf_rebuild_failure_audit_occurred_at",
        "idx_okf_rebuild_failure_audit_scope",
    ):
        assert retained_index in sql
        assert f"CREATE INDEX {retained_index}" not in sql
        assert f"CREATE UNIQUE INDEX {retained_index}" not in sql
    for index_metadata in (
        "index_method.amname",
        "index_row.indisready",
        "index_row.indislive",
        "index_row.indnkeyatts",
        "index_row.indnatts",
        "index_row.indclass",
        "index_row.indcollation",
        "index_row.indoption",
        "index_row.indexprs",
        "index_row.indpred",
    ):
        assert index_metadata in sql
    for trigger_contract in (
        "trg_okf_rebuild_failure_audit_append_only",
        "trg_okf_rebuild_failure_audit_no_truncate",
        "trigger_row.tgfoid",
        "trigger_row.tgtype",
        "trigger_row.tgenabled",
        "trigger_row.tgisinternal",
        "trigger_row.tgargs",
        "trigger_row.tgqual",
        "trigger_row.tgattr",
    ):
        assert trigger_contract in sql


@pytest.mark.parametrize(
    ("actual", "expected"),
    (
        (r"(((E'a\'()'::text)))", r"E'a\'()'::text"),
        ("(($tag$ (literal) $tag$::text))", "$tag$ (literal) $tag$::text"),
        ("((U&'name\\0061()'::text))", "U&'name\\0061()'::text"),
        ('(("Case Sensitive"::text))', '"Case Sensitive"::text'),
        (
            "((value /* outer /* nested */ comment */ ::text))",
            "value::text",
        ),
        ("((value -- comment containing ()\n::text))", "value::text"),
        (
            "((CASE WHEN value::text = 'x'::text THEN 1 ELSE 0 END))",
            "CASE WHEN value::text = 'x'::text THEN 1 ELSE 0 END",
        ),
    ),
)
def test_expression_comparator_accepts_only_lexically_safe_insignificant_variation(
    actual: str, expected: str
) -> None:
    assert acceptance._expressions_match(actual, expected)


@pytest.mark.parametrize(
    "actual",
    (
        "E'unterminated\\'",
        "U&'unterminated",
        "$tag$ unterminated",
        '"unterminated',
        "/* unterminated",
        "(value))",
    ),
)
def test_expression_comparator_fails_closed_on_malformed_lexemes(actual: str) -> None:
    assert not acceptance._expressions_match(actual, "value")


def test_expression_comparator_preserves_literal_and_quoted_identifier_content() -> (
    None
):
    assert not acceptance._expressions_match("'Manual_OKF'::text", "'manual_okf'::text")
    assert not acceptance._expressions_match('"MixedCase"', '"mixedcase"')
    assert not acceptance._expressions_match(
        "CASE WHEN x THEN 1 ELSE 0 END", "case when x then 1 else 0 end"
    )


def test_acceptance_uses_structural_catalog_rows_not_index_definition_text() -> None:
    source = Path(catalog.__file__).read_text(encoding="utf-8")

    assert "pg_get_indexdef" not in source
    assert (
        "pg_get_expr(constraint_row.conbin, constraint_row.conrelid, false)" in source
    )
    for required in (
        "index_method.amname",
        "index_row.indisready",
        "index_row.indislive",
        "index_row.indnkeyatts",
        "index_row.indnatts",
        "index_row.indclass",
        "index_row.indcollation",
        "index_row.indoption",
        "_assert_trigger_rows",
        "_assert_backing_index_rows",
    ):
        assert required in source
