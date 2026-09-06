-- P4 LightRAG-style Incremental Processing Status

-- Add processing_status to track document processing stages
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS processing_status TEXT NOT NULL DEFAULT 'registered';

-- Add timestamp columns for each processing stage
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS parsed_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS chunks_created_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS tree_built_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS entities_extracted_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS processing_status_updated_at TIMESTAMPTZ DEFAULT now();

-- Add index for querying by processing status (for incremental processing)
CREATE INDEX IF NOT EXISTS idx_document_versions_processing_status ON document_versions(processing_status) WHERE (is_active = true);

-- Add CHECK constraint to ensure processing_status is one of the valid stages
ALTER TABLE document_versions DROP CONSTRAINT IF EXISTS chk_processing_status_valid;
ALTER TABLE document_versions ADD CONSTRAINT chk_processing_status_valid
    CHECK (processing_status IN (
        'registered',
        'parsed',
        'chunks_created',
        'embedded',
        'tree_built',
        'entities_extracted',
        'complete',
        'failed'
    ));

-- Add trigger to auto-update timestamps based on status changes
CREATE OR REPLACE FUNCTION update_processing_status_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.processing_status_updated_at = now();

    -- Update stage-specific timestamp when transitioning to that stage
    IF NEW.processing_status = 'parsed' AND OLD.processing_status != 'parsed' THEN
        NEW.parsed_at = now();
    END IF;

    IF NEW.processing_status = 'chunks_created' AND OLD.processing_status != 'chunks_created' THEN
        NEW.chunks_created_at = now();
    END IF;

    IF NEW.processing_status = 'embedded' AND OLD.processing_status != 'embedded' THEN
        NEW.embedded_at = now();
    END IF;

    IF NEW.processing_status = 'tree_built' AND OLD.processing_status != 'tree_built' THEN
        NEW.tree_built_at = now();
    END IF;

    IF NEW.processing_status = 'entities_extracted' AND OLD.processing_status != 'entities_extracted' THEN
        NEW.entities_extracted_at = now();
    END IF;

    IF NEW.processing_status = 'complete' AND OLD.processing_status != 'complete' THEN
        NEW.completed_at = now();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create the trigger
DROP TRIGGER IF EXISTS trg_update_processing_status_timestamp ON document_versions;
CREATE TRIGGER trg_update_processing_status_timestamp
    BEFORE UPDATE OF processing_status ON document_versions
    FOR EACH ROW
    EXECUTE FUNCTION update_processing_status_timestamp();