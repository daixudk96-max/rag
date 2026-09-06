from __future__ import annotations

import uuid
from typing import Iterable, TypedDict

import psycopg
from psycopg.rows import dict_row

MAX_BATCH_SIZE = 1000


class SpanInput(TypedDict):
    span_id: uuid.UUID
    span_kind: str
    start_offset: int
    end_offset: int
    page_no: int | None
    heading_path: str | None
    raw_text: str | None


class ChunkInput(TypedDict):
    chunk_id: uuid.UUID
    chunk_type: str
    chunk_order: int | None
    token_count: int | None
    text_preview: str | None
    page_no: int | None
    heading_path: str | None


REQUIRED_SPAN_KEYS = {"span_id", "span_kind", "start_offset", "end_offset"}
REQUIRED_CHUNK_KEYS = {"chunk_id", "chunk_type"}


def _ensure_batch_limit(items: list[object]) -> None:
    if len(items) > MAX_BATCH_SIZE:
        raise ValueError(f"batch size exceeds {MAX_BATCH_SIZE}")


def _validate_span_input(span: SpanInput) -> None:
    missing = REQUIRED_SPAN_KEYS.difference(span.keys())
    if missing:
        raise KeyError(f"missing span keys: {sorted(missing)}")


def _validate_chunk_input(chunk: ChunkInput) -> None:
    missing = REQUIRED_CHUNK_KEYS.difference(chunk.keys())
    if missing:
        raise KeyError(f"missing chunk keys: {sorted(missing)}")


def create_document(
    conn: psycopg.Connection,
    *,
    title: str,
    source_uri: str | None = None,
    doc_type: str | None = None,
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (doc_id, source_uri, title, doc_type) VALUES (%s, %s, %s, %s)",
            (str(doc_id), source_uri, title, doc_type),
        )
    return doc_id


def create_normalization_contract(
    conn: psycopg.Connection,
    parser_name: str,
    *,
    parser_version: str | None = None,
    offset_basis: str = "normalized_char_offset",
    notes: str | None = None,
) -> uuid.UUID:
    contract_id = uuid.uuid4()
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO normalization_contracts (normalization_contract_id, parser_name, parser_version, offset_basis, notes) VALUES (%s, %s, %s, %s, %s)",
            (str(contract_id), parser_name, parser_version, offset_basis, notes),
        )
    return contract_id


def create_version(
    conn: psycopg.Connection,
    *,
    doc_id: uuid.UUID,
    content_hash: str,
    normalization_contract_id: uuid.UUID,
    version_no: int | None = None,
    status: str = "staging",
) -> uuid.UUID:
    version_id = uuid.uuid4()
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        if version_no is None:
            cur.execute(
                "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM document_versions WHERE doc_id = %s",
                (str(doc_id),),
            )
            version_no = int(cur.fetchone()["max_version"]) + 1
        cur.execute(
            "INSERT INTO document_versions (version_id, doc_id, content_hash, version_no, normalization_contract_id, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (str(version_id), str(doc_id), content_hash, version_no, str(normalization_contract_id), status),
        )
    return version_id


def activate_version(conn: psycopg.Connection, version_id: uuid.UUID) -> None:
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT doc_id FROM document_versions WHERE version_id = %s",
            (str(version_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("version not found")
        doc_id = row["doc_id"]
        cur.execute(
            "UPDATE document_versions SET is_active = FALSE, retired_at = now() WHERE doc_id = %s AND is_active = TRUE AND version_id <> %s",
            (doc_id, str(version_id)),
        )
        cur.execute(
            "UPDATE document_versions SET is_active = TRUE, activated_at = now(), status = 'active' WHERE version_id = %s",
            (str(version_id),),
        )


def write_spans(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
    spans: Iterable[SpanInput],
) -> list[uuid.UUID]:
    span_list = list(spans)
    _ensure_batch_limit(span_list)
    values: list[tuple[str, str, str, int, int, int | None, str | None, str | None]] = []
    for span in span_list:
        _validate_span_input(span)
        values.append(
            (
                str(span["span_id"]),
                str(version_id),
                span["span_kind"],
                span["start_offset"],
                span["end_offset"],
                span.get("page_no"),
                span.get("heading_path"),
                span.get("raw_text"),
            )
        )
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, end_offset, page_no, heading_path, raw_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            values,
        )
    return [uuid.UUID(v[0]) for v in values]


def write_chunks(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
    chunks: Iterable[ChunkInput],
) -> list[uuid.UUID]:
    chunk_list = list(chunks)
    _ensure_batch_limit(chunk_list)
    values: list[tuple[str, str, str, int | None, int | None, str | None, int | None, str | None]] = []
    for chunk in chunk_list:
        _validate_chunk_input(chunk)
        values.append(
            (
                str(chunk["chunk_id"]),
                str(version_id),
                chunk["chunk_type"],
                chunk.get("chunk_order"),
                chunk.get("token_count"),
                chunk.get("text_preview"),
                chunk.get("page_no"),
                chunk.get("heading_path"),
            )
        )
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO vector_chunks (chunk_id, version_id, chunk_type, chunk_order, token_count, text_preview, page_no, heading_path) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            values,
        )
    return [uuid.UUID(v[0]) for v in values]


def write_chunk_span_mappings(
    conn: psycopg.Connection,
    mappings: Iterable[tuple[uuid.UUID, uuid.UUID, int]],
) -> None:
    mapping_list = list(mappings)
    _ensure_batch_limit(mapping_list)
    values = [(str(chunk_id), str(span_id), ordinal_no) for chunk_id, span_id, ordinal_no in mapping_list]
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO vector_chunk_spans (chunk_id, span_id, ordinal_no) VALUES (%s, %s, %s)",
            values,
        )


def create_entity(
    conn: psycopg.Connection,
    *,
    entity_id: uuid.UUID,
    entity_key: str,
    entity_type: str | None,
    canonical_name: str | None,
) -> uuid.UUID:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entities (entity_id, entity_key, entity_type, canonical_name) VALUES (%s, %s, %s, %s)",
            (str(entity_id), entity_key, entity_type, canonical_name),
        )
    return entity_id


def create_relation(
    conn: psycopg.Connection,
    *,
    relation_id: uuid.UUID,
    relation_key: str,
    relation_type: str,
    source_entity_id: uuid.UUID,
    target_entity_id: uuid.UUID,
) -> uuid.UUID:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO relations (relation_id, relation_key, relation_type, source_entity_id, target_entity_id) VALUES (%s, %s, %s, %s, %s)",
            (str(relation_id), relation_key, relation_type, str(source_entity_id), str(target_entity_id)),
        )
    return relation_id


def create_evidence_link(
    conn: psycopg.Connection,
    *,
    version_id: uuid.UUID,
    span_id: uuid.UUID,
    source_kind: str,
    entity_id: uuid.UUID | None = None,
    relation_id: uuid.UUID | None = None,
    confidence_score: float | None = None,
) -> uuid.UUID:
    evidence_link_id = uuid.uuid4()
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO evidence_links (evidence_link_id, version_id, entity_id, relation_id, span_id, source_kind, confidence_score) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                str(evidence_link_id),
                str(version_id),
                str(entity_id) if entity_id else None,
                str(relation_id) if relation_id else None,
                str(span_id),
                source_kind,
                confidence_score,
            ),
        )
    return evidence_link_id
