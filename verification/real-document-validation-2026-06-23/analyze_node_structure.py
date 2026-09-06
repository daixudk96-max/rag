"""白盒分析：检查命中 node 的结构（是否 leaf、是否有子节点、是否有 chunks）"""
import os
import psycopg
from dotenv import load_dotenv
from pathlib import Path
from uuid import UUID

# Load .env
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / '.env', override=False)
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print('[ERROR] DATABASE_URL not set')
    exit(2)

# Connect
conn = psycopg.connect(db_url)
cur = conn.cursor()

# 检查命中最多的 node_id
node_ids = [
    'f5a9c94d-7392-59ca-8758-77f9d92a6a60',  # 总结 > 关键发现 (命中 7 次)
    '4071cdab-6678-5947-b397-dceecce45ab9',  # 总结 > 下一步 (命中 6 次)
    '106424cb-4e47-5866-a0d2-c41e7869218f',  # 用户意图理解 (命中 4 次)
    'c22a9191-f5d1-5901-b668-cb5f402e6881',  # Token消耗对比 (命中 2 次)
]

print('=== Node Structure Analysis ===\n')

for nid in node_ids:
    try:
        uuid_obj = UUID(nid)

        # 查询 node 基本信息
        cur.execute("""
            SELECT node_id, parent_node_id, level, heading_path, is_leaf
            FROM tree_nodes
            WHERE node_id = %s
            LIMIT 1
        """, (uuid_obj,))
        node_row = cur.fetchone()

        if node_row:
            node_id, parent_id, level, heading, is_leaf = node_row
            print(f'Node: {nid}')
            print(f'  heading_path: {heading}')
            print(f'  level: {level}')
            print(f'  is_leaf: {is_leaf}')
            print(f'  parent_node_id: {parent_id}')

            # 查询有多少子节点
            cur.execute("""
                SELECT COUNT(*) FROM tree_nodes WHERE parent_node_id = %s
            """, (uuid_obj,))
            child_count = cur.fetchone()[0]
            print(f'  child_count: {child_count}')

            # 查询有多少 chunks
            cur.execute("""
                SELECT COUNT(*) FROM node_chunk_mapping WHERE node_id = %s
            """, (uuid_obj,))
            chunk_count = cur.fetchone()[0]
            print(f'  chunk_count: {chunk_count}')

            print()
        else:
            print(f'Node {nid} NOT FOUND in tree_nodes\n')
    except Exception as e:
        print(f'[ERROR] querying {nid}: {e}\n')

conn.close()