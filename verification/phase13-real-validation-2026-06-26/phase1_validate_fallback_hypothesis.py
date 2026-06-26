"""Phase 1 诊断：验证 Q18 父节点的子树是否为空 chunk（导致 fallback）"""
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

# Q18 的 5 个 node_id（chunk_id=null）
node_ids = [
    'ba0433ef-789e-57c3-bf58-64f8ecf21431',  # Phase 2：检索backend增强
    'c22a9191-f5d1-5901-b668-cb5f402e6881',  # Token消耗对比
    'ae8e715b-3e1b-5838-8e37-c3f52a9fd51b',  # 推荐集成方案 > 架构
    'ab528c0e-e25a-5044-ba37-a2758a51aaad',  # Phase 3：配置与测试
    'd7b0e433-59b9-545c-8c8e-cf41e6af0bd4',  # 用户意图理解 > 完整集成PageIndex
]

print('=== Phase 1 Root Cause Validation ===\n')
print('Hypothesis: Parent nodes have no subtree chunks → subtree_vectors=[] → node_stats missing → fallback\n')

for nid in node_ids:
    uuid_obj = UUID(nid)

    # 1. Check if node exists
    cur = conn.execute("""
        SELECT node_id, heading_path, level_no, parent_node_id
        FROM tree_nodes
        WHERE node_id = %s
        LIMIT 1
    """, (uuid_obj,))
    node_row = cur.fetchone()

    if not node_row:
        print(f'[SKIP] Node {nid} NOT FOUND in tree_nodes (old version_id)\n')
        continue

    node_id, heading, level, parent_id = node_row
    print(f'Node: {heading}')
    print(f'  node_id: {nid}')

    # 2. Check direct chunks (node_chunk_mapping)
    cur = conn.execute("""
        SELECT COUNT(*) FROM node_chunk_mapping WHERE node_id = %s
    """, (uuid_obj,))
    direct_chunk_count = cur.fetchone()[0]
    print(f'  direct_chunks: {direct_chunk_count}')

    # 3. Check child nodes
    cur = conn.execute("""
        SELECT COUNT(*) FROM tree_nodes WHERE parent_node_id = %s
    """, (uuid_obj,))
    child_count = cur.fetchone()[0]
    print(f'  child_count: {child_count}')

    # 4. Check descendant chunks (subtree chunks) - BFS to depth 5
    subtree_chunk_count = 0
    visited = {uuid_obj}
    queue = [uuid_obj]

    for depth in range(5):  # Max depth 5
        if not queue:
            break
        current_level = queue
        queue = []

        for current_node_id in current_level:
            # Get children
            cur = conn.execute("""
                SELECT node_id FROM tree_nodes WHERE parent_node_id = %s
            """, (current_node_id,))
            children = [row[0] for row in cur.fetchall()]

            for child_id in children:
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append(child_id)

                    # Count chunks at this child
                    cur = conn.execute("""
                        SELECT COUNT(*) FROM node_chunk_mapping WHERE node_id = %s
                    """, (child_id,))
                    child_chunk_count = cur.fetchone()[0]
                    subtree_chunk_count += child_chunk_count

    print(f'  subtree_chunks (depth≤5): {subtree_chunk_count}')

    # 5. Check vector_chunks (embeddings)
    cur = conn.execute("""
        SELECT COUNT(*) FROM vector_chunks WHERE node_id = %s AND embedding IS NOT NULL
    """, (uuid_obj,))
    direct_vectors = cur.fetchone()[0]
    print(f'  direct_vectors (with embedding): {direct_vectors}')

    # 6. Check descendant vectors
    subtree_vectors = 0
    for descendant_id in visited:
        if descendant_id == uuid_obj:
            continue
        cur = conn.execute("""
            SELECT COUNT(*) FROM vector_chunks WHERE node_id = %s AND embedding IS NOT NULL
        """, (descendant_id,))
        descendant_vectors = cur.fetchone()[0]
        subtree_vectors += descendant_vectors

    print(f'  subtree_vectors (depth≤5): {subtree_vectors}')

    # 7. Diagnosis
    print(f'  ** Diagnosis: **')
    if direct_vectors == 0 and subtree_vectors == 0:
        print(f'     ✓ CONFIRMED: vectors=[] → node_stats will be skipped (line 243-244)')
        print(f'     → traverse returns [] → fallback triggered → chunk_id=null')
    elif direct_chunk_count == 0 and subtree_chunk_count > 0:
        print(f'     ⚠ UNEXPECTED: is_route_node should be True')
        print(f'     → policy should return "drill_down" → traverse should succeed')
    else:
        print(f'     ⚠ UNEXPECTED: vectors present, node_stats should exist')

    print()

conn.close()