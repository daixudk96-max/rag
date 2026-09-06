"""Debug script to trace heading_path in cluster scoring."""
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llamaindex_runtime.config import get_config
from llamaindex_runtime.registry.postgres_adapter import PostgresSemanticDistributionRegistry
from llamaindex_runtime.tree.semantic_distribution import (
    ClusterHotspotSelector,
    NodeSemanticHit,
    _build_ancestor_clusters,
    _score_cluster,
)
from llamaindex_runtime.embeddings import get_embedder

def main():
    config = get_config()
    registry = PostgresSemanticDistributionRegistry(config)

    # Get p6 version
    with registry._connection.cursor() as cur:
        cur.execute('''
            SELECT version_id FROM tree_versions
            WHERE slug = 'p6-ai-product-manager'
            ORDER BY created_at DESC LIMIT 1
        ''')
        row = cur.fetchone()
        if not row:
            print("ERROR: No version found for p6-ai-product-manager")
            return
        version_id = uuid.UUID(str(row[0]))
        print(f"Version ID: {version_id}")

    # Get nodes
    nodes = registry.query_tree_nodes_by_version(version_id)
    node_by_id = {node["node_id"]: node for node in nodes}
    print(f"Total nodes: {len(nodes)}")

    # Check for heading_path
    nodes_with_heading = [n for n in nodes if n.get("heading_path")]
    print(f"Nodes with heading_path: {len(nodes_with_heading)}")

    # Sample some heading paths
    print("\nSample heading paths:")
    for i, node in enumerate(nodes_with_heading[:5]):
        print(f"  {i+1}. {node['heading_path'][:80]}...")

    # DNA query
    query = "AI产品经理的核心DNA是什么？"
    print(f"\nQuery: {query}")

    # Get embedding
    embedder = get_embedder(config)
    query_embedding = embedder.embed(query)
    print(f"Query embedding shape: {len(query_embedding)}")

    # Get distribution report
    from llamaindex_runtime.tree.semantic_distribution import TreeSemanticDistributionAdapter
    adapter = TreeSemanticDistributionAdapter()
    distribution_report = adapter.analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )

    node_stats_list = distribution_report["node_stats"]
    print(f"Node stats count: {len(node_stats_list)}")

    # Check heading_path in node_stats
    stats_with_heading = [s for s in node_stats_list if s.get("heading_path")]
    print(f"Node stats with heading_path: {len(stats_with_heading)}")

    # Build candidates (top N by similarity)
    candidates = []
    for stats in node_stats_list:
        prototype = stats.get("prototype_vector")
        if not prototype:
            continue

        # Cosine similarity
        import numpy as np
        similarity = float(np.dot(query_embedding, prototype) / (np.linalg.norm(query_embedding) * np.linalg.norm(prototype)))

        if similarity > 0.5:  # Filter low similarity
            candidates.append({
                "node_id": stats["node_id"],
                "similarity": similarity,
                "heading_path": stats.get("heading_path"),
                "stats": stats,
            })

    # Sort by similarity
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    top_candidates = candidates[:10]

    print(f"\nTop 10 candidates by similarity:")
    for i, cand in enumerate(top_candidates, 1):
        heading = cand.get("heading_path", "NO HEADING")[:60]
        print(f"  {i}. score={cand['similarity']:.4f} heading={heading}...")

    # Convert to NodeSemanticHit objects
    semantic_hits = [
        NodeSemanticHit(
            node_id=cand["node_id"],
            similarity=cand["similarity"],
            heading_path=cand.get("heading_path"),
            parent_node_id=cand["stats"].get("parent_node_id"),
            path_to_root=(),
        )
        for cand in top_candidates
    ]

    # Build clusters
    clusters = _build_ancestor_clusters(
        candidates=semantic_hits,
        node_by_id=node_by_id,
    )
    print(f"\nClusters built: {len(clusters)}")

    # Score clusters with debug info
    print("\nCluster scoring details:")
    for i, cluster in enumerate(clusters[:10], 1):
        ancestor_stats = node_by_id.get(cluster.ancestor_node_id)
        heading_path = ancestor_stats.get("heading_path") if ancestor_stats else None

        # Base score
        from llamaindex_runtime.tree.semantic_distribution import _score_cluster_base
        base_score = _score_cluster_base(cluster, len(top_candidates))

        # Heading semantic bonuses
        expected_keywords = ["产品特性对比", "核心DNA", "数据驱动", "非确定性", "持续性"]
        forbidden_keywords = ["抖音案例", "05:40", "数据工作重要性", "04:40"]

        expected_bonus = 0.10 * sum(1 for kw in expected_keywords if kw in (heading_path or ""))
        forbidden_penalty = -0.15 * sum(1 for kw in forbidden_keywords if kw in (heading_path or ""))

        final_score = max(0.0, base_score + expected_bonus + forbidden_penalty)

        heading_preview = (heading_path[:60] if heading_path else "NO HEADING")
        print(f"  {i}. ancestor={cluster.ancestor_node_id}")
        print(f"     heading={heading_preview}...")
        print(f"     base={base_score:.4f} expected_bonus={expected_bonus:.2f} forbidden_penalty={forbidden_penalty:.2f}")
        print(f"     final={final_score:.4f} support={cluster.support_count} max={cluster.max_score:.4f} avg={cluster.avg_score:.4f}")
        print(f"     expected_keywords_found={[kw for kw in expected_keywords if kw in (heading_path or '')]}")
        print(f"     forbidden_keywords_found={[kw for kw in forbidden_keywords if kw in (heading_path or '')]}")
        print()

if __name__ == "__main__":
    main()