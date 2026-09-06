-- P5 Summary Index: first-class summary view for multi-view indexing.
-- Separates summary entities from tree node embedded summary_text.

CREATE TABLE IF NOT EXISTS summaries (
    summary_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    node_id UUID NOT NULL REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_summaries_version_id ON summaries(version_id);
CREATE INDEX IF NOT EXISTS idx_summaries_node_id ON summaries(node_id);

-- Full-text search index for keyword queries over summary_text
CREATE INDEX IF NOT EXISTS idx_summaries_text_tsvector ON summaries USING gin(to_tsvector('simple', summary_text));

-- Trigram index for ILIKE pattern matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_summaries_text_trgm ON summaries USING gin(summary_text gin_trgm_ops);