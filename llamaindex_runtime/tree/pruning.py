"""Branch pruning for tree nodes based on relevance scores.

Provides TreePruning for marking low-score nodes as pruned while preserving
span-node links for provenance integrity.
"""
from __future__ import annotations

from typing import Any

from .scoring import TreeScoring


class TreePruning:
    """Prune tree branches based on relevance scores below a threshold."""

    def __init__(self, threshold: float = 0.3) -> None:
        """Initialize pruning with a score threshold.

        Parameters
        ----------
        threshold : float
            Minimum score required to keep a node unpruned. Default 0.3.
        """
        self.threshold = threshold
        self._scorer = TreeScoring()

    def prune_tree(
        self,
        nodes: list[dict[str, Any]],
        node_spans: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Prune tree nodes based on scores, preserving span links.

        Parameters
        ----------
        nodes : list of dict
            Node dicts with "score" field added.
        node_spans : list of dict
            Span-node link dicts with "node_id" and "span_id".

        Returns
        -------
        dict with keys "nodes" and "node_spans".
            Nodes have "pruned" field added (True/False).
            node_spans unchanged (provenance preserved).
        """
        pruned_nodes = []
        for node in nodes:
            score = node.get("score", 0.0)
            is_pruned = score < self.threshold
            pruned_node = {**node, "pruned": is_pruned}
            pruned_nodes.append(pruned_node)

        # node_spans unchanged to preserve provenance
        return {
            "nodes": pruned_nodes,
            "node_spans": node_spans,
        }

    def prune_nodes(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prune nodes list based on scores, marking low-score nodes.

        Parameters
        ----------
        nodes : list of dict
            Node dicts with "score" field added.

        Returns
        -------
        list of dict
            Nodes with "pruned" field added (True/False).
        """
        pruned_nodes = []
        for node in nodes:
            score = node.get("score", 0.0)
            is_pruned = score < self.threshold
            pruned_node = {**node, "pruned": is_pruned}
            pruned_nodes.append(pruned_node)

        return pruned_nodes