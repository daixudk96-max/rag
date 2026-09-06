"""Custom exceptions for the vector backend layer.

Provides structured error handling for:
- VectorBackend operations (connection errors, timeouts, malformed data)
- VectorLoader operations (embedding failures, projection failures)
"""
from __future__ import annotations


class VectorBackendError(Exception):
    """Base exception for vector backend operations.

    Raised when:
    - Qdrant or Milvus client connection fails
    - Qdrant or Milvus client operations timeout
    - Vector backend operations fail (upsert, search, delete)
    - Malformed data returned from the vector backend (e.g., invalid UUID)
    """
    pass


class VectorLoaderError(Exception):
    """Base exception for VectorLoader operations.

    Raised when:
    - Embedding generation fails
    - Vector projection to backend fails
    - Database operations fail during vector loading
    """
    pass