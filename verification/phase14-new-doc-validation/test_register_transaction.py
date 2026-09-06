#!/usr/bin/env python3
"""
Debug script to trace transaction behavior in register_document()
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
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

db_url = os.environ["DATABASE_URL"]

# Create a test document
test_doc_path = PROJECT_ROOT / "test_trace_doc.txt"
test_doc_path.write_text("Test content for transaction trace")

print("=" * 80)
print("TRANSACTION BEHAVIOR TEST")
print("=" * 80)

# Test 1: Connection with autocommit=True
print("\n[TEST 1] Connection created with autocommit=True")
conn1 = psycopg.connect(db_url, autocommit=True)
print(f"  Connection autocommit status: {conn1.autocommit}")

registry1 = PostgresRegistryWriter(conn1)
print(f"  Registry connection autocommit: {registry1._connection.autocommit}")

# Try to register a document
print("\n  Attempting register_document()...")
try:
    result1 = registry1.register_document(
        source_path=test_doc_path,
        source_uri="test://trace_doc",
        title="Transaction Trace Test"
    )
    print(f"  SUCCESS: version_id={result1.version_id}")
    print(f"  is_active={result1.is_active}")

    # Check immediately if version exists
    cur = conn1.execute(
        "SELECT version_id, is_active FROM document_versions WHERE version_id = %s",
        (str(result1.version_id),)
    )
    row = cur.fetchone()
    print(f"  Version exists in DB (before close): {bool(row)}")
    if row:
        print(f"    is_active in DB: {row[1]}")

    # Close and check again
    conn1.close()
    print("  Connection closed")

    # Check with fresh connection
    conn2 = psycopg.connect(db_url, autocommit=True)
    cur = conn2.execute(
        "SELECT version_id, is_active FROM document_versions WHERE version_id = %s",
        (str(result1.version_id),)
    )
    row = cur.fetchone()
    print(f"  Version exists in DB (after close): {bool(row)}")
    if row:
        print(f"    is_active in DB: {row[1]}")
        print("\n  ✓ TEST PASSED: Version persisted after connection close")
    else:
        print("\n  ✗ TEST FAILED: Version disappeared after connection close")

    # Cleanup
    conn2.execute(
        "DELETE FROM document_versions WHERE version_id = %s",
        (str(result1.version_id),)
    )
    conn2.execute(
        "DELETE FROM documents WHERE doc_id = %s",
        (str(result1.doc_id),)
    )
    conn2.close()
    print("  Cleanup complete")

except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    conn1.close()

# Cleanup test file
if test_doc_path.exists():
    test_doc_path.unlink()
    print("\nTest file removed")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)