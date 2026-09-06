-- Phase 16 C2 (conditional sub-wave): conservative local coreference clusters.
-- Provisional migration 021 (re-verified as the next free slot after 020 per
-- ADR T5 at execution time). Ordered after the C1 schema: it references
-- document_versions (002) and entity_mentions (016/020) only.
--
-- Contract (supplement handoff §4.4 / R-OKF-09 / D7):
-- * coref_clusters is the per-document-version cluster master record with a
--   per-cluster tombstone soft delete; membership is NORMALIZED in
--   coref_cluster_mentions (never an unqueryable mention_ids JSON array).
-- * No merge-log table and no canonical-merge table is created: a cluster is
--   a local evidence connection between text mentions, never a proof that
--   canonical entities were merged.
-- * This migration is additive and idempotent (CREATE TABLE IF NOT EXISTS),
--   matching the 020 style; it performs no backfill and no DML.

-- 1. Cluster master record, scoped to one document version.
CREATE TABLE IF NOT EXISTS coref_clusters (
    cluster_id UUID NOT NULL,
    version_id UUID NOT NULL,
    coref_rules_version TEXT NOT NULL,
    tombstoned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_coref_clusters PRIMARY KEY (cluster_id),
    CONSTRAINT fk_coref_clusters_version FOREIGN KEY (version_id)
        REFERENCES document_versions(version_id) ON DELETE CASCADE,
    CONSTRAINT chk_coref_clusters_rules_version CHECK (coref_rules_version <> '')
);

-- 2. Normalized cluster membership: one row per (cluster, mention) pair.
-- The composite primary key makes membership queryable, indexable, and
-- auditable; ordinal_no preserves deterministic member ordering.
CREATE TABLE IF NOT EXISTS coref_cluster_mentions (
    cluster_id UUID NOT NULL,
    mention_id UUID NOT NULL,
    ordinal_no INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT pk_coref_cluster_mentions PRIMARY KEY (cluster_id, mention_id),
    CONSTRAINT fk_coref_cluster_mentions_cluster FOREIGN KEY (cluster_id)
        REFERENCES coref_clusters(cluster_id) ON DELETE CASCADE,
    CONSTRAINT fk_coref_cluster_mentions_mention FOREIGN KEY (mention_id)
        REFERENCES entity_mentions(mention_id) ON DELETE CASCADE,
    CONSTRAINT chk_coref_cluster_mentions_ordinal CHECK (ordinal_no >= 0)
);

-- 3. Supporting indexes: version-scoped cluster lookup and mention reverse
-- lookup (the cluster_id prefix of the PK already serves cluster-side scans).
CREATE INDEX IF NOT EXISTS idx_coref_clusters_version
    ON coref_clusters (version_id);
CREATE INDEX IF NOT EXISTS idx_coref_cluster_mentions_mention
    ON coref_cluster_mentions (mention_id);
