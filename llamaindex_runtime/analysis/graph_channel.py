"""LightRAG graph query channel plus two-path ranked fusion (Phase 17 W6).

Wave-2 delivery: turns a zero-LLM LightRAG ``aquery_data`` page response into
ordered :class:`GraphHit` tuples (relationships, then entities, then chunks;
malformed entries are silently skipped), and fuses those hits with a BM25
title ranking through the existing Phase 7
:func:`llamaindex_runtime.analysis.fusion.reciprocal_rank_fusion` math
(read-only reuse; fusion.py is never modified).  No network, no wall-clock,
stdlib only.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from llamaindex_runtime.analysis.fusion import reciprocal_rank_fusion
from llamaindex_runtime.graph.lightrag_backend import LightragLike, LightragQueryClient

__all__ = [
    "GraphHit",
    "LightragGraphChannel",
    "RankedHit",
    "parse_keywords",
    "ranked_fusion",
]

_KEYWORD_SPLIT_RE = re.compile(r"[,;，；]")


def parse_keywords(value: Any) -> tuple[str, ...]:
    """Normalize a keywords value into a tuple of stripped non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(
            piece.strip() for piece in _KEYWORD_SPLIT_RE.split(value) if piece.strip()
        )
    if isinstance(value, (list, tuple)):
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("keyword list entries must be strings")
            stripped = item.strip()
            if stripped:
                cleaned.append(stripped)
        return tuple(cleaned)
    raise ValueError("keywords must be a string, a list/tuple of strings, or None")


