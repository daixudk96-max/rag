#!/usr/bin/env python3
"""
真实 Parent Coverage Selection 过程白盒测试（Q18）
====================================================

目的：记录真实检索中间过程，验证 BM25-inspired saturation 公式
      如何在真实文档 + 真实 query 上选择 hotspot。

与旧 whitebox_retrieval_demo.py 的关键差异：
  1. 使用 Q18 真实 query（不是 Q2）
  2. 使用 production BM25-inspired 公式（不是旧线性相加公式）
  3. 使用 production 真实阈值（与 HybridClusterHotspotSelector 一致）
  4. 记录每个候选父节点的完整评分过程

验证目标：
  - Q18 的真实 Parent Coverage Selection 过程
  - 为什么 "实施建议" 节点最终胜出
  - 不是假设，是真实数据库 + 真实公式 + 真实阈值
"""

import io
import sys
import os
import json
import re
import math
from pathlib import Path
from uuid import UUID

# Windows console UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# CRITICAL: Set selector BEFORE any llamaindex imports (与 run_validation.py 一致)
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding
from llama_index.core.embeddings import BaseEmbedding
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
# 直接复用 production 关键词提取逻辑（jieba）— 保证与真实检索一致
from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

# Phase 14 验证的真实文档 + version_id
OUTPUT_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).parent.parent.parent

status_path = OUTPUT_DIR / "02_document_ingestion_status.json"
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status["version_id"])

# Q18 真实 query（来自 04_query_set.json）
DEMO_QUERY = "必须自研的四个模块是什么？按什么顺序优先排？"


# =============================================================================
# Production 参数（与 HybridClusterHotspotSelector 完全一致）
# =============================================================================
VECTOR_HOT_THRESHOLD = 0.35      # _VECTOR_HOT_THRESHOLD
KEYWORD_HOT_MIN_TERMS = 1        # _KEYWORD_HOT_MIN_TERMS
COVERAGE_THETA = 0.5             # _COVERAGE_THETA
MIN_SUPPORT = 2                  # _MIN_SUPPORT
ROOT_CHILD_BREADTH_CAP = 8      # _ROOT_CHILD_BREADTH_CAP
BM25_K = 2.0                    # 经验调优参数


class RealEmbedding(BaseEmbedding):
    """Embedding wrapper（与 whitebox_retrieval_demo.py 一致）"""

    def __init__(self, model_name='all-MiniLM-L6-v2'):
        super().__init__()
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedder._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedder._get_text_embedding(text)

    def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)


def cosine_similarity(vec_a, vec_b):
    """Cosine similarity（与 production _cosine_similarity 一致）"""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalize_scores(scores):
    """Min-max normalization（与 production _normalize_scores 一致）"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def extract_query_terms(query: str) -> list[str]:
    """直接调用 production 关键词提取（jieba），保证与真实检索一致。"""
    return _extract_keywords_from_query(query)


def main():
    print("=" * 80)
    print("真实 Parent Coverage Selection 过程白盒测试（Q18）")
    print("=" * 80)
    print(f"""
