"""Tests for the query classifier / routing rule.

Phase 6 scope: classify_query returns 'keyword', 'vector', or 'tree'.
The classifier is a pure function with no external dependencies.
"""
from __future__ import annotations

import pytest

from llamaindex_runtime.entrypoints.classifier import classify_query


class TestClassifyQueryKeyword:
    """Short, code-like, or symbol-heavy queries route to keyword."""

    def test_exact_term_with_digits(self) -> None:
        assert classify_query("PM2.5") == "keyword"

    def test_standard_code_with_dash(self) -> None:
        assert classify_query("GB3095-2012") == "keyword"

    def test_short_keyword_with_symbol(self) -> None:
        assert classify_query("CCTV-1") == "keyword"

    def test_very_short_query(self) -> None:
        assert classify_query("SQL") == "keyword"

    def test_query_with_slash(self) -> None:
        assert classify_query("TCP/IP") == "keyword"

    def test_query_with_underscore(self) -> None:
        assert classify_query("my_variable") == "keyword"

    def test_query_with_period(self) -> None:
        assert classify_query("v1.2.3") == "keyword"


class TestClassifyQueryVector:
    """Long, natural-language queries route to vector."""

    def test_semantic_description(self) -> None:
        assert classify_query("What are the technical parameters of air quality monitoring equipment?") == "vector"

    def test_long_natural_language(self) -> None:
        assert classify_query("Explain the relationship between PM2.5 concentration and health outcomes") == "vector"

    def test_medium_natural_language(self) -> None:
        assert classify_query("describe the air quality monitoring system") == "vector"


class TestClassifyQueryTree:
    """Structural / hierarchical queries route to tree."""

    def test_heading_structure_query(self) -> None:
        assert classify_query("show section structure") == "tree"

    def test_outline_query(self) -> None:
        assert classify_query("document outline") == "tree"

    def test_toc_query(self) -> None:
        assert classify_query("table of contents") == "tree"

    def test_hierarchy_query(self) -> None:
        assert classify_query("chapter hierarchy") == "tree"


class TestClassifyQueryEdgeCases:
    """Edge cases for query classification."""

    def test_empty_query_defaults_to_vector(self) -> None:
        assert classify_query("") == "vector"

    def test_whitespace_only_defaults_to_vector(self) -> None:
        assert classify_query("   ") == "vector"

    def test_single_word_routes_to_keyword(self) -> None:
        assert classify_query("temperature") == "keyword"

    def test_two_word_short_routes_to_keyword(self) -> None:
        assert classify_query("air quality") == "keyword"

    def test_unicode_natural_language_routes_to_vector(self) -> None:
        assert classify_query("空气质量监测设备的技术参数") == "vector"

    def test_unicode_short_term_routes_to_keyword(self) -> None:
        assert classify_query("PM2.5") == "keyword"

    def test_returns_string(self) -> None:
        result = classify_query("test")
        assert isinstance(result, str)

    def test_return_value_in_valid_set(self) -> None:
        result = classify_query("any query at all")
        assert result in {"keyword", "vector", "tree"}
