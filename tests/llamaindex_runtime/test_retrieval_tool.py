"""Tests for RetrievalTool direct query delegation.

Scope: Minimal tool-facing orchestration that delegates to the query() entrypoint
with mode='hybrid' while preserving ToolOutput behavior for agent use.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.tools import BaseTool

from llamaindex_runtime.entrypoints.types import QueryHit
from llamaindex_runtime.vector.backend import VectorBackend


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


def _make_vector_backend() -> MagicMock:
    backend = MagicMock(spec=VectorBackend)
    backend.search.return_value = []
    return backend


# ---------------------------------------------------------------------------
# Tests - RetrievalTool exists and has correct interface
# ---------------------------------------------------------------------------


class TestRetrievalToolBasics:
    """RetrievalTool should be a valid LlamaIndex BaseTool."""

    def test_retrieval_tool_class_exists(self) -> None:
        """RetrievalTool should be importable."""
        from llamaindex_runtime.agent import RetrievalTool

        assert RetrievalTool is not None

    def test_retrieval_tool_is_a_base_tool(self) -> None:
        """RetrievalTool should inherit from llama_index.core.tools.BaseTool."""
        from llamaindex_runtime.agent import RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        assert isinstance(tool, BaseTool)

    def test_retrieval_tool_has_metadata(self) -> None:
        """RetrievalTool should have name and description."""
        from llamaindex_runtime.agent import RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # BaseTool requires metadata with name and description
        assert hasattr(tool, "metadata")
        assert hasattr(tool.metadata, "name")
        assert hasattr(tool.metadata, "description")
        assert tool.metadata.name is not None
        assert tool.metadata.description is not None

    def test_retrieval_tool_has_call_method(self) -> None:
        """RetrievalTool should be callable."""
        from llamaindex_runtime.agent import RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # BaseTool should be callable via __call__
        assert callable(tool)


# ---------------------------------------------------------------------------
# Tests - RetrievalTool wraps HybridRetrievalWorkflow
# ---------------------------------------------------------------------------


class TestRetrievalToolDelegation:
    """RetrievalTool should delegate directly to query() entrypoint."""

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_delegates_to_query_function(self, mock_query) -> None:
        """Tool should call query() entrypoint directly with mode='hybrid'."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryResult

        # Setup mock query to return a QueryResult
        mock_result = QueryResult(
            mode="hybrid",
            hits=(),
            source_path="/tmp/test.pdf",
            query="PM2.5",
        )
        mock_query.return_value = mock_result

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # Call the tool
        _ = await tool.acall(query="PM2.5")

        # Verify query() was called with mode='hybrid'
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["mode"] == "hybrid"
        assert call_kwargs["query_text"] == "PM2.5"
        assert call_kwargs["source_path"] == "/tmp/test.pdf"

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_does_not_instantiate_workflow(self, mock_query) -> None:
        """Tool should not import or use HybridRetrievalWorkflow."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryResult

        mock_result = QueryResult(
            mode="hybrid",
            hits=(),
            source_path="/tmp/test.pdf",
            query="air quality",
        )
        mock_query.return_value = mock_result

        import llamaindex_runtime.agent.retrieval_tool as tool_module

        assert not hasattr(tool_module, "HybridRetrievalWorkflow")

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        _ = await tool.acall(query="air quality")

        mock_query.assert_called_once()

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_passes_all_parameters_to_query(self, mock_query) -> None:
        """Tool should pass all constructor parameters to query()."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryResult
        import uuid

        mock_result = QueryResult(
            mode="hybrid",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test query",
        )
        mock_query.return_value = mock_result

        test_version_id = uuid.uuid4()

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
            similarity_top_k=10,
            version_id=test_version_id,
            limit=20,
        )

        _ = await tool.acall(query="test query")

        # Verify all parameters passed correctly
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["source_path"] == "/tmp/test.pdf"
        assert call_kwargs["query_text"] == "test query"
        assert call_kwargs["mode"] == "hybrid"
        assert call_kwargs["similarity_top_k"] == 10
        assert call_kwargs["version_id"] == test_version_id
        assert call_kwargs["limit"] == 20
        # registry and embed_model should be passed
        assert "registry" in call_kwargs
        assert "embed_model" in call_kwargs

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_call_returns_tool_output(self, mock_query) -> None:
        """Tool call should return ToolOutput with QueryResult content."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryHit, QueryResult

        keyword_hit = QueryHit(
            text="PM2.5 indicator",
            score=1.0,
            metadata={
                "span_id": uuid.uuid4(),
                "doc_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "page_no": 1,
                "heading_path": "Section 1",
            },
        )
        mock_result = QueryResult(
            mode="hybrid",
            hits=(keyword_hit,),
            source_path="/tmp/test.pdf",
            query="PM2.5",
        )
        mock_query.return_value = mock_result

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # Call the tool with a query
        output = await tool.acall(query="PM2.5")

        # Should return ToolOutput (from BaseTool interface)
        from llama_index.core.tools import ToolOutput

        assert isinstance(output, ToolOutput)
        assert output.content is not None

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_output_contains_query_result(self, mock_query) -> None:
        """Tool output should contain QueryResult data."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryHit, QueryResult

        keyword_hit = QueryHit(
            text="air quality",
            score=0.9,
            metadata={
                "span_id": uuid.uuid4(),
                "doc_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "page_no": 1,
                "heading_path": "Section 1",
            },
        )
        mock_result = QueryResult(
            mode="hybrid",
            hits=(keyword_hit,),
            source_path="/tmp/test.pdf",
            query="air quality",
        )
        mock_query.return_value = mock_result

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        output = await tool.acall(query="air quality")

        # Content should represent QueryResult data
        # The tool should serialize the QueryResult for agent consumption
        assert output.content is not None
        # Verify it's not empty
        assert len(str(output.content)) > 0


