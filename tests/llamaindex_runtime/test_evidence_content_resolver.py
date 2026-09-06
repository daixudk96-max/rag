from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from llamaindex_runtime.tree.evidence_content_resolver import EvidenceContentResolver


def test_resolver_prefers_canonical_span_raw_text() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    span_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_spans_by_version.return_value = [
        {"span_id": span_id, "raw_text": "real canonical body"}
    ]
    registry.query_vector_chunks_by_version.return_value = []

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[span_id],
        fallback_text="fallback summary",
    )

    assert preview == "real canonical body"


def test_resolver_uses_chunk_text_when_span_text_empty() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    span_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_spans_by_version.return_value = [
        {"span_id": span_id, "raw_text": ""}
    ]
    registry.query_vector_chunk_spans_by_version.return_value = [
        {"chunk_id": chunk_id, "span_id": span_id}
    ]
    registry.query_vector_chunks_by_version.return_value = [
        {"chunk_id": chunk_id, "node_id": node_id, "text_preview": "chunk body"}
    ]

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[span_id],
        fallback_text="fallback summary",
    )

    assert preview == "chunk body"


def test_resolver_matches_chunk_by_explicit_chunk_id() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_vector_chunk_spans_by_version.return_value = []
    registry.query_vector_chunks_by_version.return_value = [
        {"chunk_id": chunk_id, "node_id": uuid.uuid4(), "text_preview": "explicit chunk"}
    ]

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[],
        fallback_text="fallback summary",
        chunk_id=chunk_id,
    )

    assert preview == "explicit chunk"


def test_resolver_falls_back_to_summary_when_evidence_missing() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_spans_by_version.return_value = []
    registry.query_vector_chunk_spans_by_version.return_value = []
    registry.query_vector_chunks_by_version.return_value = []

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[],
        fallback_text="  fallback   summary  ",
    )

    assert preview == "fallback summary"


def test_resolver_truncates_long_preview_to_1600_chars() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    span_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_spans_by_version.return_value = [
        {"span_id": span_id, "raw_text": "x" * 1700}
    ]

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[span_id],
        fallback_text="fallback summary",
    )

    assert preview.endswith("…")
    assert len(preview) <= 1600


def test_resolver_handles_missing_registry_methods() -> None:
    version_id = uuid.uuid4()
    node_id = uuid.uuid4()
    span_id = uuid.uuid4()
    registry = MagicMock()
    registry.query_spans_by_version.side_effect = AttributeError("missing spans")
    registry.query_vector_chunk_spans_by_version.side_effect = Exception("missing mappings")
    registry.query_vector_chunks_by_version.side_effect = AttributeError("missing chunks")

    preview = EvidenceContentResolver().build_text_preview(
        registry=registry,
        version_id=version_id,
        node_id=node_id,
        span_ids=[span_id],
        fallback_text="fallback summary",
    )

    assert preview == "fallback summary"
