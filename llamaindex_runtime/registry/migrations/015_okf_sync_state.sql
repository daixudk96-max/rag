-- Phase 14 OKF sync and rebuild bookkeeping.

CREATE TABLE IF NOT EXISTS okf_sync_state (
    okf_file_path TEXT PRIMARY KEY,
    doc_id UUID,
    version_id UUID,
    source_checksum TEXT NOT NULL,
    canonical_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS okf_rebuild_log (
    rebuild_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    span_count INTEGER,
    mismatch_detail JSONB
);
