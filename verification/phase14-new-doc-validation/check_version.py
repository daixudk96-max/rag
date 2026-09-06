import os
from dotenv import load_dotenv
load_dotenv('E:/github/rag/.env')
import psycopg
conn = psycopg.connect(os.environ['DATABASE_URL'])
rows = conn.execute("""
SELECT d.source_uri, dv.version_id
FROM document_versions dv
JOIN documents d ON dv.doc_id = d.doc_id
WHERE dv.version_id = '550ef3df-1691-46c3-bdbc-40a28ed89870'
""").fetchall()
for r in rows: print(f"source_uri: {r[0]}")
print(f"version_id: {r[1]}")
conn.close()