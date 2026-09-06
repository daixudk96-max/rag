-- P4 Evidence Object Slice: Minimal evidence_id grouping layer
-- Creates evidence table for grouping evidence_links
-- Adds evidence_id to evidence_links as optional foreign key

-- Create evidence table for grouping evidence_links
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Create index on version_id for efficient queries
CREATE INDEX IF NOT EXISTS idx_evidence_version ON evidence(version_id);

-- Add evidence_id column to evidence_links (optional grouping layer)
ALTER TABLE evidence_links ADD COLUMN IF NOT EXISTS evidence_id UUID REFERENCES evidence(evidence_id) ON DELETE CASCADE;

-- Create index on evidence_id for efficient grouping queries
CREATE INDEX IF NOT EXISTS idx_evidence_links_evidence ON evidence_links(evidence_id) WHERE evidence_id IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE evidence IS 'P4 evidence object: minimal grouping layer for evidence_links - no scoring, no deduplication';
COMMENT ON COLUMN evidence_links.evidence_id IS 'P4 optional evidence grouping - preserves span_id backbone provenance';