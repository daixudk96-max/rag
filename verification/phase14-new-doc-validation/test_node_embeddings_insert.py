#!/usr/bin/env python3
"""Test node_embeddings INSERT directly"""

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

db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Get one node_id from tree_nodes
node_row = conn.execute("""
    SELECT node_id FROM tree_nodes WHERE version_id = %s LIMIT 1
""", (str(VERSION_ID),)).fetchone()

if not node_row:
    print("ERROR: No tree_nodes found")
    sys.exit(1)

node_id_raw = node_row[0]
node_id = node_id_raw if isinstance(node_id_raw, UUID) else UUID(node_id_raw)
print(f"Test node_id: {node_id}")

# Test INSERT with fake embedding
fake_embedding = [0.1] * 384  # 384-dimensional vector
vector_str = "[" + ",".join(str(v) for v in fake_embedding) + "]"

print(f"Vector string format: {vector_str[:50]}...")

try:
    result = conn.execute("""
        INSERT INTO node_embeddings (node_id, embedding_model, embedding_vector)
        VALUES (%s, %s, %s)
        ON CONFLICT (node_id, embedding_model) DO NOTHING
    """, (str(node_id), 'test-model', vector_str))

    print(f"INSERT executed: {result.rowcount} rows affected")

    # Check if data was written
    check_row = conn.execute("""
        SELECT node_id, embedding_model FROM node_embeddings WHERE node_id = %s
    """, (str(node_id),)).fetchone()

    if check_row:
        print(f"SUCCESS: Data persisted - node_id={check_row[0]}, model={check_row[1]}")
    else:
        print("ERROR: Data not found after INSERT")

except Exception as e:
    print(f"ERROR: INSERT failed with exception: {e}")
    import traceback
    traceback.print_exc()

conn.close()