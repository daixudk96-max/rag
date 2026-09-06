ALTER TABLE vector_chunks
ADD COLUMN IF NOT EXISTS embedding vector(16);

CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding
ON vector_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1);
