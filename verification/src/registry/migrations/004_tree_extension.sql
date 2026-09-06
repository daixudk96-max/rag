ALTER TABLE vector_chunks
ADD COLUMN IF NOT EXISTS node_id UUID;

CREATE TABLE IF NOT EXISTS tree_nodes (
    node_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    parent_node_id UUID REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    node_type TEXT NOT NULL,
    level_no INTEGER NOT NULL,
    title TEXT,
    heading_path TEXT,
    page_start INTEGER,
    page_end INTEGER,
    summary_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tree_nodes_version_id ON tree_nodes(version_id);
CREATE INDEX IF NOT EXISTS idx_tree_nodes_parent ON tree_nodes(parent_node_id);
CREATE INDEX IF NOT EXISTS idx_tree_nodes_level ON tree_nodes(version_id, level_no);

CREATE TABLE IF NOT EXISTS tree_node_spans (
    node_id UUID NOT NULL REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    span_id UUID NOT NULL REFERENCES canonical_spans(span_id) ON DELETE CASCADE,
    ordinal_no INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (node_id, span_id)
);

CREATE INDEX IF NOT EXISTS idx_tree_node_spans_span ON tree_node_spans(span_id);
