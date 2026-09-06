#!/usr/bin/env python3
"""
Check tree_nodes heading_path values in PostgreSQL
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

print(f"Checking tree_nodes for version_id: {VERSION_ID}")

# Query PostgreSQL tree_nodes table
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Check heading_path values
result = conn.execute(
    """
    SELECT node_id, depth, heading_path, node_type, heading
    FROM tree_nodes
    WHERE version_id = %s
    ORDER BY depth, node_id
    LIMIT 20
    """,
    (VERSION_ID,)
)
nodes = result.fetchall()

print(f'\nTotal nodes sampled: {len(nodes)}')
print('\nNode details (depth, heading_path, heading):')
for node_id, depth, heading_path, node_type, heading in nodes:
    print(f'  node_id: {node_id}')
    print(f'    depth: {depth}')
    print(f'    heading_path: "{heading_path}"')
    print(f'    heading: "{heading}"')
    print(f'    node_type: {node_type}')
    print()

# Check if heading_path is empty
empty_heading_path_result = conn.execute(
    """
    SELECT COUNT(*) FROM tree_nodes
    WHERE version_id = %s AND (heading_path IS NULL OR heading_path = '')
    """,
    (VERSION_ID,)
)
empty_count = empty_heading_path_result.fetchone()[0]

total_result = conn.execute(
    "SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s",
    (VERSION_ID,)
)
total_count = total_result.fetchone()[0]

print(f'Nodes with empty heading_path: {empty_count}/{total_count}')

# Check heading_path length distribution
length_dist_result = conn.execute(
    """
    SELECT
        CASE
            WHEN heading_path IS NULL OR heading_path = '' THEN 'empty'
            WHEN LENGTH(heading_path) < 20 THEN 'short (<20)'
            WHEN LENGTH(heading_path) < 50 THEN 'medium (20-50)'
            WHEN LENGTH(heading_path) < 100 THEN 'long (50-100)'
            ELSE 'very_long (>100)'
        END as length_category,
        COUNT(*) as count
    FROM tree_nodes
    WHERE version_id = %s
    GROUP BY length_category
    ORDER BY
        CASE length_category
            WHEN 'empty' THEN 1
            WHEN 'short (<20)' THEN 2
            WHEN 'medium (20-50)' THEN 3
            WHEN 'long (50-100)' THEN 4
            ELSE 5
        END
    """,
    (VERSION_ID,)
)
length_dist = length_dist_result.fetchall()

print('\nHeading path length distribution:')
for category, count in length_dist:
    print(f'  {category}: {count} nodes')

conn.close()