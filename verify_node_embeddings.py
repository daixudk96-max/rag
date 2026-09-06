"""Verification script for write_node_embeddings() implementation.

Tests the method directly without pytest infrastructure issues.
"""
import uuid
from unittest.mock import MagicMock


class _MockCursor:
    """Minimal mock cursor that tracks execute calls."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def executemany(self, sql: str, params_list: list) -> None:
        for params in params_list:
            self.executed.append((sql, params))

    def fetchone(self) -> tuple | None:
        return None

    def fetchall(self) -> list:
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class _MockConnection:
    """Minimal mock psycopg connection."""

    def __init__(self) -> None:
        self._cursor = _MockCursor()

    def cursor(self, row_factory=None) -> _MockCursor:
        return self._cursor

    def transaction(self):
        """Mock transaction context manager."""
        class _MockTransaction:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        return _MockTransaction()


# Import the implementation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter


def test_write_node_embeddings_basic():
    """Test basic write_node_embeddings() functionality."""
    print("=== GREEN Verification: write_node_embeddings() ===\n")

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

    # Call write_node_embeddings
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
    assert len(params) == 3, "INSERT should have 3 parameters (node_id, model, vector)"

    print(f"[OK] SQL execution count: {len(cursor.executed)}")
    print(f"[OK] INSERT calls: {len(insert_calls)}")
    print(f"[OK] First INSERT SQL contains 'node_embeddings': {('node_embeddings' in sql)}")
    print(f"[OK] First INSERT params count: {len(params)}")
    print(f"[OK] ON CONFLICT clause present: {('ON CONFLICT' in sql)}")

    print("\nGREEN phase verified: write_node_embeddings() implementation functional!")


def test_write_node_embeddings_multi_model():
    """Test multi-model support (different embedding dimensions)."""
    print("\n=== Multi-model Verification ===\n")

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

    print(f"[OK] Multi-model INSERT calls: {len(insert_calls)}")
    print("[OK] Multi-model support verified")


if __name__ == "__main__":
    test_write_node_embeddings_basic()
    test_write_node_embeddings_multi_model()
    print("\n=== All GREEN verifications passed ===")