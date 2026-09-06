from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from registry import crud
from vector_path.chunker import SimpleSpanChunker
from vector_path.embedder import DeterministicEmbedder


def _to_vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def load_version_chunks(conn, version_id: uuid.UUID) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM canonical_spans WHERE version_id = %s ORDER BY start_offset",
            (str(version_id),),
        )
        spans = cur.fetchall()

    chunker = SimpleSpanChunker()
    chunks = chunker.generate(spans, version_id=version_id)
    chunk_ids = crud.write_chunks(conn, version_id, chunks)

    mappings: list[tuple[uuid.UUID, uuid.UUID, int]] = []
    for chunk in chunks:
        for idx, span_id in enumerate(chunk["span_ids"]):
            mappings.append((chunk["chunk_id"], span_id, idx))
    crud.write_chunk_span_mappings(conn, mappings)

    embedder = DeterministicEmbedder(dim=16)
    with conn.transaction(), conn.cursor() as cur:
        for chunk in chunks:
            embedding = embedder.embed_text(chunk.get("text_preview") or "")
            cur.execute(
                "UPDATE vector_chunks SET embedding = %s::vector WHERE chunk_id = %s",
                (_to_vector_literal(embedding), str(chunk["chunk_id"])),
            )

    return {"chunk_ids": chunk_ids, "count": len(chunk_ids)}
