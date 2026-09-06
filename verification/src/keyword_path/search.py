from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row


def search_by_keyword(
    conn: psycopg.Connection,
    query: str,
    *,
    version_id: uuid.UUID | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    where_version = "dv.is_active = TRUE"
    params: dict[str, Any] = {
        "query": query,
        "pattern": f"%{query}%",
        "limit": limit,
    }
    if version_id is not None:
        where_version = "cs.version_id = %(version_id)s"
        params["version_id"] = str(version_id)

    sql = f"""
        SELECT
            cs.span_id,
            dv.doc_id,
            cs.version_id,
            cs.page_no,
            cs.heading_path,
            cs.raw_text,
            GREATEST(
                CASE WHEN cs.raw_text ILIKE %(pattern)s THEN 1.0 ELSE 0.0 END,
                similarity(cs.raw_text, %(query)s)
            ) AS match_score
        FROM canonical_spans cs
        JOIN document_versions dv ON cs.version_id = dv.version_id
        WHERE {where_version}
        AND (
            cs.raw_text ILIKE %(pattern)s
            OR cs.raw_text_tsvector @@ websearch_to_tsquery('simple', %(query)s)
        )
        ORDER BY match_score DESC, cs.page_no NULLS LAST, cs.start_offset ASC
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    evidence = []
    for row in rows:
        evidence.append(
            {
                "span_id": uuid.UUID(str(row["span_id"])),
                "doc_id": uuid.UUID(str(row["doc_id"])),
                "version_id": uuid.UUID(str(row["version_id"])),
                "page_no": row["page_no"],
                "heading_path": row["heading_path"],
                "raw_text": row["raw_text"],
                "match_score": float(row["match_score"]),
            }
        )
    match_type = "phrase" if " " in query else "exact"
    return {
        "query": query,
        "match_type": match_type,
        "total_hits": len(evidence),
        "evidence": evidence,
    }
