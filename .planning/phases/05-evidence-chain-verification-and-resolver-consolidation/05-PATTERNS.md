# Phase 5: Evidence-Chain Verification and Resolver Consolidation - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 10 new/modified files
**Analogs found:** 10 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `llamaindex_runtime/tree/evidence_content_resolver.py` | utility | CRUD (registry queries) | `llamaindex_runtime/tree/reasoning_backend.py` lines 287-376 + `llamaindex_runtime/tree/pageindex_adapter.py` lines 176-249 | exact (duplicate extraction) |
| `verification/phase5-evidence-chain-verification/verify_active_version_counts.py` | verification/utility | request-response (DB queries) | `verification/phase3-real-validation/run_validation.py` lines 94-143 | role-match (replace global COUNT with version-scoped) |
| `verification/phase5-evidence-chain-verification/verify_heading_path_contract.py` | verification/utility | request-response (provenance check) | `tests/llamaindex_runtime/test_evidence_chain_completeness.py` lines 54-100 | role-match (similar fixture structure) |
| `verification/phase5-evidence-chain-verification/invoke_vector_loader.py` | verification/utility | request-response (orchestration) | `llamaindex_runtime/vector/loader.py` lines 84-149 | exact (same VectorLoader invocation) |
| `verification/phase5-evidence-chain-verification/validation_integrity_gate.py` | verification/utility | request-response (gate check) | `tests/llamaindex_runtime/test_evidence_chain_completeness.py` lines 24-28 (thresholds) | role-match |
| `tests/llamaindex_runtime/test_vector_loader.py` | test | request-response | `tests/llamaindex_runtime/test_vector_persistence.py` | role-match |
| `tests/verification/test_validation_integrity.py` | test | request-response | `tests/llamaindex_runtime/test_evidence_chain_completeness.py` | role-match |
| `tests/llamaindex_runtime/test_evidence_content_resolver.py` | test | request-response | `tests/llamaindex_runtime/test_query_quality_validation.py` lines 54-69 (mock registry pattern) | role-match |
| `llamaindex_runtime/tree/reasoning_backend.py` (modify) | service | request-response (LLM navigation) | `llamaindex_runtime/tree/reasoning_backend.py` (self - refactor target) | exact (refactor, preserve contract) |
| `llamaindex_runtime/tree/pageindex_adapter.py` (modify) | service | request-response (tree building) | `llamaindex_runtime/tree/pageindex_adapter.py` (self - refactor target) | exact (refactor, preserve contract) |

---

## Pattern Assignments

### `llamaindex_runtime/tree/evidence_content_resolver.py` (utility, CRUD)

**Analog:** `llamaindex_runtime/tree/reasoning_backend.py` lines 287-376 (duplicate logic to extract) + `llamaindex_runtime/tree/pageindex_adapter.py` lines 176-249

**Imports pattern** (from reasoning_backend.py lines 1-21):
```python
from __future__ import annotations

import json
import re
from typing import Any, Sequence
from uuid import UUID

from llamaindex_runtime.tree.backend_adapter import BackendHit
```

**Core pattern - fallback cascade** (from reasoning_backend.py lines 287-304):
```python
def build_text_preview(
    self,
    *,
    registry: Any,
    version_id: UUID,
    node_id: UUID,
    span_ids: Sequence[UUID],
    fallback_text: str,
) -> str:
    """Canonical fallback cascade: spans -> chunks -> summary."""
    # 1. Try canonical_spans.raw_text (authoritative content)
    span_text = self._text_preview_from_spans(registry, version_id, span_ids)
    if span_text:
        return span_text

    # 2. Fallback to vector_chunks.text_preview (chunk-level evidence)
    chunk_text = self._text_preview_from_chunks(registry, version_id, node_id, span_ids)
    if chunk_text:
        return chunk_text

    # 3. Final fallback to summary_text/title (heading-based summary)
    return self._normalize_preview_text(fallback_text)
```

