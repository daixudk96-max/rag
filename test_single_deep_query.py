#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Single deep query test for diagnosis."""

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

def main():
    db_url = os.environ["DATABASE_URL"]
    print("Connecting to database...")
    conn = psycopg.connect(db_url)
    registry = PostgresRegistryWriter(conn)
    print("✓ Database connected\n")

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

    print("Loading embedding model...")
    embed_model = SentenceTransformersEmbedding(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    )
    print("✓ Embedding model loaded\n")

    # Single test query (Level 3)
    query = "数据清洗标注的具体方法是什么？"
    print(f"Query: {query}")
    print("Expected: '04:13 - 数据处理 > 数据清洗标注' (Level 3)")
    print("=" * 80)

    print("\nRunning retrieval...")
    hits = retrieve_tree_hits_from_pdf(
        source_path=os.environ["REAL_VALIDATION_DOCUMENT_PATH"],
        query=query,
        embed_model=embed_model,
        similarity_top_k=3,
        version_id=version_id,
        registry=registry,
    )

    print(f"✓ Retrieved {len(hits)} hits\n")

    for i, hit in enumerate(hits, start=1):
        heading = hit.get("heading_path") or "N/A"
        score = hit.get("score") or 0.0
        depth = hit.get("drill_depth") or 0
        hotspot = str(hit.get("hotspot_node_id")) if hit.get("hotspot_node_id") else None
        nav_path = hit.get("navigation_path") or []
        span_ids = [str(sid) for sid in hit.get("span_ids", [])]
        preview = (hit.get("text_preview") or "")[:150]

        print(f"Rank {i}: {heading}")
        print(f"  Score: {score:.4f}")
        print(f"  Drill depth: {depth}")
        print(f"  Hotspot node ID: {hotspot}")
        print(f"  Navigation path: {nav_path}")
        print(f"  Span IDs count: {len(span_ids)}")
        if span_ids:
            print(f"  Span IDs sample: {span_ids[:3]}...")
        print(f"  Preview: {preview}")
        print()

    # Write result
    output_file = REPO_ROOT / "test_single_deep_query_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "query": query,
            "total_hits": len(hits),
            "hits": [
                {
                    "rank": i,
                    "heading_path": hit.get("heading_path"),
                    "score": hit.get("score"),
                    "drill_depth": hit.get("drill_depth"),
                    "hotspot_node_id": str(hit.get("hotspot_node_id")) if hit.get("hotspot_node_id") else None,
                    "navigation_path": hit.get("navigation_path"),
                    "span_ids": [str(sid) for sid in hit.get("span_ids", [])],
                    "text_preview": hit.get("text_preview"),
                }
                for i, hit in enumerate(hits, start=1)
            ]
        }, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print(f"Result written to: {output_file}")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    main()