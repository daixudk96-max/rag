"""Shared data types for the unified query entrypoint.

QueryHit and QueryResult are defined here to avoid circular imports
between the entrypoint and the keyword/vector/tree retrieval modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Mapping


@dataclass(frozen=True)
class QueryHit:
    """Structured evidence hit from a retrieval backend.

    Fields
    ------
    text:
        The text content of the retrieved node.
    score:
        Similarity score from the retrieval backend, or ``None`` if
        the backend did not assign a score.
    metadata:
        Arbitrary key-value metadata attached to the source node.
    """

    text: str
    score: float | None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class QueryResult:
    """Immutable result from a unified query call."""

    mode: Literal["vector", "tree", "keyword", "hybrid"]
    hits: tuple[QueryHit, ...]
    source_path: str
    query: str

    _VALID_MODES: ClassVar[frozenset[str]] = frozenset({"vector", "tree", "keyword", "hybrid"})

    def __post_init__(self) -> None:
        if self.mode not in self._VALID_MODES:
            raise ValueError(
                f"mode must be one of {sorted(self._VALID_MODES)}, got {self.mode!r}"
            )