@dataclass(frozen=True)
class GraphHit:
    """One parsed graph entry (relationship, entity, or chunk)."""

    title: str
    summary: str
    keywords: tuple[str, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-blank string")
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")
        for label, value in (
            ("keywords", self.keywords),
            ("source_ids", self.source_ids),
        ):
            if not isinstance(value, tuple) or any(
                not isinstance(item, str) for item in value
            ):
                raise ValueError(f"{label} must be a tuple of strings")


def _relation_hits(entries: Any) -> list[GraphHit]:
    hits: list[GraphHit] = []
    if not isinstance(entries, (list, tuple)):
        return hits
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        src_id = entry.get("src_id")
        tgt_id = entry.get("tgt_id")
        description = entry.get("description")
        if not isinstance(src_id, str) or not src_id.strip():
            continue
        if not isinstance(tgt_id, str) or not tgt_id.strip():
            continue
        if not isinstance(description, str):
            continue
        try:
            keywords = parse_keywords(entry.get("keywords"))
        except ValueError:
            continue
        hits.append(
            GraphHit(
                title=f"{src_id}->{tgt_id}",
                summary=description,
                keywords=keywords,
                source_ids=(),
            )
        )
    return hits


def _entity_hits(entries: Any) -> list[GraphHit]:
    hits: list[GraphHit] = []
    if not isinstance(entries, (list, tuple)):
        return hits
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        entity_name = entry.get("entity_name")
        if not isinstance(entity_name, str) or not entity_name.strip():
            continue
        raw_description = entry.get("description")
        description = "" if raw_description is None else raw_description
        if not isinstance(description, str):
            continue
        hits.append(
            GraphHit(
                title=entity_name,
                summary=description,
                keywords=(),
                source_ids=(),
            )
        )
    return hits


def _chunk_hits(entries: Any) -> list[GraphHit]:
    hits: list[GraphHit] = []
    if not isinstance(entries, (list, tuple)):
        return hits
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        content = entry.get("content")
        source_id = entry.get("source_id")
        if not isinstance(content, str) or not content.strip():
            continue
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        hits.append(
            GraphHit(
                title=source_id,
                summary=content,
                keywords=(),
                source_ids=(source_id,),
            )
        )
    return hits


class LightragGraphChannel:
    """Synchronous LightRAG graph channel built on the zero-LLM query client."""

    def __init__(
        self,
        rag: LightragLike,
        *,
        param_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._rag = rag
        self._param_factory = param_factory

    def fetch(
        self,
        query: str,
        *,
        hl_keywords: Sequence[str],
        ll_keywords: Sequence[str],
        top_k: int = 10,
    ) -> tuple[GraphHit, ...]:
        client = LightragQueryClient(self._rag, param_factory=self._param_factory)
        response = client.query_data(
            query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            top_k=top_k,
            chunk_top_k=top_k,
        )
        if not isinstance(response, Mapping):
            raise ValueError("graph response must be a mapping")
        if "status" not in response:
            raise ValueError("graph response missing status key")
        if response["status"] != "success":
            raise ValueError(f"graph query failed with status={response['status']}")
        data = response.get("data")
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise ValueError("graph response data must be a mapping")
        hits: list[GraphHit] = []
        hits.extend(_relation_hits(data.get("relationships")))
        hits.extend(_entity_hits(data.get("entities")))
        hits.extend(_chunk_hits(data.get("chunks")))
        return tuple(hits[:top_k])


@dataclass(frozen=True)
class RankedHit:
    """One fused, ranked title with the paths that contributed to it."""

    title: str
    score: float
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-blank string")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("score must be a finite real number")
        if not math.isfinite(float(self.score)):
            raise ValueError("score must be a finite real number")
        if not isinstance(self.sources, tuple) or any(
            not isinstance(item, str) for item in self.sources
        ):
            raise ValueError("sources must be a tuple of strings")


def ranked_fusion(
    graph_hits: Sequence[GraphHit],
    bm25_titles: Sequence[str],
    *,
    k: int = 60,
    graph_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> tuple[RankedHit, ...]:
    """Fuse graph hits and BM25 titles with the existing Phase 7 RRF math.

    Ranks are first-occurrence positions (0-based).  A title present in both
    paths earns ``graph_weight * rrf(graph rank) + bm25_weight * rrf(bm25
    rank)``; single-path titles earn only their own term.  Results are
    deduplicated by exact title and sorted by ``(-score, title)``.

    RRF is computed as ``1 / (k + rank)`` for 0-based first-occurrence ranks,
    deliberately matching ``fusion.reciprocal_rank_fusion`` behavior despite
    that function's 1-based docstring.
    """

    for hit in graph_hits:
        if not isinstance(hit, GraphHit):
            raise ValueError("graph_hits entries must be GraphHit instances")
    for title in bm25_titles:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("bm25_titles entries must be non-blank strings")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    for label, weight in (("graph_weight", graph_weight), ("bm25_weight", bm25_weight)):
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"{label} must be a finite real number")
        if not math.isfinite(float(weight)):
            raise ValueError(f"{label} must be a finite real number")
    if graph_weight < 0:
        raise ValueError("graph_weight must be non-negative")
    if bm25_weight < 0:
        raise ValueError("bm25_weight must be non-negative")
    graph_ranks: dict[str, int] = {}
    for position, hit in enumerate(graph_hits):
        if hit.title not in graph_ranks:
            graph_ranks[hit.title] = position
    bm25_ranks: dict[str, int] = {}
    for position, title in enumerate(bm25_titles):
        if title not in bm25_ranks:
            bm25_ranks[title] = position
    merged: list[RankedHit] = []
    for title in sorted(set(graph_ranks) | set(bm25_ranks)):
        score = 0.0
        sources: list[str] = []
        if title in graph_ranks:
            score += graph_weight * reciprocal_rank_fusion(
                {"graph": graph_ranks[title]}, k=k
            )
            sources.append("graph")
        if title in bm25_ranks:
            score += bm25_weight * reciprocal_rank_fusion(
                {"bm25": bm25_ranks[title]}, k=k
            )
            sources.append("bm25")
        merged.append(RankedHit(title=title, score=score, sources=tuple(sources)))
    merged.sort(key=lambda hit: (-hit.score, hit.title))
    return tuple(merged)
