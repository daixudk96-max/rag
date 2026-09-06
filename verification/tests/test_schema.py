from __future__ import annotations

from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = ROOT / "src" / "registry" / "migrations" / "001_initial.sql"


def test_migration_file_exists() -> None:
    assert MIGRATION_FILE.exists(), "001_initial.sql must exist"


def test_schema_creates_all_tables(db_connection, applied_schema) -> None:
    expected = {
        "documents",
        "document_versions",
        "normalization_contracts",
        "canonical_spans",
        "vector_chunks",
        "vector_chunk_spans",
    }
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        rows = {row[0] for row in cur.fetchall()}
    assert expected.issubset(rows)


def test_schema_has_required_constraints(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'document_versions'
              AND constraint_type = 'UNIQUE'
            """
        )
        names = {row[0] for row in cur.fetchall()}
    assert any("doc_id" in name or "content_hash" in name or "version" in name for name in names)


def test_schema_has_required_indexes(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
        )
        indexes = {row[0] for row in cur.fetchall()}
    assert "idx_document_versions_active" in indexes
    assert "idx_canonical_spans_version_id" in indexes
    assert "idx_vector_chunks_version_id" in indexes
    assert "idx_vector_chunk_spans_span" in indexes


def test_active_version_partial_unique_index(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'idx_document_versions_active'
            """
        )
        row = cur.fetchone()
    assert row is not None
    assert "WHERE (is_active = true)" in row[0]


def test_span_offset_check_constraint(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (doc_id, title) VALUES ('00000000-0000-0000-0000-000000000001', 'doc')"
        )
        cur.execute(
            "INSERT INTO normalization_contracts (normalization_contract_id, parser_name, offset_basis) VALUES ('00000000-0000-0000-0000-000000000002', 'Docling', 'normalized_char_offset')"
        )
        cur.execute(
            "INSERT INTO document_versions (version_id, doc_id, content_hash, version_no, normalization_contract_id) VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'hash', 1, '00000000-0000-0000-0000-000000000002')"
        )
        try:
            cur.execute(
                "INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, end_offset, raw_text) VALUES ('00000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000003', 'paragraph', 10, 10, 'bad')"
            )
        except psycopg.Error:
            return
    raise AssertionError("check constraint should reject end_offset <= start_offset")


def test_foreign_keys_enforced(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO canonical_spans (span_id, version_id, span_kind, start_offset, end_offset, raw_text) VALUES ('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000099', 'paragraph', 0, 5, 'oops')"
            )
        except psycopg.Error:
            return
    raise AssertionError("foreign key should reject missing version_id")
