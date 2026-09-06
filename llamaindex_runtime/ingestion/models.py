from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from llamaindex_runtime.interfaces import CanonicalSpan


@dataclass(frozen=True)
class IngestResult:
    doc_id: UUID
    version_id: UUID
    source_uri: str
    spans: tuple[CanonicalSpan, ...]
    dropped_nodes: int = 0
    reconciliation_result: Any | None = None
