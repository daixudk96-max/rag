from __future__ import annotations

import uuid

from registry import crud
from tree_path.generator import TreeGenerator
from tree_path.loader import TreeLoader
from tree_path.query import rollup_to_parent
from vector_path.loader import load_version_chunks


def test_tree_alignment_with_vector_chunks(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, title="Tree Integration Doc", source_uri="file:///tree-int.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="tree-int-v1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "第一章 > 1.1 背景", "raw_text": "背景一。"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 2, "heading_path": "第一章 > 1.2 方法", "raw_text": "方法一。"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    load_version_chunks(db_connection, version_id)
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    TreeLoader().load(db_connection, generated, attach_leaf_node_ids=True)
    with db_connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vector_chunks WHERE version_id = %s AND node_id IS NOT NULL", (str(version_id),))
        count = cur.fetchone()[0]
    assert count >= 1
