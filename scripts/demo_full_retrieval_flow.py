"""完整的 PageIndex 检索流程演示（使用修复后的代码）。

这个脚本展示：
1. 文档索引（PageIndexTreeAdapter）
2. 树结构构建
3. 检索流程（ReasoningTreeBackend）
4. chunk_id 解析

目的：验证修复后的 PageIndexTreeAdapter 是否正确保留了原始内容。
"""

import sys
import uuid
from pathlib import Path

# 设置 UTF-8 输出
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg
from psycopg.rows import dict_row

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter
from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend

# 配置
DB_URL = "postgresql://postgres:postgres@localhost:5432/rag"
SOURCE_MD = r"E:\github\rag\PageIndex完整功能分析与集成方案.md"
QUERY_TEXT = "PageIndex 和当前实现有什么区别？功能对比"


def main():
    print("=" * 80)
    print("完整的 PageIndex 检索流程演示（修复后）")
    print("=" * 80)

    # 1. 连接数据库
    print("\n【步骤1】连接数据库...")
    conn = psycopg.connect(DB_URL)
    registry = PostgresRegistryWriter(conn)

    if not registry.healthcheck():
        print("[FAIL] 数据库连接失败")
        return

    print("[OK] 数据库连接成功")

    # 2. 注册文档版本
    print("\n【步骤2】注册新版本...")
    registered = registry.register_document(
        source_path=Path(SOURCE_MD),
        source_uri="PageIndex完整功能分析与集成方案.md",
        title="PageIndex完整功能分析与集成方案",
    )

    version_id = registered.version_id
    print(f"[OK] 版本已注册: version_id={version_id}")

    # 3. 索引树结构（使用修复后的 PageIndexTreeAdapter）
    print("\n【步骤3】索引树结构（PageIndexTreeAdapter）...")
    print("[WARN] 修复点：现在直接使用 PageIndex 的 text 字段，不再生成假 summary")

    adapter = PageIndexTreeAdapter()

    try:
        adapter.index_tree(
            source_path=SOURCE_MD,
            version_id=version_id,
            registry=registry,
        )
        print("[OK] 树结构索引完成")
    except Exception as e:
        print(f"[FAIL] 索引失败: {e}")
        import traceback

        traceback.print_exc()
        return

    # 4. 检查树节点数据（验证修复）
    print("\n【步骤4】检查树节点数据（验证修复）...")
    nodes = registry.query_tree_nodes_by_version(version_id)

    if not nodes:
        print("[FAIL] 没有树节点数据")
        return

    print(f"[OK] 共 {len(nodes)} 个树节点")

    # 找到父节点 "PageIndex vs 当前实现对比"
    parent_node = None
    for node in nodes:
        if "PageIndex vs 当前实现对比" in str(node.get("heading_path", "")):
            if "功能矩阵" not in str(node.get("heading_path", "")):
                parent_node = node
                break

    if parent_node:
        summary_text = parent_node.get("summary_text")
        print(f"\n父节点 'PageIndex vs 当前实现对比':")
        print(f"  heading_path: {parent_node.get('heading_path')}")
        print(f"  summary_text 类型: {type(summary_text)}")
        if summary_text is not None:
            print(f"  summary_text 长度: {len(summary_text)} 字符")
            print(f"  summary_text 前100字符: {summary_text[:100]!r}")
            if len(summary_text) < 50:
                print("[FAIL] summary_text 太短！可能还是假数据")
            else:
                print("[OK] summary_text 有真实内容！修复生效")
        else:
            print("[WARN] summary_text 是 None！PageIndex 没有提供 text 字段")
            print("  这说明 PageIndex 本身就没有给父节点生成内容")
            print("  需要检查 PageIndex 的原始输出")
    else:
        print("[WARN] 未找到父节点")

    # 5. 检索（真实流程）
    print("\n【步骤5】真实检索流程...")
    print(f"查询: '{QUERY_TEXT}'")

    backend = ReasoningTreeBackend(llm_model="gpt-4o-mini")

    try:
        hits = backend.retrieve_tree_hits(
            query_text=QUERY_TEXT,
            version_id=version_id,
            registry=registry,
            limit=5,
        )
        print(f"[OK] 检索返回 {len(hits)} 个结果")

    except Exception as e:
        print(f"[FAIL] 检索失败: {e}")
        import traceback

        traceback.print_exc()
        return

    # 6. 分析检索结果
    print("\n【步骤6】分析检索结果...")
    for idx, hit in enumerate(hits, 1):
        print(f"\n结果 #{idx}:")
        print(f"  heading_path: {hit.heading_path}")
        print(f"  chunk_id: {hit.chunk_id}")
        print(f"  chunk_id 是零UUID: {hit.chunk_id == uuid.UUID(int=0)}")
        print(f"  text_preview 长度: {len(hit.text_preview)} 字符")
        print(f"  text_preview 前80字符: {hit.text_preview[:80]!r}")
        print(f"  backend_source: {hit.backend_source}")
        print(f"  retrieval_path: {hit.retrieval_path}")

    # 7. 统计 chunk_id 分布
    print("\n【步骤7】统计 chunk_id 分布...")
    zero_count = sum(1 for hit in hits if hit.chunk_id == uuid.UUID(int=0))
    normal_count = len(hits) - zero_count

    print(f"正常 chunk_id: {normal_count} ({normal_count/len(hits)*100:.1f}%)")
    print(f"零 chunk_id: {zero_count} ({zero_count/len(hits)*100:.1f}%)")

    if zero_count > 0:
        print("[WARN] 还有零 chunk_id！可能是索引不完整")
    else:
        print("[OK] 所有 chunk_id 正常！修复完全生效")

    # 8. 清理：关闭连接
    conn.close()
    print("\n[OK] 完成")


if __name__ == "__main__":
    main()
