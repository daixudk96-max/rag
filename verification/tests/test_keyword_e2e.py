from __future__ import annotations

import json
from pathlib import Path

from registry import crud
from keyword_path.search import search_by_keyword

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TERMS = ROOT / "tests" / "fixtures" / "sample_terms.json"


def _seed_keyword_data(db_connection, applied_schema):
    doc_id = crud.create_document(db_connection, title="Keyword Doc", source_uri="file:///keyword.pdf")
    contract_id = crud.create_normalization_contract(db_connection, "Docling", parser_version="1.0", offset_basis="normalized_char_offset")
    version_id = crud.create_version(db_connection, doc_id=doc_id, content_hash="kw-v1", normalization_contract_id=contract_id, version_no=1)
    crud.write_spans(
        db_connection,
        version_id,
        [
            {"span_id": __import__('uuid').uuid4(), "span_kind": "paragraph", "start_offset": 0, "end_offset": 20, "page_no": 1, "heading_path": "环境 > 指标", "raw_text": "PM2.5 是空气质量指标。"},
            {"span_id": __import__('uuid').uuid4(), "span_kind": "paragraph", "start_offset": 21, "end_offset": 60, "page_no": 2, "heading_path": "标准 > 国标", "raw_text": "GB3095-2012 是环境空气质量标准。"},
            {"span_id": __import__('uuid').uuid4(), "span_kind": "paragraph", "start_offset": 61, "end_offset": 90, "page_no": 3, "heading_path": "媒体 > 频道", "raw_text": "CCTV-1 是中央电视台综合频道。"}
        ],
    )
    crud.activate_version(db_connection, version_id)


def test_keyword_samples(db_connection, applied_schema) -> None:
    _seed_keyword_data(db_connection, applied_schema)
    samples = json.loads(SAMPLE_TERMS.read_text(encoding="utf-8"))
    for term in samples["exact_terms"] + samples["phrases"] + samples["prefixes"]:
        result = search_by_keyword(db_connection, term)
        assert result["total_hits"] >= 1, term
        assert result["evidence"][0]["heading_path"]
