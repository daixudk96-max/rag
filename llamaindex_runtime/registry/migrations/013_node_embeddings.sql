-- Phase 2 Task 2.1: Node embeddings precomputation
-- Stores precomputed embeddings for tree nodes to accelerate retrieval routing.

CREATE TABLE IF NOT EXISTS node_embeddings (
    node_id UUID NOT NULL REFERENCES tree_nodes(node_id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding_vector VECTOR(384) NOT NULL,  -- Matches all-MiniLM-L6-v2 dimension
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, embedding_model)
);

-- Index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_node_embeddings_vector
ON node_embeddings
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100);

-- Index for model filtering
CREATE INDEX IF NOT EXISTS idx_node_embeddings_model ON node_embeddings(embedding_model);