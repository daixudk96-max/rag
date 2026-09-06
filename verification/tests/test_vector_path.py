from __future__ import annotations

import uuid

from parser.docling_wrapper import DoclingWrapper, NormalizationContract
from parser.span_generator import SpanGenerator
from registry import crud
from vector_path.chunker import SimpleSpanChunker
from vector_path.embedder import DeterministicEmbedder
from vector_path.loader import load_version_chunks
from vector_path.search import search_by_vector_query


def _seed_spans(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Vector Doc", source_uri="file:///vector.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="vec-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 12, "page_no": 1, "heading_path": "环境 > 指标", "raw_text": "PM2.5 是空气质量指标。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 13, "end_offset": 36, "page_no": 2, "heading_path": "标准 > 国标", "raw_text": "GB3095-2012 是环境空气质量标准。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 37, "end_offset": 60, "page_no": 3, "heading_path": "监测 > 说明", "raw_text": "空气质量监测需要长期采样。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    crud.activate_version(db_connection, version_id)
    return doc_id, version_id, spans


def test_chunker_generates_chunks(db_connection, applied_schema) -> None:
    _, version_id, spans = _seed_spans(db_connection, applied_schema)
    chunks = SimpleSpanChunker().generate(spans, version_id=version_id)
    assert chunks
    assert chunks[0]["chunk_type"] == "semantic_leaf"


def test_embedder_is_deterministic() -> None:
    embedder = DeterministicEmbedder(dim=16)
    first = embedder.embed_text("PM2.5 是空气质量指标。")
    second = embedder.embed_text("PM2.5 是空气质量指标。")
    assert first == second
    assert len(first) == 16


def test_load_version_chunks_persists_embeddings(db_connection, applied_schema) -> None:
    _, version_id, _ = _seed_spans(db_connection, applied_schema)
    loaded = load_version_chunks(db_connection, version_id)
    assert loaded["chunk_ids"]
    with db_connection.cursor() as cur:
        cur.execute("SELECT embedding IS NOT NULL FROM vector_chunks WHERE version_id = %s LIMIT 1", (str(version_id),))
        row = cur.fetchone()
    assert row[0] is True


def test_vector_query_returns_provenance(db_connection, applied_schema) -> None:
    _, version_id, _ = _seed_spans(db_connection, applied_schema)
    load_version_chunks(db_connection, version_id)
    result = search_by_vector_query(db_connection, "空气质量监测标准")
    assert result["total_hits"] >= 1
    first = result["chunks"][0]
    assert {"chunk_id", "span_ids", "page_no", "heading_path", "score"}.issubset(first.keys())


def test_vector_query_prefers_relevant_chunk(db_connection, applied_schema) -> None:
    _, version_id, _ = _seed_spans(db_connection, applied_schema)
    load_version_chunks(db_connection, version_id)
    result = search_by_vector_query(db_connection, "PM2.5 浓度限值")
    assert result["total_hits"] >= 1
    texts = [c["text_preview"] for c in result["chunks"]]
    assert any("PM2.5" in t for t in texts)
