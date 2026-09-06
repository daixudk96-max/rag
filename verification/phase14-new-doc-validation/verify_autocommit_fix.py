#!/usr/bin/env python3
"""
验证 autocommit 修复
===================

测试 PostgresRegistryWriter 自动启用 autocommit 后，write_tree 能正确持久化
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

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult


class _FakeReconciler:
    """Fake reconciler for verification scripts (non-DB path).

    CLASSIFICATION: NON-E2A HISTORICAL/DIAGNOSTIC

    This reconciler is used by Phase 14 historical diagnostic scripts for
    autocommit fix verification WITHOUT database reconciliation. It returns a
    typed-shaped E2aReconciliationResult for ingestion pipeline compatibility,
    but this is NOT a real E2a reconciliation and MUST NOT be used for Phase 15
    acceptance.

    Phase 15 acceptance requires actual E2aReconciler provenance plus disposable
    database authorization. This fake reconciler is structurally excluded from
    the Phase 15 acceptance route.

    See: verification/phase15-okf-ingestion-pipeline/run_e2a_verification.py
    """

    def reconcile(self, connection: object, desired: object) -> object:
        return E2aReconciliationResult(
            outcome="no_op",
            manifest_sha256="a" * 64,
            primary_dml_by_table={},
            denylist_dml_counts={},
            comparator_parity=None,
            stale_deletion_counts={},
            cache_invalidation_counts={},
            failure_audit_outcome=None,
            post_rollback_failure_audit_outcome=None,
        )

CORPUS_PATH = PROJECT_ROOT / "docs/research/deep-research-report (1).md"

db_url = os.environ["DATABASE_URL"]

print("\n" + "="*60)
print("TEST 1: PostgresRegistryWriter autocommit 检查")
print("="*60)

# 创建 connection（不设置 autocommit）
conn1 = psycopg.connect(db_url)
print(f"Connection autocommit (before): {conn1.autocommit}")

# 创建 registry（应该自动启用 autocommit）
registry1 = PostgresRegistryWriter(conn1)
print(f"Connection autocommit (after registry init): {conn1.autocommit}")

expected_autocommit = True
actual_autocommit = conn1.autocommit

if actual_autocommit == expected_autocommit:
    print("[PASS] PostgresRegistryWriter 自动启用 autocommit")
else:
    print(f"[FAIL] Expected autocommit={expected_autocommit}, got {actual_autocommit}")
    sys.exit(2)

conn1.close()

print("\n" + "="*60)
print("TEST 2: write_tree 数据持久化验证")
print("="*60)

# 创建新 connection 和 registry
conn2 = psycopg.connect(db_url)
registry2 = PostgresRegistryWriter(conn2)

# Ingest document
pipeline = IngestionPipeline(
    registry=registry2,
    bundle_root=PROJECT_ROOT / "verification/phase14-new-doc-validation/e2a_bundle",
    connection_factory=lambda: conn2,
    reconciler=_FakeReconciler(),
)
ingest_result = pipeline.ingest(CORPUS_PATH, title="[autocommit-test] deep-research")
version_id = ingest_result.version_id

print(f"Version ID: {version_id}")

# Generate and write tree
spans = registry2.query_spans_by_version(version_id)
print(f"Spans: {len(spans)}")

generated = TreeGenerator().generate_tree(spans, version_id=version_id)
print(f"Nodes generated: {len(generated['nodes'])}")

registry2.write_tree(
    version_id=version_id,
    nodes=generated["nodes"],
    node_spans=generated["node_spans"],
)
print("write_tree() called")

# Query immediately (same connection)
nodes_same_conn = registry2.query_tree_nodes_by_version(version_id)
print(f"Nodes (same connection): {len(nodes_same_conn)}")

# Close connection
conn2.close()

# Open new connection and query
conn3 = psycopg.connect(db_url, autocommit=True)
registry3 = PostgresRegistryWriter(conn3)
nodes_new_conn = registry3.query_tree_nodes_by_version(version_id)
print(f"Nodes (new connection): {len(nodes_new_conn)}")

# Verification
expected_nodes = len(generated['nodes'])
actual_nodes = len(nodes_new_conn)

if actual_nodes == expected_nodes:
    print(f"[PASS] write_tree 数据正确持久化（{actual_nodes} nodes）")
else:
    print(f"[FAIL] Expected {expected_nodes} nodes, got {actual_nodes}")
    sys.exit(2)

conn3.close()

print("\n" + "="*60)
print("TEST 3: 数据库直接查询验证")
print("="*60)

conn4 = psycopg.connect(db_url, autocommit=True)
direct_nodes = conn4.execute("""
    SELECT count(*) FROM tree_nodes WHERE version_id = %s
""", (str(version_id),)).fetchone()

print(f"Direct SQL query: {direct_nodes[0]} nodes")

if direct_nodes[0] == expected_nodes:
    print("[PASS] 数据库直接查询验证成功")
else:
    print(f"[FAIL] Expected {expected_nodes}, got {direct_nodes[0]}")
    sys.exit(2)

conn4.close()

print("\n" + "="*60)
print("修复验证成功")
print("="*60)
print("""
结论：
  1. PostgresRegistryWriter 自动启用 autocommit ✓
  2. write_tree 数据正确持久化到数据库 ✓
  3. 新 connection 可见 tree_nodes ✓

修复方案：
  - 修改 PostgresRegistryWriter.__init__（方案 C）
  - 所有使用 registry 的地方自动生效
  - 无需修改任何 verification 脚本
""")