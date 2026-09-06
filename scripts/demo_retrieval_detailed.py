"""增强版演示：打印完整检索流程的每一步细节。"""
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

import uuid
from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
import psycopg

version_id = uuid.UUID("008442cf-ec96-47e5-8552-99962911587a")
query = "文档的主要章节结构是什么？列出所有一级标题。"

print("=== 增强版检索流程演示 ===")
print()

# 连接数据库
db_url = os.environ["DATABASE_URL"]
with psycopg.connect(db_url) as conn:
    registry = PostgresRegistryWriter(conn)

    # Step 1: 查询数据库里的所有节点
    print("Step 1: 查询数据库 tree_nodes 表")
    nodes = registry.query_tree_nodes_by_version(version_id)
    print(f"  查询到 {len(nodes)} 个节点")
    print()

    print("  前 10 个节点详情:")
    for i, node in enumerate(nodes[:10], start=1):
        print(f"    Node #{i}:")
        print(f"      node_id: {node.get('node_id')}")
        print(f"      title: {node.get('title')}")
        print(f"      heading_path: {node.get('heading_path')}")
        print(f"      page_no: {node.get('page_no') or node.get('page_start')}")
        print(f"      summary_text: {(node.get('summary_text') or '')[:50]}...")
        print()

    # Step 2: 构建树结构（准备发给 LLM）
    print("Step 2: 构建树结构（_build_structure_from_nodes）")
    backend = ReasoningTreeBackend(llm_model="gpt-4o-mini")
    structure = backend._build_structure_from_nodes(nodes)
    print(f"  结构化后的节点数: {len(structure)}")
    print()

    print("  前 5 个结构化节点:")
    for i, node in enumerate(structure[:5], start=1):
        print(f"    #{i}: node_id={node.get('node_id')}, title={node.get('title')}, heading={node.get('heading_path')[:40]}, page={node.get('page_no')}")
    print()

    # Step 3: 构建 LLM prompt
    print("Step 3: 构建 LLM prompt")
    structure_text = backend._format_structure_for_llm(structure)
    query_block = backend._query_prompt_block(query)

    prompt = (
        "Return ranked node_id JSON array.\n"
        "Nodes:\n"
        f"{structure_text}\n"
        f"{query_block}\n"
        "Relevant:"
    )

    print("  Prompt 预览（前 500 字符）:")
    print("  " + prompt[:500].replace("\n", "\n  "))
    print()
    print(f"  Prompt 总长度: {len(prompt)} 字符")
    print()

    # Step 4: 发给 LLM（真实调用）
    print("Step 4: 发给 LLM（gpt-4o-mini）")
    print("  正在调用 LLM...")
    from llamaindex_runtime.llm import get_llm
    llm = get_llm()
    response = llm.complete(prompt)
    response_text = response.text

    print(f"  LLM 返回文本长度: {len(response_text)} 字符")
    print()
    print("  LLM 返回原始文本:")
    print("  " + response_text[:300].replace("\n", "\n  "))
    print()

    # Step 5: 解析 LLM 返回的 node_ids
    print("Step 5: 解析 LLM 返回的 node_ids")
    selected_node_ids = backend._parse_llm_response_for_node_ids(response_text, structure)
    print(f"  解析出的 node_ids 数量: {len(selected_node_ids)}")
    print()

    print("  解析出的 node_ids:")
    for i, node_id in enumerate(selected_node_ids[:10], start=1):
        print(f"    #{i}: {node_id}")
    print()

    # Step 6: 从 node_ids 找到完整节点
    print("Step 6: 从 node_ids 映射回完整节点")
    nodes_by_id = {
        str(node.get("node_id")): node
        for node in structure
        if node.get("node_id") is not None
    }

    selected_nodes = []
    for i, node_id in enumerate(selected_node_ids[:5], start=1):
        node_id_text = str(node_id)
        node = nodes_by_id.get(node_id_text)
        if node:
            print(f"  Node #{i}:")
            print(f"    node_id: {node.get('node_id')}")
            print(f"    title: {node.get('title')}")
            print(f"    heading_path: {node.get('heading_path')}")
            print(f"    page_no: {node.get('page_no')}")
            print(f"    summary_text 是否存在: {bool(node.get('summary_text'))}")
            print()
            selected_nodes.append(node)

    # Step 7: 检查这些节点的 span_ids 和 chunk_id
    print("Step 7: 检查节点的 span_ids 和 chunk_id")
    for i, node in enumerate(selected_nodes, start=1):
        node_id = backend._coerce_uuid(node.get("node_id"))
        print(f"  Node #{i} (node_id={node_id}):")

        # 查 span_ids
        span_ids = backend._query_span_ids_for_node(registry, node_id, version_id)
        print(f"    span_ids: {len(span_ids)} 个")
        if len(span_ids) > 0:
            print(f"    span_ids 预览: {str(span_ids[:3])[:60]}...")
        else:
            print(f"    span_ids: [] (空)")
        print()

        # 查 chunk_id
        chunk_id = backend._query_chunk_id_for_hit(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
        )
        print(f"    chunk_id: {chunk_id}")
        if chunk_id == uuid.UUID(int=0):
            print(f"    chunk_id 是全零 UUID（说明此节点没有被向量化）")
        print()

        # 构建 text_preview
        fallback_text = node.get("summary_text") or node.get("title") or ""
        from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver
        text_preview = EvidenceContentResolver().build_text_preview(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
            fallback_text=fallback_text,
            chunk_id=chunk_id,
        )
        print(f"    fallback_text: {fallback_text[:60]}...")
        print(f"    text_preview: {text_preview[:100]}...")
        print()
        print(f"    结论: 此节点只返回了 {'标题' if not node.get('summary_text') else '摘要'}，没有实际内容段落")
        print()

print("=== 演示结束 ===")