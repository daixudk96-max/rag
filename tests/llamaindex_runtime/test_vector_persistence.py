"""Tests for Phase 4: Vector Layer -- chunk derivation, persistence, and provenance.

These tests verify:
1. SimpleSpanChunker derives vector chunks from canonical spans (1:1 mapping)
2. DeterministicEmbedder produces deterministic, normalized vectors
3. PostgresRegistryWriter.write_vector_chunks persists chunks and chunk-span mappings
4. Query methods read back persisted vector data
5. Provenance: chunks can be traced to spans, and to tree node_ids when tree data exists
6. Idempotency: writing chunks twice does not duplicate rows
7. Edge cases: empty spans, null heading_path, large batches

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests run without a database.
"""
from __future__ import annotations

import math
import uuid
from pathlib import Path

import pytest

from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.registry.tree_generator import TreeGenerator

from okf._e2a_pipeline_testkit import _FakeReconciler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_span_dict(
    *,
    span_id: uuid.UUID | None = None,
    version_id: uuid.UUID,
    heading_path: str | None = None,
    page_no: int | None = 1,
    text: str = "sample text",
    offset: int = 0,
) -> dict[str, object]:
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


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


# ===========================================================================
# UNIT TESTS -- SimpleSpanChunker (no database required)
# ===========================================================================


