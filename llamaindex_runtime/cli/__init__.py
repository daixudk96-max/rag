"""CLI module for unified entry surface (P6 productionization slice).

This module provides the minimal external entry surface for formal runtime,
wrapping the existing query() function without reimplementing retrieval logic.

Scope:
- Thin wrapper around llamaindex_runtime.entrypoints public facade
- Input validation
- Structured output (QueryResult or JSON)

NO deployment, monitoring, or ops hardening.
NO retrieval logic rewrite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.entrypoints import query
from llamaindex_runtime.entrypoints.types import QueryResult
from llamaindex_runtime.vector.backend import VectorBackend


_VALID_MODES: frozenset[str] = frozenset(
    {"vector", "tree", "keyword", "hybrid", "auto"}
)


def main(
    source_path: str | Path | None,
    query_text: str | None,
    mode: Literal["vector", "tree", "keyword", "hybrid", "auto"] | None,
    embed_model: BaseEmbedding | None = None,
    registry: Any | None = None,
    version_id: UUID | None = None,
    limit: int | None = None,
    similarity_top_k: int | None = None,
    vector_backend: VectorBackend | None = None,
) -> QueryResult:
    """Unified CLI entry point that wraps existing query() function.

    This is a minimal wrapper that validates inputs and delegates to the
    existing query() function without reimplementing retrieval logic.

    Parameters
    ----------
    source_path:
        Path to the source PDF document. Required.
    query_text:
        The natural-language query string. Required.
    mode:
        Retrieval mode. Must be one of: "vector", "tree", "keyword",
        "hybrid", or "auto". Required.
        "hybrid", or "auto". Required.
    embed_model:
        Embedding model for vector/tree retrieval. Required for vector, tree,
        hybrid modes (or auto when classifier routes to those).
    registry:
        RegistryWriter instance. Required for keyword and hybrid modes.
    version_id:
        Optional version filter for keyword search.
    limit:
        Optional maximum results for keyword search.
    similarity_top_k:
    similarity_top_k:
        Optional top-k for vector/tree backends.
    vector_backend:
        Optional VectorBackend instance. In vector mode, the formal backend
        path is enabled only when vector_backend, registry, and version_id are
        all provided together. In hybrid mode, the vector leg uses the formal
        backend path only under the same three-argument condition.

    Returns
    -------
    QueryResult
        Frozen dataclass with mode, hits, source_path, and query.

    Raises
    ------
    ValueError
        If required parameters are missing or invalid.
    """
    # Validate required parameters
    if source_path is None:
        raise ValueError("source_path is required")

    if query_text is None:
        raise ValueError("query_text is required")

    if mode is None:
        raise ValueError("mode is required")

    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")

    # Delegate to existing query() function (no retrieval logic reimplemented)
    return query(
        source_path=source_path,
        query_text=query_text,
        mode=mode,
        embed_model=embed_model,
        registry=registry,
        version_id=version_id,
        limit=limit,
        similarity_top_k=similarity_top_k,
        vector_backend=vector_backend,
    )


def format_result_as_json(result: QueryResult) -> str:
    """Format QueryResult as JSON string for CLI output.

    Parameters
    ----------
    result:
        QueryResult to format.

    Returns
    -------
    str
        JSON string representation of QueryResult.

    Notes
    -----
    UUID objects are converted to strings for JSON serialization.
    """
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

    return json.dumps(content, indent=2)


__all__ = ["main", "format_result_as_json"]
