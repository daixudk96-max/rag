from __future__ import annotations

import uuid

from registry import crud
from tree_path.generator import TreeGenerator


def _seed_spans(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Tree Doc", source_uri="file:///tree.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="tree-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景一。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景二。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 21, "end_offset": 30, "page_no": 2, "heading_path": "第一章 > 1.2 方法", "raw_text": "方法一。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    return version_id, spans


def test_generate_tree_nodes_from_heading_path(db_connection, applied_schema) -> None:
    version_id, spans = _seed_spans(db_connection, applied_schema)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    assert generated["nodes"]
    assert generated["node_spans"]


def test_parent_child_relation(db_connection, applied_schema) -> None:
    version_id, spans = _seed_spans(db_connection, applied_schema)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    child_nodes = [n for n in generated["nodes"] if n["parent_node_id"] is not None]
    assert child_nodes


def test_tree_nodes_cover_spans(db_connection, applied_schema) -> None:
    version_id, spans = _seed_spans(db_connection, applied_schema)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    covered = {link["span_id"] for link in generated["node_spans"]}
    assert covered.issuperset({s["span_id"] for s in spans})
