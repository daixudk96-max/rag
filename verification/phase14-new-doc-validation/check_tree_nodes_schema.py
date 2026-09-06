#!/usr/bin/env python3
"""
Check tree_nodes table schema
"""

import os
import sys
from pathlib import Path
import json

os.environ['RAG_TREE_HOTSPOT_SELECTOR'] = 'hybrid_cluster'

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=False)

import psycopg

# Get version_id from ingestion status
OUTPUT_DIR = Path(__file__).parent
status_path = OUTPUT_DIR / '02_document_ingestion_status.json'
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = status['version_id']

print(f"Checking tree_nodes schema for version_id: {VERSION_ID}")

# Query PostgreSQL tree_nodes table schema
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Get table columns
result = conn.execute(
    """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tree_nodes'
    ORDER BY ordinal_position
    """
)
columns = result.fetchall()

print('\ntree_nodes table columns:')
for col_name, data_type, is_nullable in columns:
    print(f'  {col_name}: {data_type} (nullable: {is_nullable})')

# Get sample record
sample_result = conn.execute(
    "SELECT * FROM tree_nodes WHERE version_id = %s LIMIT 1",
    (VERSION_ID,)
)
sample = sample_result.fetchone()

if sample:
    print('\nSample record:')
    for i, (col_name, _, _) in enumerate(columns):
        print(f'  {col_name}: "{sample[i]}"')
else:
    print('\nNo records found for this version_id')

conn.close()