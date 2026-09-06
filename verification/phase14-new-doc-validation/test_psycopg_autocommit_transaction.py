#!/usr/bin/env python3
"""
Minimal reproduction test for psycopg transaction behavior with autocommit=True

Tests hypothesis: When autocommit=True, transaction() context managers are NO-OPS
and writes inside them are discarded on connection close.
"""

import os
import sys
from pathlib import Path
import uuid
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg

db_url = os.environ["DATABASE_URL"]
test_version_id = uuid.uuid4()
test_doc_id = uuid.uuid4()
test_contract_id = uuid.uuid4()

print(f"Test version_id: {test_version_id}")
print(f"Test doc_id: {test_doc_id}")

# SCENARIO 1: autocommit=True + transaction() context manager
print("\n[SCENARIO 1] autocommit=True + transaction() context manager")
conn1 = psycopg.connect(db_url, autocommit=True)
print(f"  Connection autocommit: {conn1.autocommit}")

# First, insert the parent document (outside transaction)
conn1.execute(
    "INSERT INTO documents (doc_id, source_uri, title, doc_type) "
    "VALUES (%s, %s, %s, %s)",
    (str(test_doc_id), "test://test", "Test Document", "document")
)
print("  Inserted parent document")

# Insert normalization contract
conn1.execute(
    "INSERT INTO normalization_contracts (normalization_contract_id, parser_name, parser_version, offset_basis) "
    "VALUES (%s, %s, %s, %s)",
    (str(test_contract_id), "TestParser", "1.0", "test_offset")
)
print("  Inserted normalization contract")

# Now test: insert version inside transaction context manager
with conn1.transaction():
    conn1.execute(
        "INSERT INTO document_versions "
        "(version_id, doc_id, content_hash, version_no, normalization_contract_id, is_active, status, processing_status) "
        "VALUES (%s, %s, %s, 1, %s, TRUE, 'active', 'registered')",
        (str(test_version_id), str(test_doc_id), "test_hash_1", str(test_contract_id))
    )
    print("  Inserted version row inside transaction context manager")

# Check immediately before close
cur = conn1.execute(
    "SELECT version_id FROM document_versions WHERE version_id = %s",
    (str(test_version_id),)
)
row_before_close = cur.fetchone()
print(f"  Row exists BEFORE close: {bool(row_before_close)}")

conn1.close()
print("  Connection closed")

# Check after close with fresh connection
conn2 = psycopg.connect(db_url, autocommit=True)
cur = conn2.execute(
    "SELECT version_id FROM document_versions WHERE version_id = %s",
    (str(test_version_id),)
)
row_after_close = cur.fetchone()
print(f"  Row exists AFTER close: {bool(row_after_close)}")
conn2.close()

# RESULT
if row_after_close:
    print("\n[RESULT] SCENARIO 1: Row PERSISTED (transaction() works with autocommit=True)")
else:
    print("\n[RESULT] SCENARIO 1: Row DISAPPEARED (transaction() is NO-OP with autocommit=True)")
    print("  HYPOTHESIS CONFIRMED: transaction() context managers do NOT commit when autocommit=True")

# Cleanup test data
cleanup_conn = psycopg.connect(db_url, autocommit=True)
cleanup_conn.execute(
    "DELETE FROM document_versions WHERE version_id = %s",
    (str(test_version_id),)
)
cleanup_conn.close()
print("\n[CLEANUP] Test data deleted")