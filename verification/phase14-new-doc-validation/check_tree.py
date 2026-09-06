import os
from dotenv import load_dotenv
load_dotenv('E:/github/rag/.env')
import psycopg
from uuid import UUID

version_id = UUID("550ef3df-1691-46c3-bdbc-40a28ed89870")
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url)

# Query tree_nodes directly
rows = conn.execute("""
    SELECT node_id, parent_node_id, level_no, title
    FROM tree_nodes
    WHERE version_id = %s
    ORDER BY level_no, title
""", (version_id,)).fetchall()

print(f"Tree nodes for version {version_id}:")
for i, row in enumerate(rows):
    node_id = row[0]
    parent_id = row[1] if row[1] else "ROOT"
    level = row[2]
    title = row[3][:50] if row[3] else ""
    print(f"  [{i+1}] node_id={node_id[:36]}... parent={parent_id[:36] if parent_id != 'ROOT' else 'ROOT'}... level={level} title={title}...")

conn.close()