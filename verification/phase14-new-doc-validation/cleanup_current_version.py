#!/usr/bin/env python3
"""
清理当前 Phase 14 version 的所有数据
"""

import os
import sys
from pathlib import Path
from uuid import UUID
import json
import psycopg

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

status_path = Path(__file__).parent / "02_document_ingestion_status.json"
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status["version_id"])

print(f"[CLEANUP] Deleting version {VERSION_ID}")

db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url, autocommit=True)

# Check version exists
version_row = conn.execute("""
    SELECT version_id, doc_id FROM document_versions
    WHERE version_id = %s
""", (str(VERSION_ID),)).fetchone()

if version_row:
    print(f"  Found version: {version_row[0]}")
    print(f"  Doc ID: {version_row[1]}")

    # Delete all related data in correct order
    print("  Deleting node_embeddings...")
    conn.execute("DELETE FROM node_embeddings WHERE node_id IN (SELECT node_id FROM tree_nodes WHERE version_id = %s)", (str(VERSION_ID),))

    print("  Deleting tree_node_spans...")
    conn.execute("DELETE FROM tree_node_spans WHERE node_id IN (SELECT node_id FROM tree_nodes WHERE version_id = %s)", (str(VERSION_ID),))

    print("  Deleting tree_nodes...")
    conn.execute("DELETE FROM tree_nodes WHERE version_id = %s", (str(VERSION_ID),))

    print("  Deleting vector_chunk_spans...")
    conn.execute("DELETE FROM vector_chunk_spans WHERE span_id IN (SELECT span_id FROM canonical_spans WHERE version_id = %s)", (str(VERSION_ID),))

    print("  Deleting canonical_spans...")
    conn.execute("DELETE FROM canonical_spans WHERE version_id = %s", (str(VERSION_ID),))

    print("  Deleting document_versions...")
    conn.execute("DELETE FROM document_versions WHERE version_id = %s", (str(VERSION_ID),))

    print("  [DELETED] All data cleared")
else:
    print("  [NOT FOUND] Version already deleted")

conn.close()

print("\n[READY] Database cleaned, ready for fresh validation")