-- 022_keyword_fts_indexes.sql
-- Keyword full-text search support for canonical_spans (2026-09-06).
-- Promoted from the verification harness set
-- (verification/src/registry/migrations/002_keyword_indexes.sql) into the root
-- authoritative chain: registry.query_spans_by_keyword requires
-- cs.raw_text_tsvector, which the root chain previously lacked
-- (retrieval rerank smoke finding, 2026-09-05, user-approved promotion).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE canonical_spans
ADD COLUMN IF NOT EXISTS raw_text_tsvector tsvector;

UPDATE canonical_spans
SET raw_text_tsvector = to_tsvector('simple', COALESCE(raw_text, ''))
WHERE raw_text_tsvector IS NULL;

CREATE OR REPLACE FUNCTION canonical_spans_tsvector_update() RETURNS trigger AS $$
BEGIN
  NEW.raw_text_tsvector := to_tsvector('simple', COALESCE(NEW.raw_text, ''));
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_canonical_spans_tsvector_update ON canonical_spans;
CREATE TRIGGER trg_canonical_spans_tsvector_update
BEFORE INSERT OR UPDATE OF raw_text ON canonical_spans
FOR EACH ROW
EXECUTE FUNCTION canonical_spans_tsvector_update();

CREATE INDEX IF NOT EXISTS idx_spans_fts ON canonical_spans USING gin(raw_text_tsvector);
CREATE INDEX IF NOT EXISTS idx_spans_trgm ON canonical_spans USING gin(raw_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_spans_version_page ON canonical_spans(version_id, page_no);
