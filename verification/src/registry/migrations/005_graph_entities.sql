CREATE TABLE IF NOT EXISTS entities (
    entity_id UUID PRIMARY KEY,
    entity_key TEXT NOT NULL UNIQUE,
    entity_type TEXT,
    canonical_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS relations (
    relation_id UUID PRIMARY KEY,
    relation_key TEXT NOT NULL UNIQUE,
    relation_type TEXT NOT NULL,
    source_entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    target_entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_links (
    evidence_link_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    entity_id UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    relation_id UUID REFERENCES relations(relation_id) ON DELETE CASCADE,
    span_id UUID NOT NULL REFERENCES canonical_spans(span_id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL,
    confidence_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (entity_id IS NOT NULL OR relation_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_evidence_links_entity ON evidence_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_relation ON evidence_links(relation_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_span ON evidence_links(span_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_version ON evidence_links(version_id);
