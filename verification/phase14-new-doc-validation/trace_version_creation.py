#!/usr/bin/env python3
"""Trace the version creation flow"""

import os
import sys
from pathlib import Path
import hashlib

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg
from uuid import UUID
import json

CORPUS_PATH = PROJECT_ROOT / "docs/research/deep-research-report (1).md"

# Compute content_hash
def compute_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

content_hash = compute_hash(CORPUS_PATH)
print(f"Content hash for phase14 document: {content_hash}")

# Read status file
status_path = Path(__file__).parent / "02_document_ingestion_status.json"
if status_path.exists():
    with open(status_path, 'r', encoding='utf-8') as f:
        status = json.load(f)
        status_version_id = status.get("version_id")
        print(f"\nStatus file version_id: {status_version_id}")

        # Check when status file was last modified
        import os
        stat = os.stat(status_path)
        from datetime import datetime
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        print(f"Status file last modified: {mod_time}")

db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url, autocommit=True)

# Check all versions with this content_hash
cur = conn.execute(
    "SELECT version_id, doc_id, version_no, content_hash, is_active, status, registered_at "
    "FROM document_versions WHERE content_hash = %s",
    (content_hash,)
)
matching_versions = cur.fetchall()
print(f"\nVersions with same content_hash: {len(matching_versions)}")
for row in matching_versions:
    print(f"  version_id={row[0]}, is_active={row[4]}, status={row[5]}, registered={row[6]}")

# Check if status_version_id exists
if status_version_id:
    cur = conn.execute(
        "SELECT version_id, registered_at FROM document_versions WHERE version_id = %s",
        (status_version_id,)
    )
    row = cur.fetchone()
    if row:
        print(f"\nStatus version EXISTS in database: registered={row[1]}")
    else:
        print(f"\nStatus version NOT FOUND in database")

        # Check if it was recently deleted (check other tables)
        cur = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        tables = [row[0] for row in cur.fetchall()]

        print("Checking for orphaned data in other tables:")
        for table in tables:
            try:
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE version_id = %s",
                    (status_version_id,)
                )
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"  {table}: {count} rows with this version_id (ORPHANED DATA)")
            except:
                pass  # Table doesn't have version_id column

# Check all versions to find the active one
cur = conn.execute(
    "SELECT version_id, doc_id, content_hash, is_active, status, registered_at "
    "FROM document_versions ORDER BY registered_at DESC LIMIT 10"
)
all_versions = cur.fetchall()
print(f"\nMost recent 10 versions:")
for row in all_versions:
    print(f"  version_id={row[0]}, active={row[3]}, status={row[4]}, hash={row[2][:16]}..., registered={row[5]}")

conn.close()