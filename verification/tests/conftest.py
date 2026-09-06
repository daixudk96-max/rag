from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "src" / "registry" / "migrations"
DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/rag_registry",
)
os.environ.setdefault("DATABASE_URL", DEFAULT_DATABASE_URL)
@pytest.fixture(scope="session")
def db_url() -> str:
    return DEFAULT_DATABASE_URL


@pytest.fixture(scope="session")
def db_connection(db_url: str):
    try:
        conn = psycopg.connect(db_url, autocommit=True, connect_timeout=2)
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def applied_schema(db_connection):
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with db_connection.cursor() as cur:
        for migration_file in migration_files:
            sql = migration_file.read_text(encoding="utf-8")
            cur.execute(sql)
    return True


@pytest.fixture(autouse=True)
def clean_db(db_connection, applied_schema):
    with db_connection.cursor() as cur:
        cur.execute(
            "TRUNCATE TABLE tree_node_spans, tree_nodes, evidence_links, relations, entities, vector_chunk_spans, vector_chunks, canonical_spans, document_versions, normalization_contracts, documents RESTART IDENTITY CASCADE"
        )
    yield
