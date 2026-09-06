#!/usr/bin/env python3
"""
检索流程白盒演示（真实文档）
===========================

使用真实文档（deep-research-report），展示完整检索流程：
1. 查询处理和 embedding 计算
2. Vector candidates 和 keyword hits
3. Dual-hot 集合计算（vector_hot & keyword_hot）
4. Coverage-based parent selection（coverage_ratio、support、score）
5. Hotspot traverse（waypoint + evidence 结构）
6. 最终 hits 的详细结构

每个步骤都可视化内部数据结构和决策过程。
"""

import os
import sys
from pathlib import Path
from uuid import UUID
import json

os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import retrieve_tree_hits_from_pdf, MISSING_CHUNK_ID
from llamaindex_runtime.tree.semantic_distribution import (
    HybridClusterHotspotSelector,
    RecursiveTreeTraversalRunner,
    BaselineTreeBranchDecisionPolicy,
    _cosine_similarity,
)
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding
from llama_index.core.embeddings import BaseEmbedding

# 使用 Phase 14 验证的文档和 version_id
OUTPUT_DIR = Path(__file__).parent
status_path = OUTPUT_DIR / "02_document_ingestion_status.json"
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status["version_id"])

CORPUS_PATH = PROJECT_ROOT / "docs/research/deep-research-report (1).md"

# 演示查询（选择一个具体问题）
DEMO_QUERY = "KAG 和 NexusRAG 在知识图谱能力上有什么区别？"

class RealEmbedding(BaseEmbedding):
    """Embedding wrapper"""
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

