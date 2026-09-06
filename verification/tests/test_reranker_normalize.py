from __future__ import annotations

from reranker.normalize import normalize_scores


def test_normalize_scores_standard() -> None:
    assert normalize_scores([0.2, 0.5, 0.8]) == [0.0, 0.5, 1.0]


def test_normalize_scores_same_values() -> None:
    assert normalize_scores([0.5, 0.5, 0.5]) == [0.5, 0.5, 0.5]


def test_normalize_scores_empty() -> None:
    assert normalize_scores([]) == []


def test_normalize_scores_single() -> None:
    assert normalize_scores([0.7]) == [1.0]
