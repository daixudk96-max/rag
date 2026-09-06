"""Milvus implementation of the VectorBackend protocol.

Milvus is only used for vector projection/search.
PostgreSQL remains source-of-truth for provenance and mappings.
"""
from __future__ import annotations

from typing import Any, Sequence
from uuid import UUID

try:
    from pymilvus.exceptions import MilvusException
except ImportError:  # pragma: no cover - optional dependency for tests/mock-only environments
    MilvusException = Exception

from .backend import SearchHit, VectorPoint
from .exceptions import VectorBackendError


_MAX_SIGNED_INT64 = (1 << 63) - 1


def _normalize_collection_name(collection_name: str) -> str:
    return collection_name.replace("-", "_")


def _uuid_to_milvus_id(value: UUID) -> int:
    return value.int & _MAX_SIGNED_INT64


class MilvusVectorBackend:
    """VectorBackend implementation backed by a Milvus client.

    Parameters
    ----------
    client:
        A ``pymilvus.MilvusClient`` instance (or compatible mock).
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
        """Upsert vector points into a Milvus collection.

        Creates the collection if it does not already exist.
        Empty point sequences are a no-op.

        Raises
        ------
        VectorBackendError
            If Milvus client operations fail (connection, timeout, insert error).
        """
        if not points:
            return

        normalized_collection_name = _normalize_collection_name(collection_name)

        try:
            # Create collection if it doesn't exist
            if not self._client.has_collection(normalized_collection_name):
                self._client.create_collection(
                    collection_name=normalized_collection_name,
                    dimension=self._embed_dim,
                    metric_type="COSINE",
                )

            # Prepare data for Milvus insert
            # Milvus expects: [{"id": str, "vector": list[float], **payload}]
            data = [
                {
                    "id": _uuid_to_milvus_id(pt.id),
                    "chunk_uuid": str(pt.id),
                    "vector": pt.vector,
                    **pt.payload,
                }
                for pt in points
            ]

            self._client.insert(
                collection_name=normalized_collection_name,
                data=data,
            )
        except (MilvusException, ConnectionError, TimeoutError, RuntimeError, OSError) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[SearchHit]:
        """Search a Milvus collection for the closest vectors.

        Returns a list of SearchHit dataclass instances.

        Raises
        ------
        VectorBackendError
            If Milvus client operations fail (connection, timeout, malformed UUID).
        """
        if limit <= 0:
            return []

        normalized_collection_name = _normalize_collection_name(collection_name)

        try:
            # Milvus search expects query_vector as list of lists
            # and defaults to COSINE distance. We convert with 1 - distance.
            results = self._client.search(
                collection_name=normalized_collection_name,
                data=[query_vector],
                limit=limit,
                output_fields=["*"],  # Return all payload fields
            )

            hits: list[SearchHit] = []
            # Milvus returns list of result lists (one per query vector)
            for result_list in results:
                for result in result_list:
                    entity = result.get("entity", {})
                    payload = entity if entity is not None else {}
                    try:
                        chunk_uuid = payload.get("chunk_uuid")
                        if chunk_uuid is not None:
                            hit_id = UUID(str(chunk_uuid))
                        else:
                            hit_id = UUID(str(result.get("id")))
                    except (ValueError, AttributeError) as exc:
                        raise VectorBackendError(
                            "vector backend operation failed: malformed UUID in search result"
                        ) from exc

                    # Milvus returns distance (lower = more similar for COSINE)
                    # Convert to similarity score (1 - distance for COSINE metric)
                    distance = result.get("distance", 0.0)
                    score = 1.0 - distance

                    hits.append(
                        SearchHit(
                            id=hit_id,
                            score=score,
                            payload=payload,
                        )
                    )
            return hits
        except VectorBackendError:
            # Re-raise VectorBackendError from UUID conversion
            raise
        except (MilvusException, ConnectionError, TimeoutError, RuntimeError, OSError) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc

    def delete_collection(self, collection_name: str) -> None:
        """Delete a Milvus collection.

        Raises
        ------
        VectorBackendError
            If Milvus client operations fail (connection, timeout, delete error).
        """
        try:
            self._client.drop_collection(_normalize_collection_name(collection_name))
        except (MilvusException, ConnectionError, TimeoutError, RuntimeError, OSError) as exc:
            raise VectorBackendError(f"vector backend operation failed: {exc}") from exc