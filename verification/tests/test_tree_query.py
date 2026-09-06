from __future__ import annotations

import uuid

from registry import crud
from tree_path.generator import TreeGenerator
from tree_path.loader import TreeLoader
from tree_path.query import rollup_to_parent


def _seed_loaded_tree(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Tree Doc", source_uri="file:///tree.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="tree-query-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景一。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景二。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    TreeLoader().load(db_connection, generated)
    leaf = [n for n in generated["nodes"] if n["node_type"] == "section"][-1]
    return leaf["node_id"]


def test_leaf_hit_rollup(db_connection, applied_schema) -> None:
    leaf_node_id = _seed_loaded_tree(db_connection, applied_schema)
    parent = rollup_to_parent(db_connection, leaf_node_id)
    assert parent is not None
    assert parent["heading_path"]
