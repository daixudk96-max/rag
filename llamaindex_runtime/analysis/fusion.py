"""Candidate fusion and rerank pipeline for Phase 7 formal runtime.

Provides path-aware fusion that combines QueryHit tuples from multiple
retrieval paths (vector, keyword, graph, tree) into deduplicated,
fused FusedHit tuples with RRF-based scoring.

Adapted from the verification reference for the formal runtime, which uses
text-based dedup (QueryHit.text) instead of span_id-based dedup (HybridHit).
"""

from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType

from llamaindex_runtime.entrypoints.types import QueryHit

from .normalize import normalize_path_scores, normalize_scores
from .types import FusedHit, RerankedHit, RerankerConfig


def reciprocal_rank_fusion(ranks_per_path: dict[str, int], k: int = 60) -> float:
    """Compute reciprocal rank fusion score from per-path ranks.

    Parameters
    ----------
    ranks_per_path:
        Mapping of path name to rank position (1-based).
    k:
        RRF smoothing constant.  Higher k dampens the effect of rank
        position.

    Returns
    -------
    RRF score: sum of 1/(k + rank) across all paths.
    """
    return sum(1 / (k + rank) for rank in ranks_per_path.values())


def fuse_candidates(
    hits_by_path: dict[str, list[QueryHit]],
    config: RerankerConfig | None = None,
) -> list[FusedHit]:
    """Fuse candidate hits from multiple retrieval paths into deduplicated
    FusedHit tuples with path-aware scoring.

    Algorithm:
    1. Normalize scores per path (min-max) so heterogeneous scales become
       comparable.
    2. Rank hits within each path by normalized score.
    3. Group hits by text across paths, merging source_paths.
    4. Compute RRF score from per-path ranks.
    5. Apply multi-path bonus.
    6. Return sorted by fused score descending.

    Parameters
    ----------
    hits_by_path:
        Mapping of path name to list of QueryHit from that path.
    config:
        RerankerConfig controlling RRF k, multi_path_bonus, min_max_clip.

    Returns
    -------
    List of FusedHit sorted by rerank_score descending.
    """
    if not hits_by_path:
        return []

    config = config or RerankerConfig()

    # Filter out empty path lists
    active_paths = {p: h for p, h in hits_by_path.items() if h}
    if not active_paths:
        return []

    # Step 1: Normalize scores per path
    # Convert None scores to 0.0 for normalization
    scores_by_path: dict[str, list[float | None]] = {}
    for path, hits in active_paths.items():
        scores_by_path[path] = [hit.score for hit in hits]
    normalized_by_path = normalize_path_scores(
        scores_by_path, min_max_clip=config.min_max_clip
    )

    # Step 2: Deduplicate within each path (keep highest score per text)
    best_per_text_per_path: dict[str, dict[str, QueryHit]] = defaultdict(dict)
    best_normalized_per_text_per_path: dict[str, dict[str, float]] = defaultdict(dict)
    for path, hits in active_paths.items():
        normalized_scores = normalized_by_path[path]
        for hit, norm in zip(hits, normalized_scores):
            existing = best_per_text_per_path[path].get(hit.text)
            if existing is None:
                best_per_text_per_path[path][hit.text] = hit
                best_normalized_per_text_per_path[path][hit.text] = norm
            else:
                existing_score = (
                    existing.score if existing.score is not None else float("-inf")
                )
                new_score = hit.score if hit.score is not None else float("-inf")
                if new_score > existing_score:
                    best_per_text_per_path[path][hit.text] = hit
                    best_normalized_per_text_per_path[path][hit.text] = norm

    # Step 3: Rank deduplicated hits within each path by normalized score
    # Build lookup: path -> text -> (rank, normalized_score)
    path_ranks: dict[str, dict[str, int]] = {}
    path_normalized: dict[str, dict[str, float]] = {}
    for path, text_dict in best_per_text_per_path.items():
        ranked = sorted(
            text_dict.items(),
            key=lambda item: best_normalized_per_text_per_path[path][item[0]],
            reverse=True,
        )
        path_ranks[path] = {}
        path_normalized[path] = {}
        for rank, (text, _hit) in enumerate(ranked, start=1):
            path_ranks[path][text] = rank
            path_normalized[path][text] = best_normalized_per_text_per_path[path][text]

    # Step 4: Merge across paths by text
    text_groups: dict[str, list[tuple[str, QueryHit]]] = defaultdict(list)
    for path, text_dict in best_per_text_per_path.items():
        for text, hit in text_dict.items():
            text_groups[text].append((path, hit))

    # Step 5: Compute fused score for each text and build FusedHit tuples
    fused_tuples: list[tuple[float, FusedHit]] = []
    for text, path_hits in text_groups.items():
        # Collect all source paths
        all_paths = frozenset(p for p, _ in path_hits)
        # Best hit across paths (highest score)
        best_hit = max(
            path_hits,
            key=lambda item: (
                item[1].score if item[1].score is not None else float("-inf")
            ),
        )[1]
        # Compute RRF score from per-path ranks
        ranks: dict[str, int] = {}
        for path, hit in path_hits:
            if text in path_ranks.get(path, {}):
                ranks[path] = path_ranks[path][text]
        rrf = reciprocal_rank_fusion(ranks, k=config.rrf_k)
        fused_score = rrf * (1 + config.multi_path_bonus * max(0, len(all_paths) - 1))

        # Best normalized score across paths
        best_normalized = max(
            path_normalized.get(p, {}).get(text, 0.0) for p, _ in path_hits
        )

        # Build metadata from the best hit, adding source_paths
        best_metadata = dict(best_hit.metadata)
        best_metadata["source_paths"] = tuple(sorted(all_paths))

        fused_hit = FusedHit(
            text=best_hit.text,
            score=best_hit.score if best_hit.score is not None else 0.0,
            metadata=MappingProxyType(best_metadata),
            source_paths=all_paths,
            normalized_score=best_normalized,
            rerank_score=fused_score,
        )
        fused_tuples.append((fused_score, fused_hit))

    # Step 6: Sort by RRF fused score descending, then by score as tiebreaker
    fused_tuples.sort(key=lambda item: (item[0], item[1].score), reverse=True)
    return [hit for _, hit in fused_tuples]


