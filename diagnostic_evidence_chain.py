#!/usr/bin/env python3
"""诊断证据链数据不一致问题"""
import psycopg
from pathlib import Path

conn_str = "postgresql://postgres:postgres@localhost:5432/rag"

print("=" * 60)
print("Phase 1: 根因调查 - 数据库实际状态检查")
print("=" * 60)

with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        # 1. 检查documents表
        cur.execute("SELECT COUNT(*) FROM documents;")
        docs_count = cur.fetchone()[0]
        print(f"\n[documents表]: {docs_count} 条记录")

        # 2. 检查document_versions表
        cur.execute("SELECT COUNT(*) FROM document_versions;")
        versions_count = cur.fetchone()[0]
        print(f"[document_versions表]: {versions_count} 条记录")

        if versions_count > 0:
            cur.execute("""
                SELECT version_id, document_id, created_at
                FROM document_versions
                ORDER BY created_at DESC
                LIMIT 5;
            """)
            print("\n最近的versions:")
            for row in cur.fetchall():
                print(f"  - version_id: {row[0]}")
                print(f"    document_id: {row[1]}")
                print(f"    created_at: {row[2]}")

        # 3. 检查tree_nodes表（关键）
        cur.execute("SELECT COUNT(*) FROM tree_nodes;")
        nodes_count = cur.fetchone()[0]
        print(f"\n[tree_nodes表]: {nodes_count} 条记录")

        if nodes_count > 0:
            cur.execute("""
                SELECT level_no, COUNT(*) as count
                FROM tree_nodes
                GROUP BY level_no
                ORDER BY level_no;
            """)
            print("\ntree_nodes level分布:")
            for row in cur.fetchall():
                print(f"  Level {row[0]}: {row[1]} nodes")

            cur.execute("""
                SELECT node_id, heading_path, level_no
                FROM tree_nodes
                ORDER BY level_no, heading_path
                LIMIT 10;
            """)
            print("\ntree_nodes样本（前10条）:")
            for row in cur.fetchall():
                print(f"  - node_id: {row[0]}")
                print(f"    heading_path: {row[1]}")
                print(f"    level_no: {row[2]}")

        # 4. 检查vector_chunks表（证据链缺失的关键）
        cur.execute("SELECT COUNT(*) FROM vector_chunks;")
        chunks_count = cur.fetchone()[0]
        print(f"\n[vector_chunks表]: {chunks_count} 条记录")

        # 5. 检查tree_node_spans表
        cur.execute("SELECT COUNT(*) FROM tree_node_spans;")
        spans_count = cur.fetchone()[0]
        print(f"[tree_node_spans表]: {spans_count} 条记录")

        # 6. 检查canonical_spans表
        cur.execute("SELECT COUNT(*) FROM canonical_spans;")
        canonical_count = cur.fetchone()[0]
        print(f"[canonical_spans表]: {canonical_count} 条记录")

        # 7. 检查是否有chunk与node的关联
        if nodes_count > 0 and chunks_count > 0:
            cur.execute("""
                SELECT COUNT(*) as mapped
                FROM tree_nodes n
                JOIN vector_chunks c ON c.span_id IN (
                    SELECT span_id FROM tree_node_spans WHERE node_id = n.node_id
                );
            """)
            mapped_count = cur.fetchone()[0]
            print(f"\n[node-chunk映射]: {mapped_count} 条映射记录")

        # 8. 检查heading_path完整性
        if nodes_count > 0:
            cur.execute("""
                SELECT COUNT(*) as complete
                FROM tree_nodes
                WHERE heading_path IS NOT NULL AND heading_path != '';
            """)
            complete_count = cur.fetchone()[0]
            rate = complete_count / nodes_count * 100 if nodes_count > 0 else 0
            print(f"\n[heading_path完整性]: {complete_count}/{nodes_count} ({rate:.2f}%)")

print("\n" + "=" * 60)
print("证据链完整性诊断结论")
print("=" * 60)

# 分析矛盾点
print("\n🔍 关键发现:")
print(f"1. documents={docs_count}, versions={versions_count}, nodes={nodes_count}")
print(f"2. chunks={chunks_count}, spans={spans_count}, canonical={canonical_count}")
print(f"3. tree_max_level=4 (validation_status.json) ↔ nodes_count={nodes_count}")

if nodes_count > 0 and chunks_count == 0:
    print("\n⚠️ 根因定位:")
    print("   - tree_nodes存在 → 文档摄入成功")
    print("   - vector_chunks=0 → **证据链未建立**")
    print("   - 检索返回71个hits → 数据来源待查证")
    print("\n❓ 关键问题:")
    print("   检索如何从tree_nodes返回hits而不依赖chunks?")
    print("   ReasoningTreeBackend的检索逻辑是什么?")