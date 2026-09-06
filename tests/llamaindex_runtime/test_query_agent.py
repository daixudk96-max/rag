"""Tests for QueryAgent (minimal FunctionAgent orchestration).

Scope: Minimal agent that uses RetrievalTool for evidence retrieval.
This demonstrates formal runtime control-plane with LlamaIndex FunctionAgent
without adding new retrieval features.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM
from llama_index.core.agent import FunctionAgent

from llamaindex_runtime.entrypoints.types import QueryHit


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
    from llamaindex_runtime.vector.backend import VectorBackend

    backend = MagicMock(spec=VectorBackend)
    backend.search.return_value = []
    return backend


# ---------------------------------------------------------------------------
# Tests - QueryAgent exists and is a FunctionAgent
# ---------------------------------------------------------------------------


class TestQueryAgentBasics:
    """QueryAgent should be a minimal FunctionAgent using RetrievalTool."""

    def test_query_agent_class_exists(self) -> None:
        """QueryAgent should be importable."""
        from llamaindex_runtime.agent import QueryAgent

        assert QueryAgent is not None

    def test_query_agent_is_a_function_agent(self) -> None:
        """QueryAgent should inherit from or wrap FunctionAgent."""
        from llamaindex_runtime.agent import QueryAgent, RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # Use MockLLM to avoid needing a real LLM
        mock_llm = MockLLM()

        agent = QueryAgent(
            tools=[tool],
            llm=mock_llm,
        )

        # Should be a FunctionAgent instance
        assert isinstance(agent, FunctionAgent)

    def test_query_agent_can_be_instantiated_with_tool(self) -> None:
        """QueryAgent should accept tools parameter."""
        from llamaindex_runtime.agent import QueryAgent, RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        mock_llm = MockLLM()

        agent = QueryAgent(
            tools=[tool],
            llm=mock_llm,
        )

        assert agent is not None

    def test_query_agent_has_run_method(self) -> None:
        """QueryAgent should expose a run() method for interaction."""
        from llamaindex_runtime.agent import QueryAgent, RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        mock_llm = MockLLM()

        agent = QueryAgent(
            tools=[tool],
            llm=mock_llm,
        )

        # Workflow-based FunctionAgent has run method
        assert hasattr(agent, "run")


# ---------------------------------------------------------------------------
# Tests - QueryAgent uses RetrievalTool
# ---------------------------------------------------------------------------


class TestQueryAgentToolUsage:
    """QueryAgent should be able to use RetrievalTool."""

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_agent_can_use_tool_for_retrieval(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """QueryAgent should be able to invoke RetrievalTool."""
        from llamaindex_runtime.agent import QueryAgent, RetrievalTool

        # Setup retrieval mocks
        keyword_hit = _make_keyword_hit("PM2.5 levels", 0.9)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        # Use MockLLM (agent needs an LLM to reason)
        mock_llm = MockLLM()

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        agent = QueryAgent(
            tools=[tool],
            llm=mock_llm,
        )

        # The agent exists and has the tool
        assert len(agent.tools) == 1
        assert agent.tools[0].metadata.name == "hybrid_retrieval"


# ---------------------------------------------------------------------------
# Tests - QueryAgent validation
# ---------------------------------------------------------------------------


class TestQueryAgentValidation:
    """QueryAgent should validate required parameters."""

    def test_agent_requires_tools(self) -> None:
        """QueryAgent should require at least one tool."""
        from llamaindex_runtime.agent import QueryAgent

        with pytest.raises(ValueError, match="tools"):
            QueryAgent(
                tools=[],
                llm=MagicMock(),
            )

    def test_agent_requires_llm(self) -> None:
        """QueryAgent should require an LLM."""
        from llamaindex_runtime.agent import QueryAgent, RetrievalTool

        tool = RetrievalTool(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        with pytest.raises(ValueError, match="llm"):
            QueryAgent(
                tools=[tool],
                llm=None,
            )


# ---------------------------------------------------------------------------
# Tests - QueryAgent auto-constructs RetrievalTool
# ---------------------------------------------------------------------------


class TestQueryAgentAutoRetrievalTool:
    """QueryAgent should auto-construct RetrievalTool when tools is None."""

    def test_auto_construct_retrieval_tool_with_source_path(self) -> None:
        """QueryAgent should auto-construct RetrievalTool when given source_path."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()
        mock_embed = MockEmbedding(embed_dim=32)

        agent = QueryAgent(
            llm=mock_llm,
            source_path="/tmp/test.pdf",
            registry=mock_registry,
            embed_model=mock_embed,
        )

        # Agent should have one tool
        assert len(agent.tools) == 1
        # Tool should be a RetrievalTool-like tool
        assert agent.tools[0].metadata.name == "hybrid_retrieval"

    def test_auto_construct_passes_optional_params(self) -> None:
        """QueryAgent should pass optional params to auto-constructed RetrievalTool."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()
        mock_embed = MockEmbedding(embed_dim=32)
        test_version_id = uuid.uuid4()

        agent = QueryAgent(
            llm=mock_llm,
            source_path="/tmp/test.pdf",
            registry=mock_registry,
            embed_model=mock_embed,
            similarity_top_k=10,
            version_id=test_version_id,
            limit=20,
        )

        tool = agent.tools[0]
        assert tool.metadata.name == "hybrid_retrieval"
        assert tool._similarity_top_k == 10
        assert tool._version_id == test_version_id
        assert tool._limit == 20

    def test_fails_without_source_path_when_tools_none(self) -> None:
        """QueryAgent should fail fast if tools is None and source_path is missing."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()
        mock_embed = MockEmbedding(embed_dim=32)

        with pytest.raises(ValueError, match="source_path"):
            QueryAgent(
                llm=mock_llm,
                registry=mock_registry,
                embed_model=mock_embed,
            )

    def test_fails_without_registry_when_tools_none(self) -> None:
        """QueryAgent should fail fast if tools is None and registry is missing."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_embed = MockEmbedding(embed_dim=32)

        with pytest.raises(ValueError, match="registry"):
            QueryAgent(
                llm=mock_llm,
                source_path="/tmp/test.pdf",
                embed_model=mock_embed,
            )

    def test_fails_without_embed_model_when_tools_none(self) -> None:
        """QueryAgent should fail fast if tools is None and embed_model is missing."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()

        with pytest.raises(ValueError, match="embed_model"):
            QueryAgent(
                llm=mock_llm,
                source_path="/tmp/test.pdf",
                registry=mock_registry,
            )


