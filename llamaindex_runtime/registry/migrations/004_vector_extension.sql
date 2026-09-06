-- Phase 4 Vector Extension: add embedding and node_id columns to vector_chunks

-- Add embedding column for pgvector similarity search
ALTER TABLE vector_chunks
ADD COLUMN IF NOT EXISTS embedding vector(16);

-- Add node_id column for linking chunks to tree nodes
ALTER TABLE vector_chunks
ADD COLUMN IF NOT EXISTS node_id UUID REFERENCES tree_nodes(node_id) ON DELETE SET NULL;

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding
ON vector_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1);

-- Create index for node_id lookups
CREATE INDEX IF NOT EXISTS idx_vector_chunks_node_id ON vector_chunks(node_id) WHERE node_id IS NOT NULL;
