from __future__ import annotations


def normalize_scores(scores: list[float], *, min_max_clip: bool = False) -> list[float]:
    if not scores:
        return []
    if len(scores) == 1:
        value = 1.0
        if min_max_clip:
            value = max(0.0, min(1.0, value))
        return [value]
    minimum = min(scores)
    maximum = max(scores)
    if minimum == maximum:
        return [minimum for _ in scores]
    result = [round((score - minimum) / (maximum - minimum), 10) for score in scores]
    if min_max_clip:
        result = [max(0.0, min(1.0, v)) for v in result]
    return result


def normalize_path_scores(
    scores_by_path: dict[str, list[float | None]],
    *,
    min_max_clip: bool = False,
) -> dict[str, list[float]]:
    """Normalize scores independently per path.

    None values are treated as 0.0 for normalization purposes.
    """
    result: dict[str, list[float]] = {}
    for path, raw_scores in scores_by_path.items():
        numeric = [0.0 if s is None else s for s in raw_scores]
        result[path] = normalize_scores(numeric, min_max_clip=min_max_clip)
    return result
