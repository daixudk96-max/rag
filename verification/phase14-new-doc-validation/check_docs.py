import os
from dotenv import load_dotenv
load_dotenv('E:/github/rag/.env')
import psycopg
conn = psycopg.connect(os.environ['DATABASE_URL'])
rows = conn.execute("SELECT source_uri FROM documents LIMIT 10").fetchall()
for r in rows: print(r[0])
conn.close()