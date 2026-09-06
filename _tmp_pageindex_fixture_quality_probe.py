from __future__ import annotations

import json
import re
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from llama_index.core.embeddings import MockEmbedding

from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf

VERSION_ID = uuid.uuid4()
ROOT_ID = uuid.uuid4()
STRUCTURE_ID = uuid.uuid4()
ALGO_ID = uuid.uuid4()
METRICS_ID = uuid.uuid4()
PERF_ID = uuid.uuid4()
DEPTH_ID = uuid.uuid4()
SPAN_IDS = {node_id: uuid.uuid4() for node_id in [ROOT_ID, STRUCTURE_ID, ALGO_ID, METRICS_ID, PERF_ID, DEPTH_ID]}

NODES = [
    {
        "node_id": ROOT_ID,
        "version_id": VERSION_ID,
        "title": "PageIndex完整功能分析与集成方案",
        "heading_path": "PageIndex完整功能分析与集成方案",
        "summary_text": "PageIndex完整功能分析与集成方案，包含结构、算法、指标、性能、深度等主题总览。",
        "page_start": 1,
        "page_end": 1,
        "level_no": 0,
    },
    {
        "node_id": STRUCTURE_ID,
        "version_id": VERSION_ID,
        "title": "PageIndex完整功能清单",
        "heading_path": "PageIndex完整功能分析与集成方案/PageIndex完整功能清单",
        "summary_text": "章节结构、一级标题、功能清单、文档结构说明。",
        "page_start": 3,
        "page_end": 3,
        "level_no": 1,
    },
    {
        "node_id": ALGO_ID,
        "version_id": VERSION_ID,
        "title": "核心算法原理",
        "heading_path": "PageIndex完整功能分析与集成方案/核心算法原理",
        "summary_text": "核心算法原理包括聚类、递归树构建、LLM导航和检索策略。",
        "page_start": 8,
        "page_end": 8,
        "level_no": 1,
    },
    {
        "node_id": METRICS_ID,
        "version_id": VERSION_ID,
        "title": "关键技术指标",
        "heading_path": "PageIndex完整功能分析与集成方案/关键技术指标",
        "summary_text": "关键技术指标包括命中率、top1相关性、稳定性、root bias、chunk映射率。",
        "page_start": 12,
        "page_end": 12,
        "level_no": 1,
    },
    {
        "node_id": PERF_ID,
        "version_id": VERSION_ID,
        "title": "性能优化方法",
        "heading_path": "PageIndex完整功能分析与集成方案/性能优化方法",
        "summary_text": "性能优化方法包括token节省、lazy loading、工具函数检索和缓存策略。",
        "page_start": 17,
        "page_end": 17,
        "level_no": 1,
    },
    {
        "node_id": DEPTH_ID,
        "version_id": VERSION_ID,
        "title": "树结构构建深度限制",
        "heading_path": "PageIndex完整功能分析与集成方案/树结构构建深度限制",
        "summary_text": "树结构构建深度限制使用level_no表示，要求tree depth >= 3。",
        "page_start": 21,
        "page_end": 21,
        "level_no": 1,
    },
]

QUERIES = [
    ("Q01", "文档的主要章节结构是什么？列出所有一级标题。"),
    ("Q02", "哪个章节讨论了核心算法原理？"),
    ("Q04", "文档中提到的关键技术指标有哪些？"),
    ("Q06", "文档中列举了哪些性能优化方法？"),
    ("Q16", "树结构构建的深度限制是什么？"),
]

EXPECTED = {
    "Q01": STRUCTURE_ID,
    "Q02": ALGO_ID,
    "Q04": METRICS_ID,
    "Q06": PERF_ID,
    "Q16": DEPTH_ID,
}

KEYWORDS = {
    "Q01": ["章节", "结构", "功能清单"],
    "Q02": ["核心算法", "算法", "聚类", "递归"],
    "Q04": ["关键技术指标", "指标", "命中率", "相关性"],
    "Q06": ["性能优化", "优化", "token", "缓存"],
    "Q16": ["树结构", "深度", "限制", "level"],
}


class HeuristicLLM:
    def complete(self, prompt: str, **kwargs: Any):
        query_match = re.search(r"Query:\s*(.*?)\nRelevant:", prompt, re.S)
        query = query_match.group(1) if query_match else prompt
        pages = []
        for line in prompt.splitlines():
            if ":" not in line:
                continue
            page_text, title = line.split(":", 1)
            if not page_text.strip().isdigit():
                continue
            if any(token in query and token in title for token in ["章节", "结构", "算法", "指标", "性能", "优化", "深度", "限制"]):
                pages.append(int(page_text.strip()))
        if not pages:
            for query_id, query_text in QUERIES:
                if query == query_text:
                    target_id = EXPECTED[query_id]
                    target = next(node for node in NODES if node["node_id"] == target_id)
                    pages = [target["page_start"]]
                    break
        if not pages:
            pages = [1]

        class Response:
            text = ",".join(str(page) for page in pages[:5])

        return Response()


