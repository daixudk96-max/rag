import psycopg
import os

conn = psycopg.connect(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag"))
cursor = conn.cursor()

# Check document_versions
cursor.execute("SELECT version_id, doc_id, is_active FROM document_versions ORDER BY created_at DESC LIMIT 5")
versions = cursor.fetchall()
print(f"Recent document_versions: {len(versions)}")
for v in versions:
    print(f"  version_id={v[0]}, doc_id={v[1]}, is_active={v[2]}")

# Check tree_nodes
cursor.execute("SELECT COUNT(*) FROM tree_nodes")
tree_count = cursor.fetchone()[0]
print(f"\nTotal tree_nodes: {tree_count}")

if tree_count > 0:
    cursor.execute("SELECT version_id, COUNT(*) FROM tree_nodes GROUP BY version_id")
    node_groups = cursor.fetchall()
    print(f"tree_nodes by version:")
    for ng in node_groups:
        print(f"  version_id={ng[0]}, nodes={ng[1]}")

cursor.close()
conn.close()