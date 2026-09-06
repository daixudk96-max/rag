"""Trial-extraction routing package (Phase 17-W3, D2 v2): pure stdlib.

Re-exports the frozen public surface of :mod:`.trial`: the
BatchHomogeneity/ExtractionRoute vocabularies, the COVERAGE_THRESHOLD
quantitative gate, the MIN_TRIAL_SAMPLES per-batch floor, the
TrialReport evidence value, the RouteDecision outcome value, the
TrialEngine seam protocol, and the deterministic decide_route router.
"""

from .trial import (
    COVERAGE_THRESHOLD,
    MIN_TRIAL_SAMPLES,
    BatchHomogeneity,
    ExtractionRoute,
    RouteDecision,
    TrialEngine,
    TrialReport,
    decide_route,
)

__all__ = [
    "COVERAGE_THRESHOLD",
    "MIN_TRIAL_SAMPLES",
    "BatchHomogeneity",
    "ExtractionRoute",
    "RouteDecision",
    "TrialEngine",
    "TrialReport",
    "decide_route",
]
