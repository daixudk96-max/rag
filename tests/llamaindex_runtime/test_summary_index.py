"""Tests for P5 Summary Index Slice: first-class summary view/index.

These tests verify:
1. SummaryIndex creates summary entities from tree nodes
2. Summary entities persist to database via registry
3. Summary entities can be queried by version_id
4. Summary entities can be queried by keyword search
5. retrieve_summary_hits returns QueryHit objects

This is a separate view from existing tree.summary_text:
- Tree summary_text is embedded in tree nodes
- Summary index is a first-class queryable entity

Unit tests use SummaryIndex in isolation.
Live tests require FORMAL_RUNTIME_DATABASE_URL.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.registry.tree_generator import TreeGenerator

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
# UNIT TESTS -- SummaryIndex creation (no database)
# ===========================================================================


class TestSummaryIndexCreation:
    """Core SummaryIndex behavior: create summary entities from tree nodes."""

    def test_summary_index_exists(self) -> None:
        """SummaryIndex class must exist in summary module."""
        from llamaindex_runtime.summary import SummaryIndex

        assert SummaryIndex is not None

    def test_summary_index_creates_from_tree_nodes(self) -> None:
        """SummaryIndex must create summary entities from tree nodes."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="First paragraph."),
            _make_span(version_id=version_id, heading_path="Ch 1", text="Second paragraph."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.summary import SummaryIndex

        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=version_id,
        )

        assert len(summaries) > 0, "SummaryIndex must produce summary entities"

    def test_summary_entity_has_required_fields(self) -> None:
        """Each summary entity must have summary_id, version_id, node_id, summary_text."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Test content."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.summary import SummaryIndex

        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=version_id,
        )

        summary = summaries[0]
        assert "summary_id" in summary, "Summary must have summary_id"
        assert "version_id" in summary, "Summary must have version_id"
        assert "node_id" in summary, "Summary must have node_id (reference to tree node)"
        assert "summary_text" in summary, "Summary must have summary_text"
        assert summary["version_id"] == version_id

    def test_summary_text_matches_node_summary(self) -> None:
        """Summary entity text must match the corresponding tree node summary_text."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Expected summary."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.summary import SummaryIndex

        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=version_id,
        )

        node = tree["nodes"][0]
        summary = summaries[0]
        assert summary["summary_text"] == node["summary_text"]

    def test_summary_id_is_deterministic(self) -> None:
        """Summary ID must be deterministic uuid5 based on version_id and node_id."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", text="Test."),
        ]
        tree = TreeGenerator().generate(spans, version_id=version_id)

        from llamaindex_runtime.summary import SummaryIndex

        summary_index = SummaryIndex()
        summaries1 = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=version_id,
        )
        summaries2 = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=version_id,
        )

        # Same inputs must produce same summary_ids
        assert summaries1[0]["summary_id"] == summaries2[0]["summary_id"]

    def test_empty_tree_produces_empty_summaries(self) -> None:
        """Empty tree nodes must produce empty summary list."""
        version_id = uuid.uuid4()

        from llamaindex_runtime.summary import SummaryIndex

        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=[],
            version_id=version_id,
        )

        assert summaries == []


# ===========================================================================
# RETRIEVAL TESTS -- retrieve_summary_hits
# ===========================================================================


class TestSummaryRetrieval:
    """Summary retrieval: retrieve_summary_hits returns QueryHit objects."""

    def test_retrieve_summary_hits_exists(self) -> None:
        """retrieve_summary_hits function must exist in summary module."""
        from llamaindex_runtime.summary import retrieve_summary_hits

        assert retrieve_summary_hits is not None

    def test_retrieve_summary_hits_requires_registry(self) -> None:
        """retrieve_summary_hits must require registry parameter."""
        from llamaindex_runtime.summary import retrieve_summary_hits

        with pytest.raises(ValueError, match="registry is required"):
            retrieve_summary_hits(
                registry=None,
                query="test query",
            )

    def test_retrieve_summary_hits_requires_query(self) -> None:
        """retrieve_summary_hits must require query parameter."""
        from llamaindex_runtime.summary import retrieve_summary_hits

        mock_registry = MagicMock()
        with pytest.raises(ValueError, match="query must not be empty"):
            retrieve_summary_hits(
                registry=mock_registry,
                query="",
            )

    def test_retrieve_summary_hits_returns_query_hits(self) -> None:
        """retrieve_summary_hits must return list of QueryHit objects."""
        from llamaindex_runtime.summary import retrieve_summary_hits
        from llamaindex_runtime.entrypoints.types import QueryHit

        mock_registry = MagicMock()
        mock_registry.query_summaries_by_keyword.return_value = [
            {
                "summary_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "node_id": uuid.uuid4(),
                "summary_text": "Test summary content.",
                "heading_path": "Ch 1",
                "match_score": 0.95,
            }
        ]

        hits = retrieve_summary_hits(
            registry=mock_registry,
            query="test query",
        )

        assert len(hits) == 1
        assert isinstance(hits[0], QueryHit)
        assert hits[0].text == "Test summary content."
        assert hits[0].score == 0.95


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for summary index test.", fill="black")
    image.save(pdf_path, "PDF")


@pytest.mark.live
class TestLiveSummaryIndexPersistence:
    """Live tests that verify summary index persists correctly to database."""

    def test_write_summaries_persists_to_database(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_summaries must persist summary entities to database."""
        sample_pdf = tmp_path / "summary-index-persist.pdf"
        _build_rich_pdf(sample_pdf, text_body="Live test summary paragraph.")

        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.summary import SummaryIndex

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Summary index test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Build and write summaries
        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=result.version_id,
        )
        registry.write_summaries(
            version_id=result.version_id,
            summaries=summaries,
        )

        # Query back
        persisted = registry.query_summaries_by_version(result.version_id)
        assert len(persisted) > 0
        assert persisted[0]["summary_text"] is not None

    def test_query_summaries_by_keyword_search(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """query_summaries_by_keyword must search summary_text field."""
        sample_pdf = tmp_path / "summary-keyword-search.pdf"
        _build_rich_pdf(sample_pdf, text_body="Unique keyword: algorithm optimization.")

        from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
        from llamaindex_runtime.ingestion import IngestionPipeline
        from llamaindex_runtime.summary import SummaryIndex

        registry = PostgresRegistryWriter(live_db_connection)
        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Summary keyword test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        summary_index = SummaryIndex()
        summaries = summary_index.build_from_tree(
            nodes=tree["nodes"],
            version_id=result.version_id,
        )
        registry.write_summaries(
            version_id=result.version_id,
            summaries=summaries,
        )

        # Search for keyword
        hits = registry.query_summaries_by_keyword(
            query="algorithm",
            version_id=result.version_id,
            limit=10,
        )
        assert len(hits) > 0
        assert "algorithm" in hits[0]["summary_text"].lower()


# ===========================================================================
# REGISTRY CONTRACT TESTS
# ===========================================================================


class TestRegistrySummaryContracts:
    """Registry must implement summary methods."""

    def test_registry_has_write_summaries_method(self) -> None:
        """RegistryWriter protocol must have write_summaries method."""
        from llamaindex_runtime.registry.contracts import RegistryWriter

        # Check protocol has the method signature
        import inspect
        methods = [m[0] for m in inspect.getmembers(RegistryWriter, predicate=inspect.isfunction)]
        # Protocol classes use __call__ for method definitions
        assert hasattr(RegistryWriter, "write_summaries")

    def test_registry_has_query_summaries_by_version(self) -> None:
        """RegistryWriter protocol must have query_summaries_by_version method."""
        from llamaindex_runtime.registry.contracts import RegistryWriter

        assert hasattr(RegistryWriter, "query_summaries_by_version")

    def test_registry_has_query_summaries_by_keyword(self) -> None:
        """RegistryWriter protocol must have query_summaries_by_keyword method."""
        from llamaindex_runtime.registry.contracts import RegistryWriter

        assert hasattr(RegistryWriter, "query_summaries_by_keyword")