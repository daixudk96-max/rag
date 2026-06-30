"""RetrievalTool - minimal tool wrapper for hybrid retrieval.

Delegates to the query() entrypoint with mode='hybrid', enabling
ReActAgent to use hybrid retrieval as a tool without changing retrieval logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.tools import BaseTool, ToolMetadata, ToolOutput

from llamaindex_runtime.entrypoints.query import query as query_entrypoint
from llamaindex_runtime.vector.backend import VectorBackend


class RetrievalTool(BaseTool):
    """Minimal tool wrapper for hybrid retrieval via query() entrypoint.

    This tool delegates to the query() entrypoint with mode='hybrid', making it
    available as a tool for LlamaIndex agents (e.g., ReActAgent). It preserves
    all retrieval logic in the entrypoint layer.

    Parameters
    ----------
    source_path:
        Path to the source PDF document.
    registry:
        A RegistryWriter instance. Required for keyword path.
    embed_model:
        Embedding model for vector/tree retrieval paths.
    driver:
        Optional Neo4j driver instance for graph path.
    entity_id:
        Optional UUID for graph path (must be paired with driver).
    similarity_top_k:
        Optional top-k for vector/tree backends.
    version_id:
        Optional version filter for keyword search.
    limit:
        Optional maximum results for keyword search.
    depth:
        Optional traversal depth for graph queries.

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
        driver: Any | None = None,
        entity_id: UUID | None = None,
        similarity_top_k: int | None = None,
        version_id: UUID | None = None,
        limit: int | None = None,
        depth: int | None = None,
        vector_backend: Any | None = None,
    ) -> None:
        if registry is None:
            raise ValueError("registry is required for hybrid retrieval")
        if embed_model is None:
            raise ValueError("embed_model is required for hybrid retrieval")
        if vector_backend is not None and not isinstance(vector_backend, VectorBackend):
            raise ValueError("vector_backend must implement the VectorBackend Protocol")

        # Store parameters for later query() call
        self._source_path = source_path
        self._registry = registry
        self._embed_model = embed_model
        self._driver = driver
        self._entity_id = entity_id
        self._similarity_top_k = similarity_top_k
        self._version_id = version_id
        self._limit = limit
        self._depth = depth
        self._vector_backend = vector_backend

        # Set metadata as instance attribute
        self._metadata = ToolMetadata(
            name="hybrid_retrieval",
            description=(
                "Retrieve relevant evidence from a PDF document using hybrid search. "
                "Combines keyword, vector, tree, and optionally graph retrieval paths. "
                "Returns structured evidence hits with scores and metadata."
            ),
        )

    @property
    def metadata(self) -> ToolMetadata:
        """Tool metadata with name and description."""
        return self._metadata

    def __call__(self, query: str) -> ToolOutput:
        """Synchronous call (not supported for async workflow)."""
        raise NotImplementedError(
            "RetrievalTool requires async execution. Use acall() instead."
        )

    async def acall(self, query: str) -> ToolOutput:
        """Execute hybrid retrieval and return ToolOutput.

        This method is async for LlamaIndex tool-interface compatibility.
        The underlying query entrypoint remains synchronous.

        Parameters
        ----------
        query:
            The natural-language query string.

        Returns
        -------
        ToolOutput
            ToolOutput with content containing serialized QueryResult.

        Raises
        ------
        ValueError
            If query is empty or whitespace-only.
        """
        # Validate query
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        # Delegate to query() entrypoint with mode='hybrid'
        result = query_entrypoint(
            source_path=self._source_path,
            query_text=normalized_query,
            mode="hybrid",
            embed_model=self._embed_model,
            registry=self._registry,
            similarity_top_k=self._similarity_top_k,
            version_id=self._version_id,
            limit=self._limit,
            driver=self._driver,
            entity_id=self._entity_id,
            depth=self._depth,
            vector_backend=self._vector_backend,
        )

        # Serialize QueryResult to JSON for ToolOutput content
        # QueryResult is a frozen dataclass with mode, hits, source_path, query
        # Convert UUID objects to strings for JSON serialization
        content = {
            "mode": result.mode,
            "source_path": result.source_path,
            "query": result.query,
            "hits": [
                {
                    "text": hit.text,
                    "score": hit.score,
                    "metadata": {
                        k: str(v) if isinstance(v, UUID) else v
                        for k, v in hit.metadata.items()
                    },
                }
                for hit in result.hits
            ],
        }

        return ToolOutput(
            content=json.dumps(content),
            tool_name=self.metadata.name,
            raw_input={"query": query},
            raw_output=result,
        )