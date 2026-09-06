"""Non-DB catalog placement tests for Phase 16 C1 migration 020 and C2 migration 021.

The root migration catalog must contain exactly one ``020_ner_entity_mentions.sql``
entry immediately after ``019_e2a_materialization_contract.sql``, exactly one
``021_ner_coref_clusters.sql`` entry immediately after 020, and exactly one
``022_keyword_fts_indexes.sql`` entry immediately after 021 (keyword FTS
contract evolution: 022 is now the final catalog entry). The PageIndex curated
subset must continue to exclude all three.
"""

from __future__ import annotations

import run_migrations
from llamaindex_runtime.registry.migration_catalog import (
    FULL_MIGRATION_CATALOG,
    PAGEINDEX_MIGRATIONS,
)


def test_full_catalog_has_020_exactly_once_immediately_after_019() -> None:
    assert FULL_MIGRATION_CATALOG.count("020_ner_entity_mentions.sql") == 1
    assert FULL_MIGRATION_CATALOG.index("019_e2a_materialization_contract.sql") + 1 == (
        FULL_MIGRATION_CATALOG.index("020_ner_entity_mentions.sql")
    )


def test_full_catalog_has_021_exactly_once_immediately_after_020() -> None:
    assert FULL_MIGRATION_CATALOG.count("021_ner_coref_clusters.sql") == 1
    assert FULL_MIGRATION_CATALOG.index("020_ner_entity_mentions.sql") + 1 == (
        FULL_MIGRATION_CATALOG.index("021_ner_coref_clusters.sql")
    )


def test_full_catalog_has_022_exactly_once_immediately_after_021() -> None:
    assert FULL_MIGRATION_CATALOG.count("022_keyword_fts_indexes.sql") == 1
    assert FULL_MIGRATION_CATALOG.index("021_ner_coref_clusters.sql") + 1 == (
        FULL_MIGRATION_CATALOG.index("022_keyword_fts_indexes.sql")
    )


def test_full_catalog_022_is_final_entry() -> None:
    # Contract evolution (2026-09-06): 022 (keyword FTS) supersedes 021 as the final entry.
    assert FULL_MIGRATION_CATALOG[-1] == "022_keyword_fts_indexes.sql"


def test_root_runner_key_migrations_include_022() -> None:
    assert run_migrations.KEY_MIGRATIONS is FULL_MIGRATION_CATALOG
    assert run_migrations.KEY_MIGRATIONS[-1] == "022_keyword_fts_indexes.sql"


def test_pageindex_curated_workflow_excludes_020_021_and_022() -> None:
    assert "020_ner_entity_mentions.sql" not in PAGEINDEX_MIGRATIONS
    assert "021_ner_coref_clusters.sql" not in PAGEINDEX_MIGRATIONS
    assert "022_keyword_fts_indexes.sql" not in PAGEINDEX_MIGRATIONS
    assert PAGEINDEX_MIGRATIONS == (
        "001_initial.sql",
        "002_version_lifecycle.sql",
        "003_tree_persistence.sql",
    )
