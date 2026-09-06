#!/usr/bin/env python3
"""
扫描全部 20 个 query，识别哪些真正触发 Parent Coverage Selection（BM25 公式），
哪些走 leaf fallback。

目的：找到真正验证 BM25-inspired saturation 公式的 query。
"""

import io
import sys
import os
import json
import math
from pathlib import Path
from uuid import UUID

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
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def normalize_scores(scores):
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def analyze_query(query_text, embed_model, node_stats_list, parent_to_children):
    """对一个 query 跑完整真实选择过程，返回诊断 dict。"""
    query_embedding = embed_model._get_query_embedding(query_text)

    # Vector candidates
    vector_candidates = []
    for stats in node_stats_list:
        proto = stats.get("prototype_embedding") or stats.get("centroid")
        if proto:
            sim = cosine_similarity(query_embedding, proto)
            vector_candidates.append({"node_id": stats["node_id"], "similarity": sim})
    norm_sims = normalize_scores([c["similarity"] for c in vector_candidates])
    vector_by_node = {c["node_id"]: ns for c, ns in zip(vector_candidates, norm_sims)}

    # Keyword
    query_keywords = _extract_keywords_from_query(query_text)
    keyword_hits_list = []
    for stats in node_stats_list:
        heading = stats.get("heading_path", "") or ""
        title = stats.get("title", "") or ""
        summary = stats.get("summary_text", "") or ""
        searchable = f"{heading} {title} {summary}".lower()
        matched = tuple(kw for kw in query_keywords if kw.lower() in searchable)
        if matched:
            keyword_hits_list.append({"node_id": stats["node_id"], "matched": matched})

    all_matched_terms = set()
    for h in keyword_hits_list:
        all_matched_terms.update(h["matched"])
    terms_by_node = {}
    keyword_norm = normalize_scores([0.6] * len(keyword_hits_list)) if keyword_hits_list else []
    keyword_by_node = {}
    for h, ns in zip(keyword_hits_list, keyword_norm):
        nid = h["node_id"]
        terms_by_node.setdefault(nid, set()).update(h["matched"])
        tc = len(terms_by_node[nid]) / len(all_matched_terms) if all_matched_terms else 0.0
        keyword_by_node[nid] = max(keyword_by_node.get(nid, 0.0), ns, tc)
    exact_keyword_nodes = set()
    if len(all_matched_terms) > 1:
        for nid, matched in terms_by_node.items():
            if all_matched_terms.issubset(matched):
                exact_keyword_nodes.add(nid)

    # Dual-hot
    vector_hot = {nid for nid, s in vector_by_node.items() if s >= VECTOR_HOT_THRESHOLD}
    keyword_hot = {nid for nid, s in keyword_by_node.items() if True}  # any match → keyword_hot
    dual_hot = vector_hot & keyword_hot

    # Parent coverage
    candidate_parents = set()
    for child_id in dual_hot:
        stats = next((s for s in node_stats_list if s["node_id"] == child_id), None)
        if stats:
            pid = stats.get("parent_node_id")
            if pid is not None:
                candidate_parents.add(pid)

    parent_records = []
    for pid in candidate_parents:
        children = parent_to_children.get(pid, [])
        dual_hot_children = [c for c in children if c in dual_hot]
        coverage_ratio = len(dual_hot_children) / len(children) if children else 0.0
        hot_count = len(dual_hot_children)
        children_count = len(children)
        p_stats = next((s for s in node_stats_list if s["node_id"] == pid), None)

        gate_reason = None
        if coverage_ratio < COVERAGE_THETA:
            gate_reason = f"coverage {coverage_ratio:.2f}<{COVERAGE_THETA}"
        elif hot_count < MIN_SUPPORT:
            gate_reason = f"hot_count {hot_count}<{MIN_SUPPORT}"
        elif p_stats and p_stats.get("parent_node_id") is None:
            gate_reason = "root avoidance"
        elif children_count > ROOT_CHILD_BREADTH_CAP:
            gate_reason = f"broad {children_count}>{ROOT_CHILD_BREADTH_CAP}"

        if gate_reason:
            continue

        avg_child_vector = sum(vector_by_node.get(c, 0.0) for c in dual_hot_children) / len(dual_hot_children) if dual_hot_children else 0.0
        support_saturation = hot_count / (hot_count + BM25_K)
        parent_score = avg_child_vector * coverage_ratio * support_saturation
        parent_records.append({
            "parent_id": pid, "score": parent_score, "coverage_ratio": coverage_ratio,
            "hot_count": hot_count, "children_count": children_count,
            "avg_child_vector": avg_child_vector, "support_saturation": support_saturation,
            "dual_hot_children": dual_hot_children,
        })
    parent_records.sort(key=lambda p: p["score"], reverse=True)

    # Leaf fallback
    leaf_candidates = []
    has_hierarchy = bool(parent_to_children and any(pid is not None for pid in parent_to_children))
    for nid in exact_keyword_nodes:
        stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
        if has_hierarchy and stats and stats.get("parent_node_id") is None:
            continue
        vs = vector_by_node.get(nid, 0.0)
        ks = keyword_by_node.get(nid, 0.0)
        leaf_candidates.append({"node_id": nid, "score": vs * 0.15 + ks * 0.85, "tier": "exact_keyword"})
    for nid in dual_hot:
        if any(c["node_id"] == nid for c in leaf_candidates):
            continue
        stats = next((s for s in node_stats_list if s["node_id"] == nid), None)
        if has_hierarchy and stats and stats.get("parent_node_id") is None:
            continue
        vs = vector_by_node.get(nid, 0.0)
        ks = keyword_by_node.get(nid, 0.0)
        leaf_candidates.append({"node_id": nid, "score": vs * 0.5 + ks * 0.5, "tier": "dual_hot"})
    leaf_candidates.sort(key=lambda c: c["score"], reverse=True)

    # Determine mechanism
    if parent_records:
        mechanism = "parent_coverage"
        selected = parent_records[0]
        selected_id = selected["parent_id"]
        selected_score = selected["score"]
        selected_tier = "parent_coverage"
    elif leaf_candidates:
        mechanism = "leaf_fallback"
        selected = leaf_candidates[0]
        selected_id = selected["node_id"]
        selected_score = selected["score"]
        selected_tier = selected["tier"]
    else:
        mechanism = "pure_vector"
        top = max(vector_by_node.items(), key=lambda p: p[1])
        selected_id, selected_score = top
        selected_tier = "pure_vector"

    return {
        "mechanism": mechanism,
        "selected_id": selected_id,
        "selected_score": selected_score,
        "selected_tier": selected_tier,
        "dual_hot_count": len(dual_hot),
        "candidate_parents": len(candidate_parents),
        "passing_parents": len(parent_records),
        "parent_records": parent_records,
        "leaf_candidates_top3": leaf_candidates[:3],
    }


def main():
    print("=" * 90)
    print("全 20 query 扫描：识别真正触发 Parent Coverage Selection（BM25 公式）的 query")
    print("=" * 90)

    db_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(db_url, autocommit=True)
    registry = PostgresRegistryWriter(conn)

    # Load queries
    with open(OUTPUT_DIR / "04_query_set.json", 'r', encoding='utf-8') as f:
        qset = json.load(f)
    queries = qset["queries"]

    # Load tree + stats
    embed_model = RealEmbedding()
    nodes = registry.query_tree_nodes_by_version(VERSION_ID)

    stats_rows = conn.execute("""
        SELECT ne.node_id, ne.embedding_vector, tn.heading_path, tn.title, tn.summary_text, tn.parent_node_id
        FROM node_embeddings ne
        JOIN tree_nodes tn ON ne.node_id = tn.node_id
        WHERE tn.version_id = %s AND ne.embedding_model = 'all-MiniLM-L6-v2'
    """, (str(VERSION_ID),)).fetchall()

    node_stats_list = []
    for row in stats_rows:
        nid = row[0] if isinstance(row[0], UUID) else UUID(row[0])
        node_stats_list.append({
            "node_id": nid,
            "prototype_embedding": list(row[1]) if row[1] is not None else [],
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

    print(f"\n文档节点数：{len(node_stats_list)}  父节点数：{len(parent_to_children)}")
    print(f"\n扫描 {len(queries)} 个 query...\n")

    results = []
    for q in queries:
        diag = analyze_query(q["query"], embed_model, node_stats_list, parent_to_children)
        results.append({"query_id": q["id"], "query": q["query"], "level": q["level"], **diag})

    # Summary table
    print("=" * 90)
    print("扫描结果总览")
    print("=" * 90)
    print(f"{'QID':<5} {'机制':<16} {'tier':<14} {'dual_hot':<9} {'候选父':<7} {'通过父':<7} {'score':<10}")
    print("-" * 90)
    for r in results:
        print(f"{r['query_id']:<5} {r['mechanism']:<16} {r['selected_tier']:<14} "
              f"{r['dual_hot_count']:<9} {r['candidate_parents']:<7} {r['passing_parents']:<7} "
              f"{r['selected_score']:<10.4f}")

    # Stats
    pc = [r for r in results if r["mechanism"] == "parent_coverage"]
    lf = [r for r in results if r["mechanism"] == "leaf_fallback"]
    pv = [r for r in results if r["mechanism"] == "pure_vector"]
    print(f"\n机制分布：")
    print(f"  Parent Coverage Selection（BM25 公式触发）: {len(pc)}/{len(results)}")
    print(f"  Leaf Fallback: {len(lf)}/{len(results)}")
    print(f"  Pure Vector: {len(pv)}/{len(results)}")

    if pc:
        print(f"\n{'='*90}")
        print(f"✓ 找到 {len(pc)} 个真正触发 BM25 公式的 query！")
        print(f"{'='*90}")
        for r in pc:
            print(f"\n>>> {r['query_id']}: {r['query']}")
            print(f"    选中: {r['selected_tier']}  score={r['selected_score']:.6f}")
            print(f"    通过的父节点（BM25 评分排序）:")
            for i, p in enumerate(r["parent_records"]):
                stats = next((s for s in node_stats_list if s["node_id"] == p["parent_id"]), None)
                title = stats["title"][:30] if stats and stats.get("title") else "N/A"
                print(f"      [{i+1}] {str(p['parent_id'])[:36]}  ({title})")
                print(f"          total_children={p['children_count']}  dual_hot={p['hot_count']}")
                print(f"          coverage_ratio={p['coverage_ratio']:.4f}")
                print(f"          avg_child_vector={p['avg_child_vector']:.4f}")
                print(f"          support_saturation={p['hot_count']}/({p['hot_count']}+{BM25_K})={p['support_saturation']:.4f}")
                print(f"          BM25_score = {p['avg_child_vector']:.4f} × {p['coverage_ratio']:.4f} × {p['support_saturation']:.4f} = {p['score']:.6f}")
    else:
        print(f"\n⚠ 没有 query 触发 BM25 公式（全部走 leaf fallback/pure vector）")
        print(f"  这意味着 BM25-inspired saturation 公式在整个 Phase 14 验证集中从未被执行。")

    conn.close()


if __name__ == "__main__":
    main()
