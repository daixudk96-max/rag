from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from .types import NodeHit
from vector_path.search import search_by_vector_query


def _has_overlap(query: str, text: str) -> bool:
    qchars = {ch for ch in query.replace(" ", "") if ch.strip()}
    tchars = {ch for ch in text.replace(" ", "") if ch.strip()}
    return bool(qchars & tchars)


def collect_vector_hits_with_nodes(conn, query: str, *, version_id: uuid.UUID | None = None, top_k: int = 10):
    vector_result = search_by_vector_query(conn, query, version_id=version_id, top_k=top_k)
    if vector_result["chunks"] and not any(_has_overlap(query, chunk.get("text_preview") or "") for chunk in vector_result["chunks"]):
        return [], {}, {}, {}, 0
    hits: list[NodeHit] = []

    tree_sql = "SELECT node_id, parent_node_id, level_no, heading_path FROM tree_nodes"
    tree_params: tuple[str, ...] | tuple[()] = tuple()
    if version_id is not None:
        tree_sql += " WHERE version_id = %s"
        tree_params = (str(version_id),)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(tree_sql, tree_params)
        tree_rows = cur.fetchall()

    tree_parent_map = {uuid.UUID(str(row["node_id"])): (uuid.UUID(str(row["parent_node_id"])) if row["parent_node_id"] else None) for row in tree_rows}
    tree_level_map = {uuid.UUID(str(row["node_id"])): row["level_no"] for row in tree_rows}
    tree_heading_map = {uuid.UUID(str(row["node_id"])): row["heading_path"] for row in tree_rows}

    chunk_ids = [str(chunk["chunk_id"]) for chunk in vector_result["chunks"]]
    node_by_chunk: dict[str, uuid.UUID | None] = {}
    if chunk_ids:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT chunk_id, node_id FROM vector_chunks WHERE chunk_id = ANY(%s)",
                (chunk_ids,),
            )
            for row in cur.fetchall():
                node_by_chunk[str(row["chunk_id"])] = uuid.UUID(str(row["node_id"])) if row["node_id"] else None

    for chunk in vector_result["chunks"]:
        node_id = node_by_chunk.get(str(chunk["chunk_id"]))
        if node_id:
            hits.append(
                NodeHit(
                    node_id=node_id,
                    score=float(chunk["score"]),
                    level_no=tree_level_map.get(node_id, 0),
                    heading_path=tree_heading_map.get(node_id),
                )
            )

    return hits, tree_parent_map, tree_level_map, tree_heading_map, vector_result["total_hits"]
