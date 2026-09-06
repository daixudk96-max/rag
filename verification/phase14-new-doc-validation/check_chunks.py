import os
from dotenv import load_dotenv
load_dotenv('E:/github/rag/.env')
import psycopg
from uuid import UUID

version_id = UUID("550ef3df-1691-46c3-bdbc-40a28ed89870")
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url)

# Check vector_chunks
chunk_rows = conn.execute("""
    SELECT chunk_id, heading_path
    FROM vector_chunks
    WHERE version_id = %s
    ORDER BY heading_path
    LIMIT 10
""", (version_id,)).fetchall()

print(f"Vector chunks for version {version_id}:")
for i, row in enumerate(chunk_rows):
    chunk_id = row[0]
    heading = row[1][:60] if row[1] else ""
    print(f"  [{i+1}] chunk_id={chunk_id[:36]}... heading={heading}...")

print(f"\nTotal chunks: {len(chunk_rows)}")

# Check tree_node_spans
span_rows = conn.execute("""
    SELECT COUNT(*) as count
    FROM tree_node_spans tns
    JOIN tree_nodes tn ON tns.node_id = tn.node_id
    WHERE tn.version_id = %s
""", (version_id,)).fetchone()

print(f"Tree node spans: {span_rows[0] if span_rows else 0}")

conn.close()