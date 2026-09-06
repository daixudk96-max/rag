"""Hybrid Retrieval Workflow - minimal control-plane slice.

Wraps the existing query() hybrid path without reimplementing retrieval logic.
This is the first LlamaIndex control-plane primitive that orchestrates the
existing data-plane/hybrid retrieval path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, step

from llamaindex_runtime.entrypoints import query
from llamaindex_runtime.vector.backend import VectorBackend


class HybridRetrievalWorkflow(Workflow):
    """Minimal Workflow that wraps the existing hybrid retrieval path.

    This workflow orchestrates keyword, vector, and tree
    retrieval paths by delegating to the existing query() function with
    mode='hybrid'. It returns the same QueryResult shape as query().

    Parameters
    ----------
    source_path:
        Path to the source PDF document.
    registry:
        A RegistryWriter instance. Required for keyword path.
    embed_model:
        Embedding model for vector/tree retrieval paths.
    similarity_top_k:
    similarity_top_k:
        Optional top-k for vector/tree backends.
    version_id:
        Optional version filter for keyword search.
    limit:
        Optional maximum results for keyword search.
    Raises
    ------
    ValueError
        If registry or embed_model are None (required for hybrid mode).
    """

    def __init__(
        self,
        source_path: str | Path,
        registry: Any | None,
        embed_model: BaseEmbedding | None,
        similarity_top_k: int | None = None,
        version_id: UUID | None = None,
        limit: int | None = None,
        vector_backend: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if registry is None:
            raise ValueError("registry is required for hybrid retrieval")
        if embed_model is None:
            raise ValueError("embed_model is required for hybrid retrieval")
        if vector_backend is not None and not isinstance(vector_backend, VectorBackend):
            raise ValueError("vector_backend must implement the VectorBackend Protocol")

        self._source_path = source_path
        self._registry = registry
        self._embed_model = embed_model
        self._similarity_top_k = similarity_top_k
        self._version_id = version_id
        self._limit = limit
        self._vector_backend = vector_backend

    @step
    def run_hybrid_retrieval(self, ev: StartEvent) -> StopEvent:
        """Execute hybrid retrieval and return QueryResult.

        Parameters
        ----------
        ev:
            StartEvent with query_text parameter.

        Returns
        -------
        StopEvent
            StopEvent with result=QueryResult (mode='hybrid', hits, source_path, query).

        Raises
        ------
        ValueError
            If query_text is empty or whitespace-only.
        """
        query_text = ev.get("query_text", "")
        normalized_query = query_text.strip()
        if not normalized_query:
            raise ValueError("query_text must not be empty")

        # Delegate to existing query() with mode='hybrid'
        result = query(
            source_path=self._source_path,
            query_text=normalized_query,
            mode="hybrid",
            embed_model=self._embed_model,
            registry=self._registry,
            similarity_top_k=self._similarity_top_k,
            version_id=self._version_id,
            limit=self._limit,
            vector_backend=self._vector_backend,
        )

        return StopEvent(result=result)