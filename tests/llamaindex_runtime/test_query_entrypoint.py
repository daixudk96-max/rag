"""Tests for the unified query entrypoint.

Phase 1 scope: query() routes to vector or tree retrieval only.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from llama_index.core.embeddings import MockEmbedding
from types import MappingProxyType

from llamaindex_runtime.entrypoints import QueryHit, QueryResult, query
from llamaindex_runtime.vector.backend import VectorBackend


# ---------------------------------------------------------------------------
# Helpers -- lightweight NodeWithScore stand-ins for mocking
# ---------------------------------------------------------------------------


class _FakeTextNode:
    """Mimics llama_index TextNode with .text and .metadata."""

    def __init__(self, text: str, metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata if metadata is not None else {}


class _FakeNodeWithScore:
    """Mimics llama_index NodeWithScore with .node and .score."""

    def __init__(self, text: str, score: float, metadata: dict | None = None) -> None:
        self.node = _FakeTextNode(text, metadata)
        self.score = score


def _make_node(
    text: str, score: float, metadata: dict | None = None
) -> _FakeNodeWithScore:
    return _FakeNodeWithScore(text, score, metadata)


def _make_vector_backend() -> MagicMock:
    backend = MagicMock(spec=VectorBackend)
    backend.search.return_value = []
    return backend


# ---------------------------------------------------------------------------
# Unit tests -- validation and routing (no real PDF / no real Docling)
# ---------------------------------------------------------------------------


class TestQueryResultDataclass:
    """QueryResult is a frozen dataclass that carries retrieval metadata."""

    def test_is_frozen(self) -> None:
        result = QueryResult(
            mode="vector",
            hits=(),
            source_path="/tmp/fake.pdf",
            query="test query",
        )
        with pytest.raises(AttributeError):
            result.mode = "tree"  # type: ignore[misc]

    def test_stores_fields_immutably(self) -> None:
        hit = QueryHit(text="some text", score=0.95, metadata={"page": 1})
        result = QueryResult(
            mode="tree",
            hits=(hit,),
            source_path="/tmp/doc.pdf",
            query="hello",
        )
        assert result.mode == "tree"
        assert result.hits == (hit,)
        assert isinstance(result.hits, tuple)
        assert result.source_path == "/tmp/doc.pdf"
        assert result.query == "hello"


class TestQueryInvalidMode:
    """query() must raise ValueError on unsupported mode strings."""

    def test_empty_mode(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            query(
                source_path="/tmp/fake.pdf",
                query_text="irrelevant",
                embed_model=MockEmbedding(embed_dim=32),
                mode="",
                similarity_top_k=3,
            )

    def test_gibberish_mode(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            query(
                source_path="/tmp/fake.pdf",
                query_text="irrelevant",
                embed_model=MockEmbedding(embed_dim=32),
                mode="hybrid",
                similarity_top_k=3,
            )

    # Note: graph mode was removed (Neo4j seam retired 2026-09-05)


class TestQueryRouting:
    """query() delegates to the correct runtime function based on mode."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_calls_vector_runtime(self, mock_vector) -> None:
        mock_vector.return_value = [
            _make_node("vec-hit-1", 0.9),
            _make_node("vec-hit-2", 0.7),
        ]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find me",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=5,
        )
        mock_vector.assert_called_once()
        call_args = mock_vector.call_args
        assert call_args[0][0] == Path("/tmp/test.pdf")
        assert call_args[1]["query"] == "find me"
        assert call_args[1]["similarity_top_k"] == 5
        # Backend args should be None when not provided
        assert call_args[1]["version_id"] is None
        assert call_args[1]["registry"] is None
        assert call_args[1]["vector_backend"] is None
        assert isinstance(result, QueryResult)
        assert result.mode == "vector"
        assert len(result.hits) == 2
        assert all(isinstance(h, QueryHit) for h in result.hits)
        assert result.hits[0].text == "vec-hit-1"
        assert result.hits[0].score == 0.9
        assert result.hits[1].text == "vec-hit-2"
        assert result.hits[1].score == 0.7

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_tree_mode_calls_tree_runtime(self, mock_tree) -> None:
        mock_tree.return_value = [_make_node("tree-hit-1", 0.85)]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="merge me",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
        )
        mock_tree.assert_called_once_with(
            Path("/tmp/test.pdf"),
            query="merge me",
            embed_model=mock_tree.call_args[1]["embed_model"],
            similarity_top_k=4,
            registry=None,
            version_id=None,
            backend_type=None,
        )
        assert isinstance(result, QueryResult)
        assert result.mode == "tree"
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "tree-hit-1"
        assert result.hits[0].score == 0.85

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_tree_mode_uses_persisted_backend_when_registry_and_version_are_provided(
        self, mock_tree
    ) -> None:
        version_id = uuid4()
        registry = object()
        mock_tree.return_value = [
            {
                "node_id": uuid4(),
                "chunk_id": uuid4(),
                "chunk_id_missing": False,
                "score": 0.75,
                "text_preview": "persisted-tree-hit",
                "page_no": 3,
                "heading_path": "Section > Subsection",
                "span_ids": [uuid4()],
                "backend_source": "reasoning",
                "retrieval_path": "llm_navigation",
            }
        ]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="merge me",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            similarity_top_k=4,
            registry=registry,
            version_id=version_id,
        )
        mock_tree.assert_called_once_with(
            Path("/tmp/test.pdf"),
            query="merge me",
            embed_model=mock_tree.call_args[1]["embed_model"],
            similarity_top_k=4,
            registry=registry,
            version_id=version_id,
            backend_type=None,
        )
        assert result.hits[0].text == "persisted-tree-hit"
        assert (
            result.hits[0].metadata["node_id"] == mock_tree.return_value[0]["node_id"]
        )
        assert (
            result.hits[0].metadata["chunk_id"] == mock_tree.return_value[0]["chunk_id"]
        )
        assert result.hits[0].metadata["chunk_id_missing"] is False
        assert result.hits[0].metadata["page_no"] == 3
        assert result.hits[0].metadata["heading_path"] == "Section > Subsection"
        assert (
            result.hits[0].metadata["span_ids"] == mock_tree.return_value[0]["span_ids"]
        )
        assert result.hits[0].metadata["backend_source"] == "reasoning"
        assert result.hits[0].metadata["retrieval_path"] == "llm_navigation"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_tree_mode_forwards_explicit_tree_backend_type(self, mock_tree) -> None:
        version_id = uuid4()
        registry = object()
        mock_tree.return_value = []

        query(
            source_path="/tmp/test.pdf",
            query_text="legacy traversal",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
            registry=registry,
            version_id=version_id,
            tree_backend_type="embedding",
        )

        assert mock_tree.call_args[1]["backend_type"] == "embedding"


