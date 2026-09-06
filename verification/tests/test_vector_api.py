from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from api.routes import app
from registry import crud
from vector_path.loader import load_version_chunks


def _seed_spans(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Vector Doc", source_uri="file:///vector.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="vec-api-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 12, "page_no": 1, "heading_path": "环境 > 指标", "raw_text": "PM2.5 是空气质量指标。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 13, "end_offset": 36, "page_no": 2, "heading_path": "标准 > 国标", "raw_text": "GB3095-2012 是环境空气质量标准。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    crud.activate_version(db_connection, version_id)
    load_version_chunks(db_connection, version_id)


def test_vector_api_returns_structured_payload(db_connection, applied_schema, monkeypatch) -> None:
    _seed_spans(db_connection, applied_schema)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_registry")
    client = TestClient(app)
    response = client.get("/query/vector", params={"q": "空气质量标准"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] >= 1
    first = payload["chunks"][0]
    assert {"chunk_id", "span_ids", "page_no", "heading_path", "text_preview", "score"}.issubset(first.keys())
