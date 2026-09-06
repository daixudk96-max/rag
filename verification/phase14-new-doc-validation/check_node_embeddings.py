#!/usr/bin/env python3
"""
检查 Phase 14 的 node_embeddings 数据
"""

import os
import psycopg
from pathlib import Path
from dotenv import load_dotenv
import json
from uuid import UUID

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

status_path = Path(__file__).parent / "02_document_ingestion_status.json"
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status["version_id"])

db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url, autocommit=True)

print(f"Version ID: {VERSION_ID}")

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

# Check tree_nodes count
nodes_count = conn.execute("""
    SELECT count(*) FROM tree_nodes WHERE version_id = %s
""", (str(VERSION_ID),)).fetchone()

print(f"tree_nodes count: {nodes_count[0]}")

conn.close()