class TestQueryInputValidation:
    """query() should reject invalid query text, top-k, and limit values."""

    @pytest.mark.parametrize("query_text", ["", "   "])
    def test_empty_query_text_rejected(self, query_text: str) -> None:
        with pytest.raises(ValueError, match="query"):
            query(
                source_path="/tmp/fake.pdf",
                query_text=query_text,
                embed_model=MockEmbedding(embed_dim=32),
                mode="vector",
            )

    @pytest.mark.parametrize("top_k", [0, -1])
    def test_non_positive_top_k_rejected(self, top_k: int) -> None:
        with pytest.raises(ValueError, match="similarity_top_k"):
            query(
                source_path="/tmp/fake.pdf",
                query_text="valid query",
                embed_model=MockEmbedding(embed_dim=32),
                mode="tree",
                similarity_top_k=top_k,
            )

    def test_too_large_top_k_rejected(self) -> None:
        with pytest.raises(ValueError, match="similarity_top_k"):
            query(
                source_path="/tmp/fake.pdf",
                query_text="valid query",
                embed_model=MockEmbedding(embed_dim=32),
                mode="vector",
                similarity_top_k=101,
            )

    @pytest.mark.parametrize("limit", [0, -1])
    def test_non_positive_limit_rejected(self, limit: int) -> None:
        """limit must be positive when provided."""
        with pytest.raises(ValueError, match="limit"):
            query(
                source_path="/tmp/fake.pdf",
                query_text="valid query",
                embed_model=MockEmbedding(embed_dim=32),
                mode="hybrid",
                registry=object(),
                limit=limit,
            )


