from __future__ import annotations

from registry import connection


def test_get_pool_available() -> None:
    pool = connection.get_pool()
    assert pool is not None


def test_get_connection_works() -> None:
    with connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
    assert row[0] == 1
