from __future__ import annotations

import uuid

from unified_output import UnifiedQueryResult, from_keyword_result, from_vector_result


def test_unified_result_shape() -> None:
    result = UnifiedQueryResult(route="keyword", answer="x", evidence=[])
    assert result.route == "keyword"
    assert result.answer == "x"


def test_from_keyword_result() -> None:
    raw = {
        "query": "PM2.5",
        "total_hits": 1,
        "evidence": [
            {
                "span_id": uuid.uuid4(),
                "doc_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "page_no": 1,
                "heading_path": "环境 > 指标",
                "raw_text": "PM2.5 是空气质量指标。",
                "match_score": 1.0,
            }
        ],
    }
    result = from_keyword_result(raw)
    assert result.route == "keyword"
    assert result.evidence[0]["span_id"]


def test_from_vector_result() -> None:
    raw = {
        "query": "空气质量标准",
        "total_hits": 1,
        "chunks": [
            {
                "chunk_id": uuid.uuid4(),
                "span_ids": [uuid.uuid4()],
                "page_no": 2,
                "heading_path": "标准 > 国标",
                "text_preview": "GB3095-2012 是环境空气质量标准。",
                "score": 0.8,
            }
        ],
    }
    result = from_vector_result(raw)
    assert result.route == "vector"
    assert result.evidence[0]["chunk_id"]
