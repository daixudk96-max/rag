"""Debug script to verify heading hierarchy."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()

def main():
    # Connect to database
    database_url = "postgresql://postgres:postgres@localhost:5432/rag"
    conn = psycopg.connect(database_url, row_factory=dict_row)

    with conn.cursor() as cur:
        # Get p6 version
        cur.execute('''
            SELECT version_id FROM tree_versions
            WHERE slug = 'p6-ai-product-manager'
            ORDER BY created_at DESC LIMIT 1
        ''')
        row = cur.fetchone()
        if not row:
            print("ERROR: No version found")
            return
        version_id = row["version_id"]
        print(f"Version ID: {version_id}\n")

        # Get nodes with expected keywords
        expected_keywords = ["产品特性对比", "核心DNA", "数据驱动", "非确定性", "持续性"]
        for kw in expected_keywords:
            cur.execute('''
                SELECT node_id, heading_path, parent_node_id
                FROM tree_nodes
                WHERE version_id = %s AND heading_path LIKE %s
                ORDER BY level_no
            ''', (version_id, f"%{kw}%"))
            rows = cur.fetchall()
            print(f"Keyword '{kw}' found in {len(rows)} nodes:")
            for r in rows:
                print(f"  node_id={r['node_id']}")
                print(f"  heading_path={r['heading_path']}")
                print(f"  parent_node_id={r['parent_node_id']}")
                print()

        # Get nodes with forbidden keywords
        forbidden_keywords = ["抖音案例", "05:40", "数据工作重要性", "04:40"]
        for kw in forbidden_keywords:
            cur.execute('''
                SELECT node_id, heading_path, parent_node_id
                FROM tree_nodes
                WHERE version_id = %s AND heading_path LIKE %s
                ORDER BY level_no
            ''', (version_id, f"%{kw}%"))
            rows = cur.fetchall()
            print(f"Keyword '{kw}' found in {len(rows)} nodes:")
            for r in rows:
                print(f"  node_id={r['node_id']}")
                print(f"  heading_path={r['heading_path']}")
                print(f"  parent_node_id={r['parent_node_id']}")
                print()

        # Check ancestor chain for a specific node
        print("\n=== Ancestor chain for 'AI产品经理核心DNA' node ===")
        cur.execute('''
            SELECT node_id, heading_path, parent_node_id, level_no
            FROM tree_nodes
            WHERE version_id = %s AND heading_path LIKE '%AI产品经理核心DNA%'
            LIMIT 1
        ''', (version_id,))
        target_row = cur.fetchone()
        if target_row:
            print(f"Target node: {target_row['heading_path']}")
            print(f"  node_id={target_row['node_id']}")
            print(f"  parent_node_id={target_row['parent_node_id']}")

            # Walk up the chain
            current_id = target_row["parent_node_id"]
            depth = 0
            while current_id and depth < 10:
                cur.execute('''
                    SELECT node_id, heading_path, parent_node_id, level_no
                    FROM tree_nodes
                    WHERE node_id = %s
                ''', (current_id,))
                parent_row = cur.fetchone()
                if not parent_row:
                    break
                print(f"  Level {parent_row['level_no']}: {parent_row['heading_path']}")
                print(f"    node_id={parent_row['node_id']}")
                current_id = parent_row["parent_node_id"]
                depth += 1

    conn.close()

if __name__ == "__main__":
    main()