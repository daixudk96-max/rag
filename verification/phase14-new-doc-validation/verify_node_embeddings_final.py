#!/usr/bin/env python3
"""验证 node_embeddings 数据持久化"""

import os, sys
import psycopg
from pathlib import Path
from uuid import UUID
import json
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env', override=False)

status_path = Path(__file__).parent / '02_document_ingestion_status.json'
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status['version_id'])

print(f"Version ID: {VERSION_ID}")

db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Check node_embeddings count
result = conn.execute("""
    SELECT count(*) FROM node_embeddings ne
    JOIN tree_nodes tn ON ne.node_id = tn.node_id
    WHERE tn.version_id = %s
""", (str(VERSION_ID),)).fetchone()

print(f"node_embeddings count: {result[0]}")

# Check embedding_model values
models = conn.execute("""
    SELECT DISTINCT embedding_model FROM node_embeddings ne
    JOIN tree_nodes tn ON ne.node_id = tn.node_id
    WHERE tn.version_id = %s
""", (str(VERSION_ID),)).fetchall()

print(f"embedding_models: {[m[0] for m in models]}")

# Sample node_embedding
if result[0] > 0:
    sample = conn.execute("""
        SELECT ne.node_id, ne.embedding_model, vector_dims(ne.embedding_vector) as dim
        FROM node_embeddings ne
        JOIN tree_nodes tn ON ne.node_id = tn.node_id
        WHERE tn.version_id = %s
        LIMIT 1
    """, (str(VERSION_ID),)).fetchone()

    print(f"Sample node_embedding:")
    print(f"  node_id: {sample[0]}")
    print(f"  embedding_model: {sample[1]}")
    print(f"  embedding_dimension: {sample[2]}")

conn.close()