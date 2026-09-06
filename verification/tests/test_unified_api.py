from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from api.routes import app
from registry import crud
from vector_path.loader import load_version_chunks


def _seed_all(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Unified Doc", source_uri="file:///unified.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="unified-v1", normalization_contract_id=contract_id, version_no=1)
    crud.write_spans(
        db_connection,
        version_id,
        [
            {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 20, "page_no": 1, "heading_path": "环境 > 指标", "raw_text": "PM2.5 是空气质量指标。"},
            {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 21, "end_offset": 50, "page_no": 2, "heading_path": "监测 > 说明", "raw_text": "空气质量监测设备需要稳定运行。"}
        ],
    )
    crud.activate_version(db_connection, version_id)
    load_version_chunks(db_connection, version_id)


def test_unified_query_routes_keyword(db_connection, applied_schema, monkeypatch) -> None:
    _seed_all(db_connection, applied_schema)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_registry")
    client = TestClient(app)
    response = client.post("/query", json={"query": "PM2.5"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "keyword"
    assert payload["evidence"]


def test_unified_query_routes_vector(db_connection, applied_schema, monkeypatch) -> None:
    _seed_all(db_connection, applied_schema)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_registry")
    client = TestClient(app)
    response = client.post("/query", json={"query": "空气质量监测设备的技术参数"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "vector"
    assert payload["evidence"]