文档：deep-research-report (1).md
Version ID: {VERSION_ID}
查询（Q18）：{DEMO_QUERY}
公式：parent_score = avg_child_vector × coverage_ratio × (hot_count / (hot_count + {BM25_K}))
""")
    print("=" * 80)
    print("【重要声明】本测试使用 production BM25-inspired 公式 + 真实阈值，")
    print("           直接从数据库读取真实数据，记录真实中间过程。")
    print("=" * 80)

    # Step 0: Database setup
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(db_url, autocommit=True)
    registry = PostgresRegistryWriter(conn)

    # Step 1: Query Embedding
    print("\n" + "=" * 80)
    print("STEP 1: 查询 Embedding 计算（真实）")
    print("=" * 80)

    embed_model = RealEmbedding()
    query_embedding = embed_model._get_query_embedding(DEMO_QUERY)
    print(f"\n查询文本：{DEMO_QUERY}")
    print(f"Embedding 维度：{len(query_embedding)}")

    # Step 2: 树结构加载
    print("\n" + "=" * 80)
    print("STEP 2: 树结构加载（真实数据库）")
    print("=" * 80)

    nodes = registry.query_tree_nodes_by_version(VERSION_ID)
    node_by_id = {n["node_id"]: n for n in nodes}
    print(f"\n树节点总数：{len(nodes)}")
    print(f"树层级：{max(n['level_no'] for n in nodes)}")

    # Step 3: Node stats（embeddings + chunk_ids）
    print("\n" + "=" * 80)
    print("STEP 3: Node Stats 加载（真实 embeddings + chunk_ids）")
    print("=" * 80)

    stats_rows = conn.execute("""
        SELECT ne.node_id, ne.embedding_vector, tn.heading_path, tn.title, tn.summary_text, tn.parent_node_id
        FROM node_embeddings ne
        JOIN tree_nodes tn ON ne.node_id = tn.node_id
        WHERE tn.version_id = %s AND ne.embedding_model = 'all-MiniLM-L6-v2'
    """, (str(VERSION_ID),)).fetchall()

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

    chunk_ids_by_node = {}
    for chunk_row in chunk_rows:
        node_id_raw = chunk_row[0]
        node_id = node_id_raw if isinstance(node_id_raw, UUID) else UUID(node_id_raw)
        chunk_ids_raw = chunk_row[1] or []
        chunk_ids_by_node[node_id] = [
            c if isinstance(c, UUID) else UUID(c) for c in chunk_ids_raw
        ]

    node_stats_list = []
    for row in stats_rows:
        node_id_raw = row[0]
        node_id = node_id_raw if isinstance(node_id_raw, UUID) else UUID(node_id_raw)
        embedding = list(row[1]) if row[1] is not None else []
        heading_path = row[2] or ""
        title = row[3] or ""
        summary_text = row[4] or ""
        parent_node_id = row[5]
        if isinstance(parent_node_id, str):
            parent_node_id = UUID(parent_node_id)

        node_stats_list.append({
            "node_id": node_id,
            "prototype_embedding": embedding,
            "centroid": embedding,
            "chunk_ids": chunk_ids_by_node.get(node_id, []),
            "heading_path": heading_path,
            "title": title,
            "summary_text": summary_text,
            "parent_node_id": parent_node_id,
        })

    print(f"Node stats 总数：{len(node_stats_list)}")

    # Step 4: Vector Candidates（语义相似度）
    print("\n" + "=" * 80)
    print("STEP 4: Vector Candidates（真实语义相似度）")
    print("=" * 80)

    vector_candidates = []
    for stats in node_stats_list:
        prototype = stats.get("prototype_embedding") or stats.get("centroid")
        if prototype:
            sim = cosine_similarity(query_embedding, prototype)
            vector_candidates.append({
                "node_id": stats["node_id"],
                "similarity": sim,
                "heading": stats["heading_path"][:50],
            })

    # Production: normalize vector scores
    raw_sims = [c["similarity"] for c in vector_candidates]
    norm_sims = normalize_scores(raw_sims)
    for c, ns in zip(vector_candidates, norm_sims):
        c["normalized_sim"] = ns

    vector_candidates.sort(key=lambda c: c["normalized_sim"], reverse=True)

    print(f"\nVector candidates 总数：{len(vector_candidates)}")
    print(f"Top 8 vector candidates（normalized）:")
    for i, cand in enumerate(vector_candidates[:8]):
        print(f"  [{i+1}] normalized_sim={cand['normalized_sim']:.4f}  raw_sim={cand['similarity']:.4f}")
        print(f"      heading={cand['heading']}...")

    # Step 5: Keyword Hits
    print("\n" + "=" * 80)
    print("STEP 5: Keyword Hits（真实关键词匹配）")
    print("=" * 80)

    query_terms = extract_query_terms(DEMO_QUERY)
    print(f"\nQuery terms（提取）：{query_terms}")

    keyword_hits = []
    for stats in node_stats_list:
        heading = stats.get("heading_path", "") or ""
        title = stats.get("title", "") or ""
        summary = stats.get("summary_text", "") or ""
        searchable_text = f"{heading} {title} {summary}"
        searchable_lower = searchable_text.lower()

        matched_terms = [term for term in query_terms if term in searchable_lower]
        if matched_terms:
            keyword_hits.append({
                "node_id": stats["node_id"],
                "matched_count": len(matched_terms),
                "matched_terms": matched_terms,
                "heading": heading[:50],
            })

    keyword_hits.sort(key=lambda h: h["matched_count"], reverse=True)
    print(f"\nKeyword hits 总数：{len(keyword_hits)}")
    print(f"Top 8 keyword hits:")
    for i, hit in enumerate(keyword_hits[:8]):
        print(f"  [{i+1}] matched_count={hit['matched_count']}  terms={hit['matched_terms']}")
        print(f"      heading={hit['heading']}...")

    # Production: keyword score normalization + exact_keyword_nodes
    # keyword_by_node = max(norm_score, term_coverage)
    all_matched_terms = set()
    for hit in keyword_hits:
        all_matched_terms.update(hit["matched_terms"])

    terms_by_node = {}
    keyword_raw_scores = [0.6] * len(keyword_hits)  # production fixed score 0.6
    keyword_norm_scores = normalize_scores(keyword_raw_scores) if keyword_raw_scores else []
    keyword_by_node = {}
    for hit, norm_score in zip(keyword_hits, keyword_norm_scores):
        nid = hit["node_id"]
        terms_by_node.setdefault(nid, set()).update(hit["matched_terms"])
        term_coverage = (
            len(terms_by_node[nid]) / len(all_matched_terms) if all_matched_terms else 0.0
        )
        existing = keyword_by_node.get(nid, 0.0)
        keyword_by_node[nid] = max(existing, norm_score, term_coverage)

    # exact_keyword_nodes: nodes covering ALL matched terms (only when >1 term)
    exact_keyword_nodes = set()
    if len(all_matched_terms) > 1:
        for nid, matched in terms_by_node.items():
            if all_matched_terms.issubset(matched):
                exact_keyword_nodes.add(nid)

    print(f"\n所有匹配 terms（all_matched_terms）：{all_matched_terms}")
    print(f"exact_keyword_nodes（覆盖全部 terms）：{[str(n)[:12] for n in exact_keyword_nodes]}")
    print(f"keyword_by_node（normalized + term_coverage 取 max）:")
    for nid, sc in sorted(keyword_by_node.items(), key=lambda x: x[1], reverse=True):
        stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
        print(f"  {str(nid)[:36]}...  kw_score={sc:.4f}  heading={stats['heading_path'][:40] if stats else 'N/A'}...")

    # Step 6: Dual-hot 集合（交集门）
    print("\n" + "=" * 80)
    print("STEP 6: Dual-hot 集合（vector_hot ∩ keyword_hot）")
    print("=" * 80)
    print(f"\n阈值：VECTOR_HOT_THRESHOLD={VECTOR_HOT_THRESHOLD}, KEYWORD_HOT_MIN_TERMS={KEYWORD_HOT_MIN_TERMS}")

    vector_by_node = {c["node_id"]: c["normalized_sim"] for c in vector_candidates}
    vector_hot = {nid for nid, s in vector_by_node.items() if s >= VECTOR_HOT_THRESHOLD}
    keyword_hot = {h["node_id"] for h in keyword_hits if h["matched_count"] >= KEYWORD_HOT_MIN_TERMS}
    dual_hot = vector_hot & keyword_hot

    print(f"\nvector_hot 节点数：{len(vector_hot)}")
    print(f"keyword_hot 节点数：{len(keyword_hot)}")
    print(f"dual_hot 节点数（交集）：{len(dual_hot)}")

    if dual_hot:
        print(f"\nDual-hot 节点详情（前10个）:")
        for i, nid in enumerate(list(dual_hot)[:10]):
            stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
            if stats:
                print(f"  [{i+1}] node_id={str(nid)[:36]}...")
                print(f"      norm_sim={vector_by_node.get(nid, 0):.4f}")
                print(f"      heading={stats['heading_path'][:50]}...")

    # Step 7: Parent Coverage Selection（真实 BM25-inspired 公式）
    print("\n" + "=" * 80)
    print("STEP 7: Parent Coverage Selection（真实 BM25-inspired 公式）")
    print("=" * 80)
    print(f"\n筛选参数（production）:")
    print(f"  COVERAGE_THETA = {COVERAGE_THETA}（覆盖率阈值）")
    print(f"  MIN_SUPPORT = {MIN_SUPPORT}（最小 dual_hot 子节点数）")
    print(f"  ROOT_CHILD_BREADTH_CAP = {ROOT_CHILD_BREADTH_CAP}（根/广节点避免）")
    print(f"  BM25_K = {BM25_K}（饱和参数，经验调优）")
    print(f"\n公式：parent_score = avg_child_vector × coverage_ratio × (hot_count / (hot_count + {BM25_K}))")

    # Build parent_to_children
    parent_to_children = {}
    for stats in node_stats_list:
        parent_id = stats.get("parent_node_id")
        if parent_id:
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(stats["node_id"])

    print(f"\nParent-child mappings：{len(parent_to_children)} parents")

    # Find candidate parents from dual_hot children
    candidate_parents = set()
    for child_id in dual_hot:
        child_stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
        if child_stats:
            parent_id = child_stats.get("parent_node_id")
            if parent_id is not None:
                candidate_parents.add(parent_id)

    print(f"Candidate parents（从 dual_hot children）：{len(candidate_parents)}")

    # Compute score for each candidate parent（production logic）
    parent_records = []
    filtered_out = []

    for parent_id in candidate_parents:
        children = parent_to_children.get(parent_id, [])
        dual_hot_children = [c for c in children if c in dual_hot]

        coverage_ratio = len(dual_hot_children) / len(children) if children else 0.0
        hot_count = len(dual_hot_children)
        children_count = len(children)

        parent_stats = next((s for s in node_stats_list if s["node_id"] == parent_id), None)

        # Gate checks
        gate_reason = None
        if coverage_ratio < COVERAGE_THETA:
            gate_reason = f"coverage_ratio {coverage_ratio:.2f} < {COVERAGE_THETA}"
        elif hot_count < MIN_SUPPORT:
            gate_reason = f"hot_count {hot_count} < {MIN_SUPPORT}"
        elif parent_stats and parent_stats.get("parent_node_id") is None:
            gate_reason = "root avoidance (parent_node_id=None)"
        elif children_count > ROOT_CHILD_BREADTH_CAP:
            gate_reason = f"children_count {children_count} > {ROOT_CHILD_BREADTH_CAP} (broad avoidance)"

        if gate_reason:
            filtered_out.append({
                "parent_id": parent_id,
                "reason": gate_reason,
                "coverage_ratio": coverage_ratio,
                "hot_count": hot_count,
                "children_count": children_count,
            })
            continue

        # avg_child_vector（normalized similarity of dual_hot children）
        if dual_hot_children:
            avg_child_vector = sum(
                vector_by_node.get(c, 0.0) for c in dual_hot_children
            ) / len(dual_hot_children)
        else:
            avg_child_vector = 0.0

        # BM25-inspired saturation
        support_saturation = hot_count / (hot_count + BM25_K)
        parent_score = avg_child_vector * coverage_ratio * support_saturation

        parent_records.append({
            "parent_id": parent_id,
            "score": parent_score,
            "coverage_ratio": coverage_ratio,
            "hot_count": hot_count,
            "children_count": children_count,
            "avg_child_vector": avg_child_vector,
            "support_saturation": support_saturation,
            "dual_hot_children_ids": dual_hot_children,
        })

    parent_records.sort(key=lambda p: p["score"], reverse=True)

    print(f"\n被过滤的候选父节点：{len(filtered_out)}")
    if filtered_out:
        for fo in filtered_out[:10]:
            p_stats = next((s for s in node_stats_list if s["node_id"] == fo["parent_id"]), None)
            title = p_stats["title"][:30] if p_stats and p_stats.get("title") else "N/A"
            print(f"  - {str(fo['parent_id'])[:36]}... ({title})")
            print(f"    reason: {fo['reason']}")

    print(f"\n通过筛选的父节点：{len(parent_records)}")

    # Show ALL passing parents with full score breakdown
    print(f"\n{'='*80}")
    print("所有通过筛选父节点的完整评分过程（真实数据）:")
    print(f"{'='*80}")

    for i, parent in enumerate(parent_records):
        p_stats = next((s for s in node_stats_list if s["node_id"] == parent["parent_id"]), None)
        title = p_stats["title"][:40] if p_stats and p_stats.get("title") else "N/A"
        heading = p_stats["heading_path"][:60] if p_stats else "N/A"

        print(f"\n  [{i+1}] Parent hotspot:")
        print(f"      node_id={str(parent['parent_id'])}")
        print(f"      title={title}")
        print(f"      heading={heading}...")
        print(f"      total_children={parent['children_count']}")
        print(f"      dual_hot_children={parent['hot_count']}")
        print(f"      coverage_ratio = {parent['hot_count']}/{parent['children_count']} = {parent['coverage_ratio']:.4f}")
        print(f"      avg_child_vector = {parent['avg_child_vector']:.4f}")
        print(f"      support_saturation = {parent['hot_count']}/({parent['hot_count']}+{BM25_K}) = {parent['support_saturation']:.4f}")
        print(f"      parent_score = {parent['avg_child_vector']:.4f} × {parent['coverage_ratio']:.4f} × {parent['support_saturation']:.4f}")
        print(f"                = {parent['score']:.6f}")

    # Step 8: Leaf Fallback（当无父节点通过时，真实触发的机制）
    print("\n" + "=" * 80)
    print("STEP 8: Leaf Fallback（无父节点通过时触发的真实机制）")
    print("=" * 80)

    leaf_candidates = []
    if not parent_records:
        print("\n⚠ 0 个父节点通过 coverage gate → 触发 leaf fallback（production D-06）")
        print("\nLeaf fallback 优先级：")
        print("  Priority 1: exact_keyword_nodes（覆盖全部 terms，boost kw weight 0.85）")
        print("  Priority 2: dual_hot nodes（vector+keyword 等权 0.5/0.5）")
        print("  Priority 3: pure vector fallback（无 exact/dual 时）")

        has_parent_hierarchy = bool(
            parent_to_children and any(pid is not None for pid in parent_to_children.keys())
        )

        # Priority 1: exact keyword nodes
        print(f"\n[Priority 1] exact_keyword_nodes 评分:")
        for nid in exact_keyword_nodes:
            stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
            if has_parent_hierarchy and stats and stats.get("parent_node_id") is None:
                print(f"  - {str(nid)[:36]}... 跳过（root，存在层级）")
                continue
            vector_score = vector_by_node.get(nid, 0.0)
            keyword_score = keyword_by_node.get(nid, 0.0)
            combined = vector_score * 0.15 + keyword_score * 0.85
            print(f"  - node_id={str(nid)[:36]}...")
            print(f"    heading={stats['heading_path'][:50] if stats else 'N/A'}...")
            print(f"    vector_score={vector_score:.4f}  keyword_score={keyword_score:.4f}")
            print(f"    combined = {vector_score:.4f}×0.15 + {keyword_score:.4f}×0.85 = {combined:.6f}")
            leaf_candidates.append({"node_id": nid, "score": combined, "tier": "exact_keyword", "vector_score": vector_score, "keyword_score": keyword_score})

        # Priority 2: dual_hot
        print(f"\n[Priority 2] dual_hot nodes 评分（排除已加）:")
        for nid in dual_hot:
            if any(c["node_id"] == nid for c in leaf_candidates):
                continue
            stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
            if has_parent_hierarchy and stats and stats.get("parent_node_id") is None:
                continue
            vector_score = vector_by_node.get(nid, 0.0)
            keyword_score = keyword_by_node.get(nid, 0.0)
            combined = vector_score * 0.5 + keyword_score * 0.5
            print(f"  - node_id={str(nid)[:36]}...")
            print(f"    heading={stats['heading_path'][:50] if stats else 'N/A'}...")
            print(f"    vector_score={vector_score:.4f}  keyword_score={keyword_score:.4f}")
            print(f"    combined = {vector_score:.4f}×0.5 + {keyword_score:.4f}×0.5 = {combined:.6f}")
            leaf_candidates.append({"node_id": nid, "score": combined, "tier": "dual_hot", "vector_score": vector_score, "keyword_score": keyword_score})

        leaf_candidates.sort(key=lambda c: c["score"], reverse=True)
        print(f"\nLeaf fallback 排序结果:")
        for i, c in enumerate(leaf_candidates):
            stats = next((s for s in node_stats_list if s["node_id"] == c["node_id"]), None)
            print(f"  [{i+1}] score={c['score']:.6f}  tier={c['tier']}")
            print(f"      node_id={str(c['node_id'])}")
            print(f"      heading={stats['heading_path'][:60] if stats else 'N/A'}")
    else:
        print("\n✓ 有父节点通过 coverage gate，未触发 leaf fallback。")

    # Step 9: Selected hotspot（真实结果对比）
    print("\n" + "=" * 80)
    print("STEP 9: 最终选中的 Hotspot（真实结果对比）")
    print("=" * 80)

    selected = None
    if parent_records:
        selected_id = parent_records[0]["parent_id"]
        selected = ("parent_coverage", selected_id, parent_records[0]["score"])
    elif leaf_candidates:
        selected_id = leaf_candidates[0]["node_id"]
        selected = (leaf_candidates[0]["tier"], selected_id, leaf_candidates[0]["score"])

    if selected:
        tier, sel_id, sel_score = selected
        s_stats = next((s for s in node_stats_list if s["node_id"] == sel_id), None)
        print(f"\n选中的 Hotspot:")
        print(f"  选择机制: {tier}")
        print(f"  node_id={sel_id}")
        print(f"  title={s_stats['title'] if s_stats else 'N/A'}")
        print(f"  heading_path={s_stats['heading_path'] if s_stats else 'N/A'}")
        print(f"  score={sel_score:.6f}")

        # Compare with 05_retrieval_results.json Q18
        print(f"\n与 05_retrieval_results.json Q18 的对比:")
        with open(OUTPUT_DIR / "05_retrieval_results.json", 'r', encoding='utf-8') as f:
            results = json.load(f)
        results_list = results.get("results", results) if isinstance(results, dict) else results
        q18 = next((q for q in results_list if q["query_id"] == "Q18"), None)
        if q18:
            expected_hotspot = q18["hits"][0]["hotspot_node_id"]
            actual_hotspot = str(sel_id)
            match = expected_hotspot == actual_hotspot
            print(f"  预期 hotspot_node_id（真实验证）: {expected_hotspot}")
            print(f"  本测试 hotspot_node_id:        {actual_hotspot}")
            print(f"  匹配: {'✓ 一致' if match else '✗ 不一致'}")
            if match:
                print(f"\n  ✓ 真实选择过程与真实验证结果一致！")
                print(f"  ✓ 关键发现：Q18 实际走的是 {'leaf fallback' if tier != 'parent_coverage' else 'parent coverage'}，")
                print(f"     {'不是 Parent Coverage Selection' if tier != 'parent_coverage' else ''}")
                print(f"  ✓ 这是真实数据驱动的结论，不是假设。")
    else:
        print("\n  ⚠ 无候选节点（极端情况）")

    conn.close()

    print("\n" + "=" * 80)
    print("白盒测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
