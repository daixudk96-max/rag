from __future__ import annotations

from typing import Any

from hybrid_path.aggregator import aggregate_hits, run_distribution_analysis
from hybrid_path.collector import collect_all_paths
from hybrid_path.expander import expand_by_decision
from hybrid_path.types import HybridHit, HybridQueryResult
from reranker.reranker import rerank_hits


def hybrid_query(conn, query: str, *, version_id=None, top_k: int = 10) -> HybridQueryResult:
    raw_hits, paths_used = collect_all_paths(conn, query, version_id=version_id, top_k=top_k)
    deduped = aggregate_hits(raw_hits)
    analysis = run_distribution_analysis(conn, deduped, version_id=version_id)
    if analysis is None:
        reranked = rerank_hits(deduped)
        return HybridQueryResult(query=query, paths_used=paths_used, total_hits=len(reranked), decision="no_hits", expanded_count=0, evidence=[_reranked_to_dict(hit) for hit in reranked])
    expanded = expand_by_decision(conn, analysis.decision, version_id=version_id)
    final_hits = aggregate_hits(deduped + expanded)
    reranked = rerank_hits(final_hits)
    return HybridQueryResult(
        query=query,
        paths_used=paths_used,
        total_hits=len(reranked),
        decision=analysis.decision.decision,
        expanded_count=max(0, len(final_hits) - len(deduped)),
        evidence=[_reranked_to_dict(hit) for hit in reranked],
    )


def _hit_to_dict(hit: HybridHit) -> dict[str, Any]:
    return {
        "span_id": str(hit.span_id),
        "source_paths": sorted(hit.source_paths),
        "score": hit.best_score,
        "page_no": hit.page_no,
        "heading_path": hit.heading_path,
        "raw_text": hit.raw_text,
        "node_id": str(hit.node_id) if hit.node_id else None,
    }


def _reranked_to_dict(hit) -> dict[str, Any]:
    return {
        "span_id": str(hit.span_id),
        "source_paths": sorted(hit.source_paths),
        "score": hit.rerank_score,
        "rerank_score": hit.rerank_score,
        "original_score": hit.original_score,
        "page_no": hit.page_no,
        "heading_path": hit.heading_path,
        "raw_text": hit.raw_text,
        "node_id": str(hit.node_id) if hit.node_id else None,
    }
