from __future__ import annotations

from pathlib import Path

import pytest

from llamaindex_runtime.okf import e2a_disposable_acceptance as acceptance
from llamaindex_runtime.okf.e2a_disposable_acceptance import (
    run_disposable_migration_acceptance,
)


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "llamaindex_runtime"
    / "registry"
    / "migrations"
    / "019_e2a_materialization_contract.sql"
)


def test_migration_019_declares_manual_shadows_without_e2b_or_artifact_binding() -> (
    None
):
    sql = MIGRATION.read_text(encoding="utf-8")

    for required in (
        "manual_entity_id UUID",
        "manual_relation_id UUID",
        "chk_evidence_links_manual_projection",
        "num_nonnulls(entity_id, relation_id) = 1",
        "source_kind <> 'manual_okf'",
        "manual_entity_id IS NULL",
        "manual_relation_id IS NULL",
        "manual_entity_id = entity_id",
        "manual_relation_id = relation_id",
        "FOREIGN KEY (ownership_id, manual_entity_id)",
        "FOREIGN KEY (ownership_id, manual_relation_id)",
        "FOREIGN KEY (version_id, evidence_id, manual_entity_id)",
        "FOREIGN KEY (version_id, evidence_id, manual_relation_id)",
        "pk_okf_manual_evidence_targets PRIMARY KEY (version_id, evidence_id)",
        "idx_evidence_links_version_evidence_manual_entity",
        "idx_evidence_links_version_evidence_manual_relation",
    ):
        assert required in sql
    assert "is_manual_okf" not in sql
    assert "artifact table" not in sql.lower()
    assert "uuid_generate" not in sql.lower()
    assert "uuid5" not in sql.lower()


def test_migration_019_adds_legacy_safe_sync_ownership_without_rekeying() -> None:
    normalized = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())

    assert normalized.count("do $e2a019$") == 1
    assert "materialization_owner text not null default 'legacy_pre_e2a'" in normalized
    assert "materialization_owner in ('legacy_pre_e2a', 'e2a')" in normalized
    assert "primary key (okf_file_path, materialization_owner)" not in normalized
    assert "primary key (materialization_owner, okf_file_path)" not in normalized
    assert "set materialization_owner = 'e2a'" not in normalized
    assert "set materialization_owner='e2a'" not in normalized


def test_migration_019_classifies_fresh_final_or_partial_before_dynamic_ddl() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    first_executable = next(
        line.strip()
        for line in sql.splitlines()
        if line.strip() and not line.startswith("--")
    )
    classification, fresh_ddl = sql.split(
        "-- Only the exact fresh signature reaches this DDL phase.", maxsplit=1
    )

    assert first_executable == "DO $e2a019$"
    assert sql.count("DO $e2a019$") == 1
    for required in (
        "fresh_signature :=",
        "final_signature :=",
        "fresh_signature AND final_signature",
        "NOT fresh_signature AND NOT final_signature",
        "e2a_preflight_malformed_partial",
        "e2a_preflight_final_catalog_drift",
        "e2a_preflight_final_row_drift",
        "e2a_preflight_existing_manual_okf",
        "NOT (constraint_row.confdeltype IN ('c', 'a'))",
        "pg_catalog.pg_constraint",
        "pg_catalog.pg_attribute",
        "pg_catalog.pg_index",
        "schema_name := pg_catalog.current_schema()",
        "format('%I.%I', schema_name",
    ):
        assert required in classification
    assert "ALTER TABLE" not in classification
    assert "CREATE TABLE" not in classification
    assert "CREATE INDEX" not in classification
    assert "EXECUTE pg_catalog.format" in fresh_ddl


def test_migration_019_replaces_only_cascade_legacy_fks_by_oid_and_ordered_keys() -> (
    None
):
    sql = MIGRATION.read_text(encoding="utf-8")

    for required in (
        "constraint_row.confdeltype = 'c'",
        "constraint_row.conrelid = evidence_links_oid",
        "(evidence_links_oid, document_versions_oid, ARRAY['version_id'], ARRAY['version_id'])",
        "(evidence_links_oid, canonical_spans_oid, ARRAY['span_id'], ARRAY['span_id'])",
        "(evidence_links_oid, evidence_oid, ARRAY['evidence_id'], ARRAY['evidence_id'])",
        "(evidence_links_oid, entities_oid, ARRAY['entity_id'], ARRAY['entity_id'])",
        "(evidence_links_oid, relations_oid, ARRAY['relation_id'], ARRAY['relation_id'])",
        "constraint_row.conkey = ARRAY",
        "constraint_row.confkey = ARRAY",
        "ALTER TABLE %s DROP CONSTRAINT %I",
        "ON DELETE RESTRICT",
    ):
        assert required in sql
    assert "DROP CONSTRAINT IF EXISTS evidence_links_" not in sql


def test_migration_019_semantic_probe_covers_generic_manual_entity_and_relation_cases() -> (
    None
):
    probe = acceptance._SEMANTIC_PROBE

    for required in (
        "one evidence object may cover two different targets",
        "another_generic",
        "e2a_probe_legal_manual_relation",
        "manual_entity_id",
        "e2a_probe_missing_manual_evidence_owner_scope",
        "e2a_probe_wrong_shadow_projection",
        "e2a_probe_wrong_owner_target",
        "e2a_probe_wrong_target_mapping",
        "e2a_probe_cross_version_span_evidence",
        "e2a_probe_invalid_global_scoped_scope",
        "e2a_probe_restrict_delete",
    ):
        assert required in probe


class _NoAuthority:
    authorized = False


def test_postgres_acceptance_is_blocked_before_parser_or_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_parser(*_: object) -> None:
        calls.append("parser")
        raise AssertionError("parser must not be attempted")

    def fail_connect(*_: object, **__: object) -> None:
        calls.append("connector")
        raise AssertionError("connection must not be attempted")

    monkeypatch.setattr(acceptance, "parse_disposable_postgresql_target", fail_parser)
    assert (
        run_disposable_migration_acceptance(
            _NoAuthority(),
            "not-validated-before-gate",
            "also-not-validated",
            fail_connect,
        )
        == "blocked_not_executed"
    )
    assert calls == []
