-- EvidenceNet follow-up: Add dedup_key for idempotent deduplication at version scope
-- Minimal slice: no scoring framework, no EvidenceNet policy - just dedup contract/data-layer

-- Add dedup_key column to evidence table
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS dedup_key TEXT;

-- Create unique partial index for deduplication within version scope
-- Only applies when dedup_key IS NOT NULL (preserves evidence_id uniqueness for null dedup_key)
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_version_dedup_key
ON evidence(version_id, dedup_key)
WHERE dedup_key IS NOT NULL;

-- Create index on dedup_key for efficient lookups
CREATE INDEX IF NOT EXISTS idx_evidence_dedup_key ON evidence(dedup_key) WHERE dedup_key IS NOT NULL;

-- Update comments to reflect EvidenceNet dedup semantics
COMMENT ON TABLE evidence IS 'P4 evidence object: minimal grouping layer for evidence_links with EvidenceNet dedup_key';
COMMENT ON COLUMN evidence.dedup_key IS 'EvidenceNet deduplication key: idempotent within version scope, enables collapse of duplicate evidence';