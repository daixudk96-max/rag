-- Phase 16 C1: entity_mentions provenance + stable E2b owner scope,
-- okf_e2b_failure_audit (append-only), and okf_e2b_node_link_ownership ledger.
-- This migration is additive and idempotent. It never backfills or claims
-- pre-existing legacy/manual/unowned rows: NULL e2b_owner_scope stays NULL and
-- E2b desired-state reconciliation must never delete or claim those rows.

-- 1. Additive nullable provenance columns on entity_mentions.
-- Each is typed (NOT compact JSONB) so constraints, idempotent upserts,
-- indexable queries, deterministic rebuild natural keys, and version audit all
-- remain supported. e2b_owner_scope is nullable: NULL means legacy/manual/
-- unowned and is structurally preserved.
ALTER TABLE entity_mentions
    ADD COLUMN IF NOT EXISTS input_id UUID,
    ADD COLUMN IF NOT EXISTS input_kind TEXT,
    ADD COLUMN IF NOT EXISTS input_revision TEXT,
    ADD COLUMN IF NOT EXISTS extractor_id TEXT,
    ADD COLUMN IF NOT EXISTS extractor_version TEXT,
    ADD COLUMN IF NOT EXISTS model_id TEXT,
    ADD COLUMN IF NOT EXISTS model_revision TEXT,
    ADD COLUMN IF NOT EXISTS artifact_digest CHAR(64),
    ADD COLUMN IF NOT EXISTS schema_version TEXT,
    ADD COLUMN IF NOT EXISTS normalization_version TEXT,
    ADD COLUMN IF NOT EXISTS segmentation_version TEXT,
    ADD COLUMN IF NOT EXISTS label_map_digest CHAR(64),
    ADD COLUMN IF NOT EXISTS runtime_compatibility_id TEXT,
    ADD COLUMN IF NOT EXISTS document_char_start INTEGER,
    ADD COLUMN IF NOT EXISTS document_char_end INTEGER,
    ADD COLUMN IF NOT EXISTS segment_id UUID,
    ADD COLUMN IF NOT EXISTS raw_label TEXT,
    ADD COLUMN IF NOT EXISTS entity_type TEXT,
    ADD COLUMN IF NOT EXISTS confidence_kind TEXT,
    ADD COLUMN IF NOT EXISTS e2b_owner_scope TEXT;

