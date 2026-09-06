"""Tests for CLI entry surface (P6 productionization slice).

Scope: Minimal unified CLI that wraps existing query() function.
This is the smallest external entry surface for formal runtime,
building on existing query/workflow/RetrievalTool/QueryAgent layers.

NO deployment, monitoring, or ops hardening.
NO retrieval logic rewrite - just thin CLI wrapper.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.entrypoints.types import QueryHit, QueryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_keyword_hit(text: str, score: float = 0.9) -> QueryHit:
    return QueryHit(
        text=text,
        score=score,
        metadata={
            "span_id": uuid.uuid4(),
            "doc_id": uuid.uuid4(),
            "version_id": uuid.uuid4(),
            "page_no": 1,
            "heading_path": "Section 1",
        },
    )


def _make_registry() -> MagicMock:
    reg = MagicMock()
    reg.query_spans_by_keyword.return_value = []
    return reg


def _make_driver() -> MagicMock:
    driver = MagicMock()
    session = MagicMock()
    session.run.return_value = MagicMock(data=lambda: [])
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=None)
    return driver


# ---------------------------------------------------------------------------
# Tests - CLI module exists and is importable
# ---------------------------------------------------------------------------


class TestCLIModuleBasics:
    """CLI module should exist and provide minimal entry surface."""

    def test_cli_module_exists(self) -> None:
        """CLI module should be importable from llamaindex_runtime.cli."""
        try:
            from llamaindex_runtime.cli import main
            assert main is not None
        except ImportError:
            pytest.fail("CLI module not found - this test should FAIL first")

    def test_cli_has_main_function(self) -> None:
        """CLI should expose a main() entry point."""
        try:
            from llamaindex_runtime.cli import main
            assert callable(main)
        except ImportError:
            pytest.fail("CLI main() not found - this test should FAIL first")


# ---------------------------------------------------------------------------
# Tests - CLI wraps existing query() function
# ---------------------------------------------------------------------------


class TestCLIQueryWrapping:
    """CLI should wrap existing query() without reimplementing logic."""

    @patch("llamaindex_runtime.cli.query")
    def test_cli_calls_query_function(self, mock_query) -> None:
        """CLI main() should delegate to existing query() function."""
        # Setup mock
        mock_result = QueryResult(
            mode="vector",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test query",
        )
        mock_query.return_value = mock_result

        try:
            from llamaindex_runtime.cli import main

            # Call CLI with minimal args
            _ = main(
                source_path="/tmp/test.pdf",
                query_text="test query",
                mode="vector",
                embed_model=MockEmbedding(embed_dim=32),
            )

            # Should have called query()
            mock_query.assert_called_once()

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_cli_preserves_query_modes(self, mock_vec, mock_tree) -> None:
        """CLI should support all existing query modes."""
        mock_vec.return_value = []
        mock_tree.return_value = []

        try:
            from llamaindex_runtime.cli import main

            embed_model = MockEmbedding(embed_dim=32)

            # Test vector mode
            result_vector = main(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="vector",
                embed_model=embed_model,
            )
            assert result_vector is not None

            # Test tree mode
            result_tree = main(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="tree",
                embed_model=embed_model,
            )
            assert result_tree is not None

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")


# ---------------------------------------------------------------------------
# Tests - CLI validates inputs
# ---------------------------------------------------------------------------


class TestCLIValidation:
    """CLI should validate inputs before calling query()."""

    def test_cli_requires_source_path(self) -> None:
        """CLI should require source_path parameter."""
        try:
            from llamaindex_runtime.cli import main

            with pytest.raises(ValueError, match="source_path"):
                main(
                    source_path=None,
                    query_text="test",
                    mode="vector",
                    embed_model=MockEmbedding(embed_dim=32),
                )

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")

    def test_cli_requires_query_text(self) -> None:
        """CLI should require query_text parameter."""
        try:
            from llamaindex_runtime.cli import main

            with pytest.raises(ValueError, match="query_text"):
                main(
                    source_path="/tmp/test.pdf",
                    query_text=None,
                    mode="vector",
                    embed_model=MockEmbedding(embed_dim=32),
                )

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")

    def test_cli_requires_mode(self) -> None:
        """CLI should require mode parameter."""
        try:
            from llamaindex_runtime.cli import main

            with pytest.raises(ValueError, match="mode"):
                main(
                    source_path="/tmp/test.pdf",
                    query_text="test",
                    mode=None,
                    embed_model=MockEmbedding(embed_dim=32),
                )

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")

    def test_cli_validates_mode_value(self) -> None:
        """CLI should validate mode is one of the allowed values."""
        try:
            from llamaindex_runtime.cli import main

            with pytest.raises(ValueError, match="mode"):
                main(
                    source_path="/tmp/test.pdf",
                    query_text="test",
                    mode="invalid_mode",
                    embed_model=MockEmbedding(embed_dim=32),
                )

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")


# ---------------------------------------------------------------------------
# Tests - CLI output format
# ---------------------------------------------------------------------------


class TestCLIOutputFormat:
    """CLI should return structured output (QueryResult or JSON)."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_cli_returns_query_result(self, mock_vec) -> None:
        """CLI should return QueryResult object."""
        mock_vec.return_value = []

        try:
            from llamaindex_runtime.cli import main

            result = main(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="vector",
                embed_model=MockEmbedding(embed_dim=32),
            )

            assert isinstance(result, QueryResult)

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_cli_can_output_json(self, mock_vec) -> None:
        """CLI should optionally output JSON format."""
        mock_vec.return_value = []

        try:
            from llamaindex_runtime.cli import main, format_result_as_json

            result = main(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="vector",
                embed_model=MockEmbedding(embed_dim=32),
            )

            json_str = format_result_as_json(result)
            assert isinstance(json_str, str)

            # Should be valid JSON
            parsed = json.loads(json_str)
            assert "mode" in parsed
            assert "hits" in parsed
            assert "source_path" in parsed
            assert "query" in parsed

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")


