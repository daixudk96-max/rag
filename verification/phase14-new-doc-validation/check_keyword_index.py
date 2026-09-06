#!/usr/bin/env python3
"""
Check keyword_index table in PostgreSQL database
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

print(f"Checking keyword_index for version_id: {VERSION_ID}")

# Query PostgreSQL keyword_index table
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Check if keyword_index table exists
result = conn.execute(
    "SELECT EXISTS (SELECT FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name = 'keyword_index')"
)
table_exists = result.fetchone()[0]

print(f'keyword_index table exists: {table_exists}')

if table_exists:
    # Query count for this version
    count_result = conn.execute(
        'SELECT COUNT(*) FROM keyword_index WHERE version_id = %s',
        (VERSION_ID,)
    )
    count = count_result.fetchone()[0]
    print(f'keyword_index table count (version {VERSION_ID}): {count}')

    # Query total count
    total_count_result = conn.execute('SELECT COUNT(*) FROM keyword_index')
    total_count = total_count_result.fetchone()[0]
    print(f'keyword_index table total count: {total_count}')

    # Query sample records
    if count > 0:
        sample_result = conn.execute(
            'SELECT keyword, node_id, version_id FROM keyword_index '
            'WHERE version_id = %s LIMIT 10',
            (VERSION_ID,)
        )
        samples = sample_result.fetchall()
        print(f'\nSample records for version {VERSION_ID}:')
        for s in samples:
            print(f'  keyword: "{s[0]}" | node_id: {s[1]} | version_id: {s[2]}')

    # Check keyword distribution
    if count > 0:
        keyword_dist_result = conn.execute(
            'SELECT keyword, COUNT(*) as freq FROM keyword_index '
            'WHERE version_id = %s GROUP BY keyword ORDER BY freq DESC LIMIT 10',
            (VERSION_ID,)
        )
        keyword_dist = keyword_dist_result.fetchall()
        print(f'\nTop 10 keywords by frequency:')
        for kw, freq in keyword_dist:
            print(f'  "{kw}": {freq} nodes')

else:
    print("keyword_index table does NOT exist")

conn.close()