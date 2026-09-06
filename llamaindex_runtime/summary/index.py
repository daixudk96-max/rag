"""Summary index: build and query summary entities.

Summary entities are a first-class view separate from tree nodes:
- Each summary corresponds to a tree node
- summary_text matches the node's summary_text
- Can be queried independently via keyword search
- Persisted to database via registry
"""
from __future__ import annotations

import uuid
from typing import Any

from llamaindex_runtime.entrypoints.types import QueryHit


class SummaryIndex:
    """Build summary entities from tree nodes.

    Summary entities provide a first-class queryable view of tree summaries.
    Each entity references a tree node and contains its summary_text.
    """

    def build_from_tree(
        self,
        *,
        nodes: list[dict[str, Any]],
        version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Build summary entities from tree nodes.

        Parameters
        ----------
        nodes:
            Tree nodes from TreeGenerator.generate_tree().
            Each node must have node_id and summary_text fields.
        version_id:
            Document version these summaries belong to.

        Returns
        -------
        list of summary dicts with keys:
            - summary_id: deterministic UUID5 based on version_id + node_id
            - version_id: document version UUID
            - node_id: reference to tree node
            - summary_text: text from node's summary_text field
        """
        if not nodes:
            return []

        summaries: list[dict[str, Any]] = []
        for node in nodes:
            if node.get("summary_text") is None:
                # Skip nodes without summary_text (empty nodes)
                continue

            summary_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{version_id}:{node['node_id']}",
            )
            summaries.append({
                "summary_id": summary_id,
                "version_id": version_id,
                "node_id": node["node_id"],
                "summary_text": node["summary_text"],
            })

        return summaries


def retrieve_summary_hits(
    registry: Any,
    query: str,
    *,
    version_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[QueryHit]:
    """Search persisted summary entities by keyword and return QueryHit objects.

    Parameters
    ----------
    registry:
        A RegistryWriter with query_summaries_by_keyword support.
    query:
        The keyword search string. Must not be empty or whitespace-only.
    version_id:
        Optional version filter. If provided, only summaries from this
        version are searched.
    limit:
        Maximum number of results. Must be >= 1.

    Returns
    -------
    list[QueryHit]
        Summary match hits with summary_text, score, and provenance metadata.

    Raises
    ------
    ValueError
        If registry is None, query is empty/whitespace, or limit < 1.
    """
    from types import MappingProxyType

    if registry is None:
        raise ValueError("registry is required for summary retrieval")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    rows = registry.query_summaries_by_keyword(
        query=normalized_query,
        version_id=version_id,
        limit=limit,
    )

    hits: list[QueryHit] = []
    for row in rows:
        metadata: dict[str, Any] = {
            "summary_id": row["summary_id"],
            "version_id": row["version_id"],
            "node_id": row["node_id"],
            "heading_path": row.get("heading_path"),
        }
        hits.append(
            QueryHit(
                text=row["summary_text"],
                score=row.get("match_score"),
                metadata=MappingProxyType(metadata),
            )
        )

    return hits