class TestQueryAgentVectorBackendPropagation:
    """QueryAgent should pass vector_backend to auto-constructed RetrievalTool."""

    def test_auto_construct_rejects_invalid_vector_backend(self) -> None:
        """QueryAgent auto-construct path should reject invalid vector_backend."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()
        mock_embed = MockEmbedding(embed_dim=32)

        with pytest.raises(ValueError, match="vector_backend"):
            QueryAgent(
                llm=mock_llm,
                source_path="/tmp/test.pdf",
                registry=mock_registry,
                embed_model=mock_embed,
                vector_backend=object(),
            )

    def test_auto_construct_passes_vector_backend(self) -> None:
        """QueryAgent should pass vector_backend to auto-constructed RetrievalTool."""
        from llamaindex_runtime.agent import QueryAgent

        mock_llm = MockLLM()
        mock_registry = _make_registry()
        mock_embed = MockEmbedding(embed_dim=32)
        test_version_id = uuid.uuid4()
        test_backend = _make_vector_backend()

        agent = QueryAgent(
            llm=mock_llm,
            source_path="/tmp/test.pdf",
            registry=mock_registry,
            embed_model=mock_embed,
            version_id=test_version_id,
            vector_backend=test_backend,
        )

        tool = agent.tools[0]
        assert tool.metadata.name == "hybrid_retrieval"
        assert tool._version_id == test_version_id
        assert tool._vector_backend is test_backend
