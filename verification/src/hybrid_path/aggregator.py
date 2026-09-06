from __future__ import annotations

from collections import defaultdict
from typing import Any

from hit_distribution.analyzer import analyze_hit_distribution
from hit_distribution.types import NodeHit
from .types import HybridHit


def aggregate_hits(hits: list[HybridHit]) -> list[HybridHit]:
    grouped: dict[object, list[HybridHit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.span_id].append(hit)
    merged: list[HybridHit] = []
    for span_id, group in grouped.items():
        best = max(group, key=lambda item: item.best_score)
        sources = frozenset().union(*(item.source_paths for item in group))
        merged.append(HybridHit(span_id=best.span_id, source_paths=sources, best_score=best.best_score, page_no=best.page_no, heading_path=best.heading_path, raw_text=best.raw_text, node_id=best.node_id))
    return merged


def map_hits_to_tree_nodes(conn, hits: list[HybridHit]) -> list[NodeHit]:
    node_hits: list[NodeHit] = []
    for hit in hits:
        node_id = hit.node_id
        if node_id is None:
            with conn.cursor() as cur:
                cur.execute("SELECT node_id FROM vector_chunks WHERE heading_path = %s LIMIT 1", (hit.heading_path,))
                row = cur.fetchone()
            node_id = row[0] if row and row[0] else None
        if node_id is not None:
            node_hits.append(NodeHit(node_id=node_id, score=hit.best_score, level_no=0, heading_path=hit.heading_path))
    return node_hits


def build_tree_topology(conn, version_id=None):
    from psycopg.rows import dict_row
    sql = "SELECT node_id, parent_node_id, level_no, heading_path FROM tree_nodes"
    params = ()
    if version_id is not None:
        sql += " WHERE version_id = %s"
        params = (str(version_id),)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    parent_map = {row['node_id']: row['parent_node_id'] for row in rows}
    level_map = {row['node_id']: row['level_no'] for row in rows}
    heading_map = {row['node_id']: row['heading_path'] for row in rows}
    return parent_map, level_map, heading_map


def run_distribution_analysis(conn, hits: list[HybridHit], version_id=None):
    node_hits = map_hits_to_tree_nodes(conn, hits)
    if not node_hits:
        return None
    parent_map, level_map, heading_map = build_tree_topology(conn, version_id)
    return analyze_hit_distribution(node_hits, parent_map, level_map, heading_map)
