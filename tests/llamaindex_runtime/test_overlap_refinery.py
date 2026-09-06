"""Tests for P5 overlap refinery -- minimal overlap capability on top of existing chunkers.

These tests verify:
1. OverlapRefinery adds configurable overlap between adjacent chunks
2. Provenance (span_ids) is preserved after refinement
3. Canonical spans remain the source backbone
4. Refinery works with both SimpleSpanChunker and HeadingGroupedChunker
5. Edge cases: empty, single chunk, boundary handling

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


def _make_chunk_dict(
    *,
    chunk_id: uuid.UUID | None = None,
    version_id: uuid.UUID,
    chunk_type: str = "semantic_leaf",
    chunk_order: int = 0,
    text_preview: str = "sample text",
    span_ids: list[uuid.UUID] | None = None,
    heading_path: str | None = None,
    page_no: int | None = 1,
) -> dict[str, Any]:
    """Create a chunk dict matching the shape from existing chunkers."""
    return {
        "chunk_id": chunk_id or uuid.uuid4(),
        "chunk_type": chunk_type,
        "chunk_order": chunk_order,
        "token_count": len(text_preview.split()) if text_preview.strip() else 0,
        "text_preview": text_preview,
        "page_no": page_no,
        "heading_path": heading_path,
        "span_ids": span_ids or [uuid.uuid4()],
    }


# ===========================================================================
# UNIT TESTS -- OverlapRefinery (no database required)
# ===========================================================================


class TestOverlapRefineryBasic:
    """Core refinery behavior: add overlap between adjacent chunks."""

    def test_refinery_exists_and_can_be_imported(self) -> None:
        """OverlapRefinery must exist and be importable."""
        try:
            from llamaindex_runtime.vector.refinery import OverlapRefinery
        except ImportError as e:
            pytest.fail(f"OverlapRefinery should be importable: {e}")

    def test_refinery_accepts_overlap_tokens_parameter(self) -> None:
        """OverlapRefinery must accept overlap_tokens parameter."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        refinery = OverlapRefinery(overlap_tokens=50)
        assert refinery._overlap_tokens == 50

    def test_refinery_refines_empty_chunks_returns_empty(self) -> None:
        """Empty chunk list must return empty list."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        refinery = OverlapRefinery(overlap_tokens=50)
        refined = refinery.refine([], version_id=version_id)
        assert refined == []

    def test_refinery_refines_single_chunk_returns_same(self) -> None:
        """Single chunk must be returned unchanged (no adjacent chunks to overlap)."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        chunk = _make_chunk_dict(
            version_id=version_id,
            text_preview="Only chunk here",
            chunk_order=0,
        )
        refinery = OverlapRefinery(overlap_tokens=50)
        refined = refinery.refine([chunk], version_id=version_id)

        assert len(refined) == 1
        assert refined[0]["text_preview"] == chunk["text_preview"]
        assert refined[0]["span_ids"] == chunk["span_ids"]

    def test_refinery_adds_overlap_to_adjacent_chunks(self) -> None:
        """Adjacent chunks must have overlap text added."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()

        chunk_1 = _make_chunk_dict(
            version_id=version_id,
            text_preview="First paragraph with some content here.",
            chunk_order=0,
            span_ids=[span_id_1],
        )
        chunk_2 = _make_chunk_dict(
            version_id=version_id,
            text_preview="Second paragraph with different content.",
            chunk_order=1,
            span_ids=[span_id_2],
        )

        refinery = OverlapRefinery(overlap_tokens=5)
        refined = refinery.refine([chunk_1, chunk_2], version_id=version_id)

        assert len(refined) == 2
        # Chunk 1 should have some text from chunk 2 appended (beginning of chunk 2)
        assert "Second paragraph" in refined[0]["text_preview"]
        # Chunk 2 should have some text from chunk 1 prepended (end of chunk 1)
        # overlap_tokens=5 from chunk_1's end: "paragraph with some content here."
        assert "paragraph with some content here" in refined[1]["text_preview"]

    def test_refinery_preserves_provenance_with_extended_span_ids(self) -> None:
        """Overlapped chunks must extend span_ids to include overlapping source."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()

        chunk_1 = _make_chunk_dict(
            version_id=version_id,
            text_preview="Chunk one content",
            chunk_order=0,
            span_ids=[span_id_1],
        )
        chunk_2 = _make_chunk_dict(
            version_id=version_id,
            text_preview="Chunk two content",
            chunk_order=1,
            span_ids=[span_id_2],
        )

        refinery = OverlapRefinery(overlap_tokens=5)
        refined = refinery.refine([chunk_1, chunk_2], version_id=version_id)

        # Chunk 1 overlaps with chunk 2, so it should include span_id_2
        assert span_id_2 in refined[0]["span_ids"]
        # Chunk 2 overlaps with chunk 1, so it should include span_id_1
        assert span_id_1 in refined[1]["span_ids"]

    def test_refinery_maintains_canonical_spans_as_backbone(self) -> None:
        """Refinery must not create new chunks, only refine existing ones."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        original_chunks = [
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Chunk A",
                chunk_order=0,
            ),
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Chunk B",
                chunk_order=1,
            ),
        ]

        refinery = OverlapRefinery(overlap_tokens=5)
        refined = refinery.refine(original_chunks, version_id=version_id)

        # Must return same number of chunks (no new chunks created)
        assert len(refined) == len(original_chunks)
        # Must preserve original chunk_ids
        assert refined[0]["chunk_id"] == original_chunks[0]["chunk_id"]
        assert refined[1]["chunk_id"] == original_chunks[1]["chunk_id"]

    def test_refinery_handles_overlap_tokens_greater_than_chunk_size(self) -> None:
        """Overlap larger than chunk must not duplicate entire chunk."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()

        chunk_1 = _make_chunk_dict(
            version_id=version_id,
            text_preview="Small",  # 1 token
            chunk_order=0,
            span_ids=[span_id_1],
        )
        chunk_2 = _make_chunk_dict(
            version_id=version_id,
            text_preview="Also small",  # 2 tokens
            chunk_order=1,
            span_ids=[span_id_2],
        )

        refinery = OverlapRefinery(overlap_tokens=100)  # Much larger than chunks
        refined = refinery.refine([chunk_1, chunk_2], version_id=version_id)

        # Should still work, but not duplicate entire chunks multiple times
        assert len(refined) == 2
        # Each refined chunk should contain both original texts (limited overlap)
        assert "Small" in refined[0]["text_preview"]
        assert "Also small" in refined[0]["text_preview"]
        assert "Small" in refined[1]["text_preview"]
        assert "Also small" in refined[1]["text_preview"]

    def test_refinery_updates_token_count_after_overlap(self) -> None:
        """Token count must reflect the new text_preview after overlap."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        chunk_1 = _make_chunk_dict(
            version_id=version_id,
            text_preview="one two three",
            chunk_order=0,
        )
        chunk_2 = _make_chunk_dict(
            version_id=version_id,
            text_preview="four five six",
            chunk_order=1,
        )

        refinery = OverlapRefinery(overlap_tokens=2)
        refined = refinery.refine([chunk_1, chunk_2], version_id=version_id)

        # Token count must match final text_preview
        for chunk in refined:
            assert chunk["token_count"] == len(chunk["text_preview"].split())


class TestOverlapRefineryWithChunkers:
    """Refinery must work seamlessly with existing chunkers."""

    def test_refinery_with_simple_span_chunker(self) -> None:
        """Refinery must work with SimpleSpanChunker output."""
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        spans = [
            {
                "span_id": uuid.uuid4(),
                "version_id": version_id,
                "raw_text": "First span text content here.",
                "page_no": 1,
                "heading_path": None,
                "start_offset": 0,
                "end_offset": 100,
            },
            {
                "span_id": uuid.uuid4(),
                "version_id": version_id,
                "raw_text": "Second span text content here.",
                "page_no": 1,
                "heading_path": None,
                "start_offset": 100,
                "end_offset": 200,
            },
        ]

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        refinery = OverlapRefinery(overlap_tokens=5)
        refined = refinery.refine(chunks, version_id=version_id)

        assert len(refined) == len(chunks)
        # Refined chunks should have overlap
        assert refined[0]["text_preview"] != chunks[0]["text_preview"]
        assert refined[1]["text_preview"] != chunks[1]["text_preview"]

    def test_refinery_with_heading_grouped_chunker(self) -> None:
        """Refinery must work with HeadingGroupedChunker output."""
        from llamaindex_runtime.vector.chunker import HeadingGroupedChunker
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        heading = "Chapter 1"
        spans = [
            {
                "span_id": uuid.uuid4(),
                "version_id": version_id,
                "raw_text": "Paragraph one",
                "heading_path": heading,
                "start_offset": 0,
                "end_offset": 50,
            },
            {
                "span_id": uuid.uuid4(),
                "version_id": version_id,
                "raw_text": "Paragraph two",
                "heading_path": heading,
                "start_offset": 50,
                "end_offset": 100,
            },
        ]

        chunker = HeadingGroupedChunker()
        chunks = chunker.generate(spans, version_id=version_id)

        refinery = OverlapRefinery(overlap_tokens=3)
        refined = refinery.refine(chunks, version_id=version_id)

        assert len(refined) == len(chunks)
        # Should preserve semantic_group type
        assert refined[0]["chunk_type"] == "semantic_group"


class TestOverlapRefineryIntegration:
    """Integration with VectorLoader pipeline."""

    def test_vector_loader_accepts_refinery_parameter(self) -> None:
        """VectorLoader must accept optional refinery parameter."""
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        # Default: no refinery
        loader_default = VectorLoader()
        assert loader_default._refinery is None

        # Can pass custom refinery
        refinery = OverlapRefinery(overlap_tokens=50)
        loader_with_refinery = VectorLoader(refinery=refinery)
        assert loader_with_refinery._refinery is not None

    def test_loader_with_refinery_applies_overlap_to_chunks(
        self, tmp_path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Live test: VectorLoader with refinery must produce overlapped chunks."""
        from PIL import Image, ImageDraw

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        # Build PDF with multiple spans
        sample_pdf = tmp_path / "overlap-test.pdf"
        image = Image.new("RGB", (1200, 1600), "white")
        draw = ImageDraw.Draw(image)
        draw.text((80, 80), "Paragraph one content here.", fill="black")
        draw.text((80, 180), "Paragraph two content here.", fill="black")
        draw.text((80, 280), "Paragraph three content here.", fill="black")
        image.save(sample_pdf, "PDF")

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Overlap test")

        spans = registry.query_spans_by_version(result.version_id)

        # Use SimpleSpanChunker + OverlapRefinery
        chunker = SimpleSpanChunker()
        refinery = OverlapRefinery(overlap_tokens=5)
        loader = VectorLoader(chunker=chunker, refinery=refinery)
        loader_result = loader.load(live_db_connection, result.version_id)

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)

        # Verify chunks have overlap (refinery was applied)
        # Adjacent chunks should have overlapping text
        for i in range(len(persisted_chunks) - 1):
            chunk_i_text = persisted_chunks[i]["text_preview"]
            chunk_next_text = persisted_chunks[i + 1]["text_preview"]
            # Chunk i should have some text from chunk i+1
            # This verifies refinery was applied
            assert len(chunk_i_text) > len(spans[i]["raw_text"]), (
                f"Chunk {i} should have overlap added from refinery"
            )

        # Verify provenance: each chunk must have span_ids
        chunk_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        for chunk in persisted_chunks:
            span_ids_for_chunk = [m["span_id"] for m in chunk_mappings if m["chunk_id"] == chunk["chunk_id"]]
            assert len(span_ids_for_chunk) >= 1, f"Chunk {chunk['chunk_id']} must have provenance"


