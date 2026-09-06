"""Fuzzy merge suggestions for deferred identity pairs (Phase 17 Wave 4b).

Turns plan_merge DEFERRED_REVIEW pairs into ranked advisory suggestions for
the human review basket.  This module never merges anything and never
touches storage: output is pure data.  Pure stdlib (difflib), no I/O, no
wall-clock, deterministic ordering.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Final

from llamaindex_runtime.entity.identity import (
    EntityIdentity,
    MergeOutcome,
    plan_merge,
)

__all__ = [
    "DEFAULT_SUGGESTION_THRESHOLD",
    "FuzzySuggestion",
    "SuggestionReason",
    "suggest_merges",
]

# Frozen W4b default; override via the explicit threshold argument when
# review-basket calibration data exists.
DEFAULT_SUGGESTION_THRESHOLD: Final[float] = 0.87


class SuggestionReason(StrEnum):
    """Why a candidate was suggested for review."""

    NAME_SIMILARITY = "name_similarity"


def _finite_unit_interval(value: object, label: str) -> float:
    """Coerce to float and require a finite value inside [0.0, 1.0]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a real number, got {type(value).__name__}")
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{label} must be a finite number") from None
    if converted != converted or converted in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be a finite number")
    if not 0.0 <= converted <= 1.0:
        raise ValueError(f"{label} must be within [0.0, 1.0]")
    return converted


def _require_nonempty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _default_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


@dataclass(frozen=True)
class FuzzySuggestion:
    """One advisory merge candidate; review-basket input, never auto-applied.

    Instances are advisory claims; they never re-derive the underlying
    decision, so basket consumers MUST re-run plan_merge(target, candidate)
    and act only on its outcome.
    """

    target_identity_id: str
    candidate_identity_id: str
    candidate_normalized_name: str
    score: float
    reason: SuggestionReason

    def __post_init__(self) -> None:
        _require_nonempty_str(self.target_identity_id, "target_identity_id")
        _require_nonempty_str(self.candidate_identity_id, "candidate_identity_id")
        _require_nonempty_str(
            self.candidate_normalized_name, "candidate_normalized_name"
        )
        if self.target_identity_id == self.candidate_identity_id:
            raise ValueError("target and candidate must be different identities")
        object.__setattr__(self, "score", _finite_unit_interval(self.score, "score"))
        if not isinstance(self.reason, SuggestionReason):
            raise ValueError("reason must be a SuggestionReason value")

    def to_dict(self) -> dict[str, object]:
        return {
            "target_identity_id": self.target_identity_id,
            "candidate_identity_id": self.candidate_identity_id,
            "candidate_normalized_name": self.candidate_normalized_name,
            "score": self.score,
            "reason": self.reason.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FuzzySuggestion:
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        expected = {
            "target_identity_id",
            "candidate_identity_id",
            "candidate_normalized_name",
            "score",
            "reason",
        }
        keys = set(payload)
        if any(not isinstance(key, str) for key in keys):
            raise ValueError("payload keys must all be strings")
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        if missing or unknown:
            raise ValueError(
                f"payload keys mismatch: missing={missing!r} unknown={unknown!r}"
            )
        reason_raw = payload["reason"]
        if not isinstance(reason_raw, str) or reason_raw not in tuple(
            item.value for item in SuggestionReason
        ):
            raise ValueError("reason must be a known suggestion reason")
        target_id_raw = payload["target_identity_id"]
        candidate_id_raw = payload["candidate_identity_id"]
        name_raw = payload["candidate_normalized_name"]
        score_raw = payload["score"]
        return cls(
            target_identity_id=_require_nonempty_str(
                target_id_raw, "target_identity_id"
            ),
            candidate_identity_id=_require_nonempty_str(
                candidate_id_raw, "candidate_identity_id"
            ),
            candidate_normalized_name=_require_nonempty_str(
                name_raw, "candidate_normalized_name"
            ),
            score=_finite_unit_interval(score_raw, "score"),
            reason=SuggestionReason(reason_raw),
        )


def suggest_merges(
    target: EntityIdentity,
    universe: Sequence[EntityIdentity],
    *,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
    ratio_fn: Callable[[str, str], float] = _default_ratio,
) -> tuple[FuzzySuggestion, ...]:
    """Return advisory suggestions for DEFERRED_REVIEW pairs at or above threshold.

    Pairs that plan_merge resolves as MERGED are the resolve layer job and
    are skipped; vetoed pairs stay vetoed.  Ordering is deterministic:
    score descending, then candidate normalized name, then identity id.
    ratio_fn is called as ratio_fn(target.normalized_name,
    candidate.normalized_name) and must return a finite value in [0.0, 1.0];
    out-of-range results are rejected.
    """
    if not isinstance(target, EntityIdentity):
        raise ValueError("target must be an EntityIdentity")
    if isinstance(universe, (str, bytes)) or not isinstance(universe, Sequence):
        raise ValueError("universe must be a finite sequence of EntityIdentity values")
    if not callable(ratio_fn):
        raise ValueError("ratio_fn must be callable")
    threshold_value = _finite_unit_interval(threshold, "threshold")
    collected: list[FuzzySuggestion] = []
    seen_ids: set[str] = set()
    for candidate in universe:
        if not isinstance(candidate, EntityIdentity):
            raise ValueError("universe entries must be EntityIdentity values")
        if candidate.identity_id == target.identity_id:
            continue
        if candidate.identity_id in seen_ids:
            continue
        seen_ids.add(candidate.identity_id)
        decision = plan_merge(target, candidate)
        if decision.outcome is not MergeOutcome.DEFERRED_REVIEW:
            continue
        score = ratio_fn(target.normalized_name, candidate.normalized_name)
        score_value = _finite_unit_interval(score, "score")
        if score_value >= threshold_value:
            collected.append(
                FuzzySuggestion(
                    target_identity_id=target.identity_id,
                    candidate_identity_id=candidate.identity_id,
                    candidate_normalized_name=candidate.normalized_name,
                    score=score_value,
                    reason=SuggestionReason.NAME_SIMILARITY,
                )
            )
    # candidate_identity_id is the contract-pinned final tie-break;
    # unreachable for distinct deferred candidates (same name and type
    # merges), kept for robustness.
    collected.sort(
        key=lambda item: (
            -item.score,
            item.candidate_normalized_name,
            item.candidate_identity_id,
        )
    )
    return tuple(collected)
