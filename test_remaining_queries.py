#!/usr/bin/env python
"""Test remaining queries from plan section 2."""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"
os.environ["RAG_TREE_BACKEND_TYPE"] = "embedding"

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

def test_query(query_text: str, registry, embed_model, version_id):
    """Run single query and return hits."""
    hits = retrieve_tree_hits_from_pdf(
        source_path=os.environ["REAL_VALIDATION_DOCUMENT_PATH"],
        query=query_text,
        embed_model=embed_model,
        similarity_top_k=5,
        version_id=version_id,
        registry=registry,
    )

    results = []
    for i, hit in enumerate(hits, start=1):
        results.append({
            "rank": i,
            "heading_path": hit.get("heading_path") or "N/A",
            "score": hit.get("score") or 0.0,
            "text_preview": (hit.get("text_preview") or "")[:100],
        })

    return results

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

    embed_model = SentenceTransformersEmbedding(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    )

    # Query 1: 什么是数据闭环飞轮？
    query1 = "什么是数据闭环飞轮？"
    print(f"Query 1: {query1}")
    print("=" * 80)
    hits1 = test_query(query1, registry, embed_model, version_id)
    for hit in hits1:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Query 2: cardiac arrhythmia diagnosis
    query2 = "cardiac arrhythmia diagnosis"
    print(f"Query 2: {query2}")
    print("=" * 80)
    hits2 = test_query(query2, registry, embed_model, version_id)
    for hit in hits2:
        print(f"Rank {hit['rank']}: {hit['heading_path']}")
        print(f"  Score: {hit['score']:.4f}")
        print(f"  Preview: {hit['text_preview']}")
    print()

    # Write results
    output = {
        "query_1": {"query": query1, "hits": hits1},
        "query_2": {"query": query2, "hits": hits2},
    }

    output_file = REPO_ROOT / "test_remaining_queries_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Results written to: {output_file}")
    conn.close()

if __name__ == "__main__":
    main()