**Spans query pattern** (from reasoning_backend.py lines 306-325):
```python
def _text_preview_from_spans(
    self, registry: Any, version_id: UUID, span_ids: Sequence[UUID]
) -> str:
    if not span_ids:
        return ""

    try:
        spans = registry.query_spans_by_version(version_id)
    except Exception:
        return ""

    span_order = {span_id: index for index, span_id in enumerate(span_ids)}
    selected = []
    for span in spans:
        span_id = self._coerce_uuid(span.get("span_id"))
        if span_id in span_order:
            selected.append((span_order[span_id], span.get("raw_text") or ""))

    selected.sort(key=lambda item: item[0])
    return self._normalize_preview_text(" ".join(text for _, text in selected))
```

**Chunks query pattern** (from reasoning_backend.py lines 327-350):
```python
def _text_preview_from_chunks(
    self,
    registry: Any,
    version_id: UUID,
    node_id: UUID,
    span_ids: Sequence[UUID],
) -> str:
    try:
        chunks = registry.query_vector_chunks_by_version(version_id)
    except Exception:
        chunks = []

    if not chunks:
        return ""

    chunk_ids = self._chunk_ids_for_span_ids(registry, version_id, span_ids)
    selected = []
    for chunk in chunks:
        chunk_id = self._coerce_uuid(chunk.get("chunk_id"))
        chunk_node_id = self._coerce_uuid(chunk.get("node_id"))
        if chunk_id in chunk_ids or chunk_node_id == node_id:
            selected.append(chunk.get("text_preview") or "")

    return self._normalize_preview_text(" ".join(selected))
```

**Normalize pattern** (from reasoning_backend.py lines 372-376):
```python
def _normalize_preview_text(self, text: str, max_length: int = 1600) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"
```

**UUID coercion pattern** (from reasoning_backend.py lines 714-723):
```python
def _coerce_uuid(self, value: Any) -> UUID | None:
    """Return a UUID from either a UUID object or string value."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None
```

---

### `verification/phase5-evidence-chain-verification/verify_active_version_counts.py` (verification/utility, request-response)

**Analog:** `verification/phase3-real-validation/run_validation.py` lines 94-143 (replace global COUNT with version-scoped registry query)

**Imports pattern**:
```python
import json
import uuid
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
```

**Version-scoped DB count pattern** (use registry methods, NOT global COUNT):
```python
# BAD: Global query (can mix multiple versions' data)
# cur.execute("SELECT COUNT(*) FROM vector_chunks")
# chunk_count = cur.fetchone()["count"]

# GOOD: Version-scoped query via registry
active_version_id = resolve_active_version_id(conn)
registry = PostgresRegistryWriter(conn)

chunks = registry.query_vector_chunks_by_version(active_version_id)
chunk_count = len(chunks)

# Compute mapped_chunks rate (version-scoped)
mapped_chunks = sum(1 for c in chunks if c.get("node_id") is not None)
mapped_chunks_rate = mapped_chunks / chunk_count if chunk_count > 0 else 0.0

# Compute heading_path completeness from authoritative source (canonical_spans)
spans = registry.query_spans_by_version(active_version_id)
heading_path_complete = sum(1 for s in spans if s.get("heading_path") is not None)
heading_path_rate = heading_path_complete / len(spans) if spans else 0.0
```

---

### `verification/phase5-evidence-chain-verification/verify_heading_path_contract.py` (verification/utility, request-response)

**Analog:** `tests/llamaindex_runtime/test_evidence_chain_completeness.py` lines 54-100

**Fixture structure pattern**:
```python
def _build_heading_path_fixture(version_id: uuid.UUID) -> dict[str, list[dict]]:
    """Build fixture demonstrating heading_path provenance contract."""
    spans = [
        {
            "span_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1",  # Authoritative source
        },
    ]
    
    nodes = [
        {
            "node_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1/## Section 1.1",  # Derived (PageIndex adapter)
        },
    ]
    
    chunks = [
        {
            "chunk_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1",  # Derived (copied from span)
        },
    ]
    
    return {"spans": spans, "nodes": nodes, "chunks": chunks}
```

**Provenance check pattern**:
```python
# Validation MUST check canonical_spans.heading_path (authoritative)
spans = registry.query_spans_by_version(version_id)
heading_path_complete = sum(1 for s in spans if s.get("heading_path") is not None)
heading_path_rate = heading_path_complete / len(spans) if spans else 0.0

# DO NOT check tree_nodes or vector_chunks for heading_path completeness
# tree_nodes.heading_path is derived (PageIndex adapter computation)
# vector_chunks.heading_path is copied from spans (chunker)
```

