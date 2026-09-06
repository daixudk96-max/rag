-- Rollback-safe failure audit for guarded OKF bundle rebuilds.
-- This audit is deliberately committed through a separate connection after primary rollback;
-- it is not cross-database atomic with the canonical-span transaction.

CREATE TABLE IF NOT EXISTS okf_rebuild_failure_audit (
    audit_id UUID PRIMARY KEY,
    rebuild_run_id UUID NOT NULL UNIQUE,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    failure_category TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    failure_phase TEXT NOT NULL,
    rollback_confirmed BOOLEAN NOT NULL CHECK (rollback_confirmed),
    scope_count INTEGER NOT NULL CHECK (scope_count >= 1),
    scope_manifest JSONB NOT NULL,
    scope_manifest_sha256 CHAR(64) NOT NULL,
    failing_doc_id UUID,
    failing_version_id UUID,
    diagnostic JSONB NOT NULL,
    CONSTRAINT chk_okf_rebuild_failure_audit_category CHECK (
        failure_category IN ('scope_validation', 'identity_conflict', 'integrity', 'database', 'internal')
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_code CHECK (
        failure_code IN (
            'unregistered_document_version',
            'span_id_owned_by_other_version',
            'integrity_error',
            'database_error',
            'internal_failure'
        )
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_phase CHECK (
        failure_phase IN (
            'target_validation',
            'scope_lock',
            'span_reconciliation',
            'success_log_write',
            'transaction_commit'
        )
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_scope_manifest CHECK (
        jsonb_typeof(scope_manifest) = 'object'
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_hash CHECK (
        scope_manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_scope_pair CHECK (
        (failing_doc_id IS NULL AND failing_version_id IS NULL)
        OR (failing_doc_id IS NOT NULL AND failing_version_id IS NOT NULL)
    ),
    CONSTRAINT chk_okf_rebuild_failure_audit_diagnostic CHECK (
        jsonb_typeof(diagnostic) = 'object'
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'okf_rebuild_failure_audit'::regclass
          AND conname = 'chk_okf_rebuild_failure_audit_category_code_pair'
    ) THEN
        ALTER TABLE okf_rebuild_failure_audit
        ADD CONSTRAINT chk_okf_rebuild_failure_audit_category_code_pair CHECK (
            (failure_category = 'scope_validation'
                AND failure_code = 'unregistered_document_version')
            OR (failure_category = 'identity_conflict'
                AND failure_code = 'span_id_owned_by_other_version')
            OR (failure_category = 'integrity'
                AND failure_code = 'integrity_error')
            OR (failure_category = 'database'
                AND failure_code = 'database_error')
            OR (failure_category = 'internal'
                AND failure_code = 'internal_failure')
        );
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION prevent_okf_rebuild_failure_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'okf_rebuild_failure_audit is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_okf_rebuild_failure_audit_append_only
    ON okf_rebuild_failure_audit;
CREATE TRIGGER trg_okf_rebuild_failure_audit_append_only
    BEFORE UPDATE OR DELETE ON okf_rebuild_failure_audit
    FOR EACH ROW
    EXECUTE FUNCTION prevent_okf_rebuild_failure_audit_mutation();

DROP TRIGGER IF EXISTS trg_okf_rebuild_failure_audit_no_truncate
    ON okf_rebuild_failure_audit;
CREATE TRIGGER trg_okf_rebuild_failure_audit_no_truncate
    BEFORE TRUNCATE ON okf_rebuild_failure_audit
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_okf_rebuild_failure_audit_mutation();

CREATE INDEX IF NOT EXISTS idx_okf_rebuild_failure_audit_occurred_at
    ON okf_rebuild_failure_audit (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_okf_rebuild_failure_audit_scope
    ON okf_rebuild_failure_audit (failing_doc_id, failing_version_id)
    WHERE failing_doc_id IS NOT NULL;
