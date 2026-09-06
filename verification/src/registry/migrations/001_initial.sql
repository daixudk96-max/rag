CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id UUID PRIMARY KEY,
    source_uri TEXT,
    title TEXT,
    doc_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS normalization_contracts (
    normalization_contract_id UUID PRIMARY KEY,
    parser_name TEXT NOT NULL,
    parser_version TEXT,
    offset_basis TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    normalization_contract_id UUID REFERENCES normalization_contracts(normalization_contract_id),
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'staging',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    UNIQUE (doc_id, version_no),
    UNIQUE (doc_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_document_versions_doc_id ON document_versions(doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_active ON document_versions(doc_id) WHERE (is_active = true);

CREATE TABLE IF NOT EXISTS canonical_spans (
    span_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    span_kind TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    page_no INTEGER,
    heading_path TEXT,
    raw_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_offset > start_offset)
);

CREATE INDEX IF NOT EXISTS idx_canonical_spans_version_id ON canonical_spans(version_id);
CREATE INDEX IF NOT EXISTS idx_canonical_spans_page_no ON canonical_spans(version_id, page_no);
CREATE INDEX IF NOT EXISTS idx_canonical_spans_offset_range ON canonical_spans(version_id, start_offset, end_offset);

CREATE TABLE IF NOT EXISTS vector_chunks (
    chunk_id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL,
    chunk_order INTEGER,
    token_count INTEGER,
    text_preview TEXT,
    page_no INTEGER,
    heading_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vector_chunks_version_id ON vector_chunks(version_id);

CREATE TABLE IF NOT EXISTS vector_chunk_spans (
    chunk_id UUID NOT NULL REFERENCES vector_chunks(chunk_id) ON DELETE CASCADE,
    span_id UUID NOT NULL REFERENCES canonical_spans(span_id) ON DELETE CASCADE,
    ordinal_no INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chunk_id, span_id)
);

CREATE INDEX IF NOT EXISTS idx_vector_chunk_spans_span ON vector_chunk_spans(span_id);
