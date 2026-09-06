"""Tests for Phase 3 Slice: Tree Persistence from Canonical Spans.

These tests verify:
1. TreeGenerator derives deterministic tree nodes from span heading_path values
2. Every span is covered by a tree_node_span link
3. Parent-child relations persist correctly in the database
4. PostgresRegistryWriter.write_tree persists tree_nodes and tree_node_spans
5. Query methods read back persisted tree data
6. Idempotency: writing tree twice does not duplicate rows
7. Edge cases: empty spans, NULL heading_path, single-level headings, deep hierarchy

Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
Unit tests use the TreeGenerator in isolation and run without a database.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.interfaces import CanonicalSpan
from llamaindex_runtime.registry.contracts import RegisteredDocument, TreeNode, TreeNodeSpan
from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

from okf._e2a_pipeline_testkit import _FakeReconciler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# UNIT TESTS -- TreeGenerator in isolation, no database required
# ===========================================================================


class TestTreeGeneratorBasic:
    """Core TreeGenerator behavior: nodes, node_spans, and coverage."""

    def test_generate_returns_nodes_and_node_spans(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        assert "nodes" in result
        assert "node_spans" in result
        assert len(result["nodes"]) > 0
        assert len(result["node_spans"]) > 0

    def test_spans_with_same_heading_path_share_leaf_node(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        # Both spans should link to the same leaf node
        leaf_node_ids = {ns["node_id"] for ns in result["node_spans"]}
        assert len(leaf_node_ids) == 1, "Spans with same heading_path must share one leaf node"

    def test_parent_child_relation_from_heading_path(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        nodes = result["nodes"]
        # "Ch 1 > 1.1 Intro" produces: "Ch 1" (level 0) and "Ch 1 > 1.1 Intro" (level 1)
        assert len(nodes) == 2, f"Expected 2 nodes (parent + child), got {len(nodes)}"
        parent = [n for n in nodes if n["level_no"] == 0][0]
        child = [n for n in nodes if n["level_no"] == 1][0]
        assert child["parent_node_id"] == parent["node_id"]
        assert parent["parent_node_id"] is None

    def test_every_span_is_covered_by_node_span(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.2 Methods"),
            _make_span(version_id=version_id, heading_path="Ch 2 > 2.1 Results"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        covered_span_ids = {ns["span_id"] for ns in result["node_spans"]}
        input_span_ids = {s["span_id"] for s in spans}
        assert covered_span_ids == input_span_ids, "Every input span must be covered by a node_span link"

    def test_deterministic_node_ids(self) -> None:
        """Same input must produce same node_ids (uuid5-based)."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro"),
        ]
        result1 = TreeGenerator().generate(spans, version_id=version_id)
        result2 = TreeGenerator().generate(spans, version_id=version_id)
        ids1 = [n["node_id"] for n in result1["nodes"]]
        ids2 = [n["node_id"] for n in result2["nodes"]]
        assert ids1 == ids2, "Same input must produce identical node_ids"


