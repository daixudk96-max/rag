#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test 5 deep-level queries for hotspot traversal and document position return."""

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import os
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"
os.environ["RAG_TREE_BACKEND_TYPE"] = "embedding"

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

def test_deep_query(query_text: str, registry, embed_model, version_id):
    """Run single deep-level query and return structured results."""
    hits = retrieve_tree_hits_from_pdf(
        source_path=os.environ["REAL_VALIDATION_DOCUMENT_PATH"],
        query=query_text,
        embed_model=embed_model,
        similarity_top_k=3,  # Top 3 hits
        version_id=version_id,
        registry=registry,
    )

    results = []
    for hit in hits:
        results.append({
            "rank": hit.get("rank") if "rank" in hit else hits.index(hit) + 1,
            "heading_path": hit.get("heading_path") or "N/A",
            "score": hit.get("score") or 0.0,
            "drill_depth": hit.get("drill_depth") or 0,
            "hotspot_node_id": str(hit.get("hotspot_node_id")) if hit.get("hotspot_node_id") else None,
            "navigation_path": hit.get("navigation_path") or [],
            "span_ids": [str(sid) for sid in hit.get("span_ids", [])],
            "text_preview": (hit.get("text_preview") or "")[:150],
        })

    return {
        "query": query_text,
        "total_hits": len(hits),
        "hits": results,
    }

def main():
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(db_url)
    registry = PostgresRegistryWriter(conn)

    # Get p6 version
    doc_id_query = """
    SELECT dv.version_id
    FROM document_versions dv
    JOIN documents d ON dv.doc_id = d.doc_id
    WHERE d.source_uri LIKE '%p6_final_sample_structured%'
    ORDER BY dv.created_at DESC
    LIMIT 1
    """
    result = conn.execute(doc_id_query).fetchone()
    if not result:
        print("ERROR: No p6 document found")
        return

    version_id = result[0]
    print(f"Using version_id: {version_id}\n")
    print("=" * 80)
    print("5 Deep-Level Queries Test (Hotspot Traversal + Document Position)")
    print("=" * 80)
    print()

    embed_model = SentenceTransformersEmbedding(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    )

    all_results = []

    # Query 1: Level 3 (数据清洗标注)
    q1 = "数据清洗标注的具体方法是什么？"
    print(f"Query 1: {q1}")
    print("Expected heading: '04:13 - 数据处理 > 数据清洗标注' (Level 3)")
    print("-" * 80)
    r1 = test_deep_query(q1, registry, embed_model, version_id)
    all_results.append(r1)
    for hit in r1["hits"]:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Drill depth: {hit['drill_depth']}")
        print(f"  Hotspot node ID: {hit['hotspot_node_id']}")
        print(f"  Navigation path: {hit['navigation_path']}")
        print(f"  Span IDs: {hit['span_ids'][:2]}... ({len(hit['span_ids'])} total)")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Query 2: Level 3 (李菲菲案例)
    q2 = "李菲菲在AI 1.0时代遇到了什么困惑？"
    print(f"Query 2: {q2}")
    print("Expected heading: '04:40 - 数据工作重要性 > 李菲菲案例' (Level 3)")
    print("-" * 80)
    r2 = test_deep_query(q2, registry, embed_model, version_id)
    all_results.append(r2)
    for hit in r2["hits"]:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Drill depth: {hit['drill_depth']}")
        print(f"  Hotspot node ID: {hit['hotspot_node_id']}")
        print(f"  Navigation path: {hit['navigation_path']}")
        print(f"  Span IDs: {hit['span_ids'][:2]}... ({len(hit['span_ids'])} total)")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Query 3: Level 3 (推荐机制细节)
    q3 = "抖音推荐机制是如何训练模型的？"
    print(f"Query 3: {q3}")
    print("Expected heading: '05:40 - 抖音案例 > 推荐机制' (Level 3)")
    print("-" * 80)
    r3 = test_deep_query(q3, registry, embed_model, version_id)
    all_results.append(r3)
    for hit in r3["hits"]:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Drill depth: {hit['drill_depth']}")
        print(f"  Hotspot node ID: {hit['hotspot_node_id']}")
        print(f"  Navigation path: {hit['navigation_path']}")
        print(f"  Span IDs: {hit['span_ids'][:2]}... ({len(hit['span_ids'])} total)")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Query 4: Level 2 (护城河理论)
    q4 = "独家数据为什么是护城河？"
    print(f"Query 4: {q4}")
    print("Expected heading: '03:25 - 数据来源 > 护城河理论' (Level 2)")
    print("-" * 80)
    r4 = test_deep_query(q4, registry, embed_model, version_id)
    all_results.append(r4)
    for hit in r4["hits"]:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Drill depth: {hit['drill_depth']}")
        print(f"  Hotspot node ID: {hit['hotspot_node_id']}")
        print(f"  Navigation path: {hit['navigation_path']}")
        print(f"  Span IDs: {hit['span_ids'][:2]}... ({len(hit['span_ids'])} total)")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Query 5: Level 3 (用户行为数据)
    q5 = "抖音会收集哪些用户行为数据？"
    print(f"Query 5: {q5}")
    print("Expected heading: '05:40 - 抖音案例 > 用户行为数据' (Level 3)")
    print("-" * 80)
    r5 = test_deep_query(q5, registry, embed_model, version_id)
    all_results.append(r5)
    for hit in r5["hits"]:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Drill depth: {hit['drill_depth']}")
        print(f"  Hotspot node ID: {hit['hotspot_node_id']}")
        print(f"  Navigation path: {hit['navigation_path']}")
        print(f"  Span IDs: {hit['span_ids'][:2]}... ({len(hit['span_ids'])} total)")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Write full results to JSON
    output_file = REPO_ROOT / "test_deep_queries_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print(f"Full results written to: {output_file}")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    main()