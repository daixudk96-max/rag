"""Tests for the Milvus vector backend implementation.

Unit tests verify:
1. MilvusVectorBackend satisfies VectorBackend protocol
2. RuntimeSettings accepts 'milvus' as valid vector_backend
3. RuntimeSettings validates milvus_url field
4. Basic Milvus backend operations with mocked client (upsert/search/delete)
5. Error handling for connection, timeout, and malformed data
6. Edge cases: empty inputs, zero limit, large batches
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest


class TestVectorPackageExportsMilvus:
    def test_milvus_backend_is_reexported_from_vector_package(self) -> None:
        from llamaindex_runtime.vector import MilvusVectorBackend
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend as DirectMilvusVectorBackend

        assert MilvusVectorBackend is DirectMilvusVectorBackend


# ===========================================================================
# UNIT TESTS -- RuntimeSettings with Milvus
# ===========================================================================


class TestRuntimeSettingsMilvus:
    """RuntimeSettings must accept 'milvus' as a valid vector_backend."""

    def test_milvus_is_valid_backend(self) -> None:
        """RuntimeSettings should accept 'milvus' as vector_backend."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="milvus",
        )
        assert settings.vector_backend == "milvus"

    def test_milvus_in_valid_backends_set(self) -> None:
        """'milvus' should be in VALID_VECTOR_BACKENDS."""
        from llamaindex_runtime.config import RuntimeSettings

        assert "milvus" in RuntimeSettings.VALID_VECTOR_BACKENDS

    def test_milvus_url_field(self) -> None:
        """RuntimeSettings should have milvus_url field."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="milvus",
            milvus_url="http://localhost:19530",
        )
        assert settings.milvus_url == "http://localhost:19530"

    def test_milvus_url_defaults_to_localhost(self) -> None:
        """milvus_url should default to localhost when not provided."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="milvus",
        )
        assert settings.milvus_url == "http://localhost:19530"

    def test_invalid_backend_still_raises(self) -> None:
        """Invalid vector_backend should still raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="Unsupported vector backend"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="unknown_backend",
            )


class TestRuntimeSettingsMilvusUrlValidation:
    """RuntimeSettings must validate milvus_url when vector_backend='milvus'."""

    def test_empty_milvus_url_raises_value_error(self) -> None:
        """Empty string milvus_url with milvus backend should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="milvus_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="milvus",
                milvus_url="",
            )

    def test_whitespace_only_milvus_url_raises_value_error(self) -> None:
        """Whitespace-only milvus_url with milvus backend should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="milvus_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="milvus",
                milvus_url="   ",
            )

    def test_invalid_url_without_scheme_raises_value_error(self) -> None:
        """milvus_url without scheme (e.g., localhost:19530) should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="milvus_url"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="milvus",
                milvus_url="localhost:19530",
            )

    def test_scheme_only_url_raises_value_error(self) -> None:
        """milvus_url with scheme but no hostname (e.g., 'http://') should raise ValueError."""
        from llamaindex_runtime.config import RuntimeSettings

        with pytest.raises(ValueError, match="milvus_url must include a valid hostname"):
            RuntimeSettings(
                database_url="postgresql://localhost/test",
                vector_backend="milvus",
                milvus_url="http://",
            )

    def test_valid_http_url_passes(self) -> None:
        """Valid http URL should pass validation."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="milvus",
            milvus_url="http://localhost:19530",
        )
        assert settings.milvus_url == "http://localhost:19530"

    def test_valid_https_url_passes(self) -> None:
        """Valid https URL should pass validation."""
        from llamaindex_runtime.config import RuntimeSettings

        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="milvus",
            milvus_url="https://milvus.internal:19530",
        )
        assert settings.milvus_url == "https://milvus.internal:19530"

    def test_invalid_milvus_url_ignored_for_pgvector(self) -> None:
        """Invalid milvus_url should not raise error when backend is not milvus."""
        from llamaindex_runtime.config import RuntimeSettings

        # This should NOT raise an error because vector_backend is pgvector
        settings = RuntimeSettings(
            database_url="postgresql://localhost/test",
            vector_backend="pgvector",
            milvus_url="",  # Empty, but OK since not using milvus
        )
        assert settings.vector_backend == "pgvector"


# ===========================================================================
# UNIT TESTS -- MilvusVectorBackend protocol compliance
# ===========================================================================


class TestMilvusBackendProtocol:
    """MilvusVectorBackend must satisfy VectorBackend protocol."""

    def test_milvus_backend_satisfies_protocol(self) -> None:
        """MilvusVectorBackend instance should be recognized as VectorBackend."""
        from llamaindex_runtime.vector.backend import VectorBackend
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        mock_client = MagicMock()
        backend = MilvusVectorBackend(client=mock_client, embed_dim=8)
        assert isinstance(backend, VectorBackend)


# ===========================================================================
# UNIT TESTS -- MilvusVectorBackend with mocked client
# ===========================================================================


class TestMilvusVectorBackend:
    """MilvusVectorBackend: unit tests with mocked Milvus client."""

    def _make_mock_client(self) -> MagicMock:
        """Create a mock Milvus client with default responses."""
        client = MagicMock()
        # Default: no collections exist
        client.has_collection.return_value = False
        # search returns empty results
        client.search.return_value = []
        return client

    def test_upsert_vectors_creates_collection(self) -> None:
        """upsert_vectors should create collection if it doesn't exist."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        uid = uuid.uuid4()
        points = [VectorPoint(id=uid, vector=[1.0, 0.0, 0.0, 0.0], payload={"text": "x"})]
        backend.upsert_vectors("test_collection", points)

        # Collection should be created since it does not exist
        client.create_collection.assert_called_once()
        call_kwargs = client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["metric_type"] == "COSINE"

    def test_upsert_does_not_recreate_existing_collection(self) -> None:
        """upsert_vectors should not recreate existing collection."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        # Simulate the collection already exists
        client.has_collection.return_value = True
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        backend.upsert_vectors("test_collection", points)

        client.create_collection.assert_not_called()

    def test_upsert_vectors_calls_insert_on_client(self) -> None:
        """upsert_vectors should call insert on Milvus client."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [
            VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0], payload={"a": 1}),
            VectorPoint(id=uuid.uuid4(), vector=[0.0, 1.0, 0.0, 0.0], payload={"b": 2}),
        ]
        backend.upsert_vectors("col", points)

        client.insert.assert_called_once()

    def test_upsert_vectors_with_empty_points_is_noop(self) -> None:
        """upsert_vectors with empty points should be no-op."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        backend.upsert_vectors("col", [])

        client.insert.assert_not_called()
        client.create_collection.assert_not_called()

    def test_search_returns_search_hits(self) -> None:
        """search should return list of SearchHit instances."""
        from llamaindex_runtime.vector.backend import SearchHit
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        hit_id = uuid.uuid4()

        # Mock Milvus search result
        # Milvus search returns list of lists (one per query vector)
        mock_result = {
            "id": str(hit_id),
            "distance": 0.08,  # Milvus returns distance (lower = more similar for COSINE)
            "entity": {"text": "found"},
        }
        client.search.return_value = [[mock_result]]  # List of result lists

        backend = MilvusVectorBackend(client=client, embed_dim=4)
        results = backend.search("col", [1.0, 0.0, 0.0, 0.0], limit=5)

        assert len(results) == 1
        assert isinstance(results[0], SearchHit)
        assert results[0].id == hit_id
        # Score should be converted from distance (1 - distance for COSINE)
        assert results[0].score >= 0.0
        assert results[0].payload == {"text": "found"}

    def test_search_calls_client_with_correct_params(self) -> None:
        """search should call Milvus client with correct parameters."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        backend.search("my_col", [0.1, 0.2, 0.3, 0.4], limit=10)

        client.search.assert_called_once()
        call_kwargs = client.search.call_args[1]
        assert call_kwargs["collection_name"] == "my_col"
        assert call_kwargs["data"] == [[0.1, 0.2, 0.3, 0.4]]  # List of query vectors
        assert call_kwargs["limit"] == 10

    def test_search_with_no_results_returns_empty(self) -> None:
        """search with no results should return empty list."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        client.search.return_value = []
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        results = backend.search("col", [0.0, 0.0, 0.0, 0.0])
        assert results == []

    def test_delete_collection_calls_client(self) -> None:
        """delete_collection should call Milvus client drop_collection."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        backend.delete_collection("old_col")

        client.drop_collection.assert_called_once_with("old_col")


