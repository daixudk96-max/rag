from __future__ import annotations

import os
from pathlib import Path
from time import sleep

import psycopg
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "llamaindex_runtime" / "registry" / "migrations"


@pytest.fixture(scope="session")
def live_db_url() -> str:
    live_database_url = os.getenv("FORMAL_RUNTIME_DATABASE_URL")
    if not live_database_url:
        pytest.skip("FORMAL_RUNTIME_DATABASE_URL is required for live PostgreSQL tests")
    return live_database_url


@pytest.fixture(scope="session")
def live_db_connection(live_db_url: str):
    deadline_reached = False
    last_error: Exception | None = None
    for _ in range(10):
        try:
            conn = psycopg.connect(live_db_url, autocommit=True, connect_timeout=2)
            break
        except Exception as exc:  # pragma: no cover - readiness loop
            last_error = exc
            sleep(1)
    else:
        deadline_reached = True

    if deadline_reached:
        pytest.skip(f"Live PostgreSQL not available at {live_db_url}: {last_error}")

    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def live_applied_schema(live_db_connection):
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with live_db_connection.cursor() as cur:
        for migration_file in migration_files:
            cur.execute(migration_file.read_text(encoding="utf-8"))
    return True


@pytest.fixture
def clean_live_db(live_db_connection, live_applied_schema):
    with live_db_connection.cursor() as cur:
        cur.execute(
            "TRUNCATE TABLE node_entity_links, chunk_entity_links, evidence_links, evidence, relations, entities, tree_node_spans, summaries, tree_nodes, vector_chunk_spans, vector_chunks, canonical_spans, document_versions, normalization_contracts, documents CASCADE"
        )
    yield