---

### `verification/phase5-evidence-chain-verification/invoke_vector_loader.py` (verification/utility, request-response)

**Analog:** `llamaindex_runtime/vector/loader.py` lines 84-149

**Imports pattern**:
```python
import uuid
import psycopg

from llamaindex_runtime.vector.loader import VectorLoader
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
```

**VectorLoader invocation pattern** (lines 84-121):
```python
def verify_and_invoke_vector_loader(
    conn: psycopg.Connection, version_id: uuid.UUID
) -> dict[str, Any]:
    """Verify chunks status and invoke VectorLoader if missing.
    
    VectorLoader.load() has built-in idempotency:
    - If chunks already exist, repairs missing embeddings/node_id
    - If chunks missing, runs full pipeline (generate, persist, embed, link)
    """
    loader = VectorLoader(embed_dim=16)  # Use DeterministicEmbedder for verification
    
    # Idempotent: safe to re-invoke
    result = loader.load(conn, version_id=version_id)
    
    # Returns: {"chunk_ids": [...], "count": N}
    # Handles partial state: repairs missing embeddings, node_id
    return result
```

---

### `verification/phase5-evidence-chain-verification/validation_integrity_gate.py` (verification/utility, request-response)

**Analog:** `tests/llamaindex_runtime/test_evidence_chain_completeness.py` lines 24-28 (thresholds)

**Threshold constants pattern**:
```python
# Thresholds (from Phase 2 research, frozen)

MIN_NODE_CHUNK_MAPPING_RATE = 0.80  # 80% of chunks must have node_id
MIN_HEADING_PATH_COMPLETENESS = 0.95  # 95% of spans must have heading_path
```

**Gate check pattern**:
```python
def validation_integrity_gate(
    conn: psycopg.Connection,
    version_id: uuid.UUID,
    judgment_corpus: list[dict[str, Any]],
    retrieval_corpus: dict[str, Any],
) -> dict[str, Any]:
    """Gate check before human judgment collection.
    
    Checks:
    1. Evidence-chain thresholds (node_chunk_mapping >= 80%, heading_path >= 95%)
    2. Corpus integrity (retrieval corpus matches judgment corpus)
    
    Returns: {"passed": bool, "reasons": list[str]}
    """
    registry = PostgresRegistryWriter(conn)
    
    # Check evidence-chain thresholds
    chunks = registry.query_vector_chunks_by_version(version_id)
    mapped_chunks = sum(1 for c in chunks if c.get("node_id") is not None)
    node_chunk_mapping_rate = mapped_chunks / len(chunks) if chunks else 0.0
    
    spans = registry.query_spans_by_version(version_id)
    heading_path_complete = sum(1 for s in spans if s.get("heading_path") is not None)
    heading_path_rate = heading_path_complete / len(spans) if spans else 0.0
    
    passed = (
        node_chunk_mapping_rate >= MIN_NODE_CHUNK_MAPPING_RATE
        and heading_path_rate >= MIN_HEADING_PATH_COMPLETENESS
    )
    
    reasons = []
    if node_chunk_mapping_rate < MIN_NODE_CHUNK_MAPPING_RATE:
        reasons.append(
            f"node_chunk_mapping {node_chunk_mapping_rate:.0%} < {MIN_NODE_CHUNK_MAPPING_RATE:.0%}"
        )
    if heading_path_rate < MIN_HEADING_PATH_COMPLETENESS:
        reasons.append(
            f"heading_path {heading_path_rate:.2%} < {MIN_HEADING_PATH_COMPLETENESS:.0%}"
        )
    
    # Corpus integrity check (Phase 4 judgment integrity issue)
    # retrieval_corpus must match judgment_corpus
    # ... implementation details
    
    return {"passed": passed, "reasons": reasons}
```

---

### `tests/llamaindex_runtime/test_vector_loader.py` (test, request-response)

**Analog:** `tests/llamaindex_runtime/test_vector_persistence.py`

