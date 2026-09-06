-- P4 KAG-style Schema/Constraint Layer
-- Adds entity_type_schemas and relation_type_schemas tables
-- Enables validation of entity and relation types against defined schemas

-- Entity type schemas: defines valid entity types and their constraints
CREATE TABLE IF NOT EXISTS entity_type_schemas (
    entity_type_schema_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type_name TEXT NOT NULL UNIQUE,
    description TEXT,
    required_fields TEXT[],  -- Array of field names that must be present
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Relation type schemas: defines valid relation types and source/target constraints
CREATE TABLE IF NOT EXISTS relation_type_schemas (
    relation_type_schema_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    relation_type_name TEXT NOT NULL UNIQUE,
    allowed_source_types TEXT[],  -- Array of allowed source entity_type names
    allowed_target_types TEXT[],  -- Array of allowed target entity_type names
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient lookup
CREATE INDEX IF NOT EXISTS idx_entity_type_schemas_name ON entity_type_schemas(entity_type_name);
CREATE INDEX IF NOT EXISTS idx_relation_type_schemas_name ON relation_type_schemas(relation_type_name);

-- Comments for documentation
COMMENT ON TABLE entity_type_schemas IS 'KAG-style entity type schema definitions - defines valid entity types and constraints';
COMMENT ON TABLE relation_type_schemas IS 'KAG-style relation type schema definitions - defines valid relation types and source/target constraints';
COMMENT ON COLUMN entity_type_schemas.required_fields IS 'Array of field names that must be present for entities of this type';
COMMENT ON COLUMN relation_type_schemas.allowed_source_types IS 'Array of entity_type names allowed as source entities for this relation type';
COMMENT ON COLUMN relation_type_schemas.allowed_target_types IS 'Array of entity_type names allowed as target entities for this relation type';