-- 2. Guarded, idempotent named constraints on entity_mentions.
-- PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so every constraint is added
-- behind a pg_constraint existence guard.
DO $e2b020$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_input_kind'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_input_kind CHECK (input_kind IS NULL OR input_kind IN ('corpus_span', 'query_text'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_confidence_kind'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_confidence_kind CHECK (confidence_kind IS NULL OR confidence_kind IN ('frontmatter_declared', 'dictionary_exact', 'rule_weight', 'model_probability', 'unavailable'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_artifact_digest'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_artifact_digest CHECK (artifact_digest IS NULL OR artifact_digest ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_label_map_digest'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_label_map_digest CHECK (label_map_digest IS NULL OR label_map_digest ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_document_coordinates'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_document_coordinates CHECK ((document_char_start IS NULL AND document_char_end IS NULL) OR (document_char_start IS NOT NULL AND document_char_end IS NOT NULL AND document_char_start >= 0 AND document_char_end > document_char_start));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'entity_mentions'::regclass
          AND conname = 'chk_okf_e2b_mentions_owner_scope'
    ) THEN
        ALTER TABLE entity_mentions
        ADD CONSTRAINT chk_okf_e2b_mentions_owner_scope CHECK (e2b_owner_scope IS NULL OR e2b_owner_scope ~ '^okf:e2b:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
    END IF;
END
$e2b020$;

-- 3. Append-only E2b failure audit, structurally distinct from the Phase 15
-- rebuild failure audit (pinned by migration 019 and never reused).
CREATE TABLE IF NOT EXISTS okf_e2b_failure_audit (
    audit_id UUID NOT NULL,
    e2b_run_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    failure_phase TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    rollback_confirmed BOOLEAN NOT NULL,
    scope_count INTEGER NOT NULL,
    scope_manifest JSONB NOT NULL,
    scope_manifest_sha256 CHAR(64) NOT NULL,
    failing_doc_id UUID,
    failing_version_id UUID,
    diagnostic JSONB NOT NULL,
    CONSTRAINT pk_okf_e2b_failure_audit PRIMARY KEY (audit_id),
    CONSTRAINT uq_okf_e2b_failure_audit_run UNIQUE (e2b_run_id),
    CONSTRAINT chk_okf_e2b_failure_audit_rollback CHECK (rollback_confirmed),
    CONSTRAINT chk_okf_e2b_failure_audit_scope_count CHECK (scope_count >= 1),
    CONSTRAINT chk_okf_e2b_failure_audit_scope_manifest CHECK (jsonb_typeof(scope_manifest) = 'object'),
    CONSTRAINT chk_okf_e2b_failure_audit_hash CHECK (scope_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_okf_e2b_failure_audit_scope_pair CHECK ((failing_doc_id IS NULL AND failing_version_id IS NULL) OR (failing_doc_id IS NOT NULL AND failing_version_id IS NOT NULL)),
    CONSTRAINT chk_okf_e2b_failure_audit_diagnostic CHECK (jsonb_typeof(diagnostic) = 'object')
);

CREATE OR REPLACE FUNCTION prevent_okf_e2b_failure_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'okf_e2b_failure_audit is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_okf_e2b_failure_audit_append_only
    ON okf_e2b_failure_audit;
CREATE TRIGGER trg_okf_e2b_failure_audit_append_only
    BEFORE UPDATE OR DELETE ON okf_e2b_failure_audit
    FOR EACH ROW
    EXECUTE FUNCTION prevent_okf_e2b_failure_audit_mutation();

DROP TRIGGER IF EXISTS trg_okf_e2b_failure_audit_no_truncate
    ON okf_e2b_failure_audit;
CREATE TRIGGER trg_okf_e2b_failure_audit_no_truncate
    BEFORE TRUNCATE ON okf_e2b_failure_audit
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_okf_e2b_failure_audit_mutation();

CREATE INDEX IF NOT EXISTS idx_okf_e2b_failure_audit_occurred_at
    ON okf_e2b_failure_audit (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_okf_e2b_failure_audit_scope
    ON okf_e2b_failure_audit (failing_doc_id, failing_version_id)
    WHERE failing_doc_id IS NOT NULL;

-- 4. Typed bridge ownership ledger for E2b-created node-to-entity bridge rows.
-- This ledger records only persisted E2b-created bridge ownership proofs.
-- Independent FKs do not prove node/version consistency, so a dedicated E2b
-- trigger enforces that tree_nodes contains NEW.node_id with NEW.version_id.
CREATE TABLE IF NOT EXISTS okf_e2b_node_link_ownership (
    node_entity_link_owner_id UUID NOT NULL,
    node_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    version_id UUID NOT NULL,
    node_entity_link_key TEXT NOT NULL,
    e2b_run_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_okf_e2b_node_link_ownership PRIMARY KEY (node_entity_link_owner_id),
    CONSTRAINT fk_okf_e2b_node_link_ownership_node FOREIGN KEY (node_id)
        REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT fk_okf_e2b_node_link_ownership_entity FOREIGN KEY (entity_id)
        REFERENCES entities(entity_id) ON DELETE CASCADE,
    CONSTRAINT fk_okf_e2b_node_link_ownership_version FOREIGN KEY (version_id)
        REFERENCES document_versions(version_id) ON DELETE CASCADE,
    CONSTRAINT uq_okf_e2b_node_link_ownership UNIQUE (node_id, entity_id, version_id),
    CONSTRAINT chk_okf_e2b_node_link_key CHECK (node_entity_link_key = node_id::text || ':' || entity_id::text)
);

CREATE OR REPLACE FUNCTION validate_okf_e2b_node_link_ownership_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    node_version_count integer;
BEGIN
    SELECT count(*) INTO node_version_count
    FROM tree_nodes
    WHERE node_id = NEW.node_id
      AND version_id = NEW.version_id;

    IF node_version_count = 0 THEN
        RAISE EXCEPTION 'okf_e2b_node_link_ownership node/version mismatch';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_okf_e2b_node_link_ownership_version
    ON okf_e2b_node_link_ownership;
CREATE TRIGGER trg_okf_e2b_node_link_ownership_version
    BEFORE INSERT OR UPDATE ON okf_e2b_node_link_ownership
    FOR EACH ROW
    EXECUTE FUNCTION validate_okf_e2b_node_link_ownership_version();

CREATE INDEX IF NOT EXISTS idx_okf_e2b_node_link_ownership_node
    ON okf_e2b_node_link_ownership (node_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_okf_e2b_node_link_ownership_version
    ON okf_e2b_node_link_ownership (version_id);
