from __future__ import annotations

from collections import defaultdict

from hybrid_path.types import HybridHit
from .normalize import normalize_path_scores, normalize_scores
from .types import RerankedHit, RerankerConfig


def reciprocal_rank_fusion(ranks_per_path: dict[str, int], k: int = 60) -> float:
    return sum(1 / (k + rank) for rank in ranks_per_path.values())


def compute_rerank_scores(hits: list[HybridHit], config: RerankerConfig | None = None) -> list[RerankedHit]:
    if not hits:
        return []
    config = config or RerankerConfig()
    by_path: dict[str, list[HybridHit]] = defaultdict(list)
    for hit in hits:
        for path in hit.source_paths:
            by_path[path].append(hit)

    path_ranks: dict[str, dict[str, int]] = {}
    normalized_lookup: dict[str, float] = {}
    for path, path_hits in by_path.items():
        scores = normalize_scores(
            [hit.best_score for hit in path_hits],
            min_max_clip=config.min_max_clip,
        )
        ranked = sorted(zip(path_hits, scores), key=lambda item: item[1], reverse=True)
        path_ranks[path] = {}
        for rank, (hit, normalized) in enumerate(ranked, start=1):
            key = str(hit.span_id)
            path_ranks[path][key] = rank
            normalized_lookup[f"{path}:{key}"] = normalized

    reranked: list[RerankedHit] = []
    for hit in hits:
        key = str(hit.span_id)
        ranks = {path: path_ranks[path][key] for path in hit.source_paths if key in path_ranks.get(path, {})}
        rrf_score = reciprocal_rank_fusion(ranks, k=config.rrf_k)
        rerank_score = rrf_score * (1 + config.multi_path_bonus * max(0, len(hit.source_paths) - 1))
        normalized_score = max(normalized_lookup.get(f"{path}:{key}", 0.0) for path in hit.source_paths)
        reranked.append(
            RerankedHit(
                span_id=hit.span_id,
                source_paths=hit.source_paths,
                original_score=hit.best_score,
                normalized_score=normalized_score,
                rerank_score=rerank_score,
                page_no=hit.page_no,
                heading_path=hit.heading_path,
                raw_text=hit.raw_text,
                node_id=hit.node_id,
            )
        )
    return sorted(reranked, key=lambda item: item.rerank_score, reverse=True)


def fuse_candidates(
    hits_by_path: dict[str, list[HybridHit]],
    config: RerankerConfig | None = None,
) -> list[HybridHit]:
    """Fuse candidate hits from multiple retrieval paths into deduplicated
    HybridHit tuples with path-aware scoring.

    Algorithm:
    1. Normalize scores per path (min-max) so heterogeneous scales become
       comparable.
    2. Rank hits within each path by normalized score.
    3. Group hits by span_id across paths, merging source_paths.
    4. Compute RRF score from per-path ranks.
    5. Apply multi-path bonus.
    6. Return sorted by fused score descending.
    """
    if not hits_by_path:
        return []

    config = config or RerankerConfig()

    # Filter out empty path lists
    active_paths = {p: h for p, h in hits_by_path.items() if h}
    if not active_paths:
        return []

    # Step 1: Normalize scores per path
    scores_by_path = {
        path: [hit.best_score for hit in hits]
        for path, hits in active_paths.items()
    }
    normalized_by_path = normalize_path_scores(
        scores_by_path, min_max_clip=config.min_max_clip
    )

    # Step 2: Rank hits within each path by normalized score
    path_ranks: dict[str, dict[str, int]] = {}
    for path, hits in active_paths.items():
        normalized_scores = normalized_by_path[path]
        ranked = sorted(
            zip(hits, normalized_scores),
            key=lambda item: item[1],
            reverse=True,
        )
        path_ranks[path] = {}
        for rank, (hit, _norm) in enumerate(ranked, start=1):
            path_ranks[path][str(hit.span_id)] = rank

    # Step 3: Group by span_id, dedup within each path first
    # Build a lookup of the best hit per span_id per path
    best_per_span_per_path: dict[str, dict[str, HybridHit]] = defaultdict(dict)
    for path, hits in active_paths.items():
        for hit in hits:
            key = str(hit.span_id)
            existing = best_per_span_per_path[path].get(key)
            if existing is None or hit.best_score > existing.best_score:
                best_per_span_per_path[path][key] = hit

    # Step 4: Merge across paths by span_id
    span_groups: dict[str, list[tuple[str, HybridHit]]] = defaultdict(list)
    for path, span_dict in best_per_span_per_path.items():
        for key, hit in span_dict.items():
            span_groups[key].append((path, hit))

    # Step 5: Compute fused score for each span and build tuples
    fused_tuples: list[tuple[float, HybridHit]] = []
    for key, path_hits in span_groups.items():
        # Collect all source paths
        all_paths = frozenset(p for p, _ in path_hits)
        # Best score across paths
        best_hit = max(path_hits, key=lambda item: item[1].best_score)[1]
        # Compute RRF score from per-path ranks
        ranks: dict[str, int] = {}
        for path, hit in path_hits:
            if key in path_ranks.get(path, {}):
                ranks[path] = path_ranks[path][key]
        rrf = reciprocal_rank_fusion(ranks, k=config.rrf_k)
        fused_score = rrf * (1 + config.multi_path_bonus * max(0, len(all_paths) - 1))

        fused_hit = HybridHit(
            span_id=best_hit.span_id,
            source_paths=all_paths,
            best_score=best_hit.best_score,
            page_no=best_hit.page_no,
            heading_path=best_hit.heading_path,
            raw_text=best_hit.raw_text,
            node_id=best_hit.node_id,
        )
        fused_tuples.append((fused_score, fused_hit))

    # Step 6: Sort by RRF fused score descending, then by best_score as tiebreaker
    fused_tuples.sort(key=lambda item: (item[0], item[1].best_score), reverse=True)
    return [hit for _, hit in fused_tuples]


def rerank_pipeline(
    hits: list[HybridHit],
    config: RerankerConfig | None = None,
) -> list[RerankedHit]:
    """Full normalize -> RRF -> rerank pipeline.

    This is the complete rerank policy layer that:
    1. Accepts already-fused HybridHit tuples
    2. Normalizes scores per path (respecting min_max_clip)
    3. Computes RRF across per-path rankings
    4. Applies multi-path bonus
    5. Returns RerankedHit tuples sorted by rerank_score
    """
    return compute_rerank_scores(hits, config=config)
