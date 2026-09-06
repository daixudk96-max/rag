from __future__ import annotations

import uuid

from registry import crud
from tree_path.generator import TreeGenerator
from tree_path.loader import TreeLoader


def _seed_spans(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Tree Doc", source_uri="file:///tree.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="tree-load-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景一。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 2, "heading_path": "第一章 > 1.2 方法", "raw_text": "方法一。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    return version_id, spans


def test_load_tree_nodes(db_connection, applied_schema) -> None:
    version_id, spans = _seed_spans(db_connection, applied_schema)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    written = TreeLoader().load(db_connection, generated)
    assert written["node_count"] >= 1
    with db_connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s", (str(version_id),))
        count = cur.fetchone()[0]
    assert count >= 1