class TestOverlapRefineryEdgeCases:
    """Edge cases and boundary conditions."""

    def test_refinery_with_zero_overlap_tokens(self) -> None:
        """Zero overlap must return chunks unchanged."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        chunks = [
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Chunk one",
                chunk_order=0,
            ),
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Chunk two",
                chunk_order=1,
            ),
        ]

        refinery = OverlapRefinery(overlap_tokens=0)
        refined = refinery.refine(chunks, version_id=version_id)

        assert refined[0]["text_preview"] == chunks[0]["text_preview"]
        assert refined[1]["text_preview"] == chunks[1]["text_preview"]

    def test_refinery_preserves_chunk_order(self) -> None:
        """Chunk order must remain unchanged after refinement."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        chunks = [
            _make_chunk_dict(
                version_id=version_id,
                text_preview="First",
                chunk_order=0,
            ),
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Second",
                chunk_order=1,
            ),
            _make_chunk_dict(
                version_id=version_id,
                text_preview="Third",
                chunk_order=2,
            ),
        ]

        refinery = OverlapRefinery(overlap_tokens=2)
        refined = refinery.refine(chunks, version_id=version_id)

        assert refined[0]["chunk_order"] == 0
        assert refined[1]["chunk_order"] == 1
        assert refined[2]["chunk_order"] == 2

    def test_refinery_preserves_other_metadata(self) -> None:
        """Metadata like page_no, heading_path, chunk_type must be preserved."""
        from llamaindex_runtime.vector.refinery import OverlapRefinery

        version_id = uuid.uuid4()
        chunk = _make_chunk_dict(
            version_id=version_id,
            text_preview="Content",
            chunk_order=0,
            chunk_type="semantic_group",
            heading_path="Section A",
            page_no=5,
        )

        refinery = OverlapRefinery(overlap_tokens=10)
        refined = refinery.refine([chunk], version_id=version_id)

        assert refined[0]["chunk_type"] == chunk["chunk_type"]
        assert refined[0]["heading_path"] == chunk["heading_path"]
        assert refined[0]["page_no"] == chunk["page_no"]