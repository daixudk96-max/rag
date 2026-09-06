"""Tests for the keyword retrieval path over persisted canonical spans.

Phase 6 scope: keyword search via RegistryWriter.query_spans_by_keyword,
mapped to QueryHit objects through retrieve_keyword_hits().
"""
from __future__ import annotations

import uuid
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.entrypoints import QueryHit
from llamaindex_runtime.keyword import retrieve_keyword_hits


# ---------------------------------------------------------------------------
# Helpers -- fake registry rows matching query_spans_by_keyword contract
# ---------------------------------------------------------------------------


def _make_span_row(
    *,
    raw_text: str = "sample text",
    match_score: float = 0.9,
    page_no: int | None = 1,
    heading_path: str | None = "Intro",
    version_id: uuid.UUID | None = None,
) -> dict:
    """Build a dict matching the query_spans_by_keyword return shape."""
    return {
        "span_id": uuid.uuid4(),
        "doc_id": uuid.uuid4(),
        "version_id": version_id or uuid.uuid4(),
        "page_no": page_no,
        "heading_path": heading_path,
        "raw_text": raw_text,
        "match_score": match_score,
    }


def _make_registry(rows: list[dict] | None = None) -> MagicMock:
    """Build a mock RegistryWriter with query_spans_by_keyword."""
    reg = MagicMock()
    reg.query_spans_by_keyword.return_value = rows or []
    return reg


# ---------------------------------------------------------------------------
# Unit tests -- retrieve_keyword_hits
# ---------------------------------------------------------------------------


class TestRetrieveKeywordHitsBasic:
    """retrieve_keyword_hits returns QueryHit objects from registry results."""

    def test_returns_list_of_query_hits(self) -> None:
        rows = [
            _make_span_row(raw_text="PM2.5 is an indicator", match_score=1.0),
            _make_span_row(raw_text="GB3095-2012 standard", match_score=0.8),
        ]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "PM2.5")
        assert len(hits) == 2
        assert all(isinstance(h, QueryHit) for h in hits)

    def test_hit_text_comes_from_raw_text(self) -> None:
        rows = [_make_span_row(raw_text="matched span content")]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "matched")
        assert hits[0].text == "matched span content"

    def test_hit_score_comes_from_match_score(self) -> None:
        rows = [_make_span_row(match_score=0.75)]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "query")
        assert hits[0].score == 0.75

    def test_hit_metadata_contains_provenance(self) -> None:
        version_id = uuid.uuid4()
        rows = [_make_span_row(version_id=version_id, page_no=3, heading_path="Section > Sub")]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "query")
        meta = hits[0].metadata
        assert "span_id" in meta
        assert "doc_id" in meta
        assert "version_id" in meta
        assert meta["page_no"] == 3
        assert meta["heading_path"] == "Section > Sub"

    def test_metadata_is_immutable(self) -> None:
        rows = [_make_span_row()]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "query")
        assert isinstance(hits[0].metadata, MappingProxyType)

    def test_empty_results_returns_empty_list(self) -> None:
        registry = _make_registry([])
        hits = retrieve_keyword_hits(registry, "nonexistent")
        assert hits == []


class TestRetrieveKeywordHitsRegistryCall:
    """retrieve_keyword_hits passes correct parameters to the registry."""

    def test_calls_query_spans_by_keyword(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "test query")
        registry.query_spans_by_keyword.assert_called_once()

    def test_passes_query_text(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "PM2.5")
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs["query"] == "PM2.5"

    def test_default_limit_is_50(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "test")
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs["limit"] == 50

    def test_custom_limit_passed_through(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "test", limit=10)
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs["limit"] == 10

    def test_version_id_passed_when_provided(self) -> None:
        registry = _make_registry([])
        vid = uuid.uuid4()
        retrieve_keyword_hits(registry, "test", version_id=vid)
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs["version_id"] == vid

    def test_version_id_not_passed_when_omitted(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "test")
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs.get("version_id") is None


class TestRetrieveKeywordHitsInputValidation:
    """retrieve_keyword_hits rejects invalid inputs."""

    def test_empty_query_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(ValueError, match="query"):
            retrieve_keyword_hits(registry, "")

    def test_whitespace_only_query_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(ValueError, match="query"):
            retrieve_keyword_hits(registry, "   ")

    def test_zero_limit_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(ValueError, match="limit"):
            retrieve_keyword_hits(registry, "test", limit=0)

    def test_negative_limit_raises(self) -> None:
        registry = _make_registry()
        with pytest.raises(ValueError, match="limit"):
            retrieve_keyword_hits(registry, "test", limit=-1)


class TestRetrieveKeywordHitsEdgeCases:
    """Edge cases for keyword retrieval."""

    def test_query_stripped_before_use(self) -> None:
        registry = _make_registry([])
        retrieve_keyword_hits(registry, "  PM2.5  ")
        _args, kwargs = registry.query_spans_by_keyword.call_args
        assert kwargs["query"] == "PM2.5"

    def test_unicode_query_accepted(self) -> None:
        registry = _make_registry([])
        hits = retrieve_keyword_hits(registry, "空气质量")
        assert isinstance(hits, list)

    def test_special_characters_query_accepted(self) -> None:
        registry = _make_registry([])
        hits = retrieve_keyword_hits(registry, "GB3095-2012")
        assert isinstance(hits, list)

    def test_hit_with_none_score(self) -> None:
        rows = [_make_span_row(match_score=0.0)]
        rows[0]["match_score"] = None
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "test")
        assert hits[0].score is None

    def test_hit_with_none_page_no(self) -> None:
        rows = [_make_span_row(page_no=None)]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "test")
        assert hits[0].metadata["page_no"] is None

    def test_hit_with_none_heading_path(self) -> None:
        rows = [_make_span_row(heading_path=None)]
        registry = _make_registry(rows)
        hits = retrieve_keyword_hits(registry, "test")
        assert hits[0].metadata["heading_path"] is None
