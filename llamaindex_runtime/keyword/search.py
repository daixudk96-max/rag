"""Keyword retrieval path over persisted canonical spans.

Searches canonical_spans via the RegistryWriter protocol, mapping
database rows to QueryHit objects for integration with the unified
query entrypoint.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID

from llamaindex_runtime.entrypoints.types import QueryHit

if TYPE_CHECKING:
    from llamaindex_runtime.registry.contracts import RegistryWriter


def retrieve_keyword_hits(
    registry: RegistryWriter,
    query: str,
    *,
    version_id: UUID | None = None,
    limit: int = 50,
) -> list[QueryHit]:
    """Search persisted canonical spans by keyword and return QueryHit objects.

    Parameters
    ----------
    registry:
        A RegistryWriter with ``query_spans_by_keyword`` support.
    query:
        The keyword search string. Must not be empty or whitespace-only.
    version_id:
        Optional version filter. If provided, only spans from this
        version are searched.
    limit:
        Maximum number of results. Must be >= 1.

    Returns
    -------
    list[QueryHit]
        Keyword match hits with text, score, and provenance metadata.

    Raises
    ------
    ValueError
        If query is empty/whitespace or limit < 1.
    """
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    rows = registry.query_spans_by_keyword(
        query=normalized_query,
        version_id=version_id,
        limit=limit,
    )

    hits: list[QueryHit] = []
    for row in rows:
        metadata: dict[str, Any] = {
            "span_id": row["span_id"],
            "doc_id": row["doc_id"],
            "version_id": row["version_id"],
            "page_no": row.get("page_no"),
            "heading_path": row.get("heading_path"),
        }
        hits.append(
            QueryHit(
                text=row["raw_text"],
                score=row.get("match_score"),
                metadata=MappingProxyType(metadata),
            )
        )

    return hits