**Test structure pattern**:
```python
"""VectorLoader idempotent invocation tests."""

import uuid
from unittest.mock import MagicMock, patch
import pytest

from llamaindex_runtime.vector.loader import VectorLoader


@pytest.fixture
def mock_connection():
    """Mock psycopg connection."""
    return MagicMock()


@pytest.fixture
def sample_version_id():
    """Sample version UUID."""
    return uuid.uuid4()


def test_vector_loader_idempotent_re_invoke(mock_connection, sample_version_id):
    """Test VectorLoader handles partial state (missing embeddings/node_id)."""
    loader = VectorLoader(embed_dim=16)
    
    # First invocation: creates chunks
    result1 = loader.load(mock_connection, sample_version_id)
    
    # Second invocation: repairs missing state (idempotent)
    result2 = loader.load(mock_connection, sample_version_id)
    
    # Both should return same chunk_ids
    assert result1["chunk_ids"] == result2["chunk_ids"]
```

---

### `tests/verification/test_validation_integrity.py` (test, request-response)

**Analog:** `tests/llamaindex_runtime/test_evidence_chain_completeness.py`

**Test structure pattern**:
```python
"""Validation integrity gate tests."""

import uuid
from unittest.mock import MagicMock
import pytest

from verification.phase5_evidence_chain_verification.validation_integrity_gate import (
    validation_integrity_gate,
    MIN_NODE_CHUNK_MAPPING_RATE,
    MIN_HEADING_PATH_COMPLETENESS,
)


def test_corpus_mismatch_blocks_judgment_collection():
    """Test corpus integrity gate detects mismatch."""
    version_id = uuid.uuid4()
    mock_conn = MagicMock()
    mock_registry = MagicMock()
    
    # Setup: retrieval corpus != judgment corpus
    judgment_corpus = [{"hit_id": 1, "doc": "doc1"}]
    retrieval_corpus = {"doc_path": "doc2"}
    
    # ... implementation
```

---

### `tests/llamaindex_runtime/test_evidence_content_resolver.py` (test, request-response)

**Analog:** `tests/llamaindex_runtime/test_query_quality_validation.py` lines 54-69 (mock registry pattern)

**Test structure pattern**:
```python
"""EvidenceContentResolver tests."""

import uuid
from unittest.mock import MagicMock
import pytest

from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver


def _make_mock_registry(
    version_id: uuid.UUID,
    spans: list[dict] | None = None,
    chunks: list[dict] | None = None,
    chunk_spans: list[dict] | None = None,
):
    """Create mock registry with evidence-chain data."""
    registry = MagicMock()
    registry.query_spans_by_version = MagicMock(return_value=spans or [])
    registry.query_vector_chunks_by_version = MagicMock(return_value=chunks or [])
    registry.query_vector_chunk_spans_by_version = MagicMock(return_value=chunk_spans or [])
    return registry


def test_resolver_fallback_cascade_span_to_chunk_to_summary():
    """Test fallback cascade: spans -> chunks -> summary."""
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    span_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    
    spans = [
        {"span_id": span_id, "version_id": version_id, "raw_text": "Span content"},
    ]
    chunks = [
        {"chunk_id": chunk_id, "version_id": version_id, "node_id": node_id, "text_preview": "Chunk content"},
    ]
    
    registry = _make_mock_registry(version_id, spans=spans, chunks=chunks)
    resolver = EvidenceContentResolver()
    
    # Test span fallback
    preview = resolver.build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[span_id],
        fallback_text="Fallback",
    )
    assert "Span content" in preview
    
    # Test chunk fallback (no spans)
    preview = resolver.build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[],
        fallback_text="Fallback",
    )
    assert "Chunk content" in preview
```

---

### `llamaindex_runtime/tree/reasoning_backend.py` (modify) - refactor to use EvidenceContentResolver

**Analog:** Self (refactor target, preserve contract)

