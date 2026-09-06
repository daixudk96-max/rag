"""Hit-distribution analyzer over structured QueryHit tuples.

Composes on top of Phase 6 deep hybrid output. Accepts a tuple of QueryHit
objects and derives ancestor-score rollup, CV, and entropy from the
heading_path hierarchy embedded in each hit's metadata.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

from llamaindex_runtime.entrypoints.types import QueryHit

from .decision import decide_expansion
from .types import (
    AncestorScore,
    DistributionSignals,
    HitDistributionResult,
)


class HitDistributionAnalyzer:
    """Analyzes hit distribution across heading-path ancestors.

    Parameters
    ----------
    separator:
        The delimiter used within heading_path strings to denote hierarchy
        levels. Defaults to ``" > "``.
    """

    def __init__(self, separator: str = " > ") -> None:
        self._separator = separator

    def analyze(self, hits: tuple[QueryHit, ...]) -> HitDistributionResult:
        """Analyze hit distribution and return concentration/dispersion signals.

        Parameters
        ----------
        hits:
            Tuple of QueryHit objects from Phase 6 hybrid output. Each hit's
            ``metadata`` may contain a ``heading_path`` key. Hits without
            ``heading_path`` are treated as root-level leaves using their text
            content as the leaf identifier.

        Returns
        -------
        HitDistributionResult
            Frozen dataclass with ancestor_scores, signals, decision, and metadata.

        Raises
        ------
        ValueError
            If ``hits`` is empty.
        """
        if not hits:
            raise ValueError("hits cannot be empty")

        # Build ancestor score rollup from heading paths
        score_map: dict[str, float] = defaultdict(float)
        leaf_count: dict[str, int] = defaultdict(int)

        for hit in hits:
            # Treat None scores as 0.0 (e.g., graph hits)
            hit_score = hit.score if hit.score is not None else 0.0

            heading_path = hit.metadata.get("heading_path")
            if heading_path is None:
                # Use text as leaf identifier; no parent rollup
                leaf_key = hit.text
                score_map[leaf_key] += hit_score
                leaf_count[leaf_key] += 1
                continue

            # Roll up score along the heading path hierarchy
            ancestors = self._split_path(heading_path)
            for ancestor_path in ancestors:
                score_map[ancestor_path] += hit_score
                leaf_count[ancestor_path] += 1

        ancestor_scores = tuple(
            AncestorScore(
                heading_path=path,
                accumulated_score=score,
                contributing_leaves_count=leaf_count[path],
                depth=self._depth_of(path),
            )
            for path, score in sorted(score_map.items())
        )

        # Compute CV and entropy on ancestor accumulated scores
        values = [a.accumulated_score for a in ancestor_scores]
        cv = self._compute_cv(values)
        entropy = self._compute_entropy(values)
        max_entropy = math.log2(len(values)) if len(values) > 0 else 0.0

        signals = DistributionSignals(
            cv=cv,
            entropy=entropy,
            max_entropy=max_entropy,
            hit_count=len(hits),
            ancestor_count=len(ancestor_scores),
        )

        decision = decide_expansion(cv, entropy, max_entropy, ancestor_scores)

        return HitDistributionResult(
            ancestor_scores=ancestor_scores,
            signals=signals,
            decision=decision,
            metadata={"ancestor_count": len(ancestor_scores)},
        )

    def _split_path(self, heading_path: str) -> list[str]:
        """Split heading_path into ancestor chain including all intermediate levels.

        Example: "Chapter 1 > Section 1.1 > Subsection 1.1.1"
        Returns: ["Chapter 1", "Chapter 1 > Section 1.1", "Chapter 1 > Section 1.1 > Subsection 1.1.1"]
        """
        parts = heading_path.split(self._separator)
        ancestors = []
        for i in range(len(parts)):
            ancestor_path = self._separator.join(parts[: i + 1])
            ancestors.append(ancestor_path)
        return ancestors

    def _depth_of(self, heading_path: str) -> int:
        """Compute depth from heading_path: number of separators."""
        return heading_path.count(self._separator)

    def _compute_cv(self, values: list[float]) -> float:
        """Compute coefficient of variation (stdev / mean)."""
        if len(values) <= 1:
            return 0.0
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        return statistics.stdev(values) / mean

    def _compute_entropy(self, values: list[float]) -> float:
        """Compute Shannon entropy of the score distribution."""
        total = sum(values)
        if total <= 0:
            return 0.0
        entropy = 0.0
        for value in values:
            p = value / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy
