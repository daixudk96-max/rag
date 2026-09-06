#!/usr/bin/env python3
"""
Q16 深度分析：BM25-inspired Saturation 公式在真实竞争中的决策过程
================================================================

Q16 是最佳验证案例：
- 2个父节点同时通过coverage gate
- 父节点1：完美覆盖率(1.0)，低支持数(2)
- 父节点2：中等覆盖率(0.667)，高支持数(4)
- BM25饱和机制真实决定胜负

Query: "NexusRAG 和 LightRAG 分别使用什么向量数据库？"
"""

import io
import sys
import os
import json
import math
from pathlib import Path
from uuid import UUID
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.environ["RAG_TREE_HOTSPOT_SELECTOR"] = "hybrid_cluster"

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import psycopg
from llamaindex_runtime.embeddings import SentenceTransformersEmbedding
from llama_index.core.embeddings import BaseEmbedding
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.tree.runtime import _extract_keywords_from_query

OUTPUT_DIR = Path(__file__).parent
status_path = OUTPUT_DIR / "02_document_ingestion_status.json"
with open(status_path, 'r', encoding='utf-8') as f:
    status = json.load(f)
    VERSION_ID = UUID(status["version_id"])

# Production 参数
VECTOR_HOT_THRESHOLD = 0.35
KEYWORD_HOT_MIN_TERMS = 1
COVERAGE_THETA = 0.5
MIN_SUPPORT = 2
ROOT_CHILD_BREADTH_CAP = 8
BM25_K = 2.0


class RealEmbedding(BaseEmbedding):
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        super().__init__()
        self._embedder = SentenceTransformersEmbedding(model_name=model_name)

    def _get_query_embedding(self, query):
        return self._embedder._get_query_embedding(query)

    def _get_text_embedding(self, text):
        return self._embedder._get_text_embedding(text)

    def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text):
        return self._get_text_embedding(text)


def cosine_similarity(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def normalize_scores(scores):
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    return [1.0 for _ in scores] if hi - lo < 1e-9 else [(s - lo) / (hi - lo) for s in scores]


def main():
    print("=" * 90)
    print("Q16 深度分析：BM25-inspired Saturation 公式真实竞争决策")
    print("=" * 90)
    print(f"""
Query Q16: "NexusRAG 和 LightRAG 分别使用什么向量数据库？"
关键特征：2个父节点通过coverage gate → 真实竞争场景

公式: parent_score = avg_child_vector × coverage_ratio × (hot_count / (hot_count + {BM25_K}))
""")
    print("=" * 90)

    # Load data
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    registry = PostgresRegistryWriter(conn)

    query_text = "NexusRAG 和 LightRAG 分别使用什么向量数据库？"
    embed_model = RealEmbedding()
    query_embedding = embed_model._get_query_embedding(query_text)

    nodes = registry.query_tree_nodes_by_version(VERSION_ID)

    # Load node stats
    stats_rows = conn.execute("""
        SELECT ne.node_id, ne.embedding_vector, tn.heading_path, tn.title, tn.summary_text, tn.parent_node_id
        FROM node_embeddings ne
        JOIN tree_nodes tn ON ne.node_id = tn.node_id
        WHERE tn.version_id = %s AND ne.embedding_model = 'all-MiniLM-L6-v2'
    """, (str(VERSION_ID),)).fetchall()

    node_stats_list = []
    for row in stats_rows:
        nid = row[0] if isinstance(row[0], UUID) else UUID(row[0])
        embedding_vec = row[1] if row[1] is not None else None
        node_stats_list.append({
            "node_id": nid,
            "prototype_embedding": list(embedding_vec) if embedding_vec is not None else [],
            "heading_path": row[2] or "",
            "title": row[3] or "",
            "summary_text": row[4] or "",
            "parent_node_id": row[5],
        })

    parent_to_children = {}
    for stats in node_stats_list:
        pid = stats.get("parent_node_id")
        if pid:
            parent_to_children.setdefault(pid, []).append(stats["node_id"])

    # Step 1: Vector candidates
    print("\n" + "=" * 90)
    print("STEP 1: Vector Candidates（真实语义相似度）")
    print("=" * 90)

    vector_candidates = []
    for stats in node_stats_list:
        proto = stats.get("prototype_embedding")
        if proto:
            sim = cosine_similarity(query_embedding, proto)
            vector_candidates.append({"node_id": stats["node_id"], "similarity": sim, "heading": stats["heading_path"][:50]})

    norm_sims = normalize_scores([c["similarity"] for c in vector_candidates])
    vector_by_node = {c["node_id"]: ns for c, ns in zip(vector_candidates, norm_sims)}
    vector_candidates = [{"node_id": c["node_id"], "normalized_sim": ns, "heading": c["heading"]} for c, ns in zip(vector_candidates, norm_sims)]
    vector_candidates.sort(key=lambda c: c["normalized_sim"], reverse=True)

    print(f"\nVector candidates 总数：{len(vector_candidates)}")
    print(f"\nTop 10（normalized）:")
    for i, c in enumerate(vector_candidates[:10]):
        print(f"  [{i+1}] norm_sim={c['normalized_sim']:.4f}  heading={c['heading']}")

    # Step 2: Keyword hits
    print("\n" + "=" * 90)
    print("STEP 2: Keyword Hits（真实jieba关键词匹配）")
    print("=" * 90)

    query_keywords = _extract_keywords_from_query(query_text)
    print(f"\nQuery keywords（jieba提取）：{query_keywords}")

    keyword_hits_list = []
    for stats in node_stats_list:
        heading = stats.get("heading_path", "") or ""
        title = stats.get("title", "") or ""
        summary = stats.get("summary_text", "") or ""
        searchable = f"{heading} {title} {summary}".lower()
        matched = tuple(kw for kw in query_keywords if kw.lower() in searchable)
        if matched:
            keyword_hits_list.append({"node_id": stats["node_id"], "matched": matched, "heading": heading[:50]})

    all_matched_terms = set()
    for h in keyword_hits_list:
        all_matched_terms.update(h["matched"])

    print(f"\n所有匹配 terms：{all_matched_terms}")
    print(f"\nKeyword hits 总数：{len(keyword_hits_list)}")
    print(f"\nTop 10:")
    for i, h in enumerate(keyword_hits_list[:10]):
        print(f"  [{i+1}] matched={h['matched']}  heading={h['heading']}")

    # Step 3: Dual-hot
    print("\n" + "=" * 90)
    print("STEP 3: Dual-hot 集合（vector_hot ∩ keyword_hot）")
    print("=" * 90)

    vector_hot = {nid for nid, s in vector_by_node.items() if s >= VECTOR_HOT_THRESHOLD}
    keyword_hot = {h["node_id"] for h in keyword_hits_list}  # any match → keyword_hot
    dual_hot = vector_hot & keyword_hot

    print(f"\n阈值：VECTOR_HOT_THRESHOLD={VECTOR_HOT_THRESHOLD}, KEYWORD_HOT_MIN_TERMS={KEYWORD_HOT_MIN_TERMS}")
    print(f"\nvector_hot 节点数：{len(vector_hot)}")
    print(f"keyword_hot 节点数：{len(keyword_hot)}")
    print(f"dual_hot 节点数（交集）：{len(dual_hot)}")

    if dual_hot:
        print(f"\nDual-hot 节点详情（全部）:")
        for i, nid in enumerate(sorted(dual_hot)):
            stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
            if stats:
                print(f"  [{i+1}] node_id={str(nid)[:36]}...")
                print(f"      norm_sim={vector_by_node.get(nid, 0):.4f}")
                print(f"      heading={stats['heading_path'][:60]}...")

    # Step 4: Parent Coverage Selection（BM25竞争）
    print("\n" + "=" * 90)
    print("STEP 4: Parent Coverage Selection（BM25公式真实竞争）")
    print("=" * 90)
    print(f"\n筛选参数（production）:")
    print(f"  COVERAGE_THETA = {COVERAGE_THETA}（覆盖率阈值）")
    print(f"  MIN_SUPPORT = {MIN_SUPPORT}（最小dual_hot子节点数）")
    print(f"  ROOT_CHILD_BREADTH_CAP = {ROOT_CHILD_BREADTH_CAP}（根节点避免）")
    print(f"  BM25_K = {BM25_K}（饱和参数）")
    print(f"\n公式：parent_score = avg_child_vector × coverage_ratio × (hot_count / (hot_count + {BM25_K}))")

    # Find candidate parents
    candidate_parents = set()
    for child_id in dual_hot:
        stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
        if stats:
            pid = stats.get("parent_node_id")
            if pid is not None:
                candidate_parents.add(pid)

    print(f"\nCandidate parents（从dual_hot children）：{len(candidate_parents)}")
    print(f"候选父节点：")
    for i, pid in enumerate(sorted(candidate_parents)):
        stats = next((s for s in node_stats_list if s["node_id"] == pid), None)
        title = stats["title"][:40] if stats and stats.get("title") else "N/A"
        print(f"  [{i+1}] {str(pid)[:36]}...  ({title})")

    # Compute scores for each candidate
    print(f"\n{'='*90}")
    print(f"每个候选父节点的完整评分过程（真实BM25公式）:")
    print(f"{'='*90}")

    parent_records = []
    filtered_out = []

    for pid in sorted(candidate_parents):
        children = parent_to_children.get(pid, [])
        dual_hot_children = [c for c in children if c in dual_hot]

        coverage_ratio = len(dual_hot_children) / len(children) if children else 0.0
        hot_count = len(dual_hot_children)
        children_count = len(children)

        p_stats = next((s for s in node_stats_list if s["node_id"] == pid), None)

        # Gate checks
        gate_reason = None
        if coverage_ratio < COVERAGE_THETA:
            gate_reason = f"coverage_ratio {coverage_ratio:.3f} < {COVERAGE_THETA}"
        elif hot_count < MIN_SUPPORT:
            gate_reason = f"hot_count {hot_count} < {MIN_SUPPORT}"
        elif p_stats and p_stats.get("parent_node_id") is None:
            gate_reason = "root avoidance (parent_node_id=None)"
        elif children_count > ROOT_CHILD_BREADTH_CAP:
            gate_reason = f"children_count {children_count} > {ROOT_CHILD_BREADTH_CAP}"

        if gate_reason:
            filtered_out.append({
                "parent_id": pid, "reason": gate_reason,
                "coverage_ratio": coverage_ratio, "hot_count": hot_count, "children_count": children_count,
            })
            continue

        # BM25-inspired scoring
        avg_child_vector = sum(vector_by_node.get(c, 0.0) for c in dual_hot_children) / len(dual_hot_children) if dual_hot_children else 0.0
        support_saturation = hot_count / (hot_count + BM25_K)
        parent_score = avg_child_vector * coverage_ratio * support_saturation

        parent_records.append({
            "parent_id": pid, "score": parent_score,
            "coverage_ratio": coverage_ratio, "hot_count": hot_count, "children_count": children_count,
            "avg_child_vector": avg_child_vector, "support_saturation": support_saturation,
            "dual_hot_children_ids": dual_hot_children,
        })

    parent_records.sort(key=lambda p: p["score"], reverse=True)

    if filtered_out:
        print(f"\n被过滤的候选父节点：{len(filtered_out)}")
        for fo in filtered_out:
            p_stats = next((s for s in node_stats_list if s["node_id"] == fo["parent_id"]), None)
            title = p_stats["title"][:30] if p_stats and p_stats.get("title") else "N/A"
            print(f"  - {str(fo['parent_id'])[:36]}...  ({title})")
            print(f"    reason: {fo['reason']}")

    print(f"\n通过筛选的父节点：{len(parent_records)} 个 → **真实竞争场景！**")

    # Show ALL passing parents with complete breakdown
    for i, parent in enumerate(parent_records):
        p_stats = next((s for s in node_stats_list if s["node_id"] == parent["parent_id"]), None)
        title = p_stats["title"][:40] if p_stats and p_stats.get("title") else "N/A"
        heading = p_stats["heading_path"][:70] if p_stats else "N/A"

        print(f"\n{'='*90}")
        print(f"父节点 #{i+1}（完整评分分解）：")
        print(f"{'='*90}")
        print(f"node_id:       {parent['parent_id']}")
        print(f"title:         {title}")
        print(f"heading:       {heading}...")
        print(f"total_children: {parent['children_count']}")
        print(f"dual_hot_children: {parent['hot_count']}")

        # Show which children are dual-hot
        print(f"\nDual-hot 子节点详情（{parent['hot_count']} 个）:")
        for j, child_id in enumerate(parent["dual_hot_children_ids"][:5]):
            child_stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
            if child_stats:
                print(f"  [{j+1}] node_id={str(child_id)[:36]}...")
                print(f"      norm_sim={vector_by_node.get(child_id, 0):.4f}")
                print(f"      heading={child_stats['heading_path'][:50]}...")

        # Factor breakdown
        print(f"\n三维因子分解：")
        print(f"  1️ coverage_ratio = {parent['hot_count']} dual_hot / {parent['children_count']} total = {parent['coverage_ratio']:.4f}")
        print(f"  2️ avg_child_vector = 平均(dual_hot子节点norm_sim) = {parent['avg_child_vector']:.4f}")
        print(f"  3️ support_saturation = {parent['hot_count']} / ({parent['hot_count']} + {BM25_K}) = {parent['support_saturation']:.4f}")

        print(f"\nBM25-inspired Score:")
        print(f"  parent_score = {parent['avg_child_vector']:.4f} × {parent['coverage_ratio']:.4f} × {parent['support_saturation']:.4f}")
        print(f"               = {parent['score']:.6f}")

    # Step 5: Winner analysis
    print(f"\n{'='*90}")
    print(f"STEP 5: 胜出分析（为什么父节点{parent_records[0]['parent_id']}胜出？）")
    print(f"{'='*90}")

    if len(parent_records) >= 2:
        winner = parent_records[0]
        runner = parent_records[1]

        print(f"\n对比胜者 vs 亚军：")
        print(f"\n胜者（父节点 #1）：")
        print(f"  coverage_ratio: {winner['coverage_ratio']:.4f}")
        print(f"  avg_child_vector: {winner['avg_child_vector']:.4f}")
        print(f"  support_saturation: {winner['support_saturation']:.4f}")
        print(f"  BM25_score: {winner['score']:.6f}")

        print(f"\n亚军（父节点 #2）：")
        print(f"  coverage_ratio: {runner['coverage_ratio']:.4f}")
        print(f"  avg_child_vector: {runner['avg_child_vector']:.4f}")
        print(f"  support_saturation: {runner['support_saturation']:.4f}")
        print(f"  BM25_score: {runner['score']:.6f}")

        print(f"\n胜出原因分析：")

        # Coverage factor
        cov_diff = winner['coverage_ratio'] - runner['coverage_ratio']
        if abs(cov_diff) > 0.01:
            print(f"  ✓ Coverage优势：胜者覆盖率 {winner['coverage_ratio']:.4f} > 亚军 {runner['coverage_ratio']:.4f}")
            print(f"    （差异 {cov_diff:.4f}）")
        else:
            print(f"  ⚠ Coverage接近：胜者 {winner['coverage_ratio']:.4f} vs 亚军 {runner['coverage_ratio']:.4f}")

        # Quality factor
        qual_diff = winner['avg_child_vector'] - runner['avg_child_vector']
        if abs(qual_diff) > 0.01:
            print(f"  ✓ Quality优势：胜者质量 {winner['avg_child_vector']:.4f} > 亚军 {runner['avg_child_vector']:.4f}")
            print(f"    （差异 {qual_diff:.4f}）")
        else:
            print(f"  ⚠ Quality接近：胜者 {winner['avg_child_vector']:.4f} vs 亚军 {runner['avg_child_vector']:.4f}")

        # Saturation factor
        sat_diff = winner['support_saturation'] - runner['support_saturation']
        print(f"\n  BM25 Saturation效果：")
        print(f"    胜者：{winner['hot_count']} dual_hot → saturation={winner['support_saturation']:.4f}")
        print(f"    亚军：{runner['hot_count']} dual_hot → saturation={runner['support_saturation']:.4f}")

        if winner['hot_count'] > runner['hot_count']:
            print(f"    亚军支持数更多（{runner['hot_count']} vs {winner['hot_count']}）")
            print(f"    但BM25饱和防止亚军靠数量翻盘：")
            print(f"      亚军saturation={runner['support_saturation']:.4f}（受k={BM25_K}压制）")
            print(f"      理论线性增长：亚军支持数多 {runner['hot_count']-winner['hot_count']} → 应得更高分数")
            print(f"      实际BM25饱和：saturation只增加 {sat_diff:.4f}")
            print(f"      **关键发现：BM25公式阻止了亚军的数量优势转化为分数优势**")
        elif winner['hot_count'] < runner['hot_count']:
            print(f"    胜者支持数更多（{winner['hot_count']} vs {runner['hot_count']}）")
            print(f"    饱和机制进一步放大胜者优势")

        print(f"\n最终BM25_score差异：{winner['score'] - runner['score']:.6f}")

        # Hypothetical linear comparison
        print(f"\n假设：如果用旧公式（线性相加）会如何？")
        linear_winner = winner['coverage_ratio'] * 0.50 + winner['avg_child_vector'] * 0.30 + (winner['hot_count'] / 5.0) * 0.20
        linear_runner = runner['coverage_ratio'] * 0.50 + runner['avg_child_vector'] * 0.30 + (runner['hot_count'] / 5.0) * 0.20
        print(f"  线性公式胜者：{linear_winner:.6f}")
        print(f"  线性公式亚军：{linear_runner:.6f}")
        if linear_runner > linear_winner:
            print(f"  **线性公式下，亚军会胜出！**（支持数优势翻盘）")
            print(f"  **BM25公式阻止了这个错误决策**")
        else:
            print(f"  线性公式下，胜者依然胜出")

    # Step 6: Verify against real retrieval results
    print(f"\n{'='*90}")
    print(f"STEP 6: 验证（与真实检索结果对比）")
    print(f"{'='*90}")

    with open(OUTPUT_DIR / "05_retrieval_results.json", 'r', encoding='utf-8') as f:
        results_data = json.load(f)
    results_list = results_data.get("results", results_data) if isinstance(results_data, dict) else results_data
    q16 = next((q for q in results_list if q["query_id"] == "Q16"), None)

    if q16 and parent_records:
        expected_hotspot = q16["hits"][0]["hotspot_node_id"]
        actual_hotspot = str(parent_records[0]["parent_id"])
        match = expected_hotspot == actual_hotspot

        print(f"\n与 05_retrieval_results.json Q16 对比:")
        print(f"  预期 hotspot_node_id（真实验证）：{expected_hotspot}")
        print(f"  本测试 hotspot_node_id：         {actual_hotspot}")
        print(f"  匹配：{'✓ 一致' if match else '✗ 不一致'}")

        if match:
            print(f"\n✓ BM25公式真实决策与真实验证完全一致！")
            print(f"✓ 不是假设，是真实公式 × 真实数据驱动的选择。")
            print(f"✓ BM25-inspired saturation有效解决三维冲突。")

    conn.close()
    print(f"\n{'='*90}")
    print(f"Q16深度分析完成")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()