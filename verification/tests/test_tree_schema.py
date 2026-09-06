from __future__ import annotations


def test_tree_nodes_table_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'tree_nodes'")
        row = cur.fetchone()
    assert row is not None


def test_tree_node_spans_table_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'tree_node_spans'")
        row = cur.fetchone()
    assert row is not None


def test_tree_nodes_indexes(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'tree_nodes'")
        indexes = {r[0] for r in cur.fetchall()}
    assert "idx_tree_nodes_version_id" in indexes
    assert "idx_tree_nodes_parent" in indexes


def test_vector_chunks_has_node_id(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'vector_chunks' AND column_name = 'node_id'")
        row = cur.fetchone()
    assert row is not None
