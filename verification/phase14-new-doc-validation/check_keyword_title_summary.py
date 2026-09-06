#!/usr/bin/env python3
"""
Check if keywords appear in title or summary_text
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

print(f"Checking keyword matches in title/summary_text for version_id: {VERSION_ID}")

# Query PostgreSQL tree_nodes table
db_url = os.environ['DATABASE_URL']
conn = psycopg.connect(db_url, autocommit=True)

# Keywords to check
keywords = ['kag', 'nexusrag', '知识图谱', 'KAG', 'NexusRAG']

# Get all nodes with title and summary_text
result = conn.execute(
    """
    SELECT node_id, title, summary_text
    FROM tree_nodes
    WHERE version_id = %s
    """,
    (VERSION_ID,)
)
all_nodes = result.fetchall()

print(f'\nTotal nodes: {len(all_nodes)}')

# Check keyword matches in title and summary_text
keyword_matches = {}
for keyword in keywords:
    matches_title = []
    matches_summary = []
    keyword_lower = keyword.lower()

    for node_id, title, summary_text in all_nodes:
        if title and keyword_lower in title.lower():
            matches_title.append((node_id, title))
        if summary_text and keyword_lower in summary_text.lower():
            matches_summary.append((node_id, summary_text[:100]))  # Truncate for display

    print(f'\nKeyword "{keyword}":')
    print(f'  title matches: {len(matches_title)}')
    print(f'  summary_text matches: {len(matches_summary)}')

    keyword_matches[keyword] = {
        "title_matches": [{"node_id": str(node_id), "title": title} for node_id, title in matches_title],
        "summary_matches": [{"node_id": str(node_id), "summary_preview": summary_preview} for node_id, summary_preview in matches_summary]
    }

# Save to JSON
output_data = {
    "version_id": VERSION_ID,
    "total_nodes": len(all_nodes),
    "keyword_matches": keyword_matches
}

with open(OUTPUT_DIR / 'keyword_title_summary_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f'\nSaved analysis to keyword_title_summary_analysis.json')

conn.close()