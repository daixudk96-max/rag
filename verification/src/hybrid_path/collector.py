from __future__ import annotations

import uuid
from typing import Any


from keyword_path.search import search_by_keyword
from vector_path.search import search_by_vector_query
from .types import HybridHit, PathContribution



def collect_keyword_hits(conn, query: str, version_id: uuid.UUID | None) -> list[HybridHit]:
    raw = search_by_keyword(conn, query, version_id=version_id)
    return [
        HybridHit(
            span_id=item["span_id"],
            source_paths=frozenset({"keyword"}),
            best_score=float(item["match_score"]),
            page_no=item["page_no"],
            heading_path=item["heading_path"],
            raw_text=item["raw_text"],
            node_id=None,
        )
        for item in raw["evidence"]
    ]


def collect_vector_hits(conn, query: str, version_id: uuid.UUID | None, top_k: int) -> list[HybridHit]:
    raw = search_by_vector_query(conn, query, version_id=version_id, top_k=top_k)
    return [
        HybridHit(
            span_id=item["span_ids"][0],
            source_paths=frozenset({"vector"}),
            best_score=float(item["score"]),
            page_no=item["page_no"],
            heading_path=item["heading_path"],
            raw_text=item["text_preview"],
            node_id=None,
        )
        for item in raw["chunks"] if item.get("span_ids")
    ]


def collect_all_paths(conn, query: str, version_id: uuid.UUID | None = None, top_k: int = 10) -> tuple[list[HybridHit], list[PathContribution]]:
    keyword_hits = collect_keyword_hits(conn, query, version_id)
    vector_hits = collect_vector_hits(conn, query, version_id, top_k)
    contributions = [
        PathContribution("keyword", len(keyword_hits), True),
        PathContribution("vector", len(vector_hits), True),
    ]
    return keyword_hits + vector_hits, contributions
