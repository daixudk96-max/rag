-- Phase 5 follow-up: enrich GraphRAG-style mapping tables with optional extraction metadata

ALTER TABLE chunk_entity_links
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS mention_text TEXT;

ALTER TABLE node_entity_links
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS mention_text TEXT;
