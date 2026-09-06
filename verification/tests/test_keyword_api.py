from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from api.routes import app
from registry import crud


def _seed_keyword_data(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Keyword Doc", source_uri="file:///keyword.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="kw-api-v1", normalization_contract_id=contract_id, version_no=1)
    crud.write_spans(
        db_connection,
        version_id,
        [
            {
                "span_id": uuid.uuid4(),
                "span_kind": "paragraph",
                "start_offset": 0,
                "end_offset": 20,
                "page_no": 1,
                "heading_path": "环境 > 指标",
                "raw_text": "PM2.5 是空气质量指标。",
            }
        ],
    )
    crud.activate_version(db_connection, version_id)


def test_keyword_api_returns_structured_payload(db_connection, applied_schema, monkeypatch) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_registry")
    client = TestClient(app)
    response = client.get("/query/keyword", params={"q": "PM2.5"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] >= 1
    first = payload["evidence"][0]
    assert {"span_id", "doc_id", "version_id", "page_no", "heading_path", "raw_text", "match_score"}.issubset(first.keys())
