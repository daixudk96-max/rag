#!/usr/bin/env python3
"""
Check if keywords appear in heading_path
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

print(f"Checking keyword matches in heading_path for version_id: {VERSION_ID}")

# Query PostgreSQL tree_nodes table
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Keywords to check
keywords = ['kag', 'nexusrag', '知识图谱', 'KAG', 'NexusRAG']

# Get all heading_paths first
all_paths_result = conn.execute(
    """
    SELECT node_id, heading_path
    FROM tree_nodes
    WHERE version_id = %s AND heading_path IS NOT NULL AND heading_path != ''
    """,
    (VERSION_ID,)
)
all_paths = all_paths_result.fetchall()

print(f'\nTotal nodes with heading_path: {len(all_paths)}')

# Check keyword matches manually (case-insensitive)
keyword_matches = {}
for keyword in keywords:
    matches = []
    keyword_lower = keyword.lower()
    for node_id, heading_path in all_paths:
        if keyword_lower in heading_path.lower():
            matches.append((node_id, heading_path))

    print(f'\nKeyword "{keyword}": {len(matches)} matches')
    for node_id, heading_path in matches[:5]:  # Show first 5
        print(f'  node_id: {node_id}')
        heading_preview = heading_path[:100] + '...' if len(heading_path) > 100 else heading_path
        print(f'  heading_path: {heading_preview}')

    keyword_matches[keyword] = [
        {"node_id": str(node_id), "heading_path": heading_path}
        for node_id, heading_path in matches
    ]

# Save to JSON for better UTF-8 display
output_data = {
    "version_id": VERSION_ID,
    "total_nodes_with_heading_path": len(all_paths),
    "sample_heading_paths": [
        {"node_id": str(node_id), "heading_path": heading_path}
        for node_id, heading_path in all_paths[:20]
    ],
    "keyword_matches": keyword_matches
}

with open(OUTPUT_DIR / 'heading_path_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f'\nSaved analysis to heading_path_analysis.json')

conn.close()