# ---------------------------------------------------------------------------
# Tests - RetrievalTool validates parameters
# ---------------------------------------------------------------------------


class TestRetrievalToolValidation:
    """RetrievalTool should validate required parameters."""

    def test_tool_requires_registry(self) -> None:
        """Tool should require registry for hybrid retrieval."""
        from llamaindex_runtime.agent import RetrievalTool

        with pytest.raises(ValueError, match="registry"):
            RetrievalTool(
                source_path="/tmp/test.pdf",
                registry=None,
                embed_model=MockEmbedding(embed_dim=32),
            )

    def test_tool_requires_embed_model(self) -> None:
        """Tool should require embed_model for vector/tree paths."""
        from llamaindex_runtime.agent import RetrievalTool

        with pytest.raises(ValueError, match="embed_model"):
            RetrievalTool(
                source_path="/tmp/test.pdf",
                registry=_make_registry(),
                embed_model=None,
            )

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_call_validates_query(self, mock_query) -> None:
        """Tool call should validate query is not empty."""
        from llamaindex_runtime.agent import RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        with pytest.raises(ValueError, match="query"):
            await tool.acall(query="")


class TestRetrievalToolVectorBackendPropagation:
    """RetrievalTool should accept and pass vector_backend to query()."""

    def test_tool_accepts_vector_backend_parameter(self) -> None:
        """RetrievalTool constructor should accept vector_backend."""
        from llamaindex_runtime.agent import RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
            vector_backend=_make_vector_backend(),  # protocol-compatible backend
        )

        assert tool is not None
        assert hasattr(tool, "_vector_backend")

    def test_tool_rejects_invalid_vector_backend(self) -> None:
        """RetrievalTool should reject objects that do not implement VectorBackend."""
        from llamaindex_runtime.agent import RetrievalTool

        with pytest.raises(ValueError, match="vector_backend"):
            RetrievalTool(
                source_path="/tmp/test.pdf",
                registry=_make_registry(),
                embed_model=MockEmbedding(embed_dim=32),
                vector_backend=object(),
            )

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.agent.retrieval_tool.query_entrypoint")
    async def test_tool_passes_vector_backend_to_query(self, mock_query) -> None:
        """RetrievalTool should pass vector_backend to query() entrypoint."""
        from llamaindex_runtime.agent import RetrievalTool
        from llamaindex_runtime.entrypoints.types import QueryResult
        import uuid

        mock_result = QueryResult(
            mode="hybrid",
            hits=(),
            source_path="/tmp/test.pdf",
            query="test query",
        )
        mock_query.return_value = mock_result

        test_version_id = uuid.uuid4()
        test_backend = _make_vector_backend()

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
            version_id=test_version_id,
            vector_backend=test_backend,
        )

        _ = await tool.acall(query="test query")

        # Verify vector_backend was passed to query()
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["vector_backend"] is test_backend
        assert call_kwargs["version_id"] == test_version_id
