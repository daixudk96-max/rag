-- Phase 14 entity-mention tables. Phase 16 populates these tables.

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    source TEXT
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);

CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id UUID PRIMARY KEY,
    entity_id UUID REFERENCES entities(entity_id) ON DELETE SET NULL,
    span_id UUID NOT NULL REFERENCES canonical_spans(span_id) ON DELETE CASCADE,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    mention_text TEXT NOT NULL,
    confidence NUMERIC,
    source TEXT NOT NULL,
    okf_file_path TEXT,
    okf_paragraph_id TEXT,
    CONSTRAINT chk_entity_mentions_char_range
        CHECK (char_start >= 0 AND char_end > char_start)
);

CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_span ON entity_mentions(span_id);

CREATE TABLE IF NOT EXISTS entity_merge_log (
    merge_id UUID PRIMARY KEY,
    from_entity_id UUID NOT NULL,
    into_entity_id UUID NOT NULL,
    reason TEXT,
    merged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
