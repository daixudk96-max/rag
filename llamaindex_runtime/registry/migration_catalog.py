"""The one authoritative, ordered root registry migration catalog."""

from __future__ import annotations

FULL_MIGRATION_CATALOG: tuple[str, ...] = (
    "001_initial.sql",
    "002_version_lifecycle.sql",
    "003_tree_persistence.sql",
    "004_vector_extension.sql",
    "005_kg_extension.sql",
    "006_kg_graphrag_enrichment.sql",
    "007_processing_status.sql",
    "008_evidence_object.sql",
    "009_kag_schema.sql",
    "010_summary_index.sql",
    "011_evidence_dedup_key.sql",
    "012_mapping_table_enrichment.sql",
    "013_node_embeddings.sql",
    "014_semantic_distribution.sql",
    "015_okf_sync_state.sql",
    "016_entity_mentions.sql",
    "017_relation_qualifiers.sql",
    "018_okf_rebuild_failure_audit.sql",
    "019_e2a_materialization_contract.sql",
    "020_ner_entity_mentions.sql",
    "021_ner_coref_clusters.sql",
    "022_keyword_fts_indexes.sql",
)

# PageIndex has a deliberately curated legacy schema workflow, not root authority.
PAGEINDEX_MIGRATIONS: tuple[str, ...] = (
    "001_initial.sql",
    "002_version_lifecycle.sql",
    "003_tree_persistence.sql",
)

__all__ = ["FULL_MIGRATION_CATALOG", "PAGEINDEX_MIGRATIONS"]
