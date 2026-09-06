"""Tree backend adapter seam: protocol and data types for donor-backed tree build/retrieval.

PostgreSQL remains source-of-truth for provenance and mappings.
Tree backend adapters are only for tree structure build and retrieval projection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class BackendHit:
    """A result from donor-backed tree retrieval.

    This is an intermediate structure between donor adapter and final QueryHit.
    All provenance fields preserve immutable contracts from Phase 1.

    Attributes
    ----------
    score:
        Similarity/relevance score from donor backend (optional for some donors).
    text_preview:
        Preview text for display (may be truncated).
    heading_path:
        Heading hierarchy from tree structure (e.g., "Section > Subsection").
    page_no:
        Page number provenance (from donor's page-level tree).
    span_ids:
        Span UUIDs linked to this hit (provenance chain).
    node_id:
        Tree node UUID (provenance chain).
    chunk_id:
        Chunk UUID (provenance chain).
    entity_id:
        Entity UUID (optional, may be None for tree-only retrieval).
    relation_id:
        Relation UUID (optional, may be None for tree-only retrieval).

    Phase 2 Extensions (Task 2.4)
    backend_source:
        Backend type provenance ("tree" | "graph" | "vector" | "reasoning").
    retrieval_path:
        Retrieval method within backend ("clustering" | "reasoning" | "keyword" | "embedding").
    """

    score: float | None
    text_preview: str
    heading_path: str | None
    page_no: int | None
    span_ids: Sequence[UUID]
    node_id: UUID
    chunk_id: UUID
    entity_id: UUID | None
    relation_id: UUID | None

    # Phase 2 Task 2.4: Provenance metadata extensions (optional, backward compatible)
    backend_source: str | None = None  # "tree" | "graph" | "vector" | "reasoning"
    retrieval_path: str | None = None  # "clustering" | "reasoning" | "keyword" | "embedding"


@runtime_checkable
class TreeBackendAdapter(Protocol):
    """Protocol for tree backend adapters.

    Implementations must support building tree structure from documents and
    retrieving hits from query. PostgreSQL remains source-of-truth for
    provenance; the tree backend adapter is only a projection/retrieval layer.

    All outputs must be written through registry seam to preserve provenance.
    """

    def index_tree(
        self,
        *,
        source_path: str,
        version_id: UUID,
        registry: Any,  # RegistryWriter protocol from registry/contracts.py
    ) -> None:
        """Build tree structure from source document and write through registry.

        Parameters
        ----------
        source_path:
            Path to source document (PDF, markdown, etc.).
        version_id:
            Version UUID for provenance anchoring.
        registry:
            RegistryWriter seam for persisting tree nodes and spans.
        """
        ...

    def retrieve_tree_hits(
        self,
        *,
        query_text: str,
        version_id: UUID,
        registry: Any,  # RegistryWriter protocol
        limit: int | None = None,
    ) -> list[BackendHit]:
        """Retrieve tree hits from query and return BackendHit list.

        Parameters
        ----------
        query_text:
            Query text for retrieval.
        version_id:
            Version UUID to query.
        registry:
            RegistryWriter seam for reading persisted tree structure.
        limit:
            Optional limit on number of hits.

        Returns
        -------
        list[BackendHit]
            Intermediate hits from donor backend. These must be mapped to
            QueryHit through registry write-back to preserve provenance.
        """
        ...