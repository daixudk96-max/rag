from __future__ import annotations

import uuid

from registry import crud, queries


def test_create_document(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///test.pdf", title="测试文档")
    assert doc_id
    with db_connection.cursor() as cur:
        cur.execute("SELECT title FROM documents WHERE doc_id = %s", (str(doc_id),))
        row = cur.fetchone()
    assert row[0] == "测试文档"


def test_create_normalization_contract(db_connection, applied_schema) -> None:
    contract_id = crud.create_normalization_contract(
        db_connection,
        parser_name="Docling",
        offset_basis="normalized_char_offset",
    )
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT offset_basis FROM normalization_contracts WHERE normalization_contract_id = %s",
            (str(contract_id),),
        )
        row = cur.fetchone()
    assert row[0] == "normalized_char_offset"


def test_create_version(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="abc123", normalization_contract_id=contract_id, version_no=1)
    with db_connection.cursor() as cur:
        cur.execute("SELECT status FROM document_versions WHERE version_id = %s", (str(version_id),))
        row = cur.fetchone()
    assert row[0] == "staging"


def test_activate_version(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    v1 = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    v2 = crud.create_version(db_connection, doc_id=doc_id, content_hash="h2", normalization_contract_id=contract_id, version_no=2)
    crud.activate_version(db_connection, v1)
    crud.activate_version(db_connection, v2)
    with db_connection.cursor() as cur:
        cur.execute("SELECT version_id, is_active FROM document_versions WHERE doc_id = %s ORDER BY version_no", (str(doc_id),))
        rows = cur.fetchall()
    assert rows[0][1] is False
    assert rows[1][1] is True


def test_write_and_query_spans(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    spans = [
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "A", "raw_text": "one"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 1, "heading_path": "A", "raw_text": "two"},
        {"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 21, "end_offset": 30, "page_no": 2, "heading_path": "B", "raw_text": "three"},
    ]
    crud.write_spans(db_connection, version_id, spans)
    assert len(queries.query_spans_by_version(db_connection, version_id)) == 3
    assert len(queries.query_spans_by_version(db_connection, version_id, page_no=1)) == 2


def test_write_chunks_and_spans_mapping(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    s1 = uuid.uuid4(); s2 = uuid.uuid4()
    crud.write_spans(db_connection, version_id, [
        {"span_id": s1, "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "A", "raw_text": "one"},
        {"span_id": s2, "span_kind": "paragraph", "start_offset": 11, "end_offset": 20, "page_no": 1, "heading_path": "A", "raw_text": "two"},
    ])
    chunk_id = crud.write_chunks(db_connection, version_id, [
        {"chunk_id": uuid.uuid4(), "chunk_type": "semantic_leaf", "chunk_order": 0, "token_count": 12, "text_preview": "one two", "page_no": 1, "heading_path": "A"}
    ])[0]
    crud.write_chunk_span_mappings(db_connection, [(chunk_id, s1, 0), (chunk_id, s2, 1)])
    span_ids = queries.get_chunk_span_ids(db_connection, chunk_id)
    assert span_ids == [s1, s2]


def test_full_registry_lifecycle(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    span_id = uuid.uuid4()
    crud.write_spans(db_connection, version_id, [{"span_id": span_id, "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 1, "heading_path": "A", "raw_text": "hello"}])
    chunk_id = crud.write_chunks(db_connection, version_id, [{"chunk_id": uuid.uuid4(), "chunk_type": "semantic_leaf", "chunk_order": 0, "token_count": 3, "text_preview": "hello", "page_no": 1, "heading_path": "A"}])[0]
    crud.write_chunk_span_mappings(db_connection, [(chunk_id, span_id, 0)])
    crud.activate_version(db_connection, version_id)
    active = queries.get_active_version(db_connection, doc_id)
    traced = queries.trace_chunk_to_document(db_connection, chunk_id)
    assert active["version_id"] == version_id
    assert traced["doc_id"] == doc_id
    assert traced["is_active"] is True


def test_version_no_overwrite(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    v1 = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    v2 = crud.create_version(db_connection, doc_id=doc_id, content_hash="h2", normalization_contract_id=contract_id, version_no=2)
    crud.write_spans(db_connection, v1, [{"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 5, "page_no": 1, "heading_path": "A", "raw_text": "v1"}])
    crud.write_spans(db_connection, v2, [{"span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 5, "page_no": 1, "heading_path": "A", "raw_text": "v2"}])
    spans_v1 = queries.query_spans_by_version(db_connection, v1)
    spans_v2 = queries.query_spans_by_version(db_connection, v2)
    assert spans_v1[0]["raw_text"] == "v1"
    assert spans_v2[0]["raw_text"] == "v2"


def test_trace_chunk_to_document(db_connection, applied_schema) -> None:
    doc_id = crud.create_document(db_connection, source_uri="file:///a.pdf", title="A")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="h1", normalization_contract_id=contract_id, version_no=1)
    span_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    crud.write_spans(db_connection, version_id, [{"span_id": span_id, "span_kind": "paragraph", "start_offset": 0, "end_offset": 10, "page_no": 3, "heading_path": "X", "raw_text": "hello"}])
    crud.write_chunks(db_connection, version_id, [{"chunk_id": chunk_id, "chunk_type": "semantic_leaf", "chunk_order": 0, "token_count": 3, "text_preview": "hello", "page_no": 3, "heading_path": "X"}])
    crud.write_chunk_span_mappings(db_connection, [(chunk_id, span_id, 0)])
    traced = queries.trace_chunk_to_document(db_connection, chunk_id)
    assert traced["doc_id"] == doc_id
    assert traced["version_id"] == version_id
    assert traced["page_no"] == 3
    assert traced["heading_path"] == "X"
