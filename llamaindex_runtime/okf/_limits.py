"""Shared bounded-byte limits for raw OKF document payloads."""

from __future__ import annotations

MAX_DOCUMENT_BYTES = 64 * 1024 * 1024


def document_size_exceeds_limit(size: int) -> bool:
    """Return whether a document byte count exceeds the shared reader limit."""
    return size > MAX_DOCUMENT_BYTES
