"""检查数据库：哪些节点有 chunks，哪些没有。"""
import json
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

version_id = "a376679b-3a95-4724-a31f-ece0c9fa35b8"  # Phase 8 version

print("=== 数据库节点 chunks 覆盖检查 ===")
print()

db_url = os.environ["DATABASE_URL"]
with psycopg.connect(db_url) as conn:
    registry = PostgresRegistryWriter(conn)

    # 查询所有 tree_nodes
    print("Step 1: 查询所有 tree_nodes")
    nodes = registry.query_tree_nodes_by_version(version_id)
    print(f"  总节点数: {len(nodes)}")
    print()

    # 查询所有 vector_chunks
    print("Step 2: 查询所有 vector_chunks")
    chunks = registry.query_vector_chunks_by_version(version_id)
    print(f"  总 chunks 数: {len(chunks)}")
    print()

    # 构建节点 → chunks 映射
    print("Step 3: 构建节点 → chunks 映射")
    nodes_by_id = {str(node["node_id"]): node for node in nodes}

    # 按 node_id 分组 chunks
    chunks_by_node = {}
    for chunk in chunks:
        node_id = str(chunk.get("node_id", ""))
        if node_id not in chunks_by_node:
            chunks_by_node[node_id] = []
        chunks_by_node[node_id].append(chunk)

    print(f"  有 chunks 的节点数: {len(chunks_by_node)}")
    print(f"  无 chunks 的节点数: {len(nodes) - len(chunks_by_node)}")
    print()

    # 列出无 chunks 的节点
    print("无 chunks 的节点（未被索引）:")
    no_chunk_nodes = []
    for node_id, node in nodes_by_id.items():
        if node_id not in chunks_by_node:
            no_chunk_nodes.append({
                "node_id": node_id,
                "title": node.get("title"),
                "heading_path": node.get("heading_path"),
                "page_no": node.get("page_no") or node.get("page_start"),
            })

    for i, node in enumerate(no_chunk_nodes[:15], start=1):
        print(f"  #{i}: {node['heading_path'][:60]} - title: {node['title'][:30]} - page: {node['page_no']}")
    print()

    # 列出有 chunks 的节点
    print("有 chunks 的节点（已被索引）:")
    for i, (node_id, chunk_list) in enumerate(chunks_by_node.items(), start=1):
        node = nodes_by_id.get(node_id)
        if node:
            print(f"  #{i}: {node['heading_path'][:60]} - chunks数: {len(chunk_list)} - title: {node['title'][:30]}")
    print()

    # 分析无 chunks 的节点特征
    print("=== 分析：为什么某些节点没有 chunks？===")
    print()

    print("无 chunks 的节点 heading_path 特征:")
    heading_only_count = 0
    for node in no_chunk_nodes:
        heading_path = node["heading_path"]
        # 检查是否只有标题，没有实际内容
        title = node["title"]
        # 如果 heading_path 的最后一部分等于 title，说明这是 heading 节点
        if heading_path.split("/")[-1] == title:
            heading_only_count += 1

    print(f"  heading 节点（只有标题）: {heading_only_count}/{len(no_chunk_nodes)}")
    print()

    print("推测:")
    print("  1. 这些节点是 heading 节点，本身没有实际内容段落")
    print("  2. PageIndex 的索引逻辑：只有内容节点才会生成 chunks")
    print("  3. heading 节点只是结构节点，不应该被向量化")
    print()

    print("这是正常的吗？")
    print("  - 如果这些节点确实只有标题，没有内容，那么不索引是正确的")
    print("  - 如果这些节点有内容，但没有索引，那么是索引问题")
    print()

print("=== 检查完成 ===")