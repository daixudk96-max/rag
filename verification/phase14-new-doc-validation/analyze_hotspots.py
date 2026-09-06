#!/usr/bin/env python3
"""
Hotspot Analysis — 分析热点节点的类型和子节点结构
=================================================

目标：确定 Phase 14 验证中的热点是：
  1. Cluster hotspot（父节点，coverage-based）
  2. Leaf fallback hotspot（叶子节点）
"""

import json
import os
from pathlib import Path
from uuid import UUID
from collections import Counter

os.environ["PYTHONPATH"] = "E:\\github\\rag"

from dotenv import load_dotenv
import psycopg

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

OUTPUT_DIR = Path(__file__).parent

# Read retrieval results
with open(OUTPUT_DIR / "05_retrieval_results.json", 'r', encoding='utf-8') as f:
    results = json.load(f)

version_id = UUID(results["version_id"])

# Collect hotspot_node_ids
hotspot_counter = Counter()
for q_result in results["results"]:
    for hit in q_result["hits"]:
        hotspot_node_id = hit.get("hotspot_node_id")
        if hotspot_node_id:
            hotspot_counter[hotspot_node_id] += 1

print(f"[VERSION] {version_id}")
print(f"[HOTSPOTS] {len(hotspot_counter)} unique hotspot nodes")

# Query database for tree structure
db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url)

# Get tree nodes
nodes_rows = conn.execute("""
    SELECT node_id, parent_node_id, node_type, level_no, title, heading_path
    FROM tree_nodes
    WHERE version_id = %s
""", (version_id,)).fetchall()

node_by_id = {}
parent_to_children = {}
for row in nodes_rows:
    node_id = UUID(row[0])
    parent_id = UUID(row[1]) if row[1] else None
    node_by_id[node_id] = {
        "node_id": node_id,
        "parent_node_id": parent_id,
        "node_type": row[2],
        "level_no": row[3],
        "title": row[4],
        "heading_path": row[5],
    }
    if parent_id not in parent_to_children:
        parent_to_children[parent_id] = []
    parent_to_children[parent_id].append(node_id)

print(f"[TREE] {len(node_by_id)} nodes")

# Analyze hotspots
print("\n" + "="*60)
print("HOTSPOT ANALYSIS")
print("="*60)

for hotspot_id, hit_count in hotspot_counter.most_common(5):
    hotspot_uuid = UUID(hotspot_id)
    node_info = node_by_id.get(hotspot_uuid)

    if not node_info:
        print(f"\n[ERROR] Hotspot {hotspot_id} not found in tree_nodes")
        continue

    parent_id = node_info["parent_node_id"]
    children = parent_to_children.get(hotspot_uuid, [])
    level_no = node_info["level_no"]
    title = node_info["title"] or ""
    heading = node_info["heading_path"] or ""

    # Determine hotspot type
    is_leaf = len(children) == 0
    is_root = parent_id is None

    # Check if hotspot has direct chunks
    chunk_rows = conn.execute("""
        SELECT chunk_id FROM vector_chunks
        WHERE version_id = %s AND heading_path = %s
        LIMIT 5
    """, (version_id, heading)).fetchall()

    has_direct_chunks = len(chunk_rows) > 0

    hotspot_type = "UNKNOWN"
    if is_leaf:
        hotspot_type = "LEAF_FALLBACK"
    elif is_root:
        hotspot_type = "ROOT_OR_TOP_LEVEL"
    elif len(children) > 0:
        hotspot_type = "CLUSTER_COVERAGE"
    else:
        hotspot_type = "OTHER"

    print(f"\nHotspot {hotspot_id[:36]}...")
    print(f"  Hit count: {hit_count}")
    print(f"  Type: {hotspot_type}")
    print(f"  Level: {level_no}")
    print(f"  Title: {title[:60]}...")
    print(f"  Heading: {heading[:60]}...")
    print(f"  Parent: {parent_id[:36] if parent_id else 'ROOT'}...")
    print(f"  Children: {len(children)}")
    print(f"  Has direct chunks: {has_direct_chunks}")

    # Show children if cluster hotspot
    if hotspot_type == "CLUSTER_COVERAGE" and children:
        print(f"  Child nodes:")
        for i, child_id in enumerate(children[:3]):
            child_info = node_by_id.get(child_id)
            if child_info:
                child_title = child_info.get("title", "")[:40]
                child_level = child_info.get("level_no", "?")
                print(f"    [{i+1}] level={child_level} title={child_title}...")

conn.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("""
分析结果说明：
  - CLUSTER_COVERAGE：父节点，通过 coverage >= 0.5 选中
  - LEAF_FALLBACK：叶子节点，没有父节点满足条件时返回
  - ROOT_OR_TOP_LEVEL：根节点或顶层节点（特殊情况）
  - drill_depth=0：热点本身的 chunks（不是子节点的 chunks）
""")