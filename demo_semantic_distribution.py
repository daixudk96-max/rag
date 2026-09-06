#!/usr/bin/env python
"""White-box demo for node-level semantic distribution analysis.

This script demonstrates Phase 1 baseline:
1. Load a real document version from PostgreSQL registry
2. Compute node-level semantic distribution stats
3. Print outputs: centroid, dispersion, entropy, support_count
4. Demonstrate BaselineTreeBranchDecisionPolicy decisions
"""

import os
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.semantic_distribution import (
    BaselineTreeBranchDecisionPolicy,
    PersistedTreeSemanticDistributionAdapter,
)


def main() -> None:
    # 1. Connect to PostgreSQL registry
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        sys.exit(1)

    connection = psycopg.connect(database_url)
    registry = PostgresRegistryWriter(connection)

    # 2. Find a real version_id with tree data
    with connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT tn.version_id, d.title
            FROM tree_nodes tn
            JOIN versions v ON tn.version_id = v.version_id
            JOIN documents d ON v.doc_id = d.doc_id
            ORDER BY tn.version_id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()

    if not row:
        print("ERROR: No tree_nodes found in database")
        print("Please run vector persistence tests to populate sample data first")
        sys.exit(1)

    version_id = uuid.UUID(str(row["version_id"]))
    document_title = row["title"]

    print("=" * 80)
    print("White-box Demo: Node-level Semantic Distribution Analysis")
    print("=" * 80)
    print(f"Document: {document_title}")
    print(f"Version ID: {version_id}")
    print()

    # 3. Compute semantic distribution stats
    adapter = PersistedTreeSemanticDistributionAdapter()
    result = adapter.analyze_tree_semantic_distribution(
        version_id=version_id,
        registry=registry,
    )

    tree_signals = result["tree_signals"]
    node_stats = result["node_stats"]

    print("Tree Signals:")
    print(f"  - Node count: {tree_signals['node_count']}")
    print(f"  - Analyzed node count: {tree_signals['analyzed_node_count']}")
    print(f"  - Skipped chunk count: {tree_signals['skipped_chunk_count']}")
    print(f"  - Embedding dimension: {tree_signals['embedding_dimension']}")
    print()

    # 4. Print per-node stats
    print("Node-level Semantic Distribution Stats:")
    print("-" * 80)

    for i, stats in enumerate(node_stats[:10], 1):  # Limit to first 10 nodes for readability
        heading_path = stats.get("heading_path", "N/A")
        print(f"\nNode {i}: {heading_path}")
        print(f"  Node ID: {stats['node_id']}")
        print(f"  Span IDs: {len(stats['span_ids'])} spans")
        print(f"  Chunk IDs: {len(stats['chunk_ids'])} chunks")
        print(f"  Centroid: [{stats['centroid'][0]:.4f}, {stats['centroid'][1]:.4f}, ...] (dim={len(stats['centroid'])})")
        print(f"  Dispersion: {stats['dispersion']:.4f}")
        print(f"  Entropy: {stats['entropy']:.4f}")
        print(f"  Support count: {stats['support_count']}")

    if len(node_stats) > 10:
        print(f"\n... (showing 10 of {len(node_stats)} nodes)")

    print()
    print("-" * 80)

    # 5. Demonstrate BaselineTreeBranchDecisionPolicy
    print("\nBaselineTreeBranchDecisionPolicy Demo:")
    print("-" * 80)

    policy = BaselineTreeBranchDecisionPolicy(
        dispersion_threshold=1.0,
        entropy_threshold=0.5,
        min_support_threshold=5,
    )

    print(f"Policy parameters:")
    print(f"  - Dispersion threshold: {policy.dispersion_threshold}")
    print(f"  - Entropy threshold: {policy.entropy_threshold}")
    print(f"  - Min support threshold: {policy.min_support_threshold}")
    print()

    decisions = {}
    for stats in node_stats:
        decision = policy.decide_branch_action(
            node_stats=stats,
            tree_signals=tree_signals,
        )
        decisions[decision] = decisions.get(decision, 0) + 1

    print("Decision distribution across all nodes:")
    for decision, count in sorted(decisions.items()):
        print(f"  - {decision}: {count} nodes")

    print()
    print("=" * 80)
    print("Demo complete!")
    print("=" * 80)

    connection.close()


if __name__ == "__main__":
    main()