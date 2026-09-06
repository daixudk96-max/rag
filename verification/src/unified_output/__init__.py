from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UnifiedQueryResult:
    route: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


def from_keyword_result(raw: dict[str, Any]) -> UnifiedQueryResult:
    evidence = []
    for item in raw.get("evidence", []):
        evidence.append(
            {
                "doc_id": item.get("doc_id"),
                "version_id": item.get("version_id"),
                "span_id": item.get("span_id"),
                "chunk_id": None,
                "page_no": item.get("page_no"),
                "heading_path": item.get("heading_path"),
                "raw_text": item.get("raw_text"),
                "match_score": item.get("match_score"),
            }
        )
    answer = evidence[0]["raw_text"] if evidence else ""
    return UnifiedQueryResult(route="keyword", answer=answer, evidence=evidence)


def from_vector_result(raw: dict[str, Any]) -> UnifiedQueryResult:
    evidence = []
    for item in raw.get("chunks", []):
        evidence.append(
            {
                "doc_id": None,
                "version_id": None,
                "span_id": item.get("span_ids", [None])[0] if item.get("span_ids") else None,
                "chunk_id": item.get("chunk_id"),
                "page_no": item.get("page_no"),
                "heading_path": item.get("heading_path"),
                "raw_text": item.get("text_preview"),
                "match_score": item.get("score"),
            }
        )
    answer = evidence[0]["raw_text"] if evidence else ""
    return UnifiedQueryResult(route="vector", answer=answer, evidence=evidence)


def to_dict(result: UnifiedQueryResult) -> dict[str, Any]:
    return asdict(result)
