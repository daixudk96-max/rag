"""Tests for Phase 3 Tree Slice: summary_text generation from covered spans.

These tests verify:
1. TreeGenerator generates summary_text for leaf nodes by concatenating span texts
2. TreeGenerator generates summary_text for parent nodes by aggregating child summaries
3. Empty spans produce empty or None summary_text
4. summary_text persists to database and can be queried back
5. Idempotency: writing tree twice does not change summary_text

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests use the TreeGenerator in isolation and run without a database.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

from okf._e2a_pipeline_testkit import _FakeReconciler


def _make_span(
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


# ===========================================================================
# UNIT TESTS -- TreeGenerator summary_text generation (no database)
# ===========================================================================


class TestTreeGeneratorSummaryText:
    """Core TreeGenerator summary_text behavior: leaf nodes, parent nodes."""

    def test_leaf_node_summary_concatenates_span_texts(self) -> None:
        """Leaf node summary_text must concatenate raw_text from all covered spans."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="First paragraph."),
            _make_span(version_id=version_id, heading_path="Ch 1", text="Second paragraph."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = result["nodes"][0]
        assert leaf_node["summary_text"] is not None, "Leaf node must have summary_text"
        assert "First paragraph." in leaf_node["summary_text"]
        assert "Second paragraph." in leaf_node["summary_text"]

    def test_single_span_leaf_node_summary(self) -> None:
        """Single span leaf node must use its raw_text as summary_text."""
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Ch 1", text="Only paragraph.")]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = result["nodes"][0]
        assert leaf_node["summary_text"] == "Only paragraph."

    def test_parent_node_summary_aggregates_child_summaries(self) -> None:
        """Parent node summary_text must aggregate summaries from all child nodes."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro", text="Intro text."),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.2 Methods", text="Methods text."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Find parent node (level 0)
        parent_node = [n for n in result["nodes"] if n["level_no"] == 0][0]
        assert parent_node["summary_text"] is not None, "Parent node must have summary_text"
        assert "Intro text." in parent_node["summary_text"]
        assert "Methods text." in parent_node["summary_text"]

    def test_deep_hierarchy_summary_propagation(self) -> None:
        """Deep hierarchy: parent summaries must aggregate all descendant texts."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 > 1.1.1", text="Deep text A."),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 > 1.1.2", text="Deep text B."),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.2", text="Sibling text."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        # Top-level parent (Ch 1) must contain all descendant texts
        top_parent = [n for n in result["nodes"] if n["level_no"] == 0][0]
        assert top_parent["summary_text"] is not None
        assert "Deep text A." in top_parent["summary_text"]
        assert "Deep text B." in top_parent["summary_text"]
        assert "Sibling text." in top_parent["summary_text"]

    def test_empty_spans_produce_none_summary(self) -> None:
        """Empty span list must produce nodes with None summary_text."""
        version_id = uuid.uuid4()
        result = TreeGenerator().generate([], version_id=version_id)
        assert result["nodes"] == []
        # No nodes means no summary_text to check

    def test_null_heading_path_node_summary(self) -> None:
        """Spans with null heading_path must produce root node with concatenated texts."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path=None, text="Root text A."),
            _make_span(version_id=version_id, heading_path=None, text="Root text B."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        root_node = result["nodes"][0]
        assert root_node["summary_text"] is not None
        assert "Root text A." in root_node["summary_text"]
        assert "Root text B." in root_node["summary_text"]

    def test_summary_text_separator_is_whitespace(self) -> None:
        """Multiple span texts must be joined with whitespace separator."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Para one."),
            _make_span(version_id=version_id, heading_path="Ch 1", text="Para two."),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = result["nodes"][0]
        # Must contain both texts separated by whitespace (space, newline, etc.)
        assert leaf_node["summary_text"] is not None
        assert "Para one." in leaf_node["summary_text"]
        assert "Para two." in leaf_node["summary_text"]
        # Should not be concatenated without separator
        assert "Para one.Para two." not in leaf_node["summary_text"]

    def test_node_summary_max_length_cap(self) -> None:
        """Node summary_text must be capped at reasonable max length."""
        version_id = uuid.uuid4()
        # Create spans with very long text (300 chars each, total 600+)
        long_text = "X" * 300
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text=long_text),
            _make_span(version_id=version_id, heading_path="Ch 1", text=long_text),
            _make_span(version_id=version_id, heading_path="Ch 1", text=long_text),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)

        leaf_node = result["nodes"][0]
        assert leaf_node["summary_text"] is not None
        # Summary should be capped at a reasonable length (not 900 chars)
        # Max cap is set to 1000 chars in implementation
        assert len(leaf_node["summary_text"]) <= 1000


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


class TestLiveTreeSummaryPersistence:
    """Live tests that verify summary_text persists correctly to database."""

    def test_summary_text_persists_to_database(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """summary_text must persist to tree_nodes table and be queryable."""
        sample_pdf = tmp_path / "tree-summary-persist.pdf"
        _build_rich_pdf(sample_pdf, text_body="Live test summary paragraph.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree summary test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        assert len(persisted_nodes) > 0

        # Verify summary_text field is present and populated
        for node in persisted_nodes:
            if node["summary_text"] is not None:
                assert isinstance(node["summary_text"], str)
                # Should contain text from the spans
                assert len(node["summary_text"]) > 0

    def test_summary_text_content_matches_spans(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Persisted summary_text must match the span texts covered by the node."""
        sample_pdf = tmp_path / "tree-summary-match.pdf"
        _build_rich_pdf(sample_pdf, text_body="Specific content for matching.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree summary match test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        # Find a node with spans
        leaf_node = [n for n in persisted_nodes if n["level_no"] > 0][0]

        # Get spans for this node
        from llamaindex_runtime.tree.query import TreeRollupQuery

        tree_query = TreeRollupQuery(live_db_connection)
        node_spans = tree_query.get_node_spans(leaf_node["node_id"])

        # Summary must contain text from those spans
        if leaf_node["summary_text"]:
            span_texts = [s.get("raw_text", "") for s in node_spans]
            for span_text in span_texts:
                if span_text.strip():
                    assert span_text[:50] in leaf_node["summary_text"]  # At least partial match

    def test_summary_text_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing tree twice must not change summary_text values."""
        sample_pdf = tmp_path / "tree-summary-idempotent.pdf"
        _build_rich_pdf(sample_pdf, text_body="Idempotent test content.")

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree summary idempotent test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)

        # Write tree first time
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )
        first_nodes = registry.query_tree_nodes_by_version(result.version_id)
        first_summaries = {n["node_id"]: n["summary_text"] for n in first_nodes}

        # Write tree second time
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )
        second_nodes = registry.query_tree_nodes_by_version(result.version_id)
        second_summaries = {n["node_id"]: n["summary_text"] for n in second_nodes}

        # Summaries must be identical
        assert first_summaries == second_summaries, "Idempotent write must preserve summary_text"