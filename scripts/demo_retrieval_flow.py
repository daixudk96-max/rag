"""演示真实检索流程，打印每一步执行细节。"""
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

import uuid
import json
from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
import psycopg

# 使用刚创建的新 version（从 workflow 输出）
version_id = uuid.UUID("008442cf-ec96-47e5-8552-99962911587a")

print(f"=== 检索演示开始 ===")
print(f"Active Version ID: {version_id}")
print()

# 连接数据库
db_url = os.environ["DATABASE_URL"]
print(f"连接数据库...")
with psycopg.connect(db_url) as conn:
    registry = PostgresRegistryWriter(conn)

    # 检查健康状态
    healthy = registry.healthcheck()
    print(f"数据库健康检查: {healthy}")
    print()

    # 创建 backend
    backend = ReasoningTreeBackend(llm_model="gpt-4o-mini")
    print(f"创建 ReasoningTreeBackend (model: gpt-4o-mini)")
    print()

    # 测试 query
    query = "文档的主要章节结构是什么？列出所有一级标题。"
    print(f"测试 Query: {query}")
    print()

    print(f"=== 开始检索流程 ===")
    print(f"Step 1: 获取树结构...")
    print()

    # 调用检索
    hits = backend.retrieve_tree_hits(
        query_text=query,
        version_id=version_id,
        registry=registry,
        limit=5
    )

    print(f"=== 检索结果 ===")
    print(f"返回 {len(hits)} 个 hits")
    print()

    for i, hit in enumerate(hits, start=1):
        print(f"Hit #{i}:")
        print(f"  node_id: {hit.node_id}")
        print(f"  chunk_id: {hit.chunk_id}")
        print(f"  heading_path: {hit.heading_path}")
        print(f"  page_no: {hit.page_no}")
        print(f"  text_preview: {hit.text_preview[:100] if hit.text_preview else 'None'}...")
        print(f"  backend_source: {hit.backend_source}")
        print(f"  retrieval_path: {hit.retrieval_path}")
        print()

print("=== 检索演示结束 ===")