**Modification pattern**:
```python
# Replace lines 287-376 with:
from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver

class ReasoningTreeBackend(TreeBackendAdapter):
    def __init__(self, ..., resolver: EvidenceContentResolver | None = None) -> None:
        self._resolver = resolver or EvidenceContentResolver()
    
    def _build_text_preview_for_node(
        self,
        *,
        registry: Any,
        version_id: UUID,
        node_id: UUID,
        span_ids: Sequence[UUID],
        fallback_text: str,
    ) -> str:
        """Delegate to shared resolver."""
        return self._resolver.build_text_preview(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
            fallback_text=fallback_text,
        )
    
    # Remove duplicate helper methods:
    # - _text_preview_from_spans (moved to resolver)
    # - _text_preview_from_chunks (moved to resolver)
    # - _normalize_preview_text (moved to resolver)
    # - _chunk_ids_for_span_ids (moved to resolver)
```

---

### `llamaindex_runtime/tree/pageindex_adapter.py` (modify) - refactor to use EvidenceContentResolver

**Analog:** Self (refactor target, preserve contract)

**Modification pattern**:
```python
# Replace lines 176-248 with:
from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver

class PageIndexTreeAdapter:
    def __init__(self, ..., resolver: EvidenceContentResolver | None = None) -> None:
        self._resolver = resolver or EvidenceContentResolver()
    
    def _build_text_preview(
        self,
        *,
        registry: Any,
        version_id: UUID,
        node_id: UUID,
        chunk_id: UUID,
        span_ids: Sequence[UUID],
        fallback_text: str,
    ) -> str:
        """Delegate to shared resolver."""
        return self._resolver.build_text_preview(
            registry=registry,
            version_id=version_id,
            node_id=node_id,
            span_ids=span_ids,
            fallback_text=fallback_text,
        )
    
    # Remove duplicate helper methods:
    # - _text_preview_from_spans (moved to resolver)
    # - _text_preview_from_chunks (moved to resolver)
    # - _normalize_preview_text (moved to resolver)
```

---

## Shared Patterns

### Registry Version-Scoped Queries

**Source:** `llamaindex_runtime/registry/postgres_adapter.py` lines 705-723, 344-358, 532-550

**Apply to:** All verification scripts using registry queries

```python
# Pattern: Version-scoped queries prevent version mixing
registry = PostgresRegistryWriter(conn)

# Query chunks for specific version
chunks = registry.query_vector_chunks_by_version(version_id)

# Query spans for specific version (heading_path authoritative source)
spans = registry.query_spans_by_version(version_id)

# Query node-span mappings for specific version
node_spans = registry.query_tree_node_spans_by_version(version_id)

# All queries are version-scoped, preventing global COUNT(*) mixing multiple versions
```

---

### Evidence-Chain Thresholds

**Source:** `tests/llamaindex_runtime/test_evidence_chain_completeness.py` lines 24-28

**Apply to:** All validation integrity gates

```python
# Thresholds (from Phase 2 research, frozen)

MIN_NODE_CHUNK_MAPPING_RATE = 0.80  # 80% of chunks must have node_id
MIN_HEADING_PATH_COMPLETENESS = 0.95  # 95% of spans must have heading_path
```

---

### UUID Coercion Pattern

**Source:** `llamaindex_runtime/tree/reasoning_backend.py` lines 714-723

**Apply to:** All files handling UUID conversion from registry data

```python
def _coerce_uuid(value: Any) -> UUID | None:
    """Return a UUID from either a UUID object or string value."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None
```

---

## No Analog Found

All 10 files have analogs found in the codebase. Wave 0 test files can follow existing test patterns.

---

## Metadata

**Analog search scope:**
- `llamaindex_runtime/tree/*.py`
- `llamaindex_runtime/registry/postgres_adapter.py`
- `llamaindex_runtime/vector/loader.py`
- `verification/phase3-real-validation/*.py`
- `tests/llamaindex_runtime/test_evidence_chain_completeness.py`
- `tests/llamaindex_runtime/test_query_quality_validation.py`

**Files scanned:** 15+ files
**Pattern extraction date:** 2026-06-07

**Key patterns identified:**
1. **Evidence-content fallback cascade**: spans -> chunks -> summary (duplicated in 2 backends)
2. **Version-scoped registry queries**: prevent global COUNT version mixing
3. **Heading_path provenance contract**: canonical_spans authoritative, nodes/chunks derived
4. **VectorLoader idempotent invocation**: repairs partial state
5. **Threshold constants**: frozen from Phase 2 (0.80, 0.95)
6. **Mock registry pattern**: for unit tests