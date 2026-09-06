from __future__ import annotations

import os
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_pool_lock = Lock()


def _get_dsn(database_url: str | None = None) -> str:
    dsn = database_url or os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL must be set")
    return dsn


def init_pool(database_url: str | None = None, min_size: int | None = None, max_size: int | None = None) -> ConnectionPool:
    global _pool
    dsn = _get_dsn(database_url)
    pool_min = min_size if min_size is not None else int(os.getenv("POOL_MIN_SIZE", "2"))
    pool_max = max_size if max_size is not None else int(os.getenv("POOL_MAX_SIZE", "10"))
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=dsn,
                    min_size=pool_min,
                    max_size=pool_max,
                    open=True,
                    configure=register_vector,
                    kwargs={"autocommit": False, "connect_timeout": 2},
                )
    return _pool


def get_pool() -> ConnectionPool:
    return init_pool()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection(database_url: str | None = None, *, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    if database_url is not None:
        conn = psycopg.connect(_get_dsn(database_url), autocommit=autocommit, connect_timeout=2)
        register_vector(conn)
        try:
            yield conn
        finally:
            conn.close()
        return

    pool = get_pool()
    with pool.connection() as conn:
        conn.autocommit = autocommit
        yield conn


@contextmanager
def get_cursor(conn: psycopg.Connection) -> Iterator[psycopg.Cursor]:
    with conn.cursor() as cur:
        yield cur
