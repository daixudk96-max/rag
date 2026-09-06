"""诊断：检查 Q18 的 5 个 node_id 为什么 traverse 没有 drill down"""
import os
import psycopg
from dotenv import load_dotenv
from pathlib import Path
from uuid import UUID
import numpy as np

# Load .env
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / '.env', override=False)
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print('[ERROR] DATABASE_URL not set')
    exit(2)

# Connect
conn = psycopg.connect(db_url)

# Q18 的 5 个 node_id
node_ids = [
    'ba0433ef-789e-57c3-bf58-64f8ecf21431',  # Phase 2：检索backend增强
    'c22a9191-f5d1-5901-b668-cb5f402e6881',  # Token消耗对比
    'ae8e715b-3e1b-5838-8e37-c3f52a9fd51b',  # 推荐集成方案 > 架构
    'ab528c0e-e25a-5044-ba37-a2758a51aaad',  # Phase 3：配置与测试
    'd7b0e433-59b9-545c-8c8e-cf41e6af0bd4',  # 用户意图理解 > 完整集成PageIndex
]

print('=== Q18 traverse 逻辑诊断 ===\n')

for nid in node_ids:
    uuid_obj = UUID(nid)

    # 1. 查询 node 基本信息
    cur = conn.execute("""
        SELECT node_id, parent_node_id, level_no, heading_path, summary_text
        FROM tree_nodes
        WHERE node_id = %s
        LIMIT 1
    """, (uuid_obj,))
    node_row = cur.fetchone()

    if not node_row:
        print(f'Node {nid} NOT FOUND\n')
        continue

    node_id, parent_id, level, heading, summary = node_row
    print(f'Node: {heading}')
    print(f'  node_id: {nid}')
    print(f'  level_no: {level}')

    # 判断是否 leaf：没有子节点就是 leaf
    cur = conn.execute("""
        SELECT COUNT(*) FROM tree_nodes WHERE parent_node_id = %s
    """, (uuid_obj,))
    child_count = cur.fetchone()[0]
    is_leaf = (child_count == 0)
    print(f'  is_leaf (推断): {is_leaf} (child_count={child_count})')

    # 2. 查询子节点数量
    cur = conn.execute("""
        SELECT COUNT(*) FROM tree_nodes WHERE parent_node_id = %s
    """, (uuid_obj,))
    child_count = cur.fetchone()[0]
    print(f'  child_count: {child_count}')

    # 3. 查询 node_stats (support_count, dispersion, entropy)
    cur = conn.execute("""
        SELECT support_count, dispersion, entropy, prototype_embedding
        FROM semantic_distribution
        WHERE node_id = %s
        ORDER BY computed_at DESC
        LIMIT 1
    """, (uuid_obj,))
    stats_row = cur.fetchone()

    if stats_row:
        support, dispersion, entropy, prototype = stats_row
        print(f'  support_count: {support}')
        print(f'  dispersion: {dispersion:.4f}')
        print(f'  entropy: {entropy:.4f}')

        # 4. 模拟 policy.decide_branch_action (BaselineTreeBranchDecisionPolicy)
        # 参数来自 runtime.py line 241-244:
        # dispersion_threshold=1.0, entropy_threshold=0.5, min_support_threshold=1

        if support < 1:
            decision = "prune"
            reason = f"support_count={support} < min_support_threshold=1"
        elif child_count > 0:  # is_route_node: 有子节点
            decision = "drill_down"
            reason = f"is_route_node (child_count={child_count}, is_leaf={is_leaf})"
        else:  # is_leaf
            high_dispersion = dispersion > 1.0
            high_entropy = entropy > 0.5

            if high_dispersion and high_entropy:
                decision = "drill_down"
                reason = f"high_dispersion={high_dispersion} AND high_entropy={high_entropy}"
            else:
                decision = "keep_parent"
                reason = f"NOT (high_dispersion AND high_entropy): dispersion={dispersion:.4f}, entropy={entropy:.4f}"

        print(f'  ** policy.decide_branch_action: {decision}**')
        print(f'     reason: {reason}')
    else:
        print(f'  [WARNING] node_stats NOT FOUND in semantic_distribution')

    print()

conn.close()