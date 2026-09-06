#!/usr/bin/env python3
"""Check phase14 versions in database"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg

db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url, autocommit=True)

# Check all versions ordered by creation time
cur = conn.execute(
    "SELECT version_id, doc_id, content_hash, created_at, registered_at "
    "FROM document_versions ORDER BY created_at DESC LIMIT 10"
)
rows = cur.fetchall()
print(f"\nAll recent versions (ordered by created_at): {len(rows)}")
for row in rows:
    print(f"  version_id={row[0]}")
    print(f"    doc_id={row[1]}, created_at={row[3]}, registered_at={row[4]}")

# Check the status file version
status_path = Path(__file__).parent / "02_document_ingestion_status.json"
if status_path.exists():
    import json
    from uuid import UUID
    with open(status_path, 'r', encoding='utf-8') as f:
        status = json.load(f)
        status_version_id = status.get("version_id")
        print(f"\nStatus file version_id: {status_version_id}")

        # Check if this version exists in database
        cur = conn.execute(
            "SELECT version_id, created_at, registered_at FROM document_versions "
            "WHERE version_id = %s",
            (status_version_id,)
        )
        version_row = cur.fetchone()
        if version_row:
            print(f"  EXISTS in database")
            print(f"    created_at={version_row[1]}, registered_at={version_row[2]}")

            # Check tree_nodes count
            cur = conn.execute(
                "SELECT COUNT(*) FROM tree_nodes WHERE version_id = %s",
                (status_version_id,)
            )
            tree_count = cur.fetchone()[0]
            print(f"    tree_nodes count: {tree_count}")

            # Check canonical_spans count
            cur = conn.execute(
                "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
                (status_version_id,)
            )
            span_count = cur.fetchone()[0]
            print(f"    canonical_spans count: {span_count}")

            # Check node_embeddings count
            cur = conn.execute(
                "SELECT COUNT(*) FROM node_embeddings WHERE node_id IN "
                "(SELECT node_id FROM tree_nodes WHERE version_id = %s)",
                (status_version_id,)
            )
            emb_count = cur.fetchone()[0]
            print(f"    node_embeddings count: {emb_count}")
        else:
            print(f"  NOT FOUND in database (DATA LOSS CONFIRMED)")

            # Check if any version has similar content_hash (idempotency reuse?)
            if "span_count" in status:
                print(f"\n  Looking for versions with same document characteristics...")
                # The document should have a unique doc_id
                # Check all versions to see if spans exist for a different version_id
                cur = conn.execute(
                    "SELECT version_id, COUNT(*) as span_count FROM canonical_spans "
                    "GROUP BY version_id ORDER BY span_count DESC LIMIT 5"
                )
                span_groups = cur.fetchall()
                print(f"  All versions with spans:")
                for group in span_groups:
                    print(f"    version_id={group[0]}, span_count={group[1]}")

conn.close()