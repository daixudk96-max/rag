"""Unified query entrypoint for Phase 1 formal runtime.

Routes to vector, tree, keyword, or hybrid retrieval. Auto mode uses
the query classifier to choose the best single backend. Hybrid mode composes
keyword, vector, and tree primitives.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

from llama_index.core.base.embeddings.base import BaseEmbedding

from llamaindex_runtime.analysis.fusion import fuse_candidates
from llamaindex_runtime.keyword import retrieve_keyword_hits
from llamaindex_runtime.tree import retrieve_tree_hits_from_pdf
from llamaindex_runtime.vector import retrieve_vector_hits_from_pdf
from llamaindex_runtime.vector.backend import VectorBackend

from .classifier import classify_query
from .types import QueryHit, QueryResult

_VALID_MODES: frozenset[str] = frozenset(
    {"vector", "tree", "keyword", "hybrid", "auto"}
)
_MAX_SIMILARITY_TOP_K = 100


def _map_node_to_hit(node_with_score: Any) -> QueryHit:
    """Map a LlamaIndex NodeWithScore-like object to a QueryHit."""
    inner = node_with_score.node
    text = inner.text
    score = node_with_score.score
    metadata = getattr(inner, "metadata", None)
    if metadata is None:
        metadata = MappingProxyType({})
    else:
        metadata = MappingProxyType(dict(metadata))
    return QueryHit(text=text, score=score, metadata=metadata)


def _map_backend_dict_to_hit(hit_dict: dict[str, Any]) -> QueryHit:
    """Map a backend-returned dict to a QueryHit.

    Backend dicts have keys: chunk_id, score, text_preview, page_no,
    heading_path, span_ids.
    """
    text = hit_dict.get("text_preview", "")
    score = hit_dict.get("score")
    # Build metadata from provenance fields
    metadata_dict: dict[str, Any] = {}
    for key in (
        "chunk_id",
        "chunk_id_missing",
        "node_id",
        "page_no",
        "heading_path",
        "span_ids",
        "backend_source",
        "retrieval_path",
    ):
        if key in hit_dict:
            metadata_dict[key] = hit_dict[key]
    metadata = MappingProxyType(metadata_dict)
    return QueryHit(text=text, score=score, metadata=metadata)


def _deduplicate_hits(hits: list[QueryHit]) -> list[QueryHit]:
    """Deduplicate hits by text content, keeping the highest score."""
    best_by_text: dict[str, QueryHit] = {}
    for hit in hits:
        key = hit.text
        if key not in best_by_text:
            best_by_text[key] = hit
        else:
            existing = best_by_text[key]
            # Keep the hit with the higher score; None scores lose to any real score
            existing_score = (
                existing.score if existing.score is not None else float("-inf")
            )
            new_score = hit.score if hit.score is not None else float("-inf")
            if new_score > existing_score:
                best_by_text[key] = hit
    return list(best_by_text.values())


def query(
    source_path: str | Path,
    *,
    query_text: str,
    embed_model: BaseEmbedding | None = None,
    mode: Literal["vector", "tree", "keyword", "hybrid", "auto"],
    similarity_top_k: int | None = None,
    registry: Any | None = None,
    version_id: UUID | None = None,
    limit: int | None = None,
    vector_backend: Any | None = None,
    tree_backend_type: str | None = None,
) -> QueryResult:
    """Route a query to the appropriate retrieval backend.

    Parameters
    ----------
    source_path:
        Path to the source PDF document.
    query_text:
        The natural-language query string.
    embed_model:
        Embedding model used by vector/tree retrieval backends.
        Required when mode is ``"vector"``, ``"tree"``, or ``"hybrid"``
        (or ``"auto"`` when the classifier routes to those backends).
    mode:
        Must be ``"vector"``, ``"tree"``, ``"keyword"``, ``"hybrid"``, or
        ``"auto"``.  ``"auto"`` uses the query classifier to choose.
        ``"hybrid"`` composes keyword, vector, and tree paths.
        (optionally) graph paths.
    similarity_top_k:
        Number of top-k results for vector/tree backends.  Defaults to
        3 for vector, 4 for tree (matching the underlying runtime defaults).
    registry:
        A RegistryWriter instance. Required when mode is ``"keyword"``
        or ``"hybrid"`` (or ``"auto"`` when the classifier routes to keyword).
        For standalone ``"vector"`` mode, the formal backend path is enabled only
        when ``registry``, ``version_id``, and ``vector_backend`` are all provided together.
    version_id:
        Optional version filter for keyword search.
        For standalone ``"vector"`` mode, the formal backend path is enabled only
        when ``version_id``, ``registry``, and ``vector_backend`` are all provided together.
    limit:
        Maximum results for keyword search. Defaults to 50.
        In hybrid mode, also caps the final fused hit count after fusion.
    vector_backend:
    vector_backend:
        A VectorBackend instance. Optional.
        In ``"vector"`` mode, the formal backend path is enabled only when
        ``vector_backend``, ``registry``, and ``version_id`` are all provided together.
        In ``"hybrid"`` mode, the vector leg uses the formal backend path only under
        the same full three-argument condition.
    tree_backend_type:
        Optional tree backend selector for persisted tree retrieval. Defaults to
        the runtime default, which is PageIndex-style ``"reasoning"``. Pass
        ``"embedding"``/``"legacy"``/``"semantic"`` to force the previous
        embedding traversal fallback.

    Returns
    -------
    QueryResult
        Frozen dataclass with the mode, hits, source_path, and query.

    Raises
    ------
    ValueError
        If mode is invalid, query_text is empty, or required parameters
        are missing for the chosen backend.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")

    normalized_query_text = query_text.strip()
    if not normalized_query_text:
        raise ValueError("query_text must not be empty")
    if similarity_top_k is not None and similarity_top_k < 1:
        raise ValueError("similarity_top_k must be >= 1")
    if similarity_top_k is not None and similarity_top_k > _MAX_SIMILARITY_TOP_K:
        raise ValueError(f"similarity_top_k must be <= {_MAX_SIMILARITY_TOP_K}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")
    if vector_backend is not None and not isinstance(vector_backend, VectorBackend):
        raise ValueError("vector_backend must implement the VectorBackend Protocol")

    # Resolve auto mode to a concrete mode
    resolved_mode: Literal["vector", "tree", "keyword", "hybrid"]
    if mode == "auto":
        resolved_mode = classify_query(normalized_query_text)
    else:
        resolved_mode = mode

    resolved_path = Path(source_path)

    # Hybrid mode: compose keyword, vector, and tree
    if resolved_mode == "hybrid":
        if registry is None:
            raise ValueError("registry is required for hybrid mode (keyword path)")
        if embed_model is None:
            raise ValueError(
                "embed_model is required for hybrid mode (vector/tree paths)"
            )

        hits_by_path: dict[str, list[QueryHit]] = {}

        # 1. Keyword path
        kw_limit = limit if limit is not None else 50
        kw_hits = retrieve_keyword_hits(
            registry,
            normalized_query_text,
            version_id=version_id,
            limit=kw_limit,
        )
        hits_by_path["keyword"] = list(kw_hits)

        # 2. Vector path
        vec_top_k = similarity_top_k if similarity_top_k is not None else 3
        # Only pass backend args to vector leg when all three are present
        vec_raw = retrieve_vector_hits_from_pdf(
            resolved_path,
            query=normalized_query_text,
            embed_model=embed_model,
            similarity_top_k=vec_top_k,
            version_id=(
                version_id if (version_id and registry and vector_backend) else None
            ),
            registry=registry if (version_id and registry and vector_backend) else None,
            vector_backend=(
                vector_backend if (version_id and registry and vector_backend) else None
            ),
        )
        # Backend path returns dicts; local path returns NodeWithScore objects
        if vec_raw and isinstance(vec_raw[0], dict):
            hits_by_path["vector"] = [_map_backend_dict_to_hit(h) for h in vec_raw]
        else:
            hits_by_path["vector"] = [_map_node_to_hit(h) for h in vec_raw]

        # 3. Tree path
        tree_top_k = similarity_top_k if similarity_top_k is not None else 4
        tree_raw = retrieve_tree_hits_from_pdf(
            resolved_path,
            query=normalized_query_text,
            embed_model=embed_model,
            similarity_top_k=tree_top_k,
            registry=registry if version_id is not None else None,
            version_id=version_id,
            backend_type=tree_backend_type,
        )
        if tree_raw and isinstance(tree_raw[0], dict):
            hits_by_path["tree"] = [_map_backend_dict_to_hit(h) for h in tree_raw]
        else:
            hits_by_path["tree"] = [_map_node_to_hit(h) for h in tree_raw]

        # Fuse candidates across paths using RRF-based scoring
        fused = fuse_candidates(hits_by_path)

        # Convert FusedHit back to QueryHit for stable QueryResult shape
        fused_hits: list[QueryHit] = []
        for fh in fused:
            fused_hits.append(
                QueryHit(
                    text=fh.text,
                    score=fh.score,
                    metadata=fh.metadata,
                )
            )

        # Apply final limit cap to fused results if specified
        if limit is not None and len(fused_hits) > limit:
            fused_hits = fused_hits[:limit]

        return QueryResult(
            mode="hybrid",
            hits=tuple(fused_hits),
            source_path=str(resolved_path),
            query=normalized_query_text,
        )

    if resolved_mode == "keyword":
        if registry is None:
            raise ValueError("registry is required for keyword mode")
        kw_limit = limit if limit is not None else 50
        hits = retrieve_keyword_hits(
            registry,
            normalized_query_text,
            version_id=version_id,
            limit=kw_limit,
        )
        return QueryResult(
            mode="keyword",
            hits=tuple(hits),
            source_path=str(resolved_path),
            query=normalized_query_text,
        )

    # Vector and tree modes require an embed_model
    if embed_model is None:
        raise ValueError(f"embed_model is required for {resolved_mode} mode")

    if resolved_mode == "vector":
        top_k = similarity_top_k if similarity_top_k is not None else 3
        raw_hits = retrieve_vector_hits_from_pdf(
            resolved_path,
            query=normalized_query_text,
            embed_model=embed_model,
            similarity_top_k=top_k,
            version_id=version_id,
            registry=registry,
            vector_backend=vector_backend,
        )
        # Backend path returns dicts; local path returns NodeWithScore objects
        if raw_hits and isinstance(raw_hits[0], dict):
            hits = [_map_backend_dict_to_hit(h) for h in raw_hits]
        else:
            hits = [_map_node_to_hit(h) for h in raw_hits]
        return QueryResult(
            mode=resolved_mode,
            hits=tuple(hits),
            source_path=str(resolved_path),
            query=normalized_query_text,
        )
    else:  # resolved_mode == "tree"
        top_k = similarity_top_k if similarity_top_k is not None else 4
        raw_hits = retrieve_tree_hits_from_pdf(
            resolved_path,
            query=normalized_query_text,
            embed_model=embed_model,
            similarity_top_k=top_k,
            registry=registry if version_id is not None else None,
            version_id=version_id,
            backend_type=tree_backend_type,
        )

    if raw_hits and isinstance(raw_hits[0], dict):
        mapped_hits = [_map_backend_dict_to_hit(h) for h in raw_hits]
    else:
        mapped_hits = [_map_node_to_hit(h) for h in raw_hits]

    return QueryResult(
        mode=resolved_mode,
        hits=tuple(mapped_hits),
        source_path=str(resolved_path),
        query=normalized_query_text,
    )