class TestQueryDefaultTopK:
    """query() should forward similarity_top_k correctly."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_default_similarity_top_k_vector(self, mock_vector) -> None:
        mock_vector.return_value = []
        query(
            source_path="/tmp/test.pdf",
            query_text="default k",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        _args, kwargs = mock_vector.call_args
        assert kwargs["similarity_top_k"] == 3

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_default_similarity_top_k_tree(self, mock_tree) -> None:
        mock_tree.return_value = []
        query(
            source_path="/tmp/test.pdf",
            query_text="default k",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
        )
        _args, kwargs = mock_tree.call_args
        assert kwargs["similarity_top_k"] == 4


class TestQuerySourcePathCoercion:
    """query() should accept both str and Path for source_path."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_string_source_path(self, mock_vector) -> None:
        mock_vector.return_value = []
        query(
            source_path="/tmp/str.pdf",
            query_text="coerce",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        mock_vector.assert_called_once()
        assert mock_vector.call_args[0][0] == Path("/tmp/str.pdf")

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_path_source_path(self, mock_vector) -> None:
        mock_vector.return_value = []
        query(
            source_path=Path("/tmp/path.pdf"),
            query_text="coerce",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        mock_vector.assert_called_once()
        assert mock_vector.call_args[0][0] == Path("/tmp/path.pdf")


# ---------------------------------------------------------------------------
# Unit tests -- QueryHit structured hit model
# ---------------------------------------------------------------------------


class TestQueryHitDataclass:
    """QueryHit is a frozen dataclass that carries structured evidence."""

    def test_is_frozen(self) -> None:
        hit = QueryHit(text="hello", score=0.9, metadata={"page": 1})
        with pytest.raises(AttributeError):
            hit.text = "changed"  # type: ignore[misc]

    def test_fields(self) -> None:
        hit = QueryHit(text="chunk text", score=0.75, metadata={"source": "doc.pdf"})
        assert hit.text == "chunk text"
        assert hit.score == 0.75
        assert hit.metadata == {"source": "doc.pdf"}

    def test_metadata_defaults_to_immutable_empty_mapping(self) -> None:
        hit = QueryHit(text="no meta", score=0.5)
        assert hit.metadata == {}
        assert isinstance(hit.metadata, MappingProxyType)
        with pytest.raises(TypeError):
            hit.metadata["x"] = 1  # type: ignore[index]

    def test_score_can_be_none(self) -> None:
        hit = QueryHit(text="no score", score=None)
        assert hit.score is None

    def test_empty_text_allowed(self) -> None:
        hit = QueryHit(text="", score=0.0, metadata={})
        assert hit.text == ""


class TestQueryMappingFromNodeWithScore:
    """query() maps NodeWithScore-like objects to QueryHit."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_metadata_carried_through(self, mock_vector) -> None:
        mock_vector.return_value = [
            _make_node("text A", 0.88, {"page": 3, "section": "intro"}),
        ]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        assert result.hits[0].metadata == {"page": 3, "section": "intro"}

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_none_score_mapped(self, mock_tree) -> None:
        node = _FakeNodeWithScore("no score text", None, {})
        mock_tree.return_value = [node]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
        )
        assert result.hits[0].score is None

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_empty_hits_list(self, mock_vector) -> None:
        mock_vector.return_value = []
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        assert result.hits == ()
        assert isinstance(result.hits, tuple)

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_multiple_hits_order_preserved(self, mock_vector) -> None:
        mock_vector.return_value = [
            _make_node("first", 0.9, {"rank": 1}),
            _make_node("second", 0.7, {"rank": 2}),
            _make_node("third", 0.5, {"rank": 3}),
        ]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )
        assert len(result.hits) == 3
        assert result.hits[0].text == "first"
        assert result.hits[1].text == "second"
        assert result.hits[2].text == "third"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_node_without_metadata_key(self, mock_tree) -> None:
        """NodeWithScore whose inner node has no metadata attribute should get empty dict."""

        class BareNode:
            text = "bare"

        class BareNodeWithScore:
            node = BareNode()
            score = 0.6

        mock_tree.return_value = [BareNodeWithScore()]
        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="tree",
        )
        assert result.hits[0].text == "bare"
        assert result.hits[0].score == 0.6
        assert result.hits[0].metadata == {}


class TestQueryVectorBackendAdoption:
    """query() should use backend path for vector mode when backend context is provided."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_uses_backend_when_all_backend_args_provided(
        self, mock_retrieve
    ) -> None:
        """When registry + version_id + vector_backend are provided, backend path is used."""
        # Backend path returns provenance-rich dicts
        mock_retrieve.return_value = [
            {
                "chunk_id": "uuid-1",
                "node_id": "node-uuid-1",
                "score": 0.92,
                "text_preview": "backend hit text",
                "page_no": 3,
                "heading_path": "Section > Subsection",
                "span_ids": ["span-uuid-1"],
                "backend_source": "reasoning",
                "retrieval_path": "llm_navigation",
            },
        ]

        from uuid import UUID

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            registry=object(),  # dummy registry
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=_make_vector_backend(),  # protocol-compatible backend
            similarity_top_k=5,
        )

        # Verify backend path was called
        assert mock_retrieve.called
        call_kwargs = mock_retrieve.call_args[1]
        assert call_kwargs["registry"] is not None
        assert call_kwargs["version_id"] is not None
        assert call_kwargs["vector_backend"] is not None
        assert call_kwargs["similarity_top_k"] == 5

        # Result should be stable QueryHit
        assert result.mode == "vector"
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "backend hit text"
        assert result.hits[0].score == 0.92
        assert result.hits[0].metadata["chunk_id"] == "uuid-1"
        assert result.hits[0].metadata["node_id"] == "node-uuid-1"
        assert result.hits[0].metadata["page_no"] == 3
        assert result.hits[0].metadata["heading_path"] == "Section > Subsection"
        assert result.hits[0].metadata["backend_source"] == "reasoning"
        assert result.hits[0].metadata["retrieval_path"] == "llm_navigation"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_uses_local_path_when_backend_args_absent(
        self, mock_retrieve
    ) -> None:
        """When backend context is incomplete, local PDF path is used."""
        # Local path returns NodeWithScore-like objects
        mock_retrieve.return_value = [_make_node("local hit text", 0.88, {"page": 2})]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            similarity_top_k=3,
        )

        # Verify backend args were NOT passed
        assert mock_retrieve.called
        call_kwargs = mock_retrieve.call_args[1]
        assert "registry" not in call_kwargs or call_kwargs.get("registry") is None
        assert "version_id" not in call_kwargs or call_kwargs.get("version_id") is None
        assert (
            "vector_backend" not in call_kwargs
            or call_kwargs.get("vector_backend") is None
        )

        # Result should be stable QueryHit
        assert result.mode == "vector"
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "local hit text"
        assert result.hits[0].score == 0.88
        assert result.hits[0].metadata == {"page": 2}

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_rejects_invalid_vector_backend(self, mock_retrieve) -> None:
        """vector mode should reject objects that do not implement VectorBackend."""
        from uuid import UUID

        with pytest.raises(ValueError, match="vector_backend"):
            query(
                source_path="/tmp/test.pdf",
                query_text="test query",
                embed_model=MockEmbedding(embed_dim=32),
                mode="vector",
                registry=object(),
                version_id=UUID("12345678-1234-5678-1234-567812345678"),
                vector_backend=object(),
            )

        mock_retrieve.assert_not_called()

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_backend_dict_hits_mapped_to_stable_queryhit(
        self, mock_retrieve
    ) -> None:
        """Backend-returned dict hits must be mapped into stable QueryHit objects."""
        from uuid import UUID

        mock_retrieve.return_value = [
            {
                "chunk_id": "uuid-a",
                "score": 0.95,
                "text_preview": "first hit",
                "page_no": 1,
                "heading_path": "Intro",
                "span_ids": ["span-a"],
            },
            {
                "chunk_id": "uuid-b",
                "score": 0.75,
                "text_preview": "second hit",
                "page_no": 5,
                "heading_path": "Methods > Analysis",
                "span_ids": ["span-b", "span-c"],
            },
        ]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            registry=object(),
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=_make_vector_backend(),
        )

        assert len(result.hits) == 2
        # First hit
        assert result.hits[0].text == "first hit"
        assert result.hits[0].score == 0.95
        assert result.hits[0].metadata["chunk_id"] == "uuid-a"
        assert result.hits[0].metadata["page_no"] == 1
        assert result.hits[0].metadata["heading_path"] == "Intro"
        assert result.hits[0].metadata["span_ids"] == ["span-a"]
        # Second hit
        assert result.hits[1].text == "second hit"
        assert result.hits[1].score == 0.75
        assert result.hits[1].metadata["page_no"] == 5
        assert result.hits[1].metadata["span_ids"] == ["span-b", "span-c"]