# ---------------------------------------------------------------------------
# Tests - CLI supports hybrid mode
# ---------------------------------------------------------------------------


class TestCLIHybridMode:
    """CLI should support hybrid mode with all paths."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_cli_hybrid_mode_calls_all_paths(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """CLI hybrid mode should invoke keyword, vector, and tree paths."""
        keyword_hit = _make_keyword_hit("test result", 0.9)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        try:
            from llamaindex_runtime.cli import main

            registry = _make_registry()

            result = main(
                source_path="/tmp/test.pdf",
                query_text="test",
                mode="hybrid",
                embed_model=MockEmbedding(embed_dim=32),
                registry=registry,
            )

            # Should be hybrid result
            assert result.mode == "hybrid"

            # Should have called all three paths
            mock_kw.assert_called_once()
            mock_vec.assert_called_once()
            mock_tree.assert_called_once()

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")


# ---------------------------------------------------------------------------
# Tests - CLI propagates vector_backend parameter
# ---------------------------------------------------------------------------


class TestCLIVectorBackendPropagation:
    """CLI should propagate vector_backend parameter to query()."""

    @patch("llamaindex_runtime.cli.query")
    def test_cli_accepts_vector_backend_parameter(self, mock_query) -> None:
        """CLI main() should accept vector_backend parameter."""
        # Setup mock
        mock_result = QueryResult(
            mode="vector",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test query",
        )
        mock_query.return_value = mock_result

        try:
            from llamaindex_runtime.cli import main

            # Create mock vector backend
            mock_backend = MagicMock()

            # Call CLI with vector_backend
            _ = main(
                source_path="/tmp/test.pdf",
                query_text="test query",
                mode="vector",
                embed_model=MockEmbedding(embed_dim=32),
                vector_backend=mock_backend,
            )

            # Should have called query() with vector_backend
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["vector_backend"] is mock_backend

        except (ImportError, TypeError) as e:
            pytest.fail(f"CLI not implemented or signature wrong: {e}")

    @patch("llamaindex_runtime.cli.query")
    def test_cli_works_without_vector_backend(self, mock_query) -> None:
        """CLI main() should still work when vector_backend is not provided."""
        # Setup mock
        mock_result = QueryResult(
            mode="vector",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test query",
        )
        mock_query.return_value = mock_result

        try:
            from llamaindex_runtime.cli import main

            # Call CLI without vector_backend
            _ = main(
                source_path="/tmp/test.pdf",
                query_text="test query",
                mode="vector",
                embed_model=MockEmbedding(embed_dim=32),
            )

            # Should have called query()
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            # vector_backend should be None when not provided
            assert call_kwargs.get("vector_backend") is None

        except ImportError:
            pytest.fail("CLI not implemented - this test should FAIL first")