class TestSimpleSpanChunkerBasic:
    """Core chunker behavior: 1:1 span-to-chunk, deterministic IDs, metadata."""

    def test_generate_creates_one_chunk_per_span(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="first span"),
            _make_span_dict(version_id=version_id, text="second span"),
            _make_span_dict(version_id=version_id, text="third span"),
        ]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert len(chunks) == 3, "One chunk per span expected"

    def test_chunk_id_is_deterministic(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        span_id = uuid.uuid4()
        spans = [_make_span_dict(span_id=span_id, version_id=version_id, text="hello")]
        chunker = SimpleSpanChunker()
        chunks1 = chunker.generate(spans, version_id=version_id)
        chunks2 = chunker.generate(spans, version_id=version_id)
        assert chunks1[0]["chunk_id"] == chunks2[0]["chunk_id"], "chunk_id must be deterministic (uuid5)"

    def test_chunk_has_provenance_metadata(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        span_id = uuid.uuid4()
        spans = [
            _make_span_dict(
                span_id=span_id,
                version_id=version_id,
                text="provenance test",
                heading_path="Ch 1 > 1.1 Intro",
                page_no=5,
            )
        ]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        chunk = chunks[0]
        assert chunk["span_ids"] == [span_id], "chunk must link to its source span"
        assert chunk["page_no"] == 5
        assert chunk["heading_path"] == "Ch 1 > 1.1 Intro"
        assert chunk["text_preview"] == "provenance test"

    def test_empty_spans_returns_empty(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        chunker = SimpleSpanChunker()
        chunks = chunker.generate([], version_id=version_id)
        assert chunks == []

    def test_token_count_is_word_count(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [_make_span_dict(version_id=version_id, text="one two three four")]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert chunks[0]["token_count"] == 4, "token_count should be word count"

    def test_chunk_order_increments(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [
            _make_span_dict(version_id=version_id, text="a"),
            _make_span_dict(version_id=version_id, text="b"),
            _make_span_dict(version_id=version_id, text="c"),
        ]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert [c["chunk_order"] for c in chunks] == [0, 1, 2]

    def test_chunk_type_is_semantic_leaf(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [_make_span_dict(version_id=version_id, text="x")]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert chunks[0]["chunk_type"] == "semantic_leaf"

    def test_null_heading_path_handled(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [_make_span_dict(version_id=version_id, text="x", heading_path=None)]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert chunks[0]["heading_path"] is None

    def test_null_page_no_handled(self) -> None:
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        version_id = uuid.uuid4()
        spans = [_make_span_dict(version_id=version_id, text="x", page_no=None)]
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=version_id)
        assert chunks[0]["page_no"] is None


# ===========================================================================
# UNIT TESTS -- DeterministicEmbedder (no database required)
# ===========================================================================


class TestDeterministicEmbedder:
    """DeterministicEmbedder: hash-based embedding for testing."""

    def test_embed_text_returns_correct_dimension(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=16)
        vec = embedder.embed_text("hello world")
        assert len(vec) == 16

    def test_embed_empty_string_returns_zero_vector(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=8)
        vec = embedder.embed_text("")
        assert vec == [0.0] * 8

    def test_embed_deterministic(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=16)
        v1 = embedder.embed_text("same input")
        v2 = embedder.embed_text("same input")
        assert v1 == v2, "Same input must produce same embedding"

    def test_embed_normalized(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=16)
        vec = embedder.embed_text("normalization test")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6, "Embedding must be L2-normalized"

    def test_different_texts_produce_different_embeddings(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=16)
        v1 = embedder.embed_text("alpha")
        v2 = embedder.embed_text("beta")
        assert v1 != v2, "Different texts must produce different embeddings"

    def test_custom_dimension(self) -> None:
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder

        embedder = DeterministicEmbedder(dim=32)
        vec = embedder.embed_text("dim test")
        assert len(vec) == 32


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveVectorChunkPersistence:
    """Live tests that verify vector_chunks and vector_chunk_spans persist correctly."""

    def test_write_vector_chunks_persists_chunks(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_vector_chunks must persist vector_chunks rows for a version."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-persist.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector persist test")

        # Generate chunks from persisted spans
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)

        # Write chunks
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Read back and verify
        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted_chunks) == len(chunks), (
            f"Persisted {len(persisted_chunks)} chunks, expected {len(chunks)}"
        )

    def test_write_vector_chunks_persists_chunk_span_mappings(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_vector_chunks must persist vector_chunk_spans rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-span-link.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector span link test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        persisted_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        assert len(persisted_mappings) > 0, "chunk-span mappings must be persisted"
        # Each chunk should have at least one span mapping
        chunk_ids_with_mappings = {m["chunk_id"] for m in persisted_mappings}
        expected_chunk_ids = {c["chunk_id"] for c in chunks}
        assert chunk_ids_with_mappings == expected_chunk_ids, (
            "Every chunk must have at least one span mapping"
        )

    def test_every_span_covered_by_chunk_span_mapping(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every canonical span must be linked to a chunk via vector_chunk_spans."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-coverage.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector coverage test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        span_ids_in_db = {s["span_id"] for s in spans}
        covered_span_ids = {m["span_id"] for m in registry.query_vector_chunk_spans_by_version(result.version_id)}
        assert covered_span_ids == span_ids_in_db, (
            f"Not all spans are covered. Missing: {span_ids_in_db - covered_span_ids}"
        )

    def test_vector_provenance_traceable_to_spans(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A chunk can be traced back to its source spans via vector_chunk_spans."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-provenance.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector provenance test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        persisted_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)

        # For each chunk, verify we can find its span(s)
        for chunk in persisted_chunks:
            chunk_span_ids = [m["span_id"] for m in persisted_mappings if m["chunk_id"] == chunk["chunk_id"]]
            assert len(chunk_span_ids) >= 1, f"Chunk {chunk['chunk_id']} has no span mappings"
            # Each span_id must exist in canonical_spans
            for span_id in chunk_span_ids:
                assert any(s["span_id"] == span_id for s in spans), (
                    f"span_id {span_id} not found in canonical_spans"
                )

    def test_vector_provenance_traceable_to_tree_node(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A chunk can be traced to a tree node via: chunk -> span -> tree_node_span."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-tree-provenance.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector tree provenance test")

        # Write tree first
        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Write vector chunks
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Now verify: for each chunk, trace through span to tree node
        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        chunk_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        tree_node_spans = registry.query_tree_node_spans_by_version(result.version_id)

        # Build span -> node_id lookup
        span_to_node: dict[uuid.UUID, uuid.UUID] = {}
        for tns in tree_node_spans:
            span_to_node[tns["span_id"]] = tns["node_id"]

        # Each chunk should be traceable to at least one tree node
        for chunk in persisted_chunks:
            chunk_span_ids = [m["span_id"] for m in chunk_mappings if m["chunk_id"] == chunk["chunk_id"]]
            node_ids_for_chunk = {span_to_node[sid] for sid in chunk_span_ids if sid in span_to_node}
            assert len(node_ids_for_chunk) >= 1, (
                f"Chunk {chunk['chunk_id']} cannot be traced to any tree node"
            )

    def test_write_vector_chunks_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing chunks twice must not duplicate rows."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-idempotent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector idempotent test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)

        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )
        # Write again
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        persisted_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        assert len(persisted_chunks) == len(chunks), (
            "Idempotent write must not duplicate vector_chunks"
        )
        expected_mappings = sum(len(c["span_ids"]) for c in chunks)
        assert len(persisted_mappings) == expected_mappings, (
            "Idempotent write must not duplicate vector_chunk_spans"
        )

    def test_cascade_delete_version_removes_chunks(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting a document version must cascade to vector_chunks and vector_chunk_spans."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-cascade.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector cascade test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Verify chunks exist
        assert len(registry.query_vector_chunks_by_version(result.version_id)) > 0

        # Delete the version via cascade
        with live_db_connection.cursor() as cur:
            cur.execute(
                "DELETE FROM document_versions WHERE version_id = %s",
                (str(result.version_id),),
            )

        # Chunks must be gone
        assert len(registry.query_vector_chunks_by_version(result.version_id)) == 0
        assert len(registry.query_vector_chunk_spans_by_version(result.version_id)) == 0

    def test_query_vector_chunks_returns_correct_fields(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """query_vector_chunks_by_version must return all vector_chunks columns as UUID types."""
        from llamaindex_runtime.ingestion import IngestionPipeline

        sample_pdf = tmp_path / "vector-fields.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector fields test")

        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted_chunks) > 0
        chunk = persisted_chunks[0]
        # UUID fields must be uuid.UUID instances
        assert isinstance(chunk["chunk_id"], uuid.UUID)
        assert isinstance(chunk["version_id"], uuid.UUID)
        # Required fields must be present
        assert "chunk_type" in chunk
        assert "chunk_order" in chunk
        assert "token_count" in chunk
        assert "text_preview" in chunk

    def test_full_loader_flow(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """VectorLoader must: read spans -> chunk -> persist -> embed -> update embeddings."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-loader.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector loader test")

        loader = VectorLoader()
        loader_result = loader.load(live_db_connection, result.version_id)

        # Verify chunks were created
        assert loader_result["count"] > 0
        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted_chunks) == loader_result["count"]

        # Verify embeddings were set (non-null)
        for chunk in persisted_chunks:
            assert chunk.get("embedding") is not None, (
                f"Chunk {chunk['chunk_id']} must have an embedding after loader runs"
            )

    def test_loader_with_tree_data_sets_node_id(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """When tree data exists, VectorLoader must populate node_id on vector_chunks."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-loader-tree.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector loader tree test")

        # Write tree first
        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Run vector loader
        loader = VectorLoader()
        loader.load(live_db_connection, result.version_id)

        # Verify that at least some chunks have node_id populated
        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        chunks_with_node = [c for c in persisted_chunks if c.get("node_id") is not None]
        assert len(chunks_with_node) > 0, (
            "When tree data exists, at least some chunks must have node_id"
        )

    def test_loader_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Running VectorLoader twice must not duplicate chunks."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-loader-idempotent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector loader idempotent test")

        loader = VectorLoader()
        loader.load(live_db_connection, result.version_id)
        loader.load(live_db_connection, result.version_id)

        persisted_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted_chunks) == loader.load(live_db_connection, result.version_id)["count"]

    def test_loader_repairs_missing_embeddings(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Rerunning load() must repair chunks that have NULL embeddings.

        Simulates a partial prior run: chunks and span mappings are persisted
        (e.g. by write_vector_chunks), but embeddings were never written.
        Re-running load() must detect the gap and fill embeddings.
        """
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-repair-embed.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector repair embed test")

        # Simulate partial run: persist chunks and span mappings only,
        # but do NOT write embeddings or node_ids.
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        spans = registry.query_spans_by_version(result.version_id)
        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Verify partial state: embeddings are NULL
        persisted = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted) > 0, "Chunks must exist for partial state"
        for chunk in persisted:
            assert chunk.get("embedding") is None, (
                f"Precondition: chunk {chunk['chunk_id']} must have NULL embedding before repair"
            )

        # Re-run load() -- it must repair the missing embeddings
        loader = VectorLoader()
        loader.load(live_db_connection, result.version_id)

        # Verify repair: all embeddings must now be non-NULL
        repaired = registry.query_vector_chunks_by_version(result.version_id)
        assert len(repaired) == len(chunks), "Repair must not duplicate or lose chunks"
        for chunk in repaired:
            assert chunk.get("embedding") is not None, (
                f"Chunk {chunk['chunk_id']} must have embedding after repair run"
            )

    def test_loader_repairs_missing_node_id(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Rerunning load() must repair chunks that have NULL node_id when tree data exists.

        Simulates a partial prior run: chunks and span mappings are persisted
        but node_id was never linked (tree data was created after the first load).
        Re-running load() must detect the gap and link node_ids.
        """
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-repair-nodeid.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector repair node_id test")

        # Create tree data
        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Simulate partial run: persist chunks and span mappings only,
        # but do NOT write embeddings or node_ids.
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Verify partial state: node_ids are NULL
        persisted = registry.query_vector_chunks_by_version(result.version_id)
        assert len(persisted) > 0, "Chunks must exist for partial state"
        for chunk in persisted:
            assert chunk.get("node_id") is None, (
                f"Precondition: chunk {chunk['chunk_id']} must have NULL node_id before repair"
            )

        # Re-run load() -- it must repair the missing node_ids
        loader = VectorLoader()
        loader.load(live_db_connection, result.version_id)

        # Verify repair: at least some chunks must have node_id
        repaired = registry.query_vector_chunks_by_version(result.version_id)
        chunks_with_node = [c for c in repaired if c.get("node_id") is not None]
        assert len(chunks_with_node) > 0, (
            "When tree data exists, at least some chunks must have node_id after repair run"
        )

    def test_loader_repairs_both_missing_embeddings_and_node_id(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Rerunning load() must repair both missing embeddings AND node_ids in one pass.

        Simulates the worst partial state: chunks exist but have neither
        embeddings nor node_ids, and tree data is available.
        """
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-repair-both.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Vector repair both test")

        # Create tree data
        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Simulate partial run: chunks and mappings only
        from llamaindex_runtime.vector.chunker import SimpleSpanChunker

        chunker = SimpleSpanChunker()
        chunks = chunker.generate(spans, version_id=result.version_id)
        registry.write_vector_chunks(
            version_id=result.version_id,
            chunks=chunks,
        )

        # Verify partial state
        persisted = registry.query_vector_chunks_by_version(result.version_id)
        for chunk in persisted:
            assert chunk.get("embedding") is None
            assert chunk.get("node_id") is None

        # Re-run load() -- must repair both
        loader = VectorLoader()
        loader.load(live_db_connection, result.version_id)

        # Verify repair
        repaired = registry.query_vector_chunks_by_version(result.version_id)
        for chunk in repaired:
            assert chunk.get("embedding") is not None, (
                f"Chunk {chunk['chunk_id']} must have embedding after repair"
            )
        chunks_with_node = [c for c in repaired if c.get("node_id") is not None]
        assert len(chunks_with_node) > 0, (
            "At least some chunks must have node_id after repair"
        )


# ===========================================================================
# LIVE TESTS -- VectorLoader with Qdrant backend
# ===========================================================================


class TestLiveVectorLoaderWithQdrant:
    """Live tests for VectorLoader projecting vectors to Qdrant."""

    def test_loader_with_qdrant_projects_vectors(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """VectorLoader must project vectors to Qdrant when backend is provided."""
        from qdrant_client import QdrantClient

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        sample_pdf = tmp_path / "vector-qdrant-project.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Qdrant project test")

        # Create in-memory Qdrant client
        qdrant_client = QdrantClient(":memory:")
        qdrant_backend = QdrantVectorBackend(client=qdrant_client, embed_dim=16)

        # Run vector loader with Qdrant backend
        loader = VectorLoader(embed_dim=16, vector_backend=qdrant_backend)
        loader_result = loader.load(live_db_connection, result.version_id)

        # Verify vectors were projected to Qdrant
        collection_name = f"version_{result.version_id}"
        collections = qdrant_client.get_collections().collections
        assert any(c.name == collection_name for c in collections), (
            f"Collection {collection_name} must exist in Qdrant"
        )

        # Verify points exist in collection
        info = qdrant_client.get_collection(collection_name)
        assert info.points_count > 0, "Qdrant collection must have points"
        assert info.points_count == loader_result["count"], (
            "Qdrant points count must match chunk count"
        )

    def test_loader_with_qdrant_preserves_postgres_provenance(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """When Qdrant backend is provided, PostgreSQL provenance must still be written."""
        from qdrant_client import QdrantClient

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        sample_pdf = tmp_path / "vector-qdrant-provenance.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Qdrant provenance test")

        qdrant_client = QdrantClient(":memory:")
        qdrant_backend = QdrantVectorBackend(client=qdrant_client, embed_dim=16)
        loader = VectorLoader(embed_dim=16, vector_backend=qdrant_backend)
        loader.load(live_db_connection, result.version_id)

        # Verify PostgreSQL provenance is intact
        pg_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(pg_chunks) > 0, "PostgreSQL chunks must exist"
        for chunk in pg_chunks:
            assert chunk.get("embedding") is not None, (
                f"Chunk {chunk['chunk_id']} must have embedding in PostgreSQL"
            )

        pg_mappings = registry.query_vector_chunk_spans_by_version(result.version_id)
        assert len(pg_mappings) > 0, "PostgreSQL chunk-span mappings must exist"

    def test_loader_without_qdrant_backward_compatible(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """VectorLoader without Qdrant backend must work as before (backward compatible)."""
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader

        sample_pdf = tmp_path / "vector-backward.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Backward test")

        # Run loader without Qdrant backend (default behavior)
        loader = VectorLoader(embed_dim=16)
        loader.load(live_db_connection, result.version_id)

        # PostgreSQL provenance must be intact
        pg_chunks = registry.query_vector_chunks_by_version(result.version_id)
        assert len(pg_chunks) > 0, "PostgreSQL chunks must exist without Qdrant"
        for chunk in pg_chunks:
            assert chunk.get("embedding") is not None, "Embeddings must be in PostgreSQL"

    def test_qdrant_search_round_trips_provenance(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Search Qdrant and then look up chunk/span provenance from PostgreSQL."""
        from qdrant_client import QdrantClient

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.embedder import DeterministicEmbedder
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend
        from llamaindex_runtime.vector.runtime import retrieve_vector_hits_from_backend

        sample_pdf = tmp_path / "vector-roundtrip.pdf"
        _build_rich_pdf(sample_pdf, text_body="unique searchable content for roundtrip test")

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Roundtrip test")

        qdrant_client = QdrantClient(":memory:")
        qdrant_backend = QdrantVectorBackend(client=qdrant_client, embed_dim=16)
        loader = VectorLoader(embed_dim=16, vector_backend=qdrant_backend)
        loader.load(live_db_connection, result.version_id)

        # Search for vectors in Qdrant
        embedder = DeterministicEmbedder(dim=16)
        hits = retrieve_vector_hits_from_backend(
            "unique searchable",
            version_id=result.version_id,
            registry=registry,
            vector_backend=qdrant_backend,
            embedder=embedder,
            limit=5,
        )

        # Verify hits have full provenance
        assert len(hits) > 0, "Search must return results"
        for hit in hits:
            assert hit["chunk_id"] is not None
            assert hit["score"] >= 0
            assert hit["text_preview"] is not None, "text_preview from PostgreSQL"
            assert len(hit["span_ids"]) > 0, "span_ids from PostgreSQL chunk-span mappings"

    def test_qdrant_repair_reprojects_vectors(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Re-running VectorLoader with Qdrant must re-project vectors to Qdrant."""
        from qdrant_client import QdrantClient

        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.vector.loader import VectorLoader
        from llamaindex_runtime.vector.qdrant_backend import QdrantVectorBackend

        sample_pdf = tmp_path / "vector-reproject.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Reproject test")

        qdrant_client = QdrantClient(":memory:")
        qdrant_backend = QdrantVectorBackend(client=qdrant_client, embed_dim=16)
        loader = VectorLoader(embed_dim=16, vector_backend=qdrant_backend)

        # First load
        loader.load(live_db_connection, result.version_id)
        collection_name = f"version_{result.version_id}"
        info1 = qdrant_client.get_collection(collection_name)

        # Second load (repair path)
        loader.load(live_db_connection, result.version_id)
        info2 = qdrant_client.get_collection(collection_name)

        # Points count should remain the same (idempotent upsert)
        assert info2.points_count == info1.points_count, (
            "Re-project must not duplicate points"
        )
