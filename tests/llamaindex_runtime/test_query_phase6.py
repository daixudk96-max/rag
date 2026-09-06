"""Tests for the unified query entrypoint extended with keyword and auto modes.

Phase 6 scope: query() now supports mode="keyword" and mode="auto".
  - "keyword" requires registry parameter and calls retrieve_keyword_hits.
  - "auto" uses classify_query to choose between keyword, vector, tree.
  - QueryResult.mode Literal type now includes "keyword".
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query


# ---------------------------------------------------------------------------
# Helpers -- lightweight stand-ins for mocking
# ---------------------------------------------------------------------------


class _FakeTextNode:
    def __init__(self, text: str, metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata if metadata is not None else {}


class _FakeNodeWithScore:
    def __init__(self, text: str, score: float, metadata: dict | None = None) -> None:
        self.node = _FakeTextNode(text, metadata)
        self.score = score


def _make_node(text: str, score: float, metadata: dict | None = None) -> _FakeNodeWithScore:
    return _FakeNodeWithScore(text, score, metadata)


def _make_keyword_hit(text: str, score: float = 0.9) -> QueryHit:
    return QueryHit(text=text, score=score, metadata={"span_id": uuid.uuid4(), "doc_id": uuid.uuid4(), "version_id": uuid.uuid4()})


def _make_registry() -> MagicMock:
    reg = MagicMock()
    reg.query_spans_by_keyword.return_value = []
    return reg


# ---------------------------------------------------------------------------
# Unit tests -- keyword mode
# ---------------------------------------------------------------------------


class TestQueryKeywordMode:
    """query() with mode='keyword' delegates to retrieve_keyword_hits."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_calls_retrieve_keyword_hits(self, mock_kw) -> None:
        hit = _make_keyword_hit("PM2.5 indicator", 1.0)
        mock_kw.return_value = [hit]
        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="PM2.5",
            mode="keyword",
            registry=registry,
        )
        mock_kw.assert_called_once()
        assert result.mode == "keyword"
        assert len(result.hits) == 1
        assert result.hits[0].text == "PM2.5 indicator"
        assert result.hits[0].score == 1.0

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_passes_registry(self, mock_kw) -> None:
        mock_kw.return_value = []
        registry = _make_registry()
        query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry)
        _args, kwargs = mock_kw.call_args
        # registry is the first positional argument
        assert _args[0] is registry

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_passes_query_text(self, mock_kw) -> None:
        mock_kw.return_value = []
        registry = _make_registry()
        query(source_path="/tmp/test.pdf", query_text="GB3095", mode="keyword", registry=registry)
        _args, kwargs = mock_kw.call_args
        # query is the second positional argument
        assert _args[1] == "GB3095"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_passes_version_id(self, mock_kw) -> None:
        mock_kw.return_value = []
        registry = _make_registry()
        vid = uuid.uuid4()
        query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry, version_id=vid)
        _args, kwargs = mock_kw.call_args
        assert kwargs.get("version_id") == vid

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_passes_limit(self, mock_kw) -> None:
        mock_kw.return_value = []
        registry = _make_registry()
        query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry, limit=10)
        _args, kwargs = mock_kw.call_args
        assert kwargs.get("limit") == 10

    def test_keyword_mode_without_registry_raises(self) -> None:
        with pytest.raises(ValueError, match="registry"):
            query(
                source_path="/tmp/test.pdf",
                query_text="PM2.5",
                mode="keyword",
            )

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_result_is_frozen(self, mock_kw) -> None:
        mock_kw.return_value = [_make_keyword_hit("text", 0.5)]
        registry = _make_registry()
        result = query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry)
        with pytest.raises(AttributeError):
            result.mode = "vector"  # type: ignore[misc]

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_empty_hits(self, mock_kw) -> None:
        mock_kw.return_value = []
        registry = _make_registry()
        result = query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry)
        assert result.hits == ()
        assert isinstance(result.hits, tuple)


