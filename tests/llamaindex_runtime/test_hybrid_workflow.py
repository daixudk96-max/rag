"""Tests for HybridRetrievalWorkflow (Phase 1 control-plane slice).

Scope: Minimal Workflow that wraps the existing hybrid retrieval path.
No full ReActAgent, no new retrieval logic - just orchestration of existing data-plane.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.workflow import Workflow, StartEvent, StopEvent

from llamaindex_runtime.entrypoints.types import QueryHit, QueryResult
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
# Tests - Workflow can be instantiated
# ---------------------------------------------------------------------------


class TestHybridRetrievalWorkflowBasics:
    """Basic workflow instantiation and contract tests."""

    def test_workflow_class_exists(self) -> None:
        """HybridRetrievalWorkflow should be importable."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        assert HybridRetrievalWorkflow is not None

    def test_workflow_is_a_workflow_instance(self) -> None:
        """HybridRetrievalWorkflow should inherit from Workflow."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )
        # Should be a Workflow instance
        assert isinstance(workflow, Workflow)

    def test_workflow_can_be_instantiated(self) -> None:
        """Workflow should be instantiable with required parameters."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )
        assert workflow is not None

    def test_workflow_has_run_method(self) -> None:
        """Workflow should expose a run() method."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )
        assert hasattr(workflow, "run")


# ---------------------------------------------------------------------------
# Tests - Workflow delegates to existing hybrid path
# ---------------------------------------------------------------------------


class TestHybridRetrievalWorkflowDelegation:
    """Workflow should wrap existing query() hybrid path."""

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_workflow_run_calls_underlying_hybrid_path(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Workflow.run() should delegate to query() with mode='hybrid'."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        keyword_hit = _make_keyword_hit("PM2.5 indicator", 1.0)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        registry = _make_registry()
        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=registry,
            embed_model=MockEmbedding(embed_dim=32),
        )

        result = await workflow.run(query_text="PM2.5")

        # Should call keyword, vector, and tree retrievers
        mock_kw.assert_called_once()
        mock_vec.assert_called_once()
        mock_tree.assert_called_once()

        # Result should be QueryResult with mode='hybrid'
        assert isinstance(result, QueryResult)
        assert result.mode == "hybrid"

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_workflow_returns_same_shape_as_query(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Workflow should return the same QueryResult shape as query()."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        keyword_hit = _make_keyword_hit("air quality", 0.9)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        registry = _make_registry()
        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=registry,
            embed_model=MockEmbedding(embed_dim=32),
        )

        result = await workflow.run(query_text="air quality")

        # QueryResult shape is frozen dataclass with mode, hits, source_path, query
        assert hasattr(result, "mode")
        assert hasattr(result, "hits")
        assert hasattr(result, "source_path")
        assert hasattr(result, "query")
        assert result.mode == "hybrid"
        assert isinstance(result.hits, tuple)


# ---------------------------------------------------------------------------
# Tests - Workflow validates parameters
# ---------------------------------------------------------------------------


class TestHybridRetrievalWorkflowValidation:
    """Workflow should validate required parameters."""

    def test_workflow_requires_registry(self) -> None:
        """Workflow should require registry for hybrid retrieval."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        with pytest.raises(ValueError, match="registry"):
            HybridRetrievalWorkflow(
                source_path="/tmp/test.pdf",
                registry=None,
                embed_model=MockEmbedding(embed_dim=32),
            )

    def test_workflow_requires_embed_model(self) -> None:
        """Workflow should require embed_model for vector/tree paths."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        registry = _make_registry()
        with pytest.raises(ValueError, match="embed_model"):
            HybridRetrievalWorkflow(
                source_path="/tmp/test.pdf",
                registry=registry,
                embed_model=None,
            )

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_workflow_run_validates_query_text(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Workflow.run() should validate query_text is not empty."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        registry = _make_registry()
        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=registry,
            embed_model=MockEmbedding(embed_dim=32),
        )

        with pytest.raises(ValueError, match="query_text"):
            await workflow.run(query_text="")


class TestHybridRetrievalWorkflowEvents:
    """Workflow should use LlamaIndex Events for orchestration."""

    def test_workflow_has_events_defined(self) -> None:
        """Workflow should define Event classes for its steps."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        # Workflow should have at least StartEvent and StopEvent
        # (these are standard Workflow events)
        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
        )

        # Check that workflow accepts StartEvent (standard Workflow API)
        # This is a basic check that it's integrated with Workflow system
        assert hasattr(workflow, "run")

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_workflow_run_returns_query_result(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Workflow.run() should return QueryResult via StopEvent."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        keyword_hit = _make_keyword_hit("test query", 0.9)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        registry = _make_registry()
        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=registry,
            embed_model=MockEmbedding(embed_dim=32),
        )

        result = await workflow.run(query_text="test query")

        # Should return QueryResult (from StopEvent)
        assert isinstance(result, QueryResult)
        assert result.mode == "hybrid"


class TestHybridRetrievalWorkflowVectorBackendPropagation:
    """Workflow should accept and pass vector_backend to query()."""

    def test_workflow_accepts_vector_backend_parameter(self) -> None:
        """Workflow constructor should accept vector_backend."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=_make_registry(),
            embed_model=MockEmbedding(embed_dim=32),
            vector_backend=_make_vector_backend(),  # protocol-compatible backend
        )

        assert workflow is not None
        assert hasattr(workflow, "_vector_backend")

    def test_workflow_rejects_invalid_vector_backend(self) -> None:
        """Workflow should reject objects that do not implement VectorBackend."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        with pytest.raises(ValueError, match="vector_backend"):
            HybridRetrievalWorkflow(
                source_path="/tmp/test.pdf",
                registry=_make_registry(),
                embed_model=MockEmbedding(embed_dim=32),
                vector_backend=object(),
            )

    @pytest.mark.asyncio
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    async def test_workflow_passes_vector_backend_to_query(
        self, mock_vec, mock_kw, mock_tree
    ) -> None:
        """Workflow should pass vector_backend to query() entrypoint."""
        from llamaindex_runtime.workflow import HybridRetrievalWorkflow

        keyword_hit = _make_keyword_hit("test query", 0.9)
        mock_kw.return_value = [keyword_hit]
        mock_vec.return_value = []
        mock_tree.return_value = []

        registry = _make_registry()
        test_version_id = uuid.uuid4()
        test_backend = _make_vector_backend()

        workflow = HybridRetrievalWorkflow(
            source_path="/tmp/test.pdf",
            registry=registry,
            embed_model=MockEmbedding(embed_dim=32),
            version_id=test_version_id,
            vector_backend=test_backend,
        )

        result = await workflow.run(query_text="test query")

        # Verify vector_backend was passed to query() (via retrieve_vector_hits_from_pdf call)
        assert mock_vec.called
        vec_call_kwargs = mock_vec.call_args[1]
        assert vec_call_kwargs.get("vector_backend") is test_backend
        assert vec_call_kwargs.get("version_id") == test_version_id