class TestMilvusBackendEdgeCases:
    """Edge cases for MilvusVectorBackend."""

    def _make_mock_client(self) -> MagicMock:
        client = MagicMock()
        client.has_collection.return_value = False
        client.search.return_value = []
        return client

    def test_search_with_zero_limit_returns_empty(self) -> None:
        """search with limit=0 should return empty list."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        results = backend.search("col", [0.0, 0.0, 0.0, 0.0], limit=0)
        assert results == []

    def test_upsert_sanitizes_collection_name(self) -> None:
        """Milvus backend should normalize collection names with hyphens."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        backend.upsert_vectors("version_123e4567-e89b-12d3-a456-426614174000", points)

        create_kwargs = client.create_collection.call_args.kwargs
        assert create_kwargs["collection_name"] == "version_123e4567_e89b_12d3_a456_426614174000"

    def test_upsert_with_single_point(self) -> None:
        """upsert_vectors with single point should work."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        backend.upsert_vectors("col", points)
        client.insert.assert_called_once()

    def test_upsert_large_batch(self) -> None:
        """upsert_vectors with large batch should work."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [
            VectorPoint(
                id=uuid.uuid4(),
                vector=[float(i % 4 == 0), float(i % 4 == 1), float(i % 4 == 2), float(i % 4 == 3)],
            )
            for i in range(500)
        ]
        backend.upsert_vectors("col", points)
        client.insert.assert_called_once()

    def test_search_hit_with_null_payload(self) -> None:
        """search should handle null payload in result."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        mock_result = {
            "id": str(uuid.uuid4()),
            "distance": 0.5,
            "entity": None,  # Null payload
        }
        client.search.return_value = [[mock_result]]

        backend = MilvusVectorBackend(client=client, embed_dim=4)
        results = backend.search("col", [1.0, 0.0, 0.0, 0.0])

        assert len(results) == 1
        assert results[0].payload == {}

    def test_embed_dim_stored(self) -> None:
        """MilvusVectorBackend should store embed_dim."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = self._make_mock_client()
        backend = MilvusVectorBackend(client=client, embed_dim=32)
        assert backend.embed_dim == 32


