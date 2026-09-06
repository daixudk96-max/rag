from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import NodeParser

from llamaindex_runtime.ingestion.bundle import build_docling_bundle
from llamaindex_runtime.integration import load_docling_node_parser_class

from .exceptions import VectorLoaderError
from .factory import create_vector_index

if TYPE_CHECKING:
    from .backend import VectorBackend


logger = logging.getLogger(__name__)


def retrieve_vector_hits_from_pdf(
    source_path: str | Path,
    *,
    query: str,
    embed_model: BaseEmbedding,
    similarity_top_k: int = 3,
    node_parser: NodeParser | None = None,
    version_id: uuid.UUID | None = None,
    registry: Any = None,
    vector_backend: "VectorBackend | None" = None,
) -> list[Any]:
    """Retrieve vector hits from a PDF, optionally using a formal backend.

    When version_id, registry, and vector_backend are all provided, delegates to
    the formal backend path (retrieve_vector_hits_from_backend).

    Otherwise, uses the local PDF indexing path (build_docling_bundle + create_vector_index).

    Parameters
    ----------
    source_path:
        Path to the PDF file.
    query:
        Natural-language query string.
    embed_model:
        BaseEmbedding instance for embedding the query.
    similarity_top_k:
        Maximum number of results.
    node_parser:
        Optional NodeParser for chunking (local path only).
    version_id:
        Optional document version ID (backend path only).
    registry:
        Optional RegistryWriter instance (backend path only).
    vector_backend:
        Optional VectorBackend instance (backend path only).

    Returns
    -------
    list[Any]
        For backend path: list of dict with keys chunk_id, score, text_preview, etc.
        For local path: list of NodeWithScore objects from LlamaIndex.
    """
    # Backend path: all three backend args provided
    if version_id is not None and registry is not None and vector_backend is not None:
        # Tiny shim to adapt BaseEmbedding to embedder interface
        class _EmbedderShim:
            def __init__(self, base_embedding: BaseEmbedding):
                self._base_embedding = base_embedding

            def embed_text(self, text: str) -> list[float]:
                """Adapt BaseEmbedding.get_text_embedding to embedder.embed_text interface."""
                return self._base_embedding.get_text_embedding(text)

        embedder_shim = _EmbedderShim(embed_model)
        return retrieve_vector_hits_from_backend(
            query,
            version_id=version_id,
            registry=registry,
            vector_backend=vector_backend,
            embedder=embedder_shim,
            limit=similarity_top_k,
        )

    # Local path: existing behavior
    bundle = build_docling_bundle(source_path)
    parser = node_parser or load_docling_node_parser_class()()
    nodes = parser.get_nodes_from_documents(bundle.json_documents)
    index = create_vector_index(nodes, embed_model=embed_model)
    return list(index.as_retriever(similarity_top_k=similarity_top_k).retrieve(query))


def retrieve_vector_hits_from_backend(
    query_text: str,
    *,
    version_id: uuid.UUID,
    registry: Any,
    vector_backend: VectorBackend,
    embedder: Any,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search a vector backend, then enrich hits with PostgreSQL provenance.

    1. Embed the query text using the provided embedder.
    2. Search the vector backend for the closest vectors.
    3. For each hit, look up chunk metadata and span mappings from the
       PostgreSQL registry to provide full provenance.

    PostgreSQL remains source-of-truth for provenance and mappings.
    The vector backend is only for similarity search.

    Parameters
    ----------
    query_text:
        The natural-language query string.
    version_id:
        The document version to search within.
    registry:
        A RegistryWriter instance for querying chunk and span provenance.
    vector_backend:
        A VectorBackend instance for vector similarity search.
    embedder:
        An embedder with an ``embed_text(text) -> list[float]`` method.
    limit:
        Maximum number of results from the vector search.

    Returns
    -------
    list of dict
        Each dict has keys: chunk_id, score, text_preview, page_no,
        heading_path, span_ids.
    """
    try:
        query_vector = embedder.embed_text(query_text)
    except Exception as exc:
        raise VectorLoaderError(f"embedding generation failed: {exc}") from exc

    collection_name = f"version_{version_id}"

    hits = vector_backend.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=limit,
    )

    if not hits:
        return []

    # Build a lookup of chunk_id -> chunk metadata from PostgreSQL
    try:
        all_chunks = registry.query_vector_chunks_by_version(version_id)
    except Exception as exc:
        raise VectorLoaderError(f"registry query for vector chunks failed: {exc}") from exc

    chunk_lookup: dict[uuid.UUID, dict[str, Any]] = {
        c["chunk_id"]: c for c in all_chunks
    }

    # Build chunk_id -> span_ids mapping from PostgreSQL
    try:
        all_mappings = registry.query_vector_chunk_spans_by_version(version_id)
    except Exception as exc:
        raise VectorLoaderError(f"registry query for chunk-span mappings failed: {exc}") from exc
    chunk_to_spans: dict[uuid.UUID, list[uuid.UUID]] = {}
    for mapping in all_mappings:
        cid = mapping["chunk_id"]
        chunk_to_spans.setdefault(cid, []).append(mapping["span_id"])

    # Enrich each hit with provenance
    results: list[dict[str, Any]] = []
    for hit in hits:
        chunk_data = chunk_lookup.get(hit.id)
        if chunk_data is None:
            logger.warning(
                "vector backend hit skipped because PostgreSQL provenance is missing",
                extra={"chunk_id": str(hit.id), "version_id": str(version_id)},
            )
            continue

        results.append(
            {
                "chunk_id": hit.id,
                "score": hit.score,
                "text_preview": chunk_data.get("text_preview", ""),
                "page_no": chunk_data.get("page_no"),
                "heading_path": chunk_data.get("heading_path"),
                "span_ids": chunk_to_spans.get(hit.id, []),
            }
        )

    return results
