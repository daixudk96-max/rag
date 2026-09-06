from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row


def get_active_version(
    conn: psycopg.Connection,
    doc_id: uuid.UUID,
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM document_versions WHERE doc_id = %s AND is_active = TRUE",
            (str(doc_id),),
        )
        row = cur.fetchone()
    if row is None:
        return None
    row["version_id"] = uuid.UUID(str(row["version_id"]))
    row["doc_id"] = uuid.UUID(str(row["doc_id"]))
    if row.get("normalization_contract_id"):
        row["normalization_contract_id"] = uuid.UUID(str(row["normalization_contract_id"]))
    return row


def query_spans_by_version(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
    page_no: int | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM canonical_spans WHERE version_id = %s"
    params: list[Any] = [str(version_id)]
    if page_no is not None:
        sql += " AND page_no = %s"
        params.append(page_no)
    sql += " ORDER BY start_offset LIMIT 1000"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        row["span_id"] = uuid.UUID(str(row["span_id"]))
        row["version_id"] = uuid.UUID(str(row["version_id"]))
        result.append(row)
    return result


def get_chunk_span_ids(
    conn: psycopg.Connection,
    chunk_id: uuid.UUID,
) -> list[uuid.UUID]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT span_id FROM vector_chunk_spans WHERE chunk_id = %s ORDER BY ordinal_no",
            (str(chunk_id),),
        )
        rows = cur.fetchall()
    return [uuid.UUID(str(row[0])) for row in rows]


def trace_chunk_to_document(
    conn: psycopg.Connection,
    chunk_id: uuid.UUID,
) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT vc.chunk_id, vc.page_no, vc.heading_path, dv.version_id, dv.is_active, d.doc_id, d.title
            FROM vector_chunks vc
            JOIN document_versions dv ON vc.version_id = dv.version_id
            JOIN documents d ON dv.doc_id = d.doc_id
            WHERE vc.chunk_id = %s
            """,
            (str(chunk_id),),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError("chunk not found")
    row["chunk_id"] = uuid.UUID(str(row["chunk_id"]))
    row["version_id"] = uuid.UUID(str(row["version_id"]))
    row["doc_id"] = uuid.UUID(str(row["doc_id"]))
    return row
