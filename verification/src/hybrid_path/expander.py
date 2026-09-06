from __future__ import annotations

import uuid

from psycopg.rows import dict_row

from tree_path.query import rollup_to_parent
from .types import HybridHit


def _fetch_node_span_hits(conn, node_ids: list[uuid.UUID]) -> list[HybridHit]:
    if not node_ids:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT tns.node_id, cs.span_id, cs.page_no, cs.heading_path, cs.raw_text
            FROM tree_node_spans tns
            JOIN canonical_spans cs ON tns.span_id = cs.span_id
            WHERE tns.node_id = ANY(%s)
            ORDER BY cs.start_offset
            """,
            ([str(node_id) for node_id in node_ids],),
        )
        rows = cur.fetchall()
    return [
        HybridHit(
            span_id=row["span_id"],
            source_paths=frozenset({"tree_expansion"}),
            best_score=0.0,
            page_no=row["page_no"],
            heading_path=row["heading_path"],
            raw_text=row["raw_text"],
            node_id=row["node_id"],
        )
        for row in rows
    ]


def expand_by_decision(conn, decision, version_id=None):
    if decision.decision == "high_concentration":
        base = decision.suggested_node_ids[:2]
    elif decision.decision == "high_dispersion":
        base = decision.suggested_node_ids
    elif decision.decision == "moderate":
        base = decision.suggested_node_ids[:1]
    else:
        return []
    expanded = _fetch_node_span_hits(conn, base)
    for node_id in list(base):
        parent = rollup_to_parent(conn, node_id)
        if parent:
            expanded.extend(_fetch_node_span_hits(conn, [parent["node_id"]]))
    return expanded
