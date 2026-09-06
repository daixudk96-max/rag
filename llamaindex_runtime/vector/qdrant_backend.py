"""Qdrant implementation of the VectorBackend protocol.

Qdrant is only used for vector projection/search.
PostgreSQL remains source-of-truth for provenance and mappings.
"""
from __future__ import annotations

from typing import Any, Sequence
from uuid import UUID

try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:  # pragma: no cover - optional dependency for tests/mock-only environments
    ApiException = ResponseHandlingException = UnexpectedResponse = Exception

from .backend import SearchHit, VectorPoint
from .exceptions import VectorBackendError


def _collection_exists(client: Any, collection_name: str) -> bool:
    """Check whether a collection already exists in the Qdrant client."""
    collections = client.get_collections()
    return any(c.name == collection_name for c in collections.collections)


class QdrantVectorBackend:
    """VectorBackend implementation backed by a Qdrant client.

    Parameters
    ----------
    client:
        A ``qdrant_client.QdrantClient`` instance (or compatible mock).
    embed_dim:
        Dimension of the embedding vectors stored in this backend.
        Used when creating new collections.
    """

    def __init__(self, client: Any, embed_dim: int = 16) -> None:
        self._client = client
        self._embed_dim = embed_dim

    @property
    def embed_dim(self) -> int:
        return self._embed_dim

    def upsert_vectors(
        self,
        collection_name: str,
        points: Sequence[VectorPoint],
    ) -> None:
        """Upsert vector points into a Qdrant collection.

        Creates the collection if it does not already exist.
        Empty point sequences are a no-op.

        Raises
        ------
        VectorBackendError
            If Qdrant client operations fail (connection, timeout, upsert error).
        """
        if not points:
            return

        try:
            if not _collection_exists(self._client, collection_name):
                from qdrant_client.models import Distance, VectorParams

                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self._embed_dim,
                        distance=Distance.COSINE,
                    ),
                )

            from qdrant_client.models import PointStruct

            qdrant_points = [
                PointStruct(
                    id=str(pt.id),
                    vector=pt.vector,
                    payload=pt.payload,
                )
                for pt in points
            ]

            self._client.upsert(
                collection_name=collection_name,
                points=qdrant_points,
            )
        except (
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            ConnectionError,
            TimeoutError,
            RuntimeError,
            OSError,
        ) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[SearchHit]:
        """Search a Qdrant collection for the closest vectors.

        Returns a list of SearchHit dataclass instances.

        Raises
        ------
        VectorBackendError
            If Qdrant client operations fail (connection, timeout, malformed UUID).
        """
        if limit <= 0:
            return []

        try:
            response = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
            )

            hits: list[SearchHit] = []
            for result in response.points:
                try:
                    hit_id = UUID(str(result.id)) if not isinstance(result.id, UUID) else result.id
                except (ValueError, AttributeError) as exc:
                    raise VectorBackendError(
                        "vector backend operation failed: malformed UUID in search result"
                    ) from exc
                payload = result.payload if result.payload is not None else {}
                hits.append(
                    SearchHit(
                        id=hit_id,
                        score=result.score,
                        payload=payload,
                    )
                )
            return hits
        except VectorBackendError:
            # Re-raise VectorBackendError from UUID conversion
            raise
        except (
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            ConnectionError,
            TimeoutError,
            RuntimeError,
            OSError,
        ) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc

    def delete_collection(self, collection_name: str) -> None:
        """Delete a Qdrant collection.

        Raises
        ------
        VectorBackendError
            If Qdrant client operations fail (connection, timeout, delete error).
        """
        try:
            self._client.delete_collection(collection_name=collection_name)
        except (
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            ConnectionError,
            TimeoutError,
            RuntimeError,
            OSError,
        ) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc
