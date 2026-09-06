#!/usr/bin/env python
"""Real-time single query test for Phase 11 hybrid_cluster selector."""

import json
import os
import sys
from pathlib import Path

# Script is in project root, so parent[0] is correct
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

# Load environment before any other imports
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

# Force hybrid_cluster selector AFTER loading .env
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"
# Force embedding backend to use hotspot traversal (not reasoning)
os.environ["RAG_TREE_BACKEND_TYPE"] = "embedding"

import psycopg

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

def main():
    # Connect to registry
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(db_url)
    registry = PostgresRegistryWriter(conn)

    # Get latest version for p6 document
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
        print("ERROR: No p6 document found in registry")
        return

    version_id = result[0]
    print(f"Using version_id: {version_id}")

    # Setup embed model
    embed_model = SentenceTransformersEmbedding(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    )

    # New query (not in original 10 queries)
    query_text = "为什么数据对AI产品如此重要？"
    print(f"\nQuery: {query_text}")
    print("=" * 80)

    # Retrieve hits
    hits = retrieve_tree_hits_from_pdf(
        source_path=os.environ["REAL_VALIDATION_DOCUMENT_PATH"],
        query=query_text,
        embed_model=embed_model,
        similarity_top_k=5,
        version_id=version_id,
        registry=registry,
    )

    print(f"Total hits: {len(hits)}")
    print()

    # Display hits
    results = []
    for i, hit in enumerate(hits, start=1):
        node_id = hit.get("node_id")
        heading = hit.get("heading_path") or "N/A"
        score = hit.get("score") or 0.0
        preview = hit.get("text_preview") or ""
        hotspot_id = hit.get("hotspot_node_id") or "N/A"
        nav_path = hit.get("navigation_path") or []
        drill_depth = hit.get("drill_depth") or 0

        results.append({
            "rank": i,
            "node_id": str(node_id) if node_id else None,
            "heading_path": heading,
            "score": score,
            "text_preview": preview,
            "hotspot_node_id": str(hotspot_id) if hotspot_id != "N/A" else None,
            "navigation_path": nav_path,
            "drill_depth": drill_depth,
        })

    # Write to JSON for clean Chinese output
    output_file = REPO_ROOT / "test_single_query_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "query": query_text,
            "total_hits": len(hits),
            "hits": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"Results written to: {output_file}")
    print(f"Total hits: {len(hits)}")

    conn.close()

if __name__ == "__main__":
    main()