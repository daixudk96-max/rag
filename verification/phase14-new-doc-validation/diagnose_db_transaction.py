#!/usr/bin/env python3
"""
数据库事务排障诊断
===================

诊断问题：
1. tree_nodes 为什么查询返回 0 rows？
2. 事务是否正确提交？
3. Connection autocommit 设置？
"""

import os
import sys
from pathlib import Path
from uuid import UUID

# Setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg
from psycopg.rows import dict_row

version_id = UUID("550ef3df-1691-46c3-bdbc-40a28ed89870")
db_url = os.environ["DATABASE_URL"]

print(f"[VERSION] {version_id}")
print(f"[DB_URL] {db_url[:50]}...")

# Test 1: Direct query with autocommit
print("\n" + "="*60)
print("TEST 1: Direct query (autocommit=True)")
print("="*60)

conn1 = psycopg.connect(db_url, autocommit=True)
rows1 = conn1.execute("""
    SELECT node_id, parent_node_id, level_no, title
    FROM tree_nodes
    WHERE version_id = %s
    ORDER BY level_no
""", (str(version_id),)).fetchall()

print(f"Rows found: {len(rows1)}")
if rows1:
    for i, row in enumerate(rows1[:5]):
        print(f"  [{i+1}] node_id={row[0][:36]}... level={row[2]} title={row[3][:40]}...")
else:
    print("  [RESULT] 0 rows — transaction not committed or data not written")

conn1.close()

# Test 2: Check transaction status
print("\n" + "="*60)
print("TEST 2: Check pending transactions")
print("="*60)

conn2 = psycopg.connect(db_url, autocommit=True)
active_tx = conn2.execute("""
    SELECT count(*) as pending_count
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
      AND query_start < now() - interval '5 minutes'
""").fetchone()

print(f"Pending transactions (idle > 5min): {active_tx[0]}")

# Test 3: Check table row count directly
print("\n" + "="*60)
print("TEST 3: Table row count (any version)")
print("="*60)

conn3 = psycopg.connect(db_url, autocommit=True)
total_rows = conn3.execute("""
    SELECT count(*) as total_nodes FROM tree_nodes
""").fetchone()

print(f"Total tree_nodes rows (all versions): {total_rows[0]}")

# Test 4: Check version existence
print("\n" + "="*60)
print("TEST 4: Version existence check")
print("="*60)

conn4 = psycopg.connect(db_url, autocommit=True)
version_row = conn4.execute("""
    SELECT version_id, doc_id, status, is_active
    FROM document_versions
    WHERE version_id = %s
""", (str(version_id),)).fetchone()

if version_row:
    print(f"Version exists: {version_row[0]}")
    print(f"  doc_id: {version_row[1]}")
    print(f"  status: {version_row[2]}")
    print(f"  is_active: {version_row[3]}")
else:
    print("[ERROR] Version not found in document_versions")

conn4.close()

# Test 5: Check spans existence
print("\n" + "="*60)
print("TEST 5: Spans existence check")
print("="*60)

conn5 = psycopg.connect(db_url, autocommit=True)
spans_count = conn5.execute("""
    SELECT count(*) as span_count
    FROM canonical_spans
    WHERE version_id = %s
""", (str(version_id),)).fetchone()

print(f"Canonical spans: {spans_count[0]}")

conn5.close()

# Test 6: Check tree_node_spans
print("\n" + "="*60)
print("TEST 6: tree_node_spans existence")
print("="*60)

conn6 = psycopg.connect(db_url, autocommit=True)
tns_count = conn6.execute("""
    SELECT count(*) as mapping_count
    FROM tree_node_spans tns
    JOIN tree_nodes tn ON tns.node_id = tn.node_id
    WHERE tn.version_id = %s
""", (str(version_id),)).fetchone()

print(f"tree_node_spans mappings: {tns_count[0]}")

conn6.close()

print("\n" + "="*60)
print("DIAGNOSIS SUMMARY")
print("="*60)

if len(rows1) == 0:
    print("""
[ROOT CAUSE] tree_nodes 数据未写入数据库

可能原因：
  1. write_tree 的事务未提交（connection.transaction() 应该自动提交）
  2. run_validation.py 的 connection 在 write_tree 前关闭
  3. TreeGenerator 生成的 nodes 为空（但 03_tree_vector_status.json 显示 tree_nodes=10）
  4. 数据写入但立即被删除（DELETE CASCADE）

建议排查：
  - 检查 run_validation.py 的 connection 生命周期
  - 检查 write_tree 是否真的调用
  - 检查 TreeGenerator 输出是否非空
""")
else:
    print(f"""
[SUCCESS] tree_nodes 正常写入，共 {len(rows1)} 个节点

结论：
  - 事务提交机制正常
  - 数据写入成功
  - 演示脚本查询时机或 connection 问题
""")