class TestHybridModeLimitBudget:
    """Hybrid mode must honor the `limit` parameter as final fused hit count cap."""

    @patch("llamaindex_runtime.entrypoints._query.fuse_candidates")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_hybrid_with_limit_one_returns_at_most_one_hit(
        self,
        mock_kw,
        mock_vec,
        mock_tree,
        mock_fuse,
    ) -> None:
        """limit=1 must return at most 1 fused hit."""
        # Setup mocks to return multiple hits
        mock_kw.return_value = [
            _make_node("kw-hit-1", 0.9),
            _make_node("kw-hit-2", 0.8),
        ]
        mock_vec.return_value = [
            _make_node("vec-hit-1", 0.95),
            _make_node("vec-hit-2", 0.85),
        ]
        mock_tree.return_value = [
            _make_node("tree-hit-1", 0.92),
            _make_node("tree-hit-2", 0.82),
        ]

        # Mock fuse_candidates to return 3 fused hits
        from llamaindex_runtime.analysis.types import FusedHit

        mock_fuse.return_value = [
            FusedHit(
                text="fused-1",
                score=0.95,
                metadata={},
                source_paths=frozenset(["vector", "tree"]),
            ),
            FusedHit(
                text="fused-2",
                score=0.90,
                metadata={},
                source_paths=frozenset(["keyword"]),
            ),
            FusedHit(
                text="fused-3",
                score=0.85,
                metadata={},
                source_paths=frozenset(["vector"]),
            ),
        ]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),  # dummy registry
            limit=1,
        )

        assert result.mode == "hybrid"
        # GREEN EXPECTED: limit=1 correctly caps fused results to at most 1 hit
        assert len(result.hits) <= 1, f"Expected at most 1 hit, got {len(result.hits)}"

    @patch("llamaindex_runtime.entrypoints._query.fuse_candidates")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_hybrid_with_limit_two_returns_at_most_two_hits(
        self,
        mock_kw,
        mock_vec,
        mock_tree,
        mock_fuse,
    ) -> None:
        """limit=2 must return at most 2 fused hits."""
        mock_kw.return_value = [_make_node("kw-hit-1", 0.9)]
        mock_vec.return_value = [_make_node("vec-hit-1", 0.95)]
        mock_tree.return_value = [_make_node("tree-hit-1", 0.92)]

        from llamaindex_runtime.analysis.types import FusedHit

        mock_fuse.return_value = [
            FusedHit(
                text="fused-1",
                score=0.95,
                metadata={},
                source_paths=frozenset(["vector"]),
            ),
            FusedHit(
                text="fused-2",
                score=0.90,
                metadata={},
                source_paths=frozenset(["keyword"]),
            ),
            FusedHit(
                text="fused-3",
                score=0.85,
                metadata={},
                source_paths=frozenset(["tree"]),
            ),
            FusedHit(
                text="fused-4",
                score=0.80,
                metadata={},
                source_paths=frozenset(["vector"]),
            ),
        ]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),
            limit=2,
        )

        assert result.mode == "hybrid"
        # GREEN EXPECTED: limit=2 correctly caps fused results to at most 2 hits
        assert len(result.hits) <= 2, f"Expected at most 2 hits, got {len(result.hits)}"

    @patch("llamaindex_runtime.entrypoints._query.fuse_candidates")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    def test_hybrid_with_no_limit_returns_all_fused_hits(
        self,
        mock_kw,
        mock_vec,
        mock_tree,
        mock_fuse,
    ) -> None:
        """limit=None must preserve current uncapped behavior."""
        mock_kw.return_value = [_make_node("kw-hit-1", 0.9)]
        mock_vec.return_value = [_make_node("vec-hit-1", 0.95)]
        mock_tree.return_value = [_make_node("tree-hit-1", 0.92)]

        from llamaindex_runtime.analysis.types import FusedHit

        mock_fuse.return_value = [
            FusedHit(
                text="fused-1",
                score=0.95,
                metadata={},
                source_paths=frozenset(["vector"]),
            ),
            FusedHit(
                text="fused-2",
                score=0.90,
                metadata={},
                source_paths=frozenset(["keyword"]),
            ),
            FusedHit(
                text="fused-3",
                score=0.85,
                metadata={},
                source_paths=frozenset(["tree"]),
            ),
        ]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),
            limit=None,
        )

        assert result.mode == "hybrid"
        # GREEN EXPECTED: Current behavior returns all fused hits when limit=None
        assert len(result.hits) == 3

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_metadata_copied_and_immutable(self, mock_vector) -> None:
        shared_metadata = {"page": 1}
        mock_vector.return_value = [_make_node("text", 0.5, shared_metadata)]

        result = query(
            source_path="/tmp/test.pdf",
            query_text="find",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
        )

        shared_metadata["page"] = 2
        assert result.hits[0].metadata == {"page": 1}
        assert isinstance(result.hits[0].metadata, MappingProxyType)
        with pytest.raises(TypeError):
            result.hits[0].metadata["page"] = 3  # type: ignore[index]