# ---------------------------------------------------------------------------
# Unit tests -- auto mode
# ---------------------------------------------------------------------------


class TestQueryAutoMode:
    """query() with mode='auto' uses classify_query to choose the backend."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.classify_query")
    def test_auto_routes_keyword_for_short_code(self, mock_classify, mock_kw) -> None:
        mock_classify.return_value = "keyword"
        mock_kw.return_value = [_make_keyword_hit("PM2.5", 1.0)]
        registry = _make_registry()
        result = query(
            source_path="/tmp/test.pdf",
            query_text="PM2.5",
            mode="auto",
            embed_model=MockEmbedding(embed_dim=32),
            registry=registry,
        )
        mock_classify.assert_called_once_with("PM2.5")
        assert result.mode == "keyword"
        mock_kw.assert_called_once()

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.classify_query")
    def test_auto_routes_vector_for_long_query(self, mock_classify, mock_vec) -> None:
        mock_classify.return_value = "vector"
        mock_vec.return_value = [_make_node("semantic result", 0.85)]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="explain the air quality monitoring system",
            mode="auto",
            embed_model=MockEmbedding(embed_dim=32),
        )
        mock_classify.assert_called_once()
        assert result.mode == "vector"
        mock_vec.assert_called_once()

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.classify_query")
    def test_auto_routes_tree_for_structural_query(self, mock_classify, mock_tree) -> None:
        mock_classify.return_value = "tree"
        mock_tree.return_value = [_make_node("section heading", 0.9)]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="document outline",
            mode="auto",
            embed_model=MockEmbedding(embed_dim=32),
        )
        mock_classify.assert_called_once()
        assert result.mode == "tree"
        mock_tree.assert_called_once()

    @patch("llamaindex_runtime.entrypoints._query.classify_query")
    def test_auto_keyword_without_registry_raises(self, mock_classify) -> None:
        mock_classify.return_value = "keyword"
        with pytest.raises(ValueError, match="registry"):
            query(
                source_path="/tmp/test.pdf",
                query_text="PM2.5",
                mode="auto",
                embed_model=MockEmbedding(embed_dim=32),
            )

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.classify_query")
    def test_auto_vector_without_registry_is_fine(self, mock_classify, mock_vec) -> None:
        mock_classify.return_value = "vector"
        mock_vec.return_value = []
        result = query(
            source_path="/tmp/test.pdf",
            query_text="explain the system",
            mode="auto",
            embed_model=MockEmbedding(embed_dim=32),
        )
        assert result.mode == "vector"


# ---------------------------------------------------------------------------
# Unit tests -- QueryResult.mode type
# ---------------------------------------------------------------------------


class TestQueryResultModeType:
    """QueryResult.mode now includes 'keyword' and 'auto' is not a valid mode for results."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_keyword_mode_in_result(self, mock_kw) -> None:
        mock_kw.return_value = [_make_keyword_hit("text", 0.5)]
        registry = _make_registry()
        result = query(source_path="/tmp/test.pdf", query_text="test", mode="keyword", registry=registry)
        assert result.mode == "keyword"

    def test_auto_is_not_a_valid_result_mode(self) -> None:
        """'auto' is a routing directive, not a result mode. Results always have a concrete mode."""
        with pytest.raises(ValueError):
            QueryResult(mode="auto", hits=(), source_path="/tmp/test.pdf", query="test")


# ---------------------------------------------------------------------------
# Unit tests -- existing modes still work
# ---------------------------------------------------------------------------


class TestQueryExistingModesStillWork:
    """Adding keyword/auto must not break existing vector and tree modes."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_still_works(self, mock_vector) -> None:
        mock_vector.return_value = [_make_node("vec", 0.9)]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find me",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        assert result.mode == "vector"
        assert len(result.hits) == 1

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_tree_mode_still_works(self, mock_tree) -> None:
        mock_tree.return_value = [_make_node("tree", 0.85)]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="merge me",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
        )
        assert result.mode == "tree"
        assert len(result.hits) == 1
