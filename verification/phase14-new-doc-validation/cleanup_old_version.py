#!/usr/bin/env python3
"""
清理 Phase 14 旧数据，准备重新验证
=====================================

删除旧的 version，确保干净验证
"""

import os
import sys
from pathlib import Path
from uuid import UUID
import psycopg

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

db_url = os.environ["DATABASE_URL"]

# 旧 version_id（从 02_document_ingestion_status.json）
old_version_id = UUID("550ef3df-1691-46c3-bdbc-40a28ed89870")

print(f"[CLEANUP] Deleting old version {old_version_id}")

conn = psycopg.connect(db_url, autocommit=True)

# 检查 version 是否存在
version_row = conn.execute("""
    SELECT version_id, doc_id FROM document_versions
    WHERE version_id = %s
""", (str(old_version_id),)).fetchone()

if version_row:
    print(f"  Found version: {version_row[0]}")
    print(f"  Doc ID: {version_row[1]}")

    # 删除 document（会级联删除 version, spans, tree_nodes, chunks）
    conn.execute("""
        DELETE FROM documents WHERE doc_id = %s
    """, (str(version_row[1]),))

    print("  [DELETED] Document and all related data")
else:
    print("  [NOT FOUND] Version already deleted or never existed")

conn.close()

print("\n[READY] Database cleaned, ready for fresh validation")