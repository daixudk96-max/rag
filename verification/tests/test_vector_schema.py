from __future__ import annotations


def test_vector_extension_available(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
    assert row is not None


def test_vector_chunks_has_embedding_column(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_name = 'vector_chunks' AND column_name = 'embedding'
            """
        )
        row = cur.fetchone()
    assert row is not None


def test_vector_index_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'vector_chunks'")
        indexes = {r[0] for r in cur.fetchall()}
    assert "idx_vector_chunks_embedding" in indexes
