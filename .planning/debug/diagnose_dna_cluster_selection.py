#!/usr/bin/env python3
"""Diagnostic script to trace ClusterHotspotSelector decision for DNA query."""

import os
import sys
from pathlib import Path
from uuid import UUID

# Force cluster selector
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "cluster"

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.semantic_distribution import (
    ClusterHotspotSelector,
    PersistedTreeSemanticDistributionAdapter,
    _cosine_similarity,
)
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding

# Use the same doc_id/version_id from Phase 11 validation
DOC_ID = UUID("6d742c06-3c5a-4996-ac36-614510bd729f")
VERSION_ID = UUID("a287ec5a-604b-416e-8ec5-a541d3d23cbe")

DNA_QUERY = "AI产品经理的核心DNA是什么？"

EXPECTED_NODE_HEADING = "AI产品经理项目实战与深度思考架构分析 > 00:31 - 产品特性对比 > AI产品经理核心DNA"
FORBIDDEN_NODE_HEADING = "AI产品经理项目实战与深度思考架构分析 > 05:40 - 抖音案例 > AI产品经理的思考方向"


def main():
    print("=" * 80)
    print("DIAGNOSTIC: ClusterHotspotSelector DNA Query Decision Trace")
    print("=" * 80)

    # Get query embedding
    embedder = SentenceTransformersEmbedding(model_name="all-MiniLM-L6-v2")
    query_embedding = embedder._get_query_embedding(DNA_QUERY)

    print(f"\nQuery: {DNA_QUERY}")
    print(f"Embedding dimension: {len(query_embedding)}")

    # Connect to database
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    with psycopg.connect(db_url) as conn:
        registry = PostgresRegistryWriter(conn)

        # Get node stats using adapter
        adapter = PersistedTreeSemanticDistributionAdapter()
        report = adapter.analyze_tree_semantic_distribution(
            version_id=VERSION_ID,
            registry=registry,
        )

        node_stats = report.get("node_stats", [])
        tree_signals = {
            "embedding_dimension": report.get("embedding_dimension"),
        }

        print(f"\nTotal nodes with semantic stats: {len(node_stats)}")

        # Find expected and forbidden nodes
        expected_node = None
        forbidden_node = None
        for stats in node_stats:
            heading = stats.get("heading_path", "")
            if heading == EXPECTED_NODE_HEADING:
                expected_node = stats
            elif heading == FORBIDDEN_NODE_HEADING:
                forbidden_node = stats

        if expected_node:
            print(f"\n✓ Expected node found:")
            print(f"  heading: {expected_node.get('heading_path')}")
            print(f"  node_id: {expected_node.get('node_id')}")
            prototype = expected_node.get("prototype_embedding") or expected_node.get("centroid")
            if prototype:
                sim = _cosine_similarity(query_embedding, prototype)
                print(f"  similarity to query: {sim:.6f}")
        else:
            print(f"\n✗ Expected node NOT FOUND in node_stats!")

        if forbidden_node:
            print(f"\n✓ Forbidden node found:")
            print(f"  heading: {forbidden_node.get('heading_path')}")
            print(f"  node_id: {forbidden_node.get('node_id')}")
            prototype = forbidden_node.get("prototype_embedding") or forbidden_node.get("centroid")
            if prototype:
                sim = _cosine_similarity(query_embedding, prototype)
                print(f"  similarity to query: {sim:.6f}")
        else:
            print(f"\n✗ Forbidden node NOT FOUND in node_stats!")

        # Run selector
        print("\n" + "=" * 80)
        print("Running ClusterHotspotSelector.select_hotspots(limit=1)...")
        print("=" * 80)

        selector = ClusterHotspotSelector()

        hotspots = selector.select_hotspots(
            query_embedding=query_embedding,
            node_stats=node_stats,
            tree_signals=tree_signals,
            limit=1,
        )

        print("\n" + "=" * 80)
        print("FINAL RESULT: Selected hotspots")
        print("=" * 80)

        for i, hotspot in enumerate(hotspots, 1):
            stats = None
            for s in node_stats:
                if s.get("node_id") == hotspot.node_id:
                    stats = s
                    break

            heading = stats.get("heading_path", "N/A") if stats else "N/A"
            print(f"\nHotspot {i}:")
            print(f"  node_id: {hotspot.node_id}")
            print(f"  heading: {heading}")
            print(f"  score: {hotspot.score:.6f}")
            print(f"  reason: {hotspot.reason}")
            print(f"  support_count: {hotspot.support_count}")

            if heading == EXPECTED_NODE_HEADING:
                print("  ✓ CORRECT HOTSPOT SELECTED!")
            elif heading == FORBIDDEN_NODE_HEADING:
                print("  ✗ FORBIDDEN HOTSPOT SELECTED (BUG)")
            else:
                print(f"  ? UNEXPECTED HOTSPOT: {heading}")


if __name__ == "__main__":
    main()