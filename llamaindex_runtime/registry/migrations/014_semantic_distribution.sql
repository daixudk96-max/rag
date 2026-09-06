-- Phase 4 Task 4.1: Semantic distribution precomputation
-- Stores precomputed distribution stats per node for query-time acceleration.

CREATE TABLE IF NOT EXISTS semantic_distribution (
    node_id UUID NOT NULL REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,

    -- Distribution statistics (per-node)
    support_count INTEGER NOT NULL DEFAULT 0,  -- Number of hits supporting this node
    dispersion REAL NOT NULL DEFAULT 0.0,      -- Coefficient of variation (CV)
    entropy REAL NOT NULL DEFAULT 0.0,         -- Shannon entropy

    -- Tree-level signals (optional, can be derived at query time)
    max_entropy REAL DEFAULT 0.0,
    depth INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, version_id)
);

-- Index for version-based retrieval
CREATE INDEX IF NOT EXISTS idx_semantic_distribution_version
ON semantic_distribution(version_id);

-- Index for node-based lookup
CREATE INDEX IF NOT EXISTS idx_semantic_distribution_node
ON semantic_distribution(node_id);