class TestHybridModeVectorBackendAdoption:
    """Hybrid mode should pass backend context to its vector leg when available."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_hybrid_mode_passes_backend_args_to_vector_leg(
        self, mock_tree, mock_kw, mock_vec
    ) -> None:
        """When registry + version_id + vector_backend are provided, hybrid vector leg uses backend."""
        from uuid import UUID

        # Mock backend path returns dicts
        mock_vec.return_value = [
            {
                "chunk_id": "uuid-vec-1",
                "score": 0.92,
                "text_preview": "backend vector hit",
                "page_no": 5,
                "heading_path": "Section 1",
                "span_ids": ["span-uuid-1"],
            }
        ]
        mock_kw.return_value = []
        mock_tree.return_value = []

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),  # dummy registry
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=_make_vector_backend(),  # protocol-compatible backend
            similarity_top_k=5,
        )

        # Verify backend args passed to vector leg
        assert mock_vec.called
        vec_call_kwargs = mock_vec.call_args[1]
        assert vec_call_kwargs["registry"] is not None
        assert vec_call_kwargs["version_id"] is not None
        assert vec_call_kwargs["vector_backend"] is not None
        assert vec_call_kwargs["similarity_top_k"] == 5

        # Result should be hybrid mode with backend-enriched vector hit
        assert result.mode == "hybrid"
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "backend vector hit"
        assert result.hits[0].score == 0.92
        assert result.hits[0].metadata["chunk_id"] == "uuid-vec-1"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_hybrid_vector_leg_without_backend_args_uses_local_path(
        self, mock_tree, mock_kw, mock_vec
    ) -> None:
        """Hybrid vector leg uses local path when backend args are absent."""
        mock_vec.return_value = [_make_node("local vector hit", 0.88, {"page": 3})]
        mock_kw.return_value = []
        mock_tree.return_value = []

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),
        )

        # Verify backend args NOT passed to vector leg
        assert mock_vec.called
        vec_call_kwargs = mock_vec.call_args[1]
        assert vec_call_kwargs.get("registry") is None
        assert vec_call_kwargs.get("version_id") is None
        assert vec_call_kwargs.get("vector_backend") is None

        # Result should be hybrid mode with local vector hit
        assert result.mode == "hybrid"
        assert len(result.hits) == 1
        assert result.hits[0].text == "local vector hit"


class TestQueryVectorModeMilvusBackendCanary:
    """Canary: query() vector mode should work with MilvusVectorBackend through generic VectorBackend seam."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_milvus_backend_returns_stable_queryhit(
        self, mock_retrieve
    ) -> None:
        """query() vector mode should accept MilvusVectorBackend and return stable QueryHit shape."""
        from uuid import UUID
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend
        from unittest.mock import MagicMock

        milvus_chunk_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        # Mock backend path returns provenance-rich dicts
        mock_retrieve.return_value = [
            {
                "chunk_id": milvus_chunk_id,
                "score": 0.93,
                "text_preview": "milvus backend hit text",
                "page_no": 7,
                "heading_path": "Chapter 2 > Results",
                "span_ids": ["span-milvus-1"],
            },
        ]

        # Create mock Milvus client and backend
        mock_milvus_client = MagicMock()
        mock_milvus_backend = MilvusVectorBackend(
            client=mock_milvus_client, embed_dim=32
        )

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test milvus query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            registry=object(),  # dummy registry
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=mock_milvus_backend,  # MilvusVectorBackend instance
            similarity_top_k=5,
        )

        # Verify backend path was called with Milvus backend
        assert mock_retrieve.called
        call_kwargs = mock_retrieve.call_args[1]
        assert call_kwargs["registry"] is not None
        assert call_kwargs["version_id"] is not None
        # vector_backend should be the MilvusVectorBackend instance
        assert call_kwargs["vector_backend"] is mock_milvus_backend
        assert call_kwargs["similarity_top_k"] == 5

        # Result should be stable QueryHit/QueryResult shape
        assert result.mode == "vector"
        assert isinstance(result, QueryResult)
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "milvus backend hit text"
        assert result.hits[0].score == 0.93
        assert result.hits[0].metadata["chunk_id"] == milvus_chunk_id
        assert result.hits[0].metadata["page_no"] == 7
        assert result.hits[0].metadata["heading_path"] == "Chapter 2 > Results"

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    def test_vector_mode_milvus_backend_multiple_hits(self, mock_retrieve) -> None:
        """query() vector mode should handle multiple Milvus backend hits."""
        from uuid import UUID
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend
        from unittest.mock import MagicMock

        milvus_chunk_id_a = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        milvus_chunk_id_b = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

        mock_retrieve.return_value = [
            {
                "chunk_id": milvus_chunk_id_a,
                "score": 0.95,
                "text_preview": "first milvus hit",
                "page_no": 1,
                "heading_path": "Intro",
                "span_ids": ["span-a"],
            },
            {
                "chunk_id": milvus_chunk_id_b,
                "score": 0.80,
                "text_preview": "second milvus hit",
                "page_no": 10,
                "heading_path": "Methods",
                "span_ids": ["span-b", "span-c"],
            },
        ]

        mock_milvus_client = MagicMock()
        mock_milvus_backend = MilvusVectorBackend(
            client=mock_milvus_client, embed_dim=32
        )

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="vector",
            registry=object(),
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=mock_milvus_backend,
        )

        assert len(result.hits) == 2
        assert result.hits[0].text == "first milvus hit"
        assert result.hits[0].score == 0.95
        assert result.hits[0].metadata["page_no"] == 1
        assert result.hits[1].text == "second milvus hit"
        assert result.hits[1].score == 0.80
        assert result.hits[1].metadata["page_no"] == 10


