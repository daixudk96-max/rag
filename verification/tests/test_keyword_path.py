from __future__ import annotations

import uuid

from registry import crud
from keyword_path.search import search_by_keyword


def _seed_keyword_data(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Keyword Doc", source_uri="file:///keyword.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="kw-v1", normalization_contract_id=contract_id, version_no=1)
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
            },
            {
                "span_id": uuid.uuid4(),
                "span_kind": "paragraph",
                "start_offset": 21,
                "end_offset": 60,
                "page_no": 2,
                "heading_path": "标准 > 国标",
                "raw_text": "GB3095-2012 是环境空气质量标准。",
            },
            {
                "span_id": uuid.uuid4(),
                "span_kind": "paragraph",
                "start_offset": 61,
                "end_offset": 90,
                "page_no": 3,
                "heading_path": "媒体 > 频道",
                "raw_text": "CCTV-1 是中央电视台综合频道。",
            },
        ],
    )
    crud.activate_version(db_connection, version_id)
    return doc_id, version_id


def test_exact_term_match(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    result = search_by_keyword(db_connection, "PM2.5")
    assert result["total_hits"] >= 1


def test_phrase_match(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    result = search_by_keyword(db_connection, "空气质量标准")
    assert result["total_hits"] >= 1


def test_prefix_match(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    result = search_by_keyword(db_connection, "GB")
    assert result["total_hits"] >= 1


def test_case_insensitive(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    result = search_by_keyword(db_connection, "pm2.5")
    assert result["total_hits"] >= 1


def test_active_version_filter(db_connection, applied_schema) -> None:
    doc_id, version_id = _seed_keyword_data(db_connection, applied_schema)
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    v2 = crud.create_version(db_connection, doc_id=doc_id, content_hash="kw-v2", normalization_contract_id=contract_id, version_no=2)
    crud.write_spans(db_connection, v2, [{
        "span_id": uuid.uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 12, "page_no": 9, "heading_path": "新版本", "raw_text": "新版 PM2.5"
    }])
    result = search_by_keyword(db_connection, "新版")
    assert result["total_hits"] == 0
    result2 = search_by_keyword(db_connection, "新版", version_id=v2)
    assert result2["total_hits"] == 1


def test_result_fields(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    result = search_by_keyword(db_connection, "CCTV-1")
    first = result["evidence"][0]
    assert {"span_id", "doc_id", "version_id", "page_no", "heading_path", "raw_text", "match_score"}.issubset(first.keys())
