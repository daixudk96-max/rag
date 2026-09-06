from __future__ import annotations


def test_entities_table_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entities'")
        row = cur.fetchone()
    assert row is not None


def test_relations_table_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'relations'")
        row = cur.fetchone()
    assert row is not None


def test_evidence_links_table_exists(db_connection, applied_schema) -> None:
    with db_connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'evidence_links'")
        row = cur.fetchone()
    assert row is not None
