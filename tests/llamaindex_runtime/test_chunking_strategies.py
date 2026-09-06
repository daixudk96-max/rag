"""Tests for P5 chunking strategies -- heading-grouped and pluggable chunker selection.

These tests verify:
1. HeadingGroupedChunker groups spans under the same heading_path into semantic chunks
2. HeadingGroupedChunker preserves provenance (span_ids) for each chunk
3. HeadingGroupedChunker handles edge cases (empty, null heading_path, mixed)
4. Chunker selection is pluggable via VectorLoader
5. Both chunkers maintain canonical spans as the source backbone

TDD workflow:
1. Write failing tests (RED)
2. Verify they fail for expected reasons
3. Implement minimum production code to pass (GREEN)
4. Verify tests pass
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from okf._e2a_pipeline_testkit import _FakeReconciler


def _make_span_dict(
    *,
    span_id: uuid.UUID | None = None,
    version_id: uuid.UUID,
    heading_path: str | None = None,
    page_no: int | None = 1,
    text: str = "sample text",
    offset: int = 0,
) -> dict[str, Any]:
    """Create a span dict matching the shape returned by query_spans_by_version."""
    return {
        "span_id": span_id or uuid.uuid4(),
        "version_id": version_id,
        "span_kind": "paragraph",
        "start_offset": offset,
        "end_offset": offset + len(text),
        "page_no": page_no,
        "heading_path": heading_path,
        "raw_text": text,
    }


# ===========================================================================
# UNIT TESTS -- HeadingGroupedChunker (no database required)
# ===========================================================================


class TestHeadingGroupedChunkerBasic:
    """Core chunker behavior: group spans by heading_path, preserve provenance."""

    def test_groups_spans_with_same_heading_into_one_chunk(self) -> None:
        """Spans under the same heading_path must be grouped into one chunk."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        heading = "Chapter 1 > 1.1 Introduction"
        spans = [
            _make_span_dict(version_id=version_id, text="First para", heading_path=heading, offset=0),
            _make_span_dict(version_id=version_id, text="Second para", heading_path=heading, offset=100),
            _make_span_dict(version_id=version_id, text="Third para", heading_path=heading, offset=200),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        assert len(chunks) == 1, "All spans with same heading must be in one chunk"
        assert len(chunks[0]["span_ids"]) == 3, "Chunk must reference all three spans"
        # Text preview should concatenate span texts
        assert "First para" in chunks[0]["text_preview"]
        assert "Second para" in chunks[0]["text_preview"]
        assert "Third para" in chunks[0]["text_preview"]

    def test_groups_spans_by_different_headings(self) -> None:
        """Spans under different headings must be in separate chunks."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="Intro", heading_path="Ch 1", offset=0),
            _make_span_dict(version_id=version_id, text="Methods", heading_path="Ch 2", offset=100),
            _make_span_dict(version_id=version_id, text="Results", heading_path="Ch 3", offset=200),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        assert len(chunks) == 3, "Different headings must produce separate chunks"
        assert chunks[0]["heading_path"] == "Ch 1"
        assert chunks[1]["heading_path"] == "Ch 2"
        assert chunks[2]["heading_path"] == "Ch 3"

    def test_chunk_id_is_deterministic(self) -> None:
        """Heading-grouped chunk IDs must be deterministic based on heading_path."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        heading = "Section A"
        spans = [
            _make_span_dict(version_id=version_id, text="Para 1", heading_path=heading),
        ]
        chunker = HeadingGroupedChunker()
        chunks1 = chunker.generate(spans, version_id=version_id)
        chunks2 = chunker.generate(spans, version_id=version_id)

        assert chunks1[0]["chunk_id"] == chunks2[0]["chunk_id"], (
            "HeadingGrouped chunk_id must be deterministic (uuid5 based on heading)"
        )

    def test_preserves_provenance_with_multiple_span_ids(self) -> None:
        """Each grouped chunk must have span_ids referencing all source spans."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="A", heading_path="H1"),
            _make_span_dict(version_id=version_id, text="B", heading_path="H1"),
            _make_span_dict(version_id=version_id, text="C", heading_path="H2"),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        # First chunk (H1) should reference spans A and B
        assert len(chunks[0]["span_ids"]) == 2
        assert spans[0]["span_id"] in chunks[0]["span_ids"]
        assert spans[1]["span_id"] in chunks[0]["span_ids"]

        # Second chunk (H2) should reference span C
        assert len(chunks[1]["span_ids"]) == 1
        assert spans[2]["span_id"] in chunks[1]["span_ids"]

    def test_empty_spans_returns_empty(self) -> None:
        """Empty span list must return empty chunk list."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate([], version_id=version_id)
        assert chunks == []

    def test_missing_span_id_rejected(self) -> None:
        """Malformed span missing span_id should fail fast with clear error."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [{
            "version_id": version_id,
            "raw_text": "text",
            "heading_path": "H",
            "start_offset": 0,
        }]
        chunker = HeadingGroupedChunker()
        with pytest.raises(ValueError, match="span_id"):
            chunker.generate(spans, version_id=version_id)

    def test_missing_start_offset_rejected(self) -> None:
        """Malformed span missing start_offset should fail fast with clear error."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [{
            "span_id": uuid.uuid4(),
            "version_id": version_id,
            "raw_text": "text",
            "heading_path": "H",
        }]
        chunker = HeadingGroupedChunker()
        with pytest.raises(ValueError, match="start_offset"):
            chunker.generate(spans, version_id=version_id)

    def test_null_heading_path_creates_separate_chunks(self) -> None:
        """Spans with NULL heading_path must each be their own chunk."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="Orphan 1", heading_path=None),
            _make_span_dict(version_id=version_id, text="Orphan 2", heading_path=None),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        # Each NULL heading span becomes its own chunk (fallback to 1:1)
        assert len(chunks) == 2
        assert len(chunks[0]["span_ids"]) == 1
        assert len(chunks[1]["span_ids"]) == 1

    def test_mixed_null_and_non_null_headings(self) -> None:
        """Mix of NULL and non-NULL heading_paths must be handled correctly."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="Grouped 1", heading_path="Section A"),
            _make_span_dict(version_id=version_id, text="Grouped 2", heading_path="Section A"),
            _make_span_dict(version_id=version_id, text="Orphan", heading_path=None),
            _make_span_dict(version_id=version_id, text="Grouped 3", heading_path="Section B"),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        assert len(chunks) == 3, "Two grouped chunks + one orphan chunk"
        # Section A chunk (2 spans)
        assert chunks[0]["heading_path"] == "Section A"
        assert len(chunks[0]["span_ids"]) == 2
        # Orphan chunk (1 span, NULL heading)
        assert chunks[1]["heading_path"] is None
        assert len(chunks[1]["span_ids"]) == 1
        # Section B chunk (1 span)
        assert chunks[2]["heading_path"] == "Section B"
        assert len(chunks[2]["span_ids"]) == 1

    def test_token_count_matches_final_text_preview_tokenization(self) -> None:
        """Token count must match the final stored text_preview tokenization."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="one   two", heading_path="H"),
            _make_span_dict(version_id=version_id, text=" three four  five ", heading_path="H"),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        assert chunks[0]["token_count"] == len(chunks[0]["text_preview"].split())

    def test_chunk_type_is_semantic_group(self) -> None:
        """Heading-grouped chunks must have chunk_type 'semantic_group'."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="x", heading_path="H"),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        assert chunks[0]["chunk_type"] == "semantic_group"

    def test_chunk_order_preserves_span_order(self) -> None:
        """Chunk order must follow the order of first span in each group."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="A", heading_path="H2", offset=200),
            _make_span_dict(version_id=version_id, text="B", heading_path="H1", offset=100),
            _make_span_dict(version_id=version_id, text="C", heading_path="H1", offset=150),
        ]
        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        # Spans sorted by offset: B(100) -> C(150) -> A(200)
        # Groups: H1 (B,C) -> H2 (A)
        # So chunk order: H1 group first, then H2 group
        assert chunks[0]["heading_path"] == "H1"
        assert chunks[0]["chunk_order"] == 0
        assert chunks[1]["heading_path"] == "H2"
        assert chunks[1]["chunk_order"] == 1


class TestPluggableChunkerSelection:
    """VectorLoader must accept pluggable chunker strategies."""

    def test_vector_loader_accepts_chunker_parameter(self) -> None:
        """VectorLoader must accept a chunker instance as a parameter."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker, SimpleSpanChunker
        from llamaindex_runtime.vector.loader import VectorLoader

        # Default chunker is SimpleSpanChunker
        loader_default = VectorLoader()
        assert isinstance(loader_default._chunker, SimpleSpanChunker)

        # Can pass custom chunker
        custom_chunker = HeadingGroupedChunker()
        loader_custom = VectorLoader(chunker=custom_chunker)
        assert isinstance(loader_custom._chunker, HeadingGroupedChunker)

    def test_loader_with_heading_chunker_produces_grouped_chunks(
        self, tmp_path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Live test: VectorLoader with HeadingGroupedChunker must produce grouped chunks."""
        from PIL import Image, ImageDraw

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker
        from llamaindex_runtime.vector.loader import VectorLoader

        # Build PDF with multiple spans under same heading
        sample_pdf = tmp_path / "heading-chunker.pdf"
        image = Image.new("RGB", (1200, 1600), "white")
        draw = ImageDraw.Draw(image)
        draw.text((80, 80), "Chapter 1", fill="black")
        draw.text((80, 180), "Paragraph one under Chapter 1.", fill="black")
        draw.text((80, 280), "Paragraph two under Chapter 1.", fill="black")
        draw.text((80, 380), "Paragraph three under Chapter 1.", fill="black")
        draw.text((80, 480), "Chapter 2", fill="black")
        draw.text((80, 580), "Paragraph one under Chapter 2.", fill="black")
        image.save(sample_pdf, "PDF")

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Heading chunker test")

        spans = registry.query_spans_by_version(result.version_id)

        # Use HeadingGroupedChunker
        chunker = HeadingGroupedChunker()
        loader = VectorLoader(chunker=chunker)
        loader_result = loader.load(live_db_connection, result.version_id)

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)

        # Should have fewer chunks than spans (spans are grouped by heading)
        assert len(persisted_chunks) < len(spans), (
            "HeadingGroupedChunker must produce fewer chunks than spans (grouped)"
        )

        # Verify provenance: each chunk must have span_ids
        chunk_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        for chunk in persisted_chunks:
            span_ids_for_chunk = [m["span_id"] for m in chunk_mappings if m["chunk_id"] == chunk["chunk_id"]]
            assert len(span_ids_for_chunk) >= 1, f"Chunk {chunk['chunk_id']} must have provenance"

        # Verify chunk_type is semantic_group for grouped chunks
        grouped_chunks = [c for c in persisted_chunks if c["chunk_type"] == "semantic_group"]
        assert len(grouped_chunks) > 0, "Must have at least one semantic_group chunk"