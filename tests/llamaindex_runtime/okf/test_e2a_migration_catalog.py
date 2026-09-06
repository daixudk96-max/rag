from __future__ import annotations

from pathlib import Path

import run_migrations
from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG


def test_root_catalog_is_complete_and_contains_019_once_after_018() -> None:
    assert FULL_MIGRATION_CATALOG.count("019_e2a_materialization_contract.sql") == 1
    assert FULL_MIGRATION_CATALOG.index("018_okf_rebuild_failure_audit.sql") + 1 == (
        FULL_MIGRATION_CATALOG.index("019_e2a_materialization_contract.sql")
    )
    assert run_migrations.KEY_MIGRATIONS is FULL_MIGRATION_CATALOG


def test_pageindex_limited_workflow_is_explicitly_non_applicable() -> None:
    assert (
        "019_e2a_materialization_contract.sql"
        not in run_migrations.PAGEINDEX_MIGRATIONS
    )


def test_migration_019_preserves_legacy_source_kinds_and_uses_target_safe_dedup() -> (
    None
):
    sql = (
        Path(__file__).resolve().parents[3]
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
        / "019_e2a_materialization_contract.sql"
    ).read_text(encoding="utf-8")

    assert "source_kind IN ('legacy', 'manual_okf')" not in sql
    for required in (
        "preexisting manual_okf ownership",
        "idx_evidence_links_e2a_entity_dedup",
        "idx_evidence_links_e2a_relation_dedup",
        "idx_evidence_links_version_span",
        "idx_evidence_links_version_evidence",
        "idx_okf_manual_fact_ownership_document_version",
        "num_nonnulls(entity_id, relation_id) = 1",
    ):
        assert required in sql
