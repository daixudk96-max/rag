"""Leaf->parent rollup query and multi-granular expansion over persisted tree data.

Provides TreeRollupQuery for navigating the tree hierarchy stored in
tree_nodes and tree_node_spans tables, with provenance traceability
back to canonical spans.

Expansion methods:
- expand_children: get all children of a node (downward)
- expand_siblings: get all nodes with the same parent (lateral)
- expand_adjacent: get nodes within page proximity (sequential)
"""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row


class TreeRollupQuery:
    """Query methods for navigating the persisted tree hierarchy.

    All methods operate on the database tables tree_nodes and tree_node_spans,
    not on transient LlamaIndex runtime objects.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def rollup_to_parent(self, node_id: uuid.UUID) -> dict[str, Any] | None:
        """Return the parent node of the given node, or None if it is a root.

        Parameters
        ----------
        node_id : UUID
            The node to look up.

        Returns
        -------
        dict or None
            The parent node dict, or None if the node is a root.

        Raises
        ------
        ValueError
            If node_id does not exist in tree_nodes.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT parent_node_id FROM tree_nodes WHERE node_id = %s",
                (str(node_id),),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"node not found: {node_id}")
            parent_node_id = row["parent_node_id"]
            if parent_node_id is None:
                return None
            cur.execute(
                "SELECT node_id, version_id, parent_node_id, node_type, level_no, "
                "title, heading_path, page_start, page_end, summary_text, created_at "
                "FROM tree_nodes WHERE node_id = %s",
                (str(parent_node_id),),
            )
            parent = cur.fetchone()
        if parent is None:
            return None
        return self._coerce_node_row(parent)

    def rollup_chain(self, node_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return the full chain from the given node up to the root.

        The chain is ordered [node, parent, ..., root]. The first element
        is the starting node, the last is the root (parent_node_id is None).

        Parameters
        ----------
        node_id : UUID
            The starting node.

        Returns
        -------
        list of dict
            Ordered list from the starting node to the root.

        Raises
        ------
        ValueError
            If node_id does not exist in tree_nodes.
        """
        chain: list[dict[str, Any]] = []
        visited: set[uuid.UUID] = set()
        current_id = node_id

        while current_id is not None:
            if current_id in visited:
                break  # cycle safety
            visited.add(current_id)

            with self._connection.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT node_id, version_id, parent_node_id, node_type, level_no, "
                    "title, heading_path, page_start, page_end, summary_text, created_at "
                    "FROM tree_nodes WHERE node_id = %s",
                    (str(current_id),),
                )
                node = cur.fetchone()

            if node is None:
                if len(chain) == 0:
                    raise ValueError(f"node not found: {node_id}")
                break

            chain.append(self._coerce_node_row(node))
            current_id = node["parent_node_id"]

        return chain

    def get_node_spans(self, node_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return the canonical spans linked to a tree node via tree_node_spans.

        Spans are ordered by ordinal_no to preserve their original sequence.

        Parameters
        ----------
        node_id : UUID
            The tree node whose spans to retrieve.

        Returns
        -------
        list of dict
            Canonical span dicts with all columns from canonical_spans.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT cs.span_id, cs.span_kind, cs.start_offset, cs.end_offset, "
                "cs.page_no, cs.heading_path, cs.raw_text "
                "FROM tree_node_spans tns "
                "JOIN canonical_spans cs ON tns.span_id = cs.span_id "
                "WHERE tns.node_id = %s "
                "ORDER BY tns.ordinal_no",
                (str(node_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            row["span_id"] = uuid.UUID(str(row["span_id"]))
            result.append(row)
        return result

    def resolve_span_provenance(self, span_id: uuid.UUID) -> dict[str, Any] | None:
        """Trace a canonical span back to its tree node and parent chain.

        Parameters
        ----------
        span_id : UUID
            The canonical span to trace.

        Returns
        -------
        dict or None
            Dict with keys:
              - "node": the tree node this span is linked to
              - "chain": the full chain from that node to root
            Or None if the span is not linked to any tree node.
        """
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT node_id FROM tree_node_spans WHERE span_id = %s LIMIT 1",
                (str(span_id),),
            )
            link = cur.fetchone()

        if link is None:
            return None

        node_id = uuid.UUID(str(link["node_id"]))
        chain = self.rollup_chain(node_id)

        return {
            "node": chain[0],
            "chain": chain,
        }

    def expand_children(self, node_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all children of the given node.

        Parameters
        ----------
        node_id : UUID
            The parent node whose children to retrieve.

        Returns
        -------
        list of dict
            List of child node dicts.

        Raises
        ------
        ValueError
            If node_id does not exist in tree_nodes.
        """
        # Verify the node exists
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT node_id FROM tree_nodes WHERE node_id = %s",
                (str(node_id),),
            )
            if cur.fetchone() is None:
                raise ValueError(f"node not found: {node_id}")

            # Fetch all children
            cur.execute(
                "SELECT node_id, version_id, parent_node_id, node_type, level_no, "
                "title, heading_path, page_start, page_end, summary_text, created_at "
                "FROM tree_nodes WHERE parent_node_id = %s",
                (str(node_id),),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(self._coerce_node_row(row))
        return result

    def expand_siblings(self, node_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all siblings of the given node, including itself.

        Siblings are all nodes with the same parent_node_id.

        Parameters
        ----------
        node_id : UUID
            The node whose siblings to retrieve.

        Returns
        -------
        list of dict
            List of sibling node dicts, including the node itself.

        Raises
        ------
        ValueError
            If node_id does not exist in tree_nodes.
        """
        # Get the parent_node_id of the node
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT parent_node_id FROM tree_nodes WHERE node_id = %s",
                (str(node_id),),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"node not found: {node_id}")
            parent_node_id = row["parent_node_id"]

            # Fetch all nodes with the same parent
            cur.execute(
                "SELECT node_id, version_id, parent_node_id, node_type, level_no, "
                "title, heading_path, page_start, page_end, summary_text, created_at "
                "FROM tree_nodes WHERE parent_node_id = %s",
                (str(parent_node_id) if parent_node_id is not None else None,),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(self._coerce_node_row(row))
        return result

    def expand_adjacent(
        self, node_id: uuid.UUID, page_threshold: int = 5
    ) -> list[dict[str, Any]]:
        """Return nodes adjacent to the given node based on page proximity.

        Adjacent nodes are those whose page_start is within page_threshold
        of the target node's page_start.

        Parameters
        ----------
        node_id : UUID
            The node whose adjacent nodes to retrieve.
        page_threshold : int
            Maximum page distance to consider adjacent. Default 5.

        Returns
        -------
        list of dict
            List of adjacent node dicts.

        Raises
        ------
        ValueError
            If node_id does not exist in tree_nodes.
        """
        # Get the page range of the target node
        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT page_start, page_end FROM tree_nodes WHERE node_id = %s",
                (str(node_id),),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"node not found: {node_id}")

            page_start = row.get("page_start")
            if page_start is None:
                return []  # No page info, cannot determine adjacency

            # Fetch nodes within page threshold
            cur.execute(
                "SELECT node_id, version_id, parent_node_id, node_type, level_no, "
                "title, heading_path, page_start, page_end, summary_text, created_at "
                "FROM tree_nodes WHERE page_start IS NOT NULL "
                "AND ABS(page_start - %s) <= %s",
                (page_start, page_threshold),
            )
            rows = cur.fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(self._coerce_node_row(row))
        return result

    @staticmethod
    def _coerce_node_row(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce UUID string fields back to uuid.UUID objects without mutating input."""
        coerced = dict(row)
        coerced["node_id"] = uuid.UUID(str(row["node_id"]))
        coerced["version_id"] = uuid.UUID(str(row["version_id"]))
        if row.get("parent_node_id") is not None:
            coerced["parent_node_id"] = uuid.UUID(str(row["parent_node_id"]))
        return coerced
