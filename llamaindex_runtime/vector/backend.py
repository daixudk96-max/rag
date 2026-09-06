"""Vector backend seam: protocol and data types for pluggable vector stores.

PostgreSQL remains source-of-truth for provenance and mappings.
Vector backends are only for vector projection and similarity search.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class VectorPoint:
    """A point to upsert into a vector store.

    Attributes
    ----------
    id:
        Unique identifier for the point (typically a chunk UUID).
    vector:
        The embedding vector.
    payload:
        Optional key-value metadata stored alongside the vector.
    """

    id: UUID
    vector: list[float]
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchHit:
    """A result from a vector similarity search.

    Attributes
    ----------
    id:
        Unique identifier of the matched point.
    score:
        Similarity score from the search backend.
    payload:
        Metadata payload attached to the matched point.
    """

    id: UUID
    score: float
    payload: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class VectorBackend(Protocol):
    """Protocol for vector store backends.

    Implementations must support upserting vectors, searching by vector,
    and deleting collections.  PostgreSQL remains source-of-truth for
    provenance; the vector backend is only a projection/search layer.
    """

    def upsert_vectors(
        self,
        collection_name: str,
        points: Sequence[VectorPoint],
    ) -> None: ...

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[SearchHit]: ...

    def delete_collection(self, collection_name: str) -> None: ...