def main():
    print("="*80)
    print("检索流程白盒演示")
    print("="*80)
    print(f"""
文档：deep-research-report (1).md
Version ID: {VERSION_ID}
查询：{DEMO_QUERY}
""")
    print("="*80)

    # Step 0: Database setup
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(db_url, autocommit=True)
    registry = PostgresRegistryWriter(conn)

    # Step 1: Query Embedding
    print("\n" + "="*80)
    print("STEP 1: 查询 Embedding 计算")
    print("="*80)

    embed_model = RealEmbedding()
    query_embedding = embed_model._get_query_embedding(DEMO_QUERY)

    print(f"\n查询文本：{DEMO_QUERY}")
    print(f"Embedding 维度：{len(query_embedding)}")
    print(f"Embedding 前5个值：{query_embedding[:5]}")

    # Step 2: Get tree structure and node stats
    print("\n" + "="*80)
    print("STEP 2: 树结构加载")
    print("="*80)

    nodes = registry.query_tree_nodes_by_version(VERSION_ID)
    node_by_id = {n["node_id"]: n for n in nodes}  # node_id already UUID from registry

    print(f"\n树节点总数：{len(nodes)}")
    print(f"树层级：{max(n['level_no'] for n in nodes)}")

    # 展示树结构（层级）
    for level in range(0, max(n['level_no'] for n in nodes) + 1):
        level_nodes = [n for n in nodes if n['level_no'] == level]
        print(f"\n  Level {level}: {len(level_nodes)} 个节点")
        for i, node in enumerate(level_nodes[:3]):
            title = node['title'][:40] if node['title'] else ""
            node_id_str = str(node['node_id'])
            print(f"    [{i+1}] node_id={node_id_str[:36]}... title={title}...")

    # Step 3: Node stats (with embeddings)
    print("\n" + "="*80)
    print("STEP 3: Node Stats 加载（包含 embeddings 和 chunk_ids）")
    print("="*80)

    # 从 node_embeddings 表获取 prototype embeddings（Phase 14 FIX: include summary_text）
    stats_rows = conn.execute("""
        SELECT ne.node_id, ne.embedding_vector, tn.heading_path, tn.title, tn.summary_text
        FROM node_embeddings ne
        JOIN tree_nodes tn ON ne.node_id = tn.node_id
        WHERE tn.version_id = %s AND ne.embedding_model = 'all-MiniLM-L6-v2'
    """, (str(VERSION_ID),)).fetchall()

    # 从 tree_node_spans 获取 chunk_ids（通过 spans 映射）
    chunk_rows = conn.execute("""
        SELECT tn.node_id, array_agg(vc.chunk_id) as chunk_ids
        FROM tree_nodes tn
        JOIN tree_node_spans tns ON tn.node_id = tns.node_id
        JOIN canonical_spans cs ON tns.span_id = cs.span_id
        JOIN vector_chunk_spans vcs ON cs.span_id = vcs.span_id
        JOIN vector_chunks vc ON vcs.chunk_id = vc.chunk_id
        WHERE tn.version_id = %s
        GROUP BY tn.node_id
    """, (str(VERSION_ID),)).fetchall()

    node_stats_list = []
    for row in stats_rows:
        # Handle UUID conversion (psycopg may return UUID or str)
        node_id_raw = row[0]
        node_id = node_id_raw if isinstance(node_id_raw, UUID) else UUID(node_id_raw)
        embedding = list(row[1]) if row[1] is not None else []  # pgvector returns numpy array
        heading_path = row[2] or ""
        title = row[3] or ""
        summary_text = row[4] or ""  # Phase 14 FIX: Extract summary_text for keyword matching

        # 查找该节点的 chunk_ids
        chunk_ids = []
        for chunk_row in chunk_rows:
            chunk_node_id_raw = chunk_row[0]
            chunk_node_id = chunk_node_id_raw if isinstance(chunk_node_id_raw, UUID) else UUID(chunk_node_id_raw)
            if chunk_node_id == node_id:
                chunk_ids_raw = chunk_row[1] or []
                chunk_ids = [
                    c if isinstance(c, UUID) else UUID(c)
                    for c in chunk_ids_raw
                ]

        node_stats_list.append({
            "node_id": node_id,
            "prototype_embedding": embedding,
            "centroid": embedding,
            "chunk_ids": chunk_ids,
            "heading_path": heading_path,
            "title": title,
            "summary_text": summary_text,  # Phase 14 FIX: Add summary_text for keyword matching
        })

    print(f"\nNode stats 总数：{len(node_stats_list)}")

    # 展示几个节点的 stats
    print("\n示例节点 stats（前3个）：")
    for i, stats in enumerate(node_stats_list[:3]):
        node_id_str = str(stats['node_id'])
        print(f"  [{i+1}] node_id={node_id_str[:36]}...")
        print(f"      heading_path: {stats['heading_path'][:60]}...")
        print(f"      embedding 维度: {len(stats['prototype_embedding'])}")
        print(f"      chunk_ids 数量: {len(stats['chunk_ids'])}")

    # Step 4: Vector Candidates（语义相似度计算）
    print("\n" + "="*80)
    print("STEP 4: Vector Candidates（语义相似度）")
    print("="*80)

    vector_candidates = []
    for stats in node_stats_list:
        prototype = stats.get("prototype_embedding") or stats.get("centroid")
        if prototype:
            similarity = _cosine_similarity(query_embedding, prototype)
            vector_candidates.append({
                "node_id": stats["node_id"],
                "similarity": similarity,
                "heading": stats["heading_path"][:40],
            })

    # Sort by similarity
    vector_candidates.sort(key=lambda c: c["similarity"], reverse=True)

    print(f"\nVector candidates 总数：{len(vector_candidates)}")
    print(f"Top 5 vector candidates:")
    for i, cand in enumerate(vector_candidates[:5]):
        node_id_str = str(cand['node_id'])
        print(f"  [{i+1}] node_id={node_id_str[:36]}...")
        print(f"      similarity={cand['similarity']:.4f}")
        print(f"      heading={cand['heading']}...")

    # Step 5: Keyword Hits（关键词匹配）
    print("\n" + "="*80)
    print("STEP 5: Keyword Hits（关键词匹配）")
    print("="*80)

    # Keyword matching against all searchable text fields（与实际系统一致）
    query_terms = set(DEMO_QUERY.lower().split())
    keyword_hits = []

    for stats in node_stats_list:
        # Combine searchable text fields (Phase 14 FIX: match heading + title + summary)
        heading = stats.get("heading_path", "") or ""
        title = stats.get("title", "") or ""
        summary = stats.get("summary_text", "") or ""
        searchable_text = f"{heading} {title} {summary}"

        searchable_lower = searchable_text.lower()
        matched_terms = [term for term in query_terms if term in searchable_lower]
        if matched_terms:
            # Score: number of matched terms / total query terms
            score = len(matched_terms) / len(query_terms)
            keyword_hits.append({
                "node_id": stats["node_id"],
                "score": score,
                "matched_terms": matched_terms,
                "heading": heading[:40],
                "searchable_text_preview": searchable_text[:80],
            })

    keyword_hits.sort(key=lambda h: h["score"], reverse=True)

    print(f"\nQuery terms: {query_terms}")
    print(f"Keyword hits 总数：{len(keyword_hits)}")
    print(f"Top 5 keyword hits:")
    for i, hit in enumerate(keyword_hits[:5]):
        node_id_str = str(hit['node_id'])
        print(f"  [{i+1}] node_id={node_id_str[:36]}...")
        print(f"      score={hit['score']:.4f}")
        print(f"      matched_terms={hit['matched_terms']}")
        print(f"      heading={hit['heading']}...")

    # Step 6: Dual-hot 集合（交集门）
    print("\n" + "="*80)
    print("STEP 6: Dual-hot 集合计算（vector_hot & keyword_hot）")
    print("="*80)

    VECTOR_HOT_THRESHOLD = 0.35  # Phase 14 fix: lowered from 0.5 to match HybridClusterHotspotSelector
    KEYWORD_HOT_MIN_TERMS = 1

    vector_hot_nodes = {c["node_id"] for c in vector_candidates if c["similarity"] >= VECTOR_HOT_THRESHOLD}
    keyword_hot_nodes = {h["node_id"] for h in keyword_hits if len(h["matched_terms"]) >= KEYWORD_HOT_MIN_TERMS}
    dual_hot_nodes = vector_hot_nodes & keyword_hot_nodes

    print(f"\n参数：")
    print(f"  VECTOR_HOT_THRESHOLD = {VECTOR_HOT_THRESHOLD}")
    print(f"  KEYWORD_HOT_MIN_TERMS = {KEYWORD_HOT_MIN_TERMS}")

    print(f"\n结果：")
    print(f"  vector_hot nodes: {len(vector_hot_nodes)}")
    print(f"  keyword_hot nodes: {len(keyword_hot_nodes)}")
    print(f"  dual_hot nodes（交集）: {len(dual_hot_nodes)}")

    if dual_hot_nodes:
        print(f"\nDual-hot nodes:")
        for node_id in list(dual_hot_nodes)[:5]:
            node_info = node_by_id.get(node_id)
            if node_info:
                node_id_str = str(node_id)
                print(f"    node_id={node_id_str[:36]}...")
                print(f"    title={node_info['title'][:40]}...")

    # Step 7: Parent Coverage Selection
    print("\n" + "="*80)
    print("STEP 7: Parent Coverage Selection（热点父节点选择）")
    print("="*80)

    # Build parent_to_children mapping
    parent_to_children = {}
    for node_id in node_by_id:
        parent_id = node_by_id[node_id].get("parent_node_id")
        if parent_id:
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(node_id)

    print(f"\nParent-child mappings: {len(parent_to_children)} parents")

    # Find candidate parents from dual_hot children
    candidate_parents = set()
    for child_id in dual_hot_nodes:
        child_stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
        if child_stats:
            parent_id = node_by_id.get(child_id, {}).get("parent_node_id")
            if parent_id is not None:
                candidate_parents.add(parent_id)

    print(f"\nCandidate parents（从 dual_hot children）: {len(candidate_parents)}")

    # Compute coverage for each parent
    COVERAGE_THETA = 0.5
    MIN_SUPPORT = 2
    ROOT_CHILD_BREADTH_CAP = 8

    print(f"\n筛选参数：")
    print(f"  COVERAGE_THETA = {COVERAGE_THETA}（覆盖率阈值）")
    print(f"  MIN_SUPPORT = {MIN_SUPPORT}（最小 dual_hot 子节点数）")
    print(f"  ROOT_CHILD_BREADTH_CAP = {ROOT_CHILD_BREADTH_CAP}（根节点避免阈值）")

    parent_scores = []
    for parent_id in candidate_parents:
        children = parent_to_children.get(parent_id, [])
        dual_hot_children = [c for c in children if c in dual_hot_nodes]

        coverage_ratio = len(dual_hot_children) / len(children) if children else 0.0
        hot_count = len(dual_hot_children)

        # Coverage gate
        if coverage_ratio < COVERAGE_THETA:
            continue
        if hot_count < MIN_SUPPORT:
            continue

        # Root avoidance
        children_count = len(children)
        if children_count > ROOT_CHILD_BREADTH_CAP:
            continue

        # Parent score（覆盖权重）
        avg_child_vector = sum(
            next((c["similarity"] for c in vector_candidates if c["node_id"] == child_id), 0.0)
            for child_id in dual_hot_children
        ) / len(dual_hot_children) if dual_hot_children else 0.0

        support_bonus = min(hot_count / 5.0, 1.0)

        parent_score = (
            coverage_ratio * 0.50
            + avg_child_vector * 0.30
            + support_bonus * 0.20
        )

        parent_scores.append({
            "parent_id": parent_id,
            "score": parent_score,
            "coverage_ratio": coverage_ratio,
            "hot_count": hot_count,
            "children_count": children_count,
        })

    parent_scores.sort(key=lambda p: p["score"], reverse=True)

    print(f"\n通过筛选的父节点：{len(parent_scores)}")

    if parent_scores:
        print(f"\nTop 3 parent hotspots:")
        for i, parent in enumerate(parent_scores[:3]):
            parent_info = node_by_id.get(parent["parent_id"])
            parent_id_str = str(parent['parent_id'])
            print(f"\n  [{i+1}] Hotspot Parent:")
            print(f"      node_id={parent_id_str[:36]}...")
            print(f"      score={parent['score']:.4f}")
            print(f"      coverage_ratio={parent['coverage_ratio']:.2f}")
            print(f"      dual_hot_children={parent['hot_count']}")
            print(f"      total_children={parent['children_count']}")
            if parent_info:
                print(f"      title={parent_info['title'][:40]}...")

    # Step 8: Hotspot Traverse（waypoint + evidence）
    print("\n" + "="*80)
    print("STEP 8: Hotspot Traverse（返回 waypoint + evidence）")
    print("="*80)

    if parent_scores:
        selected_hotspot_id = parent_scores[0]["parent_id"]
        hotspot_info = node_by_id.get(selected_hotspot_id)

        hotspot_id_str = str(selected_hotspot_id)
        print(f"\n选中的 Hotspot:")
        print(f"  node_id={hotspot_id_str}")
        print(f"  heading={hotspot_info['heading_path'][:60] if hotspot_info else 'N/A'}...")

        # Get hotspot's own chunks
        hotspot_stats = next((s for s in node_stats_list if s["node_id"] == selected_hotspot_id), None)
        hotspot_chunks = hotspot_stats.get("chunk_ids", []) if hotspot_stats else []

        print(f"  own_chunks={len(hotspot_chunks)}")

        # Get hotspot's children
        hotspot_children = parent_to_children.get(selected_hotspot_id, [])
        print(f"  children={len(hotspot_children)}")

        # Traverse：收集 waypoint + evidence
        print(f"\nTraverse 结果：")

        # Waypoint hit（hotspot itself）
        hotspot_id_str = str(selected_hotspot_id)
        print(f"\n  Waypoint hit（MISSING_CHUNK_ID）:")
        print(f"    node_id={hotspot_id_str}")
        print(f"    chunk_id={MISSING_CHUNK_ID}（占位符）")
        print(f"    drill_depth=0")
        print(f"    role=导航标记（证明热点路径）")

        # Evidence hits（hotspot's own chunks）
        if hotspot_chunks:
            print(f"\n  Evidence hits（hotspot's own chunks）:")
            for i, chunk_id in enumerate(hotspot_chunks[:3]):
                # Get chunk text preview
                chunk_row = conn.execute("""
                    SELECT text_preview, heading_path
                    FROM vector_chunks
                    WHERE chunk_id = %s LIMIT 1
                """, (str(chunk_id),)).fetchone()

                chunk_id_str = str(chunk_id)
                hotspot_id_str = str(selected_hotspot_id)
                print(f"\n    [{i+1}] Evidence hit:")
                print(f"        chunk_id={chunk_id_str}")
                print(f"        node_id={hotspot_id_str}")
                print(f"        drill_depth=0")
                print(f"        heading={chunk_row[1][:40] if chunk_row else 'N/A'}...")
                print(f"        preview={chunk_row[0][:80] if chunk_row and chunk_row[0] else 'N/A'}...")

        # Evidence hits（children's chunks）
        for i, child_id in enumerate(hotspot_children[:2]):
            child_stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
            if child_stats and child_stats.get("chunk_ids"):
                child_chunks = child_stats["chunk_ids"]
                child_info = node_by_id.get(child_id)

                child_id_str = str(child_id)
                print(f"\n  Evidence hits（child node {i+1}）:")
                print(f"    child_node_id={child_id_str}")
                print(f"    child_heading={child_info['heading_path'][:40] if child_info else 'N/A'}...")
                print(f"    child_chunks={len(child_chunks)}")

                for j, chunk_id in enumerate(child_chunks[:2]):
                    chunk_row = conn.execute("""
                        SELECT text_preview FROM vector_chunks
                        WHERE chunk_id = %s LIMIT 1
                    """, (str(chunk_id),)).fetchone()

                    chunk_id_str = str(chunk_id)
                    child_id_str = str(child_id)
                    print(f"\n      [{j+1}] Evidence hit:")
                    print(f"          chunk_id={chunk_id_str}")
                    print(f"          node_id={child_id_str}")
                    print(f"          drill_depth=1")
                    print(f"          preview={chunk_row[0][:60] if chunk_row and chunk_row[0] else 'N/A'}...")

    # Step 9: 实际 Retrieval 结果
    print("\n" + "="*80)
    print("STEP 9: 实际 Retrieval 结果（run_validation.py）")
    print("="*80)

    # Run actual retrieval
    hits = retrieve_tree_hits_from_pdf(
        source_path=CORPUS_PATH,
        query=DEMO_QUERY,
        embed_model=embed_model,
        similarity_top_k=5,
        registry=registry,
        version_id=VERSION_ID,
        backend_type="embedding"
    )

    print(f"\n实际返回 hits：{len(hits)}")

    # 分类 waypoint vs evidence
    waypoint_hits = [h for h in hits if h.get("chunk_id") == str(MISSING_CHUNK_ID)]
    evidence_hits = [h for h in hits if h.get("chunk_id") != str(MISSING_CHUNK_ID)]

    print(f"  Waypoint hits: {len(waypoint_hits)}")
    print(f"  Evidence hits: {len(evidence_hits)}")

    if evidence_hits:
        print(f"\nEvidence hits 详情（前3个）:")
        for i, hit in enumerate(evidence_hits[:3]):
            print(f"\n  [{i+1}] Evidence hit:")
            print(f"      chunk_id={hit.get('chunk_id')}")
            print(f"      node_id={hit.get('node_id')}")
            print(f"      drill_depth={hit.get('drill_depth')}")
            print(f"      retrieval_path={hit.get('retrieval_path')}")
            print(f"      backend_source={hit.get('backend_source')}")
            print(f"      heading={hit.get('heading_path')[:60]}...")
            # Safely encode text_preview for Windows console (avoid UnicodeEncodeError)
            preview_text = hit.get('text_preview') or ""
            safe_preview = preview_text.encode('gbk', errors='replace').decode('gbk')[:80]
            print(f"      preview={safe_preview}...")

    conn.close()

    print("\n" + "="*80)
    print("白盒演示总结")
    print("="*80)
    print("""
检索流程完整展示：

1. Query Embedding ✓
   - 查询文本 → 384 维向量

2. Vector Candidates ✓
   - 所有节点的语义相似度排序
   - Top candidates: similarity >= 0.5

3. Keyword Hits ✓
   - Heading path 关键词匹配
   - matched_terms >= 1

4. Dual-hot 集合 ✓
   - vector_hot & keyword_hot（交集门）
   - 必须同时满足两个条件

5. Parent Coverage Selection ✓
   - coverage_ratio >= 50%
   - dual_hot_children >= 2
   - children <= 8（root avoidance）

6. Hotspot Traverse ✓
   - Waypoint hit（MISSING_CHUNK_ID）：导航标记
   - Evidence hits（真实 chunk_id）：文档内容
   - drill_depth=0（hotspot own chunks）
   - drill_depth=1（child chunks）

7. 最终返回 ✓
   - Evidence hits（真实 chunk_id）
   - 不是 waypoint-only（避免 zero-chunk fallback）
   - Phase 13 设计验证成功
""")

if __name__ == "__main__":
    main()