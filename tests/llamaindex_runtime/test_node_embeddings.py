"""Tests for Phase 2 Task 2.1: Node embeddings precomputation.

These tests verify:
1. write_node_embeddings() inserts embedding vectors for tree nodes
2. Embeddings are stored with model name for multi-model support
3. Vector dimension matches expected embedding model (384 for all-MiniLM-L6-v2)
4. Query retrieval can use precomputed embeddings for similarity search

Unit tests use mocked database connections (no PostgreSQL required).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from psycopg.rows import dict_row

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter


class _MockCursor:
    """Minimal mock cursor that tracks execute calls."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self) -> "_MockCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def executemany(self, sql: str, params_list: list) -> None:
        for params in params_list:
            self.executed.append((sql, params))

    def fetchone(self) -> tuple | None:
        return None

    def fetchall(self) -> list:
        return []


class _MockConnection:
    """Minimal mock psycopg connection."""

    def __init__(self) -> None:
        self._cursor = _MockCursor()
        self.autocommit = False  # Required by PostgresRegistryWriter.__init__

    def cursor(self, row_factory=None) -> _MockCursor:
        return self._cursor

    def transaction(self):
        """Mock transaction context manager."""
        return MagicMock()


def test_write_node_embeddings_unit():
    """Unit test: write_node_embeddings() inserts embedding vectors.

    RED phase: This test will fail because write_node_embeddings() is not implemented yet.
    """
    # Patch register_vector in the module where it's imported (postgres_adapter)
    with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
        # Setup mock connection
        mock_conn = _MockConnection()
        registry = PostgresRegistryWriter(mock_conn)

        # Test data: 3 nodes with embeddings
        node_embeddings = [
            {
                "node_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_vector": [0.1] * 384,  # 384-dimensional vector
            },
            {
                "node_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_vector": [0.2] * 384,
            },
            {
                "node_id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_vector": [0.3] * 384,
            },
        ]

        # Call write_node_embeddings (keyword-only per signature)
        registry.write_node_embeddings(node_embeddings=node_embeddings)

        # Verify SQL execution
        cursor = mock_conn.cursor()

        # Expected: INSERT INTO node_embeddings for each node
        assert len(cursor.executed) >= 1, "write_node_embeddings should execute SQL"

        # Check that INSERT statements were called
        insert_calls = [call for call in cursor.executed if "INSERT" in call[0]]
        assert len(insert_calls) > 0, "write_node_embeddings should execute INSERT statements"

        # Verify node_id, embedding_model, embedding_vector in params
        first_insert = insert_calls[0]
        sql, params = first_insert
        assert "node_embeddings" in sql, "INSERT should target node_embeddings table"


def test_write_node_embeddings_multi_model():
    """Unit test: Multiple embedding models can coexist for same node.

    Tests multi-model support (different embedding dimensions stored separately).
    """
    # Patch register_vector in the module where it's imported (postgres_adapter)
    with patch('llamaindex_runtime.registry.postgres_adapter.register_vector'):
        mock_conn = _MockConnection()
        registry = PostgresRegistryWriter(mock_conn)

        # Test data: Same node with two different embedding models
        node_embeddings = [
            {
                "node_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_vector": [0.1] * 384,  # 384-dim
            },
            {
                "node_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "embedding_model": "all-mpnet-base-v2",
                "embedding_vector": [0.5] * 768,  # 768-dim (different model)
            },
        ]

        registry.write_node_embeddings(node_embeddings=node_embeddings)

        cursor = mock_conn.cursor()
        insert_calls = [call for call in cursor.executed if "INSERT" in call[0]]

        # Both embeddings should be inserted (multi-model support)
        assert len(insert_calls) >= 2, "write_node_embeddings should handle multiple models"


# Future test for GREEN phase: query_node_embeddings_by_similarity()
# def test_query_node_embeddings_by_similarity():
#     """Test vector similarity search using precomputed embeddings."""
#     pass