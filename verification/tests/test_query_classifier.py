from __future__ import annotations

from query_classifier import classify_query


def test_exact_term_routes_to_keyword() -> None:
    assert classify_query("PM2.5") == "keyword"


def test_standard_code_routes_to_keyword() -> None:
    assert classify_query("GB3095-2012") == "keyword"


def test_short_keyword_phrase_routes_to_keyword() -> None:
    assert classify_query("CCTV-1") == "keyword"


def test_semantic_description_routes_to_vector() -> None:
    assert classify_query("空气质量监测设备的技术参数") == "vector"
