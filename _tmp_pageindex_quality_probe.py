from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any
from unittest.mock import patch

import psycopg
from llama_index.core.embeddings import MockEmbedding
from psycopg.rows import dict_row

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf

CONNECTION_STRING = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag")
QUERIES = [
    ("Q01", "文档的主要章节结构是什么？列出所有一级标题。"),
    ("Q02", "哪个章节讨论了核心算法原理？"),
    ("Q04", "文档中提到的关键技术指标有哪些？"),
    ("Q06", "文档中列举了哪些性能优化方法？"),
    ("Q16", "树结构构建的深度限制是什么？"),
]


class HeuristicLLM:
    def complete(self, prompt: str, **kwargs: Any):
        query_match = re.search(r"Query:\s*(.*?)\nRelevant:", prompt, re.S)
        query = query_match.group(1) if query_match else prompt
        page_scores: list[tuple[int, int]] = []
        keyword_map = {
            "结构": ["结构", "章节", "功能清单"],
            "章节": ["章节", "功能清单", "关键发现"],
            "算法": ["算法", "聚类", "递归", "检索"],
            "指标": ["指标", "质量", "阈值", "评估"],
            "性能": ["性能", "优化", "token", "效率"],
            "深度": ["深度", "树结构", "level"],
            "限制": ["限制", "约束", "阈值"],
        }
        for line in prompt.splitlines():
            if ":" not in line:
                continue
            page_text, title = line.split(":", 1)
            if not page_text.strip().isdigit():
                continue
            page = int(page_text.strip())
            score = 0
            for token in re.findall(r"[\w一-鿿]+", query):
                if len(token) >= 2 and token in title:
                    score += len(token)
            for key, values in keyword_map.items():
                if key in query:
                    score += sum(3 for value in values if value in title)
            if score > 0:
                page_scores.append((score, page))
        page_scores.sort(reverse=True)
        pages = [page for _, page in page_scores[:5]] or [1]

        class Response:
            text = ",".join(str(page) for page in pages)

        return Response()


def text_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]+|[一-鿿]{2,}", text or "")
        if len(token) >= 2
    }


def relevance_score(query: str, hit: dict[str, Any]) -> float:
    query_tokens = text_tokens(query)
    hit_tokens = text_tokens(
        f"{hit.get('heading_path') or ''} {hit.get('text_preview') or ''}"
    )
    if not query_tokens:
        return 0.0
    return len(query_tokens & hit_tokens) / len(query_tokens)


def is_root_hit(hit: dict[str, Any]) -> bool:
    heading = hit.get("heading_path") or ""
    return "/" not in heading and ">" not in heading


def normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": str(hit.get("node_id")),
        "chunk_id": str(hit.get("chunk_id")) if hit.get("chunk_id") is not None else None,
        "chunk_id_missing": bool(hit.get("chunk_id_missing", False)),
        "score": hit.get("score"),
        "heading_path": hit.get("heading_path"),
        "page_no": hit.get("page_no"),
        "text_preview": hit.get("text_preview"),
        "span_ids": [str(span_id) for span_id in hit.get("span_ids", [])],
        "backend_source": hit.get("backend_source"),
        "retrieval_path": hit.get("retrieval_path"),
    }


def summarize(label: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    top_hits = [row["hits"][0] for row in results if row["hits"]]
    all_hits = [hit for row in results for hit in row["hits"]]
    return {
        "label": label,
        "query_count": len(results),
        "queries_with_hits": sum(1 for row in results if row["hits"]),
        "total_hits": len(all_hits),
        "avg_hits_per_query": round(len(all_hits) / len(results), 2) if results else 0,
        "top1_root_bias_rate": round(sum(1 for hit in top_hits if is_root_hit(hit)) / len(top_hits), 3) if top_hits else None,
        "any_hit_root_bias_rate": round(sum(1 for hit in all_hits if is_root_hit(hit)) / len(all_hits), 3) if all_hits else None,
        "top1_avg_relevance_overlap": round(sum(row["top1_relevance_overlap"] for row in results) / len(results), 3) if results else 0,
        "span_ids_complete_rate": round(sum(1 for hit in all_hits if hit.get("span_ids")) / len(all_hits), 3) if all_hits else None,
        "chunk_id_complete_rate": round(sum(1 for hit in all_hits if hit.get("chunk_id") and not hit.get("chunk_id_missing")) / len(all_hits), 3) if all_hits else None,
        "chunk_id_missing_rate": round(sum(1 for hit in all_hits if hit.get("chunk_id_missing")) / len(all_hits), 3) if all_hits else None,
        "top1_headings": [hit.get("heading_path") for hit in top_hits],
    }


def run_backend(label: str, registry: Any, version_id: uuid.UUID, backend_type: str | None) -> list[dict[str, Any]]:
    rows = []
    for query_id, query_text in QUERIES:
        hits = retrieve_tree_hits_from_pdf(
            "quality-probe.pdf",
            query=query_text,
            embed_model=MockEmbedding(embed_dim=32),
            similarity_top_k=5,
            registry=registry,
            version_id=version_id,
            backend_type=backend_type,
        )
        normalized_hits = [normalize_hit(hit) for hit in hits]
        rows.append(
            {
                "query_id": query_id,
                "query": query_text,
                "hit_count": len(normalized_hits),
                "top1_relevance_overlap": relevance_score(query_text, normalized_hits[0]) if normalized_hits else 0,
                "hits": normalized_hits,
            }
        )
    return rows


def main() -> None:
    with psycopg.connect(CONNECTION_STRING) as connection:
        registry = PostgresRegistryWriter(connection)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT version_id, COUNT(*) AS node_count, MAX(level_no) AS max_level
                FROM tree_nodes
                GROUP BY version_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
            selected = cursor.fetchone()
            if not selected:
                print(json.dumps({"status": "NO_TREE_NODES"}, ensure_ascii=False))
                return
            version_id = uuid.UUID(str(selected["version_id"]))

        with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", lambda: HeuristicLLM()):
            reasoning_results = run_backend("reasoning_default", registry, version_id, None)
        embedding_results = run_backend("embedding_fallback", registry, version_id, "embedding")

    report = {
        "status": "QUALITY_PROBE_COMPLETE",
        "version_id": str(version_id),
        "node_count": selected["node_count"],
        "max_level": selected["max_level"],
        "llm_mode": "patched_heuristic_llm_for_reproducible_reasoning_probe",
        "queries": [{"query_id": query_id, "query": query_text} for query_id, query_text in QUERIES],
        "summary": {
            "reasoning_default": summarize("reasoning_default", reasoning_results),
            "embedding_fallback": summarize("embedding_fallback", embedding_results),
        },
        "details": {
            "reasoning_default": reasoning_results,
            "embedding_fallback": embedding_results,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