def compute_rerank_scores(
    hits: list[FusedHit],
    config: RerankerConfig | None = None,
) -> list[RerankedHit]:
    """Compute rerank scores from already-fused FusedHit tuples.

    Re-normalizes scores across the fused set, computes per-path RRF,
    applies multi-path bonus, and returns RerankedHit tuples sorted
    by rerank_score descending.

    Parameters
    ----------
    hits:
        List of FusedHit from fuse_candidates.
    config:
        RerankerConfig controlling RRF k, multi_path_bonus, min_max_clip.

    Returns
    -------
    List of RerankedHit sorted by rerank_score descending.
    """
    if not hits:
        return []
    config = config or RerankerConfig()

    # Group by path for per-path normalization
    by_path: dict[str, list[FusedHit]] = defaultdict(list)
    for hit in hits:
        for path in hit.source_paths:
            by_path[path].append(hit)

    # Normalize per path and compute ranks
    path_ranks: dict[str, dict[str, int]] = {}
    normalized_lookup: dict[str, float] = {}
    for path, path_hits in by_path.items():
        scores = normalize_scores(
            [hit.score for hit in path_hits],
            min_max_clip=config.min_max_clip,
        )
        ranked = sorted(zip(path_hits, scores), key=lambda item: item[1], reverse=True)
        path_ranks[path] = {}
        for rank, (hit, normalized) in enumerate(ranked, start=1):
            path_ranks[path][hit.text] = rank
            normalized_lookup[f"{path}:{hit.text}"] = normalized

    # Compute rerank scores
    reranked: list[RerankedHit] = []
    for hit in hits:
        ranks = {
            path: path_ranks[path][hit.text]
            for path in hit.source_paths
            if hit.text in path_ranks.get(path, {})
        }
        rrf_score = reciprocal_rank_fusion(ranks, k=config.rrf_k)
        rerank_score = rrf_score * (
            1 + config.multi_path_bonus * max(0, len(hit.source_paths) - 1)
        )
        normalized_score = max(
            normalized_lookup.get(f"{path}:{hit.text}", 0.0)
            for path in hit.source_paths
        )
        reranked.append(
            RerankedHit(
                text=hit.text,
                score=hit.score,
                metadata=hit.metadata,
                source_paths=hit.source_paths,
                original_score=hit.score,
                normalized_score=normalized_score,
                rerank_score=rerank_score,
            )
        )
    return sorted(reranked, key=lambda item: item.rerank_score, reverse=True)


def rerank_pipeline(
    hits: list[FusedHit],
    config: RerankerConfig | None = None,
) -> list[RerankedHit]:
    """Full normalize -> RRF -> rerank pipeline.

    This is the complete rerank policy layer that:
    1. Accepts already-fused FusedHit tuples
    2. Normalizes scores per path (respecting min_max_clip)
    3. Computes RRF across per-path rankings
    4. Applies multi-path bonus
    5. Returns RerankedHit tuples sorted by rerank_score

    Parameters
    ----------
    hits:
        List of FusedHit from fuse_candidates.
    config:
        RerankerConfig controlling RRF k, multi_path_bonus, min_max_clip.

    Returns
    -------
    List of RerankedHit sorted by rerank_score descending.
    """
    return compute_rerank_scores(hits, config=config)
