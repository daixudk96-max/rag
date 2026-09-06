from __future__ import annotations

import uuid

from hybrid_path.orchestrator import hybrid_query
from registry import crud
from tree_path.generator import TreeGenerator
from tree_path.loader import TreeLoader
from vector_path.loader import load_version_chunks


def _seed_hybrid(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Hybrid Doc", source_uri="file:///hybrid.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="hybrid-v1", normalization_contract_id=contract_id, version_no=1)
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


def test_hybrid_query_basic(db_connection, applied_schema) -> None:
    version_id = _seed_hybrid(db_connection, applied_schema)
    result = hybrid_query(db_connection, "PM2.5 空气质量", version_id=version_id)
    assert result.total_hits >= 1
    assert result.evidence


def test_hybrid_query_empty(db_connection, applied_schema) -> None:
    version_id = _seed_hybrid(db_connection, applied_schema)
    result = hybrid_query(db_connection, "完全不存在的混合问题", version_id=version_id)
    assert result.decision in {"no_hits", "high_dispersion", "moderate", "high_concentration"}
