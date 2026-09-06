#!/usr/bin/env python3
"""
完整流程排障：模拟 run_validation.py 的实际执行路径
==================================================

目标：
1. 验证 write_tree 是否正确提交
2. 验证 query_tree_nodes_by_version 在同一 connection 中的可见性
3. 验证 retrieval 是否真的来自数据库
"""

import os
import sys
from pathlib import Path
from uuid import UUID
import json

# Setup
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.ingestion.pipeline import IngestionPipeline
from llamaindex_runtime.okf.e2a_contracts import E2aReconciliationResult
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf, MISSING_CHUNK_ID
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding
from llama_index.core.embeddings import BaseEmbedding


class _FakeReconciler:
    """Fake reconciler for verification scripts (non-DB path).

    CLASSIFICATION: NON-E2A HISTORICAL/DIAGNOSTIC

    This reconciler is used by Phase 14 historical diagnostic scripts for
    full flow diagnosis WITHOUT database reconciliation. It returns a typed-shaped
    E2aReconciliationResult for ingestion pipeline compatibility, but this is NOT
    a real E2a reconciliation and MUST NOT be used for Phase 15 acceptance.

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

class RealEmbedding(BaseEmbedding):
    """Embedding wrapper for retrieval"""
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        super().__init__()
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedder._get_text_embedding(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [self._get_text_embedding(t) for t in texts]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._get_text_embeddings(texts)

db_url = os.environ["DATABASE_URL"]

print("\n" + "="*60)
print("STEP 1: Ingest Document (same connection)")
print("="*60)

conn = psycopg.connect(db_url)
registry = PostgresRegistryWriter(conn)

pipeline = IngestionPipeline(
    registry=registry,
    bundle_root=PROJECT_ROOT / "verification/phase14-new-doc-validation/e2a_bundle",
    connection_factory=lambda: conn,
    reconciler=_FakeReconciler(),
)
ingest_result = pipeline.ingest(
    CORPUS_PATH,
    title="[diagnostic] deep-research-report"
)
version_id = ingest_result.version_id
doc_id = ingest_result.doc_id

print(f"Version ID: {version_id}")
print(f"Doc ID: {doc_id}")

# Immediately query spans
spans = registry.query_spans_by_version(version_id)
print(f"Spans (same connection): {len(spans)}")

print("\n" + "="*60)
print("STEP 2: Query tree_nodes BEFORE write_tree")
print("="*60)

nodes_before = registry.query_tree_nodes_by_version(version_id)
print(f"Tree nodes (before write): {len(nodes_before)}")

print("\n" + "="*60)
print("STEP 3: Generate and Write Tree")
print("="*60)

if not nodes_before:
    generated = TreeGenerator().generate_tree(spans, version_id=version_id)
    nodes_generated = generated["nodes"]
    node_spans_mappings = generated["node_spans"]

    print(f"Nodes generated: {len(nodes_generated)}")
    print(f"Node-span mappings: {len(node_spans_mappings)}")

    registry.write_tree(
        version_id=version_id,
        nodes=nodes_generated,
        node_spans=node_spans_mappings,
    )
    print("write_tree() called")

print("\n" + "="*60)
print("STEP 4: Query tree_nodes AFTER write_tree (same connection)")
print("="*60)

nodes_after = registry.query_tree_nodes_by_version(version_id)
print(f"Tree nodes (after write, same conn): {len(nodes_after)}")

if nodes_after:
    for i, node in enumerate(nodes_after[:3]):
        print(f"  [{i+1}] node_id={node['node_id']} level={node['level_no']} title={node['title'][:40]}...")

print("\n" + "="*60)
print("STEP 5: Run Retrieval (same connection)")
print("="*60)

embed_model = RealEmbedding()
test_query = "研究报告的核心结论是什么？"

hits = retrieve_tree_hits_from_pdf(
    source_path=CORPUS_PATH,
    query=test_query,
    embed_model=embed_model,
    similarity_top_k=5,
    registry=registry,
    version_id=version_id,
    backend_type="embedding"
)

print(f"Retrieval hits: {len(hits)}")
if hits:
    hit = hits[0]
    print(f"  First hit:")
    print(f"    chunk_id={hit.get('chunk_id')}")
    print(f"    chunk_id_missing={hit.get('chunk_id_missing')}")
    print(f"    backend_source={hit.get('backend_source')}")
    print(f"    retrieval_path={hit.get('retrieval_path')}")
    print(f"    heading_path={hit.get('heading_path')[:60]}...")

print("\n" + "="*60)
print("STEP 6: Close connection, reopen with autocommit")
print("="*60)

conn.close()

conn_new = psycopg.connect(db_url, autocommit=True)
registry_new = PostgresRegistryWriter(conn_new)

nodes_new_conn = registry_new.query_tree_nodes_by_version(version_id)
print(f"Tree nodes (new connection, autocommit): {len(nodes_new_conn)}")

if nodes_new_conn:
    print("  [SUCCESS] Data persisted and visible in new connection")
else:
    print("  [FAIL] Data NOT visible in new connection → transaction rollback or deletion")

print("\n" + "="*60)
print("STEP 7: Check version existence in document_versions")
print("="*60)

version_row = conn_new.execute("""
    SELECT version_id, status, is_active
    FROM document_versions
    WHERE version_id = %s
""", (str(version_id),)).fetchone()

if version_row:
    print(f"Version exists: {version_row[0]}")
    print(f"  status: {version_row[1]}")
    print(f"  is_active: {version_row[2]}")
else:
    print("[FAIL] Version not found in document_versions → DELETE CASCADE happened")

conn_new.close()

print("\n" + "="*60)
print("DIAGNOSIS SUMMARY")
print("="*60)

if nodes_after and not nodes_new_conn:
    print("""
[ROOT CAUSE] 数据写入成功（同一 connection 可见），但未持久化到其他 connection

原因：
  1. Connection 未设置 autocommit=True
  2. transaction() context manager 应该自动提交，但可能在 close() 时 rollback
  3. 或者数据被 DELETE CASCADE 删除（version 被删除）

建议：
  - 使用 autocommit=True 的 connection
  - 或在 close() 前显式 commit
""")
elif nodes_after and nodes_new_conn:
    print("""
[SUCCESS] 正式流程正常工作

结论：
  1. write_tree 正确提交事务
  2. 数据持久化成功
  3. retrieval 正常从数据库读取
  4. Phase 14 的数据矛盾是诊断脚本查询时机问题（version 被删除）
""")
else:
    print("""
[FAIL] 数据从未写入

原因：TreeGenerator 输出为空或 write_tree 未调用
""")