from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from api.routes import app
from registry import crud
from tree_path.generator import TreeGenerator
from tree_path.loader import TreeLoader
from vector_path.loader import load_version_chunks


def _seed_hybrid(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Rerank Doc", source_uri="file:///rerank.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="rerank-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 20, "page_no": 1, "heading_path": "环境 > 指标", "raw_text": "PM2.5 是空气质量指标。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 21, "end_offset": 50, "page_no": 2, "heading_path": "监测 > 说明", "raw_text": "空气质量监测设备需要稳定运行。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    crud.activate_version(db_connection, version_id)
    load_version_chunks(db_connection, version_id)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    TreeLoader().load(db_connection, generated, attach_leaf_node_ids=True)
    return version_id


def test_hybrid_api_returns_reranked_evidence(db_connection, applied_schema, monkeypatch) -> None:
    version_id = _seed_hybrid(db_connection, applied_schema)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_registry")
    client = TestClient(app)
    response = client.post("/query/hybrid", json={"query": "PM2.5 空气质量", "version_id": str(version_id), "top_k": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]
    assert "rerank_score" in payload["evidence"][0]
