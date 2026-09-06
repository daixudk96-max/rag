#!/usr/bin/env python3
"""Test if registry.query_spans_by_version(version_id) returns empty for non-existent version"""

import os
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg

db_url = os.environ["DATABASE_URL"]
conn = psycopg.connect(db_url, autocommit=True)

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

registry = PostgresRegistryWriter(conn)

# Try querying a version that doesn't exist
fake_version_id = UUID("00000000-0000-0000-0000-000000000000")
print(f"Querying non-existent version_id: {fake_version_id}")

spans = registry.query_spans_by_version(fake_version_id)
print(f"Result: {len(spans)} spans")
print(f"Type: {type(spans)}")

if len(spans) == 0:
    print("[EXPECTED] Empty list returned for non-existent version")
else:
    print("[UNEXPECTED] Non-empty result for non-existent version")

conn.close()