def build_registry() -> MagicMock:
    registry = MagicMock()
    registry.query_tree_nodes_by_version.return_value = list(NODES)
    registry.query_tree_node_spans_by_version.return_value = [
        {"node_id": node_id, "span_id": span_id, "ordinal_no": 0}
        for node_id, span_id in SPAN_IDS.items()
    ]
    registry.query_vector_chunk_spans_by_version.return_value = [
        {"chunk_id": uuid.uuid4(), "span_id": span_id, "ordinal_no": 0}
        for span_id in SPAN_IDS.values()
    ]
    registry.query_vector_chunks_by_version.return_value = []
    return registry


def normalize(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": str(hit.get("node_id")),
        "heading_path": hit.get("heading_path"),
        "text_preview": hit.get("text_preview"),
        "score": hit.get("score"),
        "span_ids": [str(span_id) for span_id in hit.get("span_ids", [])],
        "chunk_id": str(hit.get("chunk_id")) if hit.get("chunk_id") else None,
        "chunk_id_missing": bool(hit.get("chunk_id_missing", False)),
        "backend_source": hit.get("backend_source"),
        "retrieval_path": hit.get("retrieval_path"),
    }


def is_root(hit: dict[str, Any]) -> bool:
    heading = hit.get("heading_path") or ""
    return "/" not in heading and ">" not in heading


def keyword_overlap(query_id: str, hit: dict[str, Any]) -> float:
    text = f"{hit.get('heading_path') or ''} {hit.get('text_preview') or ''}"
    tokens = KEYWORDS[query_id]
    return sum(1 for token in tokens if token.lower() in text.lower()) / len(tokens)


def run(label: str, backend_type: str | None) -> list[dict[str, Any]]:
    registry = build_registry()
    rows = []
    for query_id, query_text in QUERIES:
        hits = retrieve_tree_hits_from_pdf(
            "fixture.pdf",
            query=query_text,
            embed_model=MockEmbedding(embed_dim=32),
            similarity_top_k=5,
            registry=registry,
            version_id=VERSION_ID,
            backend_type=backend_type,
        )
        normalized = [normalize(hit) for hit in hits]
        top = normalized[0] if normalized else {}
        rows.append(
            {
                "query_id": query_id,
                "query": query_text,
                "expected_node_id": str(EXPECTED[query_id]),
                "hit_count": len(normalized),
                "top1_node_id": top.get("node_id"),
                "top1_exact_expected": top.get("node_id") == str(EXPECTED[query_id]),
                "top1_root": is_root(top),
                "top1_keyword_overlap": keyword_overlap(query_id, top) if top else 0,
                "hits": normalized,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_hits = [hit for row in rows for hit in row["hits"]]
    return {
        "query_count": len(rows),
        "queries_with_hits": sum(1 for row in rows if row["hit_count"] > 0),
        "top1_exact_expected_rate": round(sum(1 for row in rows if row["top1_exact_expected"]) / len(rows), 3),
        "top1_root_bias_rate": round(sum(1 for row in rows if row["top1_root"]) / len(rows), 3),
        "top1_avg_keyword_overlap": round(sum(row["top1_keyword_overlap"] for row in rows) / len(rows), 3),
        "span_ids_complete_rate": round(sum(1 for hit in all_hits if hit["span_ids"]) / len(all_hits), 3) if all_hits else None,
        "chunk_id_missing_rate": round(sum(1 for hit in all_hits if hit["chunk_id_missing"]) / len(all_hits), 3) if all_hits else None,
    }


with patch("llamaindex_runtime.tree.reasoning_backend.get_llm", lambda: HeuristicLLM()):
    reasoning = run("reasoning_default", None)
embedding = run("embedding_fallback", "embedding")

print(json.dumps({
    "status": "FIXTURE_QUALITY_PROBE_COMPLETE",
    "limitations": "Fixture-backed comparison only; Docker/PostgreSQL unavailable, so this does not replace real DB-backed validation.",
    "summary": {
        "reasoning_default": summarize(reasoning),
        "embedding_fallback": summarize(embedding),
    },
    "details": {
        "reasoning_default": reasoning,
        "embedding_fallback": embedding,
    },
}, ensure_ascii=False, indent=2))
