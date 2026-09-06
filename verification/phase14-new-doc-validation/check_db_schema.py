#!/usr/bin/env python3
"""Check document_versions table schema"""

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

# Check document_versions columns
cur = conn.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name = 'document_versions' ORDER BY ordinal_position"
)
rows = cur.fetchall()
print("document_versions columns:")
for row in rows:
    print(f"  {row[0]}")

conn.close()