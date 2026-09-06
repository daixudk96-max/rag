"""Hierarchical scoring for tree nodes based on summary_text content matching.

Provides TreeScoring for computing relevance scores between nodes and queries,
with hierarchical propagation from leaf nodes to parent nodes.
"""
from __future__ import annotations

import re
from typing import Any


class TreeScoring:
    """Score tree nodes based on how well their summary_text matches a query."""

    def score_node(self, node: dict[str, Any], query: str) -> float:
        """Compute a relevance score for a node given a query string.

        Scoring strategy:
        - If node has no summary_text, return 0.0
        - Compute text overlap between query terms and summary_text
        - Use simple term frequency approach (can be enhanced later)

        Parameters
        ----------
        node : dict
            Node dict with at least "summary_text" field.
        query : str
            Query string to match against.

        Returns
        -------
        float
            Relevance score between 0.0 and 1.0.
        """
        if query is None:
            raise ValueError("query must not be None")

        summary_text = node.get("summary_text")
        if not summary_text:
            return 0.0

        # Normalize texts
        query_terms = set(self._normalize_text(query).split())
        summary_terms = set(self._normalize_text(summary_text).split())

        if not query_terms:
            return 0.0

        # Compute overlap: Jaccard similarity
        intersection = query_terms & summary_terms
        union = query_terms | summary_terms

        if not union:
            return 0.0

        score = len(intersection) / len(union)

        # Boost score if multiple query terms match
        if len(intersection) > 1:
            score *= 1.2  # 20% boost for multi-term match

        # Cap at 1.0
        return min(score, 1.0)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching: lowercase, remove punctuation."""
        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        # Normalize whitespace
        text = ' '.join(text.split())
        return text