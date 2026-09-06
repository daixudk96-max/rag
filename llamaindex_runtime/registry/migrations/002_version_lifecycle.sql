-- Phase 2 Version Lifecycle: stable document identity and explainable versioning

-- 1. Ensure source_uri is unique for stable document identity
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source_uri ON documents(source_uri);

-- 2. Ensure normalization contracts can be looked up by their parameters
-- This allows reusing normalization contracts when ingesting the same source
CREATE UNIQUE INDEX IF NOT EXISTS idx_normalization_contracts_params
    ON normalization_contracts(parser_name, parser_version, offset_basis);

-- 3. Change document_versions unique constraint to include normalization_contract_id
-- This allows same content with different normalization contracts to coexist as separate versions
-- The old constraint UNIQUE (doc_id, content_hash) would block this use case

-- First, drop the old constraint (PostgreSQL names it document_versions_doc_id_content_hash_key)
ALTER TABLE document_versions DROP CONSTRAINT IF EXISTS document_versions_doc_id_content_hash_key;

-- Then, create a new unique constraint that includes normalization_contract_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_content_contract
    ON document_versions(doc_id, content_hash, normalization_contract_id);