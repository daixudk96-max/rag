from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from registry.queries import get_chunk_span_ids
from vector_path.embedder import DeterministicEmbedder


def _to_vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def search_by_vector_query(
    conn,
    query: str,
    *,
    version_id: uuid.UUID | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    embedder = DeterministicEmbedder(dim=16)
    query_embedding = embedder.embed_text(query)

    where_version = "dv.is_active = TRUE"
    params: dict[str, Any] = {"query_embedding": _to_vector_literal(query_embedding), "top_k": top_k}
    if version_id is not None:
        where_version = "vc.version_id = %(version_id)s"
        params["version_id"] = str(version_id)

    sql = f"""
        SELECT
            vc.chunk_id,
            vc.page_no,
            vc.heading_path,
            vc.text_preview,
            vc.version_id,
            (1 - (vc.embedding <=> %(query_embedding)s::vector)) AS score
        FROM vector_chunks vc
        JOIN document_versions dv ON vc.version_id = dv.version_id
        WHERE {where_version}
          AND vc.embedding IS NOT NULL
        ORDER BY vc.embedding <=> %(query_embedding)s::vector
        LIMIT %(top_k)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    chunks = []
    for row in rows:
        chunk_uuid = uuid.UUID(str(row["chunk_id"]))
        chunks.append(
            {
                "chunk_id": chunk_uuid,
                "span_ids": get_chunk_span_ids(conn, chunk_uuid),
                "page_no": row["page_no"],
                "heading_path": row["heading_path"],
                "text_preview": row["text_preview"],
                "score": float(row["score"]),
            }
        )
    return {"query": query, "path": "vector", "total_hits": len(chunks), "chunks": chunks}
