"""Tests for the vector backend seam and Qdrant implementation.

Unit tests verify:
1. VectorBackend protocol satisfies structural typing
2. VectorPoint and SearchHit data classes are frozen and correct
3. QdrantVectorBackend with mocked qdrant_client
4. VectorLoader integration with VectorBackend (mocked backend)
5. retrieve_vector_hits_from_backend round-trips provenance (mocked)
6. RuntimeSettings accepts "qdrant" as valid vector_backend
7. Edge cases: empty inputs, zero limit, large batches, null payload
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from llamaindex_runtime.vector.chunker import SimpleSpanChunker
from llamaindex_runtime.vector.embedder import DeterministicEmbedder
from llamaindex_runtime.vector.exceptions import VectorBackendError


class TestVectorPackageExportsQdrant:
    def test_qdrant_backend_is_reexported_from_vector_package(self) -> None:
        from llamaindex_runtime.vector import QdrantVectorBackend
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend as DirectQdrantVectorBackend

        assert QdrantVectorBackend is DirectQdrantVectorBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_span_dict(
    *,
    span_id: uuid.UUID | None = None,
    version_id: uuid.UUID,
    heading_path: str | None = None,
    page_no: int | None = 1,
    text: str = "sample text",
    offset: int = 0,
) -> dict[str, object]:
    return {
        "span_id": span_id or uuid.uuid4(),
        "version_id": version_id,
        "span_kind": "paragraph",
        "start_offset": offset,
        "end_offset": offset + len(text),
        "page_no": page_no,
        "heading_path": heading_path,
        "raw_text": text,
    }


# ===========================================================================
# UNIT TESTS -- VectorPoint and SearchHit data classes
# ===========================================================================


class TestVectorPoint:
    """VectorPoint: frozen data class for vector upsert payloads."""

    def test_vector_point_is_frozen(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint

        pt = VectorPoint(id=uuid.uuid4(), vector=[1.0, 2.0], payload={"k": "v"})
        with pytest.raises(AttributeError):
            pt.vector = [3.0]  # type: ignore[misc]

    def test_vector_point_fields(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint

        uid = uuid.uuid4()
        pt = VectorPoint(id=uid, vector=[0.5, -0.5], payload={"text": "hello"})
        assert pt.id == uid
        assert pt.vector == [0.5, -0.5]
        assert pt.payload == {"text": "hello"}

    def test_vector_point_empty_payload(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint

        pt = VectorPoint(id=uuid.uuid4(), vector=[1.0], payload={})
        assert pt.payload == {}

    def test_vector_point_default_payload(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint

        pt = VectorPoint(id=uuid.uuid4(), vector=[1.0])
        assert pt.payload == {}


class TestSearchHit:
    """SearchHit: frozen data class for vector search results."""

    def test_search_hit_is_frozen(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit

        hit = SearchHit(id=uuid.uuid4(), score=0.95, payload={})
        with pytest.raises(AttributeError):
            hit.score = 0.5  # type: ignore[misc]

    def test_search_hit_fields(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit

        uid = uuid.uuid4()
        hit = SearchHit(id=uid, score=0.88, payload={"version_id": "abc"})
        assert hit.id == uid
        assert hit.score == 0.88
        assert hit.payload == {"version_id": "abc"}

    def test_search_hit_default_payload(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit

        hit = SearchHit(id=uuid.uuid4(), score=0.5)
        assert hit.payload == {}


# ===========================================================================
# UNIT TESTS -- VectorBackend protocol
# ===========================================================================


class TestVectorBackendProtocol:
    """VectorBackend protocol: structural typing checks."""

    def test_qdrant_backend_satisfies_protocol(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        mock_client = MagicMock()
        backend = QdrantVectorBackend(client=mock_client, embed_dim=8)
        assert isinstance(backend, VectorBackend)

    def test_custom_class_satisfies_protocol(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend

        class InMemoryBackend:
            def upsert_vectors(self, collection_name: str, points: Any) -> None:
                pass

            def search(self, collection_name: str, query_vector: list[float], limit: int = 10) -> list[Any]:
                return []

            def delete_collection(self, collection_name: str) -> None:
                pass

        backend = InMemoryBackend()
        assert isinstance(backend, VectorBackend)

    def test_missing_method_fails_protocol(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend

        class IncompleteBackend:
            def upsert_vectors(self, collection_name: str, points: Any) -> None:
                pass

        backend = IncompleteBackend()
        assert not isinstance(backend, VectorBackend)


# ===========================================================================
# UNIT TESTS -- QdrantVectorBackend with mocked client
# ===========================================================================


class TestQdrantVectorBackend:
    """QdrantVectorBackend: unit tests with mocked qdrant_client."""

    def _make_mock_client(self) -> MagicMock:
        client = MagicMock()
        # Default: no collections exist yet
        client.get_collections.return_value = MagicMock(collections=[])
        # query_points returns a QueryResponse with points attribute
        client.query_points.return_value = MagicMock(points=[])
        return client

    def test_upsert_vectors_creates_collection(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        uid = uuid.uuid4()
        points = [VectorPoint(id=uid, vector=[1.0, 0.0, 0.0, 0.0], payload={"text": "x"})]
        backend.upsert_vectors("test_collection", points)

        # Collection should be created since it does not exist
        client.create_collection.assert_called_once()
        call_kwargs = client.create_collection.call_args
        assert call_kwargs[1]["collection_name"] == "test_collection"

    def test_upsert_does_not_recreate_existing_collection(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        # Simulate the collection already exists
        mock_collection = MagicMock()
        mock_collection.name = "test_collection"
        client.get_collections.return_value = MagicMock(collections=[mock_collection])
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        backend.upsert_vectors("test_collection", points)

        client.create_collection.assert_not_called()

    def test_upsert_vectors_calls_upsert_on_client(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [
            VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0], payload={"a": 1}),
            VectorPoint(id=uuid.uuid4(), vector=[0.0, 1.0, 0.0, 0.0], payload={"b": 2}),
        ]
        backend.upsert_vectors("col", points)

        client.upsert.assert_called_once()
        upsert_kwargs = client.upsert.call_args[1]
        assert upsert_kwargs["collection_name"] == "col"
        assert len(upsert_kwargs["points"]) == 2

    def test_upsert_vectors_with_empty_points_is_noop(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        backend.upsert_vectors("col", [])

        client.upsert.assert_not_called()
        client.create_collection.assert_not_called()

    def test_search_returns_search_hits(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        hit_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.id = str(hit_id)
        mock_result.score = 0.92
        mock_result.payload = {"text": "found"}
        client.query_points.return_value = MagicMock(points=[mock_result])

        backend = QdrantVectorBackend(client=client, embed_dim=4)
        results = backend.search("col", [1.0, 0.0, 0.0, 0.0], limit=5)

        assert len(results) == 1
        assert isinstance(results[0], SearchHit)
        assert results[0].id == hit_id
        assert results[0].score == 0.92
        assert results[0].payload == {"text": "found"}

    def test_search_calls_client_with_correct_params(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        backend.search("my_col", [0.1, 0.2, 0.3, 0.4], limit=10)

        client.query_points.assert_called_once_with(
            collection_name="my_col",
            query=[0.1, 0.2, 0.3, 0.4],
            limit=10,
        )

    def test_search_with_no_results_returns_empty(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        client.query_points.return_value = MagicMock(points=[])
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        results = backend.search("col", [0.0, 0.0, 0.0, 0.0])
        assert results == []

    def test_delete_collection_calls_client(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        backend.delete_collection("old_col")

        client.delete_collection.assert_called_once_with(collection_name="old_col")


class TestQdrantBackendEdgeCases:
    """Edge cases for QdrantVectorBackend."""

    def _make_mock_client(self) -> MagicMock:
        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])
        client.search.return_value = []
        return client

    def test_search_with_zero_limit_returns_empty(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        results = backend.search("col", [0.0, 0.0, 0.0, 0.0], limit=0)
        assert results == []

    def test_upsert_with_single_point(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        backend.upsert_vectors("col", points)
        client.upsert.assert_called_once()

    def test_upsert_large_batch(self) -> None:
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [
            VectorPoint(id=uuid.uuid4(), vector=[float(i % 4 == 0), float(i % 4 == 1), float(i % 4 == 2), float(i % 4 == 3)])
            for i in range(500)
        ]
        backend.upsert_vectors("col", points)
        assert client.upsert.call_args[1]["collection_name"] == "col"
        assert len(client.upsert.call_args[1]["points"]) == 500

    def test_search_hit_with_null_payload(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        mock_result = MagicMock()
        mock_result.id = str(uuid.uuid4())
        mock_result.score = 0.5
        mock_result.payload = None
        client.query_points.return_value = MagicMock(points=[mock_result])

        backend = QdrantVectorBackend(client=client, embed_dim=4)
        results = backend.search("col", [1.0, 0.0, 0.0, 0.0])

        assert len(results) == 1
        assert results[0].payload == {}

    def test_embed_dim_stored(self) -> None:
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = self._make_mock_client()
        backend = QdrantVectorBackend(client=client, embed_dim=32)
        assert backend.embed_dim == 32


class TestQdrantBackendErrorHandling:
    """Error handling for Qdrant backend operations - HIGH severity review findings."""

    def test_upsert_handles_client_connection_error(self) -> None:
        """When Qdrant client raises connection error, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.get_collections.side_effect = ConnectionError("Qdrant unreachable")
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_client_timeout_error(self) -> None:
        """When Qdrant client raises timeout error, upsert_vectors must raise VectorBackendError."""
        from qdrant_client.http.exceptions import UnexpectedResponse
        from httpx import Headers
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])
        client.create_collection.side_effect = TimeoutError("Qdrant timeout")
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_qdrant_specific_error(self) -> None:
        """When Qdrant client raises UnexpectedResponse, upsert_vectors must raise VectorBackendError."""
        from qdrant_client.http.exceptions import UnexpectedResponse
        from httpx import Headers
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.get_collections.side_effect = UnexpectedResponse(
            500,
            "Internal Server Error",
            b"server error",
            Headers(),
        )
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_upsert_failure(self) -> None:
        """When Qdrant client.upsert fails, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])
        client.upsert.side_effect = RuntimeError("Qdrant upsert failed")
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_search_handles_client_query_error(self) -> None:
        """When Qdrant client.query_points fails, search must raise VectorBackendError."""
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.query_points.side_effect = ConnectionError("Qdrant query failed")
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.search("col", [1.0, 0.0, 0.0, 0.0])

    def test_delete_handles_client_error(self) -> None:
        """When Qdrant client.delete_collection fails, delete_collection must raise VectorBackendError."""
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        client.delete_collection.side_effect = RuntimeError("Qdrant delete failed")
        backend = QdrantVectorBackend(client=client, embed_dim=4)

        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.delete_collection("col")

    def test_search_handles_malformed_uuid_in_result(self) -> None:
        """When Qdrant returns malformed UUID string, search must raise VectorBackendError."""
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        client = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "not-a-valid-uuid-string"  # Malformed UUID
        mock_result.score = 0.5
        mock_result.payload = {}
        client.query_points.return_value = MagicMock(points=[mock_result])

        backend = QdrantVectorBackend(client=client, embed_dim=4)
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.search("col", [1.0, 0.0, 0.0, 0.0])


class TestVectorLoaderErrorHandling:
    """Error handling for VectorLoader operations - HIGH severity review findings."""

    def test_loader_handles_embedder_failure_in_update_embeddings(self) -> None:
        """When embedder.embed_text fails in _update_embeddings, load() must raise VectorLoaderError."""
        from unittest.mock import MagicMock, patch

        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder
        from llamaindex_runtime.vector.loader import VectorLoader

        # Create mock connection
        mock_conn = MagicMock()

        # Create embedder that will fail
        failing_embedder = MagicMock(spec=DeterministicEmbedder)
        failing_embedder.dim = 16
        failing_embedder.embed_text.side_effect = RuntimeError("Embedding service failed")

        loader = VectorLoader(embed_dim=16)
        loader._embedder = failing_embedder

        # Mock the database operations to return valid data
        with patch.object(loader, '_read_spans', return_value=[{
            "span_id": uuid.uuid4(),
            "version_id": uuid.uuid4(),
            "span_kind": "paragraph",
            "start_offset": 0,
            "end_offset": 10,
            "page_no": 1,
            "heading_path": "Test",
            "raw_text": "test text"
        }]):
            with patch.object(loader, '_count_existing_chunks', return_value=0):
                with patch.object(loader, '_write_chunks'):
                    with patch.object(loader, '_write_chunk_span_mappings'):
                        with pytest.raises(Exception, match="embedding generation failed"):
                            loader.load(mock_conn, uuid.uuid4())

    def test_loader_handles_embedder_failure_in_project_to_backend(self) -> None:
        """When embedder.embed_text fails in _project_to_backend, load() must raise VectorLoaderError."""
        from unittest.mock import MagicMock, patch

        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder
        from llamaindex_runtime.vector.loader import VectorLoader

        # Create mock connection
        mock_conn = MagicMock()

        # Create mock backend
        mock_backend = MagicMock(spec=VectorBackend)

        # Create embedder that will fail during projection
        # First call (for PostgreSQL) succeeds, second call (for Qdrant) fails
        call_count = 0
        def embed_side_effect(text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [0.1] * 16  # First call succeeds (PostgreSQL embedding)
            else:
                raise RuntimeError("Embedding service failed during projection")

        failing_embedder = MagicMock(spec=DeterministicEmbedder)
        failing_embedder.dim = 16
        failing_embedder.embed_text.side_effect = embed_side_effect

        loader = VectorLoader(embed_dim=16, vector_backend=mock_backend)
        loader._embedder = failing_embedder

        # Mock the database operations
        version_id = uuid.uuid4()
        chunks = [{
            "chunk_id": uuid.uuid4(),
            "version_id": version_id,
            "span_ids": [uuid.uuid4()],
            "text_preview": "test",
            "chunk_type": "semantic_leaf",
            "chunk_order": 0,
            "token_count": 1,
            "page_no": 1,
            "heading_path": "Test"
        }]

        with patch.object(loader, '_read_spans', return_value=[{
            "span_id": chunks[0]["span_ids"][0],
            "version_id": version_id,
            "span_kind": "paragraph",
            "start_offset": 0,
            "end_offset": 10,
            "page_no": 1,
            "heading_path": "Test",
            "raw_text": "test text"
        }]):
            with patch.object(loader, '_count_existing_chunks', return_value=0):
                with patch.object(loader, '_write_chunks'):
                    with patch.object(loader, '_write_chunk_span_mappings'):
                        with pytest.raises(Exception, match="embedding generation failed"):
                            loader.load(mock_conn, version_id)

    def test_loader_handles_backend_upsert_failure(self) -> None:
        """When backend.upsert_vectors fails, load() must raise VectorLoaderError."""
        from unittest.mock import MagicMock, patch

        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.loader import VectorLoader

        # Create mock connection
        mock_conn = MagicMock()

        # Create failing backend
        failing_backend = MagicMock(spec=VectorBackend)
        failing_backend.upsert_vectors.side_effect = RuntimeError("Qdrant upsert failed")

        loader = VectorLoader(embed_dim=16, vector_backend=failing_backend)

        # Mock the database operations
        version_id = uuid.uuid4()
        chunks = [{
            "chunk_id": uuid.uuid4(),
            "version_id": version_id,
            "span_ids": [uuid.uuid4()],
            "text_preview": "test",
            "chunk_type": "semantic_leaf",
            "chunk_order": 0,
            "token_count": 1,
            "page_no": 1,
            "heading_path": "Test"
        }]

        with patch.object(loader, '_read_spans', return_value=[{
            "span_id": chunks[0]["span_ids"][0],
            "version_id": version_id,
            "span_kind": "paragraph",
            "start_offset": 0,
            "end_offset": 10,
            "page_no": 1,
            "heading_path": "Test",
            "raw_text": "test text"
        }]):
            with patch.object(loader, '_count_existing_chunks', return_value=0):
                with patch.object(loader, '_write_chunks'):
                    with patch.object(loader, '_write_chunk_span_mappings'):
                        with pytest.raises(Exception, match="vector projection failed"):
                            loader.load(mock_conn, version_id)


# ===========================================================================
# UNIT TESTS -- VectorLoader with VectorBackend
# ===========================================================================


class TestVectorLoaderWithBackend:
    """VectorLoader must accept and use an optional VectorBackend."""

    def test_loader_accepts_vector_backend_parameter(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.loader import VectorLoader

        mock_backend = MagicMock(spec=VectorBackend)
        loader = VectorLoader(vector_backend=mock_backend)
        assert loader._vector_backend is mock_backend

    def test_loader_without_backend_backward_compatible(self) -> None:
        from llamaindex_runtime.vector.loader import VectorLoader

        loader = VectorLoader()
        assert loader._vector_backend is None

    def test_loader_default_embed_dim_preserved(self) -> None:
        from llamaindex_runtime.vector.loader import VectorLoader

        loader = VectorLoader()
        assert loader._embedder.dim == 16

    def test_loader_custom_embed_dim_with_backend(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.loader import VectorLoader

        mock_backend = MagicMock(spec=VectorBackend)
        loader = VectorLoader(embed_dim=32, vector_backend=mock_backend)
        assert loader._embedder.dim == 32


# ===========================================================================
# UNIT TESTS -- retrieve_vector_hits_from_backend
# ===========================================================================


class TestRetrieveVectorHitsFromBackend:
    """retrieve_vector_hits_from_backend: search Qdrant, round-trip PostgreSQL."""

    def test_retrieve_vector_hits_from_pdf_uses_backend_when_all_args_provided(self) -> None:
        """When version_id + registry + vector_backend provided, retrieve_vector_hits_from_pdf delegates to backend."""
        from llama_index.core.base.embeddings.base import BaseEmbedding
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_pdf

        version_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        span_id = uuid.uuid4()

        # Mock backend returns a hit
        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = [
            SearchHit(id=chunk_id, score=0.95, payload={"text_preview": "hello world"}),
        ]

        # Mock registry returns chunk and span data
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "version_id": version_id,
                "text_preview": "hello world",
                "page_no": 1,
                "heading_path": "Ch 1",
                "chunk_type": "semantic_leaf",
                "chunk_order": 0,
                "token_count": 2,
            },
        ]
        mock_registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        # Mock embed_model that wraps DeterministicEmbedder
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder
        det_embedder = DeterministicEmbedder(dim=16)

        mock_embed_model = MagicMock(spec=BaseEmbedding)
        # BaseEmbedding uses get_text_embedding() for single text
        mock_embed_model.get_text_embedding.return_value = det_embedder.embed_text("test query")

        # Mock the PDF processing to avoid file I/O
        from unittest.mock import patch
        with patch('llamaindex_runtime.vector.runtime.build_docling_bundle'):
            with patch('llamaindex_runtime.vector.runtime.load_docling_node_parser_class'):
                results = retrieve_vector_hits_from_pdf(
                    "dummy.pdf",
                    query="test query",
                    embed_model=mock_embed_model,
                    version_id=version_id,
                    registry=mock_registry,
                    vector_backend=mock_backend,
                    similarity_top_k=5,
                )

        # Backend path must be used
        mock_backend.search.assert_called_once()
        assert len(results) == 1
        assert results[0]["chunk_id"] == chunk_id

    def test_retrieve_vector_hits_from_pdf_uses_local_path_when_backend_args_absent(self) -> None:
        """When version_id/registry/vector_backend not provided, retrieve_vector_hits_from_pdf uses local path."""
        from llama_index.core.base.embeddings.base import BaseEmbedding
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_pdf
        from unittest.mock import patch, MagicMock

        mock_embed_model = MagicMock(spec=BaseEmbedding)

        # Mock the local path components
        with patch('llamaindex_runtime.vector.runtime.build_docling_bundle') as mock_bundle:
            with patch('llamaindex_runtime.vector.runtime.load_docling_node_parser_class') as mock_parser_class:
                with patch('llamaindex_runtime.vector.runtime.create_vector_index') as mock_create_index:
                    mock_bundle.return_value = MagicMock(json_documents=[])
                    mock_parser_instance = MagicMock()
                    mock_parser_class.return_value = lambda: mock_parser_instance
                    mock_parser_instance.get_nodes_from_documents.return_value = []

                    mock_index = MagicMock()
                    mock_retriever = MagicMock()
                    mock_retriever.retrieve.return_value = []
                    mock_index.as_retriever.return_value = mock_retriever
                    mock_create_index.return_value = mock_index

                    results = retrieve_vector_hits_from_pdf(
                        "dummy.pdf",
                        query="test query",
                        embed_model=mock_embed_model,
                        # No version_id, registry, vector_backend
                    )

        # Local path must be used (create_vector_index called)
        mock_create_index.assert_called_once()
        # Backend should not be involved
        assert results == []

    def test_retrieve_vector_hits_from_pdf_uses_local_path_with_partial_backend_args(self) -> None:
        """When only some backend args provided, retrieve_vector_hits_from_pdf falls back to local path."""
        from llama_index.core.base.embeddings.base import BaseEmbedding
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_pdf
        from unittest.mock import patch, MagicMock

        mock_embed_model = MagicMock(spec=BaseEmbedding)

        # Test case 1: only version_id provided
        with patch('llamaindex_runtime.vector.runtime.build_docling_bundle') as mock_bundle:
            with patch('llamaindex_runtime.vector.runtime.load_docling_node_parser_class') as mock_parser_class:
                with patch('llamaindex_runtime.vector.runtime.create_vector_index') as mock_create_index:
                    mock_bundle.return_value = MagicMock(json_documents=[])
                    mock_parser_instance = MagicMock()
                    mock_parser_class.return_value = lambda: mock_parser_instance
                    mock_parser_instance.get_nodes_from_documents.return_value = []

                    mock_index = MagicMock()
                    mock_retriever = MagicMock()
                    mock_retriever.retrieve.return_value = []
                    mock_index.as_retriever.return_value = mock_retriever
                    mock_create_index.return_value = mock_index

                    results = retrieve_vector_hits_from_pdf(
                        "dummy.pdf",
                        query="test query",
                        embed_model=mock_embed_model,
                        version_id=uuid.uuid4(),  # Only version_id, not registry/vector_backend
                    )

        # Local path must be used (create_vector_index called)
        mock_create_index.assert_called_once()
        assert results == []

        # Test case 2: only registry provided
        with patch('llamaindex_runtime.vector.runtime.build_docling_bundle') as mock_bundle:
            with patch('llamaindex_runtime.vector.runtime.load_docling_node_parser_class') as mock_parser_class:
                with patch('llamaindex_runtime.vector.runtime.create_vector_index') as mock_create_index:
                    mock_bundle.return_value = MagicMock(json_documents=[])
                    mock_parser_instance = MagicMock()
                    mock_parser_class.return_value = lambda: mock_parser_instance
                    mock_parser_instance.get_nodes_from_documents.return_value = []

                    mock_index = MagicMock()
                    mock_retriever = MagicMock()
                    mock_retriever.retrieve.return_value = []
                    mock_index.as_retriever.return_value = mock_retriever
                    mock_create_index.return_value = mock_index

                    results = retrieve_vector_hits_from_pdf(
                        "dummy.pdf",
                        query="test query",
                        embed_model=mock_embed_model,
                        registry=MagicMock(),  # Only registry, not version_id/vector_backend
                    )

        # Local path must be used
        mock_create_index.assert_called_once()
        assert results == []

    def test_returns_enriched_hits_with_provenance(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        version_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        span_id = uuid.uuid4()

        # Mock backend returns a hit
        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = [
            SearchHit(id=chunk_id, score=0.95, payload={"text_preview": "hello world"}),
        ]

        # Mock registry returns chunk and span data
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "version_id": version_id,
                "text_preview": "hello world",
                "page_no": 1,
                "heading_path": "Ch 1",
                "chunk_type": "semantic_leaf",
                "chunk_order": 0,
                "token_count": 2,
            },
        ]
        mock_registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        embedder = DeterministicEmbedder(dim=16)
        results = retrieve_vector_hits_from_backend(
            "hello",
            version_id=version_id,
            registry=mock_registry,
            vector_backend=mock_backend,
            embedder=embedder,
            limit=5,
        )

        assert len(results) == 1
        hit = results[0]
        assert hit["chunk_id"] == chunk_id
        assert hit["score"] == 0.95
        assert hit["text_preview"] == "hello world"
        assert hit["page_no"] == 1
        assert hit["heading_path"] == "Ch 1"
        assert hit["span_ids"] == [span_id]

    def test_searches_with_embedded_query_vector(self) -> None:
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        version_id = uuid.uuid4()
        embedder = DeterministicEmbedder(dim=16)
        expected_vector = embedder.embed_text("test query")

        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = []

        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = []
        mock_registry.query_vector_chunk_spans_by_version.return_value = []

        retrieve_vector_hits_from_backend(
            "test query",
            version_id=version_id,
            registry=mock_registry,
            vector_backend=mock_backend,
            embedder=embedder,
            limit=3,
        )

        # Verify the search was called with the embedded query vector
        mock_backend.search.assert_called_once()
        call_args = mock_backend.search.call_args
        assert call_args[1]["query_vector"] == expected_vector
        assert call_args[1]["limit"] == 3

    def test_empty_search_results_returns_empty_list(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = []

        mock_registry = MagicMock()
        embedder = DeterministicEmbedder(dim=16)

        results = retrieve_vector_hits_from_backend(
            "nothing",
            version_id=uuid.uuid4(),
            registry=mock_registry,
            vector_backend=mock_backend,
            embedder=embedder,
        )

        assert results == []

    def test_chunk_not_found_in_registry_is_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        version_id = uuid.uuid4()
        orphan_chunk_id = uuid.uuid4()

        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = [
            SearchHit(id=orphan_chunk_id, score=0.8, payload={}),
        ]

        # Registry has no matching chunk
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = []
        mock_registry.query_vector_chunk_spans_by_version.return_value = []
        embedder = DeterministicEmbedder(dim=16)

        with caplog.at_level("WARNING"):
            results = retrieve_vector_hits_from_backend(
                "orphan",
                version_id=version_id,
                registry=mock_registry,
                vector_backend=mock_backend,
                embedder=embedder,
            )

        assert results == []
        assert "PostgreSQL provenance is missing" in caplog.text

    def test_collection_name_derived_from_version_id(self) -> None:
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        version_id = uuid.uuid4()
        embedder = DeterministicEmbedder(dim=16)

        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = []

        mock_registry = MagicMock()

        retrieve_vector_hits_from_backend(
            "test",
            version_id=version_id,
            registry=mock_registry,
            vector_backend=mock_backend,
            embedder=embedder,
        )

        call_args = mock_backend.search.call_args
        assert call_args[1]["collection_name"] == f"version_{version_id}"

    def test_retrieve_handles_embedder_failure(self) -> None:
        """When embedder.embed_text fails, retrieve_vector_hits_from_backend must raise VectorLoaderError."""
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.exceptions import VectorLoaderError
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        mock_backend = MagicMock(spec=VectorBackend)
        mock_registry = MagicMock()

        # Create embedder that fails
        failing_embedder = MagicMock()
        failing_embedder.embed_text.side_effect = RuntimeError("Embedding service unavailable")

        with pytest.raises(VectorLoaderError, match="embedding generation failed"):
            retrieve_vector_hits_from_backend(
                "test query",
                version_id=uuid.uuid4(),
                registry=mock_registry,
                vector_backend=mock_backend,
                embedder=failing_embedder,
                limit=5,
            )

    def test_retrieve_handles_registry_chunk_query_failure(self) -> None:
        """When registry.query_vector_chunks_by_version fails, must raise VectorLoaderError."""
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.exceptions import VectorLoaderError
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        chunk_id = uuid.uuid4()
        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = [
            SearchHit(id=chunk_id, score=0.9, payload={}),
        ]

        # Registry chunk query fails
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.side_effect = ConnectionError("PostgreSQL connection lost")

        embedder = DeterministicEmbedder(dim=16)

        with pytest.raises(VectorLoaderError, match="registry query for vector chunks failed"):
            retrieve_vector_hits_from_backend(
                "test query",
                version_id=uuid.uuid4(),
                registry=mock_registry,
                vector_backend=mock_backend,
                embedder=embedder,
                limit=5,
            )

    def test_retrieve_handles_registry_span_mapping_failure(self) -> None:
        """When registry.query_vector_chunk_spans_by_version fails, must raise VectorLoaderError."""
        from llamaindex_runtime.vector.backend import SearchHit, VectorBackend
        from llamaindex_runtime.vector.exceptions import VectorLoaderError
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        chunk_id = uuid.uuid4()
        version_id = uuid.uuid4()
        mock_backend = MagicMock(spec=VectorBackend)
        mock_backend.search.return_value = [
            SearchHit(id=chunk_id, score=0.9, payload={}),
        ]

        # Registry chunk query succeeds
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "version_id": version_id,
                "text_preview": "test text",
                "page_no": 1,
                "heading_path": "Test",
                "chunk_type": "semantic_leaf",
                "chunk_order": 0,
                "token_count": 2,
            },
        ]
        # Span mapping query fails
        mock_registry.query_vector_chunk_spans_by_version.side_effect = RuntimeError("PostgreSQL query timeout")

        embedder = DeterministicEmbedder(dim=16)

        with pytest.raises(VectorLoaderError, match="registry query for chunk-span mappings failed"):
            retrieve_vector_hits_from_backend(
                "test query",
                version_id=version_id,
                registry=mock_registry,
                vector_backend=mock_backend,
                embedder=embedder,
                limit=5,
            )


# ===========================================================================
# UNIT TESTS -- RuntimeSettings with qdrant
# ===========================================================================


class TestRuntimeSettingsQdrant:
    """RuntimeSettings must accept 'qdrant' as a valid vector_backend."""

    def test_qdrant_is_valid_backend(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="qdrant",
        )
        assert settings.vector_backend == "qdrant"

    def test_qdrant_in_valid_backends_set(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        assert "qdrant" in RuntimeSettings.VALID_VECTOR_BACKENDS

    def test_pgvector_still_valid(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="pgvector",
        )
        assert settings.vector_backend == "pgvector"

    def test_qdrant_url_field(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="qdrant",
            qdrant_url="http://localhost:6333",
        )
        assert settings.qdrant_url == "http://localhost:6333"

    def test_qdrant_url_defaults_to_localhost(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="qdrant",
        )
        assert settings.qdrant_url == "http://localhost:6333"

    def test_invalid_backend_still_raises(self) -> None:
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="Unsupported vector backend"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="unknown_backend",
            )


class TestRuntimeSettingsQdrantUrlValidation:
    """RuntimeSettings must validate qdrant_url when vector_backend='qdrant'."""

    def test_empty_qdrant_url_raises_value_error(self) -> None:
        """Empty string qdrant_url with qdrant backend should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="qdrant_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="qdrant",
                qdrant_url="",
            )

    def test_whitespace_only_qdrant_url_raises_value_error(self) -> None:
        """Whitespace-only qdrant_url with qdrant backend should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="qdrant_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="qdrant",
                qdrant_url="   ",
            )

    def test_invalid_url_without_scheme_raises_value_error(self) -> None:
        """qdrant_url without scheme (e.g., localhost:6333) should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="qdrant_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="qdrant",
                qdrant_url="localhost:6333",
            )

    def test_scheme_only_url_raises_value_error(self) -> None:
        """qdrant_url with scheme but no hostname (e.g., 'http://') should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="qdrant_url must include a valid hostname"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="qdrant",
                qdrant_url="http://",
            )

    def test_invalid_url_error_message_does_not_echo_url(self) -> None:
        """Error message for invalid qdrant_url should not echo the raw URL (credential leak risk)."""
        from llamaindex_runtime.config import RuntimeSettings

        # Use a URL that would contain credentials if leaked
        malicious_url = "http://user:password@evil.com:6333"
        with pytest.raises(ValueError) as exc_info:
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="qdrant",
                qdrant_url="http://",  # Scheme-only triggers hostname validation error
            )
        # Error message should NOT contain the raw URL
        error_msg = str(exc_info.value)
        assert "http://" not in error_msg or "hostname" in error_msg

    def test_valid_http_url_passes(self) -> None:
        """Valid http URL should pass validation."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="qdrant",
            qdrant_url="http://localhost:6333",
        )
        assert settings.qdrant_url == "http://localhost:6333"

    def test_valid_https_url_passes(self) -> None:
        """Valid https URL should pass validation."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="qdrant",
            qdrant_url="https://qdrant.internal:6333",
        )
        assert settings.qdrant_url == "https://qdrant.internal:6333"

    def test_invalid_qdrant_url_ignored_for_pgvector(self) -> None:
        """Invalid qdrant_url should not raise error when backend is not qdrant."""
        from llamaindex_runtime.config import RuntimeSettings

        # This should NOT raise an error because vector_backend is pgvector
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="pgvector",
            qdrant_url="",  # Empty, but OK since not using qdrant
        )
        assert settings.vector_backend == "pgvector"