class TestMilvusBackendErrorHandling:
    """Error handling for Milvus backend operations."""

    def test_upsert_handles_client_connection_error(self) -> None:
        """When Milvus client raises connection error, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        client.has_collection.side_effect = ConnectionError("Milvus unreachable")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_client_timeout_error(self) -> None:
        """When Milvus client raises timeout error, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        client.has_collection.return_value = False
        client.create_collection.side_effect = TimeoutError("Milvus timeout")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_milvus_specific_error(self) -> None:
        """When Milvus client raises MilvusException, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusException, MilvusVectorBackend

        client = MagicMock()
        client.has_collection.side_effect = MilvusException("Milvus-specific failure")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_upsert_handles_insert_failure(self) -> None:
        """When Milvus client.insert fails, upsert_vectors must raise VectorBackendError."""
        from llamaindex_runtime.vector.backend import VectorPoint
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        client.has_collection.return_value = False
        client.insert.side_effect = RuntimeError("Milvus insert failed")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        points = [VectorPoint(id=uuid.uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.upsert_vectors("col", points)

    def test_search_handles_client_query_error(self) -> None:
        """When Milvus client.search fails, search must raise VectorBackendError."""
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        client.search.side_effect = ConnectionError("Milvus query failed")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.search("col", [1.0, 0.0, 0.0, 0.0])

    def test_delete_handles_client_error(self) -> None:
        """When Milvus client.drop_collection fails, delete_collection must raise VectorBackendError."""
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        client.drop_collection.side_effect = RuntimeError("Milvus delete failed")
        backend = MilvusVectorBackend(client=client, embed_dim=4)

        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.delete_collection("col")

    def test_search_handles_malformed_uuid_in_result(self) -> None:
        """When Milvus returns malformed UUID string, search must raise VectorBackendError."""
        from llamaindex_runtime.vector.exceptions import VectorBackendError
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend

        client = MagicMock()
        mock_result = {
            "id": "not-a-valid-uuid-string",  # Malformed UUID
            "distance": 0.5,
            "entity": {},
        }
        client.search.return_value = [[mock_result]]

        backend = MilvusVectorBackend(client=client, embed_dim=4)
        with pytest.raises(VectorBackendError, match="vector backend operation failed"):
            backend.search("col", [1.0, 0.0, 0.0, 0.0])


# ===========================================================================
# CANARY TESTS -- retrieve_vector_hits_from_backend with Milvus
# ===========================================================================


class TestRetrieveVectorHitsFromBackendMilvusCanary:
    """Canary: retrieve_vector_hits_from_backend works with MilvusVectorBackend + mocked registry."""

    def test_milvus_backend_roundtrip_with_provenance(self) -> None:
        """retrieve_vector_hits_from_backend should work with MilvusVectorBackend and return enriched dicts."""
        from llamaindex_runtime.vector.backend import SearchHit
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        version_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        span_id = uuid.uuid4()

        # Mock Milvus client
        mock_client = MagicMock()
        mock_client.has_collection.return_value = False
        mock_client.search.return_value = [
            [
                {
                    "id": str(chunk_id),
                    "distance": 0.05,  # Low distance = high similarity for COSINE
                    "entity": {"text_preview": "milvus hit text"},
                }
            ]
        ]

        # Create MilvusVectorBackend with mocked client
        backend = MilvusVectorBackend(client=mock_client, embed_dim=16)

        # Mock registry returns chunk and span data
        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = [
            {
                "chunk_id": chunk_id,
                "version_id": version_id,
                "text_preview": "milvus hit text",
                "page_no": 5,
                "heading_path": "Section > Subsection",
                "chunk_type": "semantic_leaf",
                "chunk_order": 2,
                "token_count": 10,
            },
        ]
        mock_registry.query_vector_chunk_spans_by_version.return_value = [
            {"chunk_id": chunk_id, "span_id": span_id, "ordinal_no": 0},
        ]

        # Create embedder
        embedder = DeterministicEmbedder(dim=16)

        # Call retrieve_vector_hits_from_backend
        results = retrieve_vector_hits_from_backend(
            "test query",
            version_id=version_id,
            registry=mock_registry,
            vector_backend=backend,
            embedder=embedder,
            limit=5,
        )

        # Verify backend search was called
        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs["collection_name"] == f"version_{str(version_id).replace('-', '_')}"
        assert call_kwargs["limit"] == 5

        # Verify registry queries were called
        mock_registry.query_vector_chunks_by_version.assert_called_once_with(version_id)
        mock_registry.query_vector_chunk_spans_by_version.assert_called_once_with(version_id)

        # Verify enriched results
        assert len(results) == 1
        hit = results[0]
        assert hit["chunk_id"] == chunk_id
        assert hit["score"] >= 0.0  # Score should be converted from distance
        assert hit["text_preview"] == "milvus hit text"
        assert hit["page_no"] == 5
        assert hit["heading_path"] == "Section > Subsection"
        assert hit["span_ids"] == [span_id]

    def test_milvus_backend_empty_search_returns_empty_list(self) -> None:
        """retrieve_vector_hits_from_backend with Milvus returning no hits should return empty list."""
        from llamaindex_runtime.vector.milvus_backend import MilvusVectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        version_id = uuid.uuid4()

        # Mock Milvus client returns empty search results
        mock_client = MagicMock()
        mock_client.search.return_value = []

        backend = MilvusVectorBackend(client=mock_client, embed_dim=16)

        mock_registry = MagicMock()
        mock_registry.query_vector_chunks_by_version.return_value = []
        mock_registry.query_vector_chunk_spans_by_version.return_value = []

        embedder = DeterministicEmbedder(dim=16)

        results = retrieve_vector_hits_from_backend(
            "test query",
            version_id=version_id,
            registry=mock_registry,
            vector_backend=backend,
            embedder=embedder,
            limit=5,
        )

        assert results == []
        mock_registry.query_vector_chunks_by_version.assert_not_called()
        mock_registry.query_vector_chunk_spans_by_version.assert_not_called()