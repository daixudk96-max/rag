#!/usr/bin/env python3
"""Check Phase 14 registry connection autocommit status"""

import os, sys
import psycopg
from pathlib import Path
from uuid import UUID
import json
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env', override=False)

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

status_path = Path(__file__).parent / '02_document_ingestion_status.json'
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status['version_id'])

db_url = os.environ['DATABASE_URL']

# Test 1: Connection without autocommit (Phase 14 pattern)
conn1 = psycopg.connect(db_url)  # No autocommit
print(f"Test 1 - Connection autocommit before registry: {conn1.autocommit}")

registry1 = PostgresRegistryWriter(conn1)
print(f"Test 1 - Connection autocommit after registry: {conn1.autocommit}")

# Check node_embeddings
count1 = conn1.execute("SELECT count(*) FROM node_embeddings").fetchone()
print(f"Test 1 - node_embeddings count: {count1[0]}")

conn1.close()

print("\n" + "="*60 + "\n")

# Test 2: Connection with autocommit (correct pattern)
conn2 = psycopg.connect(db_url, autocommit=True)
print(f"Test 2 - Connection autocommit: {conn2.autocommit}")

registry2 = PostgresRegistryWriter(conn2)
print(f"Test 2 - Registry connection autocommit: {conn2.autocommit}")

# Check node_embeddings
count2 = conn2.execute("SELECT count(*) FROM node_embeddings").fetchone()
print(f"Test 2 - node_embeddings count: {count2[0]}")

conn2.close()