-- P4 KG Enhancement: GraphRAG-style entity and relation enrichment
-- Adds description and community_id to entities
-- Adds description to relations

-- Add GraphRAG-style fields to entities table
ALTER TABLE entities ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS community_id UUID;

-- Add GraphRAG-style field to relations table
ALTER TABLE relations ADD COLUMN IF NOT EXISTS description TEXT;

-- Create index on community_id for community-based queries
CREATE INDEX IF NOT EXISTS idx_entities_community ON entities(community_id) WHERE community_id IS NOT NULL;

-- Comments for documentation
COMMENT ON COLUMN entities.description IS 'GraphRAG-style entity description - textual description of the entity';
COMMENT ON COLUMN entities.community_id IS 'GraphRAG-style community identifier - for community detection/grouping';
COMMENT ON COLUMN relations.description IS 'GraphRAG-style relationship description - textual description of the relationship';