class TestHybridModeMilvusBackendCanary:
    """Canary: hybrid mode vector leg should work with MilvusVectorBackend."""

    @patch("llamaindex_runtime.entrypoints._query.retrieve_vector_hits_from_pdf")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_keyword_hits")
    @patch("llamaindex_runtime.entrypoints._query.retrieve_tree_hits_from_pdf")
    def test_hybrid_mode_milvus_backend_vector_leg(
        self, mock_tree, mock_kw, mock_vec
    ) -> None:
        """Hybrid mode should accept MilvusVectorBackend and pass it to vector leg."""
        from uuid import UUID
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend
        from unittest.mock import MagicMock

        # Mock backend path returns dicts for vector leg
        mock_vec.return_value = [
            {
                "chunk_id": "uuid-milvus-hybrid",
                "score": 0.90,
                "text_preview": "milvus hybrid vector hit",
                "page_no": 3,
                "heading_path": "Section A",
                "span_ids": ["span-hybrid"],
            }
        ]
        mock_kw.return_value = []
        mock_tree.return_value = []

        mock_milvus_client = MagicMock()
        mock_milvus_backend = MilvusVectorBackend(
            client=mock_milvus_client, embed_dim=32
        )

        result = query(
            source_path="/tmp/test.pdf",
            query_text="test hybrid query",
            embed_model=MockEmbedding(embed_dim=32),
            mode="hybrid",
            registry=object(),
            version_id=UUID("12345678-1234-5678-1234-567812345678"),
            vector_backend=mock_milvus_backend,
            similarity_top_k=5,
        )

        # Verify Milvus backend passed to vector leg
        assert mock_vec.called
        vec_call_kwargs = mock_vec.call_args[1]
        assert vec_call_kwargs["registry"] is not None
        assert vec_call_kwargs["version_id"] is not None
        assert vec_call_kwargs["vector_backend"] is mock_milvus_backend
        assert vec_call_kwargs["similarity_top_k"] == 5

        # Result should be hybrid mode with Milvus backend-enriched hit
        assert result.mode == "hybrid"
        assert isinstance(result, QueryResult)
        assert len(result.hits) == 1
        assert isinstance(result.hits[0], QueryHit)
        assert result.hits[0].text == "milvus hybrid vector hit"
        assert result.hits[0].score == 0.90
        assert result.hits[0].metadata["chunk_id"] == "uuid-milvus-hybrid"