class TestTreeGeneratorNodeTypes:
    """Verify node_type, level_no, title, heading_path fields."""

    def test_chapter_at_level_0(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro")]
        result = TreeGenerator().generate(spans, version_id=version_id)
        level_0_nodes = [n for n in result["nodes"] if n["level_no"] == 0]
        assert len(level_0_nodes) == 1
        assert level_0_nodes[0]["node_type"] == "chapter"
        assert level_0_nodes[0]["title"] == "Ch 1"

    def test_section_at_deeper_levels(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro")]
        result = TreeGenerator().generate(spans, version_id=version_id)
        deeper_nodes = [n for n in result["nodes"] if n["level_no"] > 0]
        assert len(deeper_nodes) >= 1
        for node in deeper_nodes:
            assert node["node_type"] == "section"

    def test_heading_path_field_on_node(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Ch 1 > 1.1 Intro")]
        result = TreeGenerator().generate(spans, version_id=version_id)
        heading_paths = {n["heading_path"] for n in result["nodes"]}
        assert "Ch 1" in heading_paths
        assert "Ch 1 > 1.1 Intro" in heading_paths


class TestTreeGeneratorEdgeCases:
    """Edge cases: empty, null heading, single level, deep hierarchy."""

    def test_empty_spans_returns_empty(self) -> None:
        version_id = uuid.uuid4()
        result = TreeGenerator().generate([], version_id=version_id)
        assert result["nodes"] == []
        assert result["node_spans"] == []

    def test_null_heading_path_creates_root_node(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path=None)]
        result = TreeGenerator().generate(spans, version_id=version_id)
        assert len(result["nodes"]) == 1
        root_node = result["nodes"][0]
        assert root_node["level_no"] == 0
        assert root_node["title"] == "(root)"
        assert root_node["parent_node_id"] is None

    def test_single_level_heading(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Chapter One")]
        result = TreeGenerator().generate(spans, version_id=version_id)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["title"] == "Chapter One"
        assert result["nodes"][0]["level_no"] == 0

    def test_deep_hierarchy(self) -> None:
        version_id = uuid.uuid4()
        spans = [_make_span(version_id=version_id, heading_path="Ch 1 > 1.1 > 1.1.1 > 1.1.1.1 Deep")]
        result = TreeGenerator().generate(spans, version_id=version_id)
        assert len(result["nodes"]) == 4, "Four heading parts must produce four nodes"
        # Parent chain must be intact
        for i in range(1, len(result["nodes"])):
            child = [n for n in result["nodes"] if n["level_no"] == i][0]
            parent = [n for n in result["nodes"] if n["level_no"] == i - 1][0]
            assert child["parent_node_id"] == parent["node_id"]

    def test_page_range_from_spans(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", page_no=1),
            _make_span(version_id=version_id, heading_path="Ch 1", page_no=3),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        # The leaf node for "Ch 1" should have page_start=1, page_end=3
        leaf_node = result["nodes"][0]
        assert leaf_node["page_start"] == 1
        assert leaf_node["page_end"] == 3

    def test_spans_with_none_page_no(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1", page_no=None),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        leaf_node = result["nodes"][0]
        assert leaf_node["page_start"] is None
        assert leaf_node["page_end"] is None

    def test_multiple_chapters_share_no_parent(self) -> None:
        """Two different top-level chapters must both have parent_node_id=None."""
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1"),
            _make_span(version_id=version_id, heading_path="Ch 2"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        level_0_nodes = [n for n in result["nodes"] if n["level_no"] == 0]
        assert len(level_0_nodes) == 2
        for node in level_0_nodes:
            assert node["parent_node_id"] is None

    def test_ordinal_no_increments_per_leaf(self) -> None:
        version_id = uuid.uuid4()
        spans = [
            _make_span(version_id=version_id, heading_path="Ch 1"),
            _make_span(version_id=version_id, heading_path="Ch 1"),
            _make_span(version_id=version_id, heading_path="Ch 1"),
        ]
        result = TreeGenerator().generate(spans, version_id=version_id)
        ordinals = [ns["ordinal_no"] for ns in result["node_spans"]]
        assert sorted(ordinals) == [0, 1, 2]


# ===========================================================================
# UNIT TESTS -- TreeNode and TreeNodeSpan contracts
# ===========================================================================


class TestTreeNodeContract:
    def test_frozen_dataclass(self) -> None:
        node = TreeNode(
            node_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            parent_node_id=None,
            node_type="chapter",
            level_no=0,
            title="Ch 1",
            heading_path="Ch 1",
            page_start=1,
            page_end=3,
            summary_text=None,
        )
        with pytest.raises(AttributeError):
            node.title = "modified"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        node = TreeNode(
            node_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            parent_node_id=uuid.uuid4(),
            node_type="section",
            level_no=1,
            title="1.1",
            heading_path="Ch 1 > 1.1",
            page_start=None,
            page_end=None,
            summary_text=None,
        )
        assert isinstance(node.node_id, uuid.UUID)
        assert isinstance(node.version_id, uuid.UUID)
        assert isinstance(node.parent_node_id, uuid.UUID)
        assert node.node_type == "section"
        assert node.level_no == 1


class TestTreeNodeSpanContract:
    def test_frozen_dataclass(self) -> None:
        ns = TreeNodeSpan(
            node_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            ordinal_no=0,
        )
        with pytest.raises(AttributeError):
            ns.ordinal_no = 5  # type: ignore[misc]

    def test_required_fields(self) -> None:
        ns = TreeNodeSpan(
            node_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            ordinal_no=3,
        )
        assert isinstance(ns.node_id, uuid.UUID)
        assert isinstance(ns.span_id, uuid.UUID)
        assert ns.ordinal_no == 3


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


class TestLiveTreePersistence:
    """Live tests that verify tree_nodes and tree_node_spans persist correctly."""

    def test_write_tree_persists_nodes(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_tree must persist tree_nodes rows for a version."""
        sample_pdf = tmp_path / "tree-persist.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree persist test")

        # Generate tree from persisted spans
        spans = registry.query_spans_by_version(result.version_id)
        generator = TreeGenerator()
        tree = generator.generate(spans, version_id=result.version_id)

        # Write tree
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Read back and verify
        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        assert len(persisted_nodes) == len(tree["nodes"]), (
            f"Persisted {len(persisted_nodes)} nodes, expected {len(tree['nodes'])}"
        )

    def test_write_tree_persists_node_spans_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """write_tree must persist tree_node_spans rows linking nodes to spans."""
        sample_pdf = tmp_path / "tree-spans-link.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree span link test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_spans = registry.query_tree_node_spans_by_version(result.version_id)
        assert len(persisted_spans) == len(tree["node_spans"]), (
            f"Persisted {len(persisted_spans)} node_spans, expected {len(tree['node_spans'])}"
        )

    def test_every_span_covered_by_tree_node_span(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every canonical span must be linked to a tree node via tree_node_spans."""
        sample_pdf = tmp_path / "tree-coverage.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree coverage test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        span_ids_in_db = {s["span_id"] for s in spans}
        covered_span_ids = {ns["span_id"] for ns in registry.query_tree_node_spans_by_version(result.version_id)}
        assert covered_span_ids == span_ids_in_db, (
            f"Not all spans are covered. Missing: {span_ids_in_db - covered_span_ids}"
        )

    def test_parent_child_relations_persist(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Parent-child FK in tree_nodes must be valid after write_tree."""
        sample_pdf = tmp_path / "tree-parent-child.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree parent child test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        node_ids = {n["node_id"] for n in persisted_nodes}
        for node in persisted_nodes:
            if node["parent_node_id"] is not None:
                assert node["parent_node_id"] in node_ids, (
                    f"parent_node_id {node['parent_node_id']} not found in persisted nodes"
                )

    def test_write_tree_idempotent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Writing tree twice must not duplicate rows."""
        sample_pdf = tmp_path / "tree-idempotent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree idempotent test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)

        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )
        # Write again
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        persisted_spans = registry.query_tree_node_spans_by_version(result.version_id)
        assert len(persisted_nodes) == len(tree["nodes"]), (
            "Idempotent write must not duplicate tree_nodes"
        )
        assert len(persisted_spans) == len(tree["node_spans"]), (
            "Idempotent write must not duplicate tree_node_spans"
        )

    def test_cascade_delete_version_removes_tree(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Deleting a document version must cascade to tree_nodes and tree_node_spans."""
        sample_pdf = tmp_path / "tree-cascade.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree cascade test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Verify tree exists
        assert len(registry.query_tree_nodes_by_version(result.version_id)) > 0

        # Delete the version via cascade
        with live_db_connection.cursor() as cur:
            cur.execute(
                "DELETE FROM document_versions WHERE version_id = %s",
                (str(result.version_id),),
            )

        # Tree must be gone
        assert len(registry.query_tree_nodes_by_version(result.version_id)) == 0
        assert len(registry.query_tree_node_spans_by_version(result.version_id)) == 0

    def test_query_tree_nodes_returns_correct_fields(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """query_tree_nodes_by_version must return all tree_nodes columns as UUID types."""
        sample_pdf = tmp_path / "tree-fields.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Tree fields test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        persisted_nodes = registry.query_tree_nodes_by_version(result.version_id)
        assert len(persisted_nodes) > 0
        node = persisted_nodes[0]
        # UUID fields must be uuid.UUID instances
        assert isinstance(node["node_id"], uuid.UUID)
        assert isinstance(node["version_id"], uuid.UUID)
        # Required fields must be present
        assert "node_type" in node
        assert "level_no" in node
        assert "title" in node
        assert "heading_path" in node
