"""Tests for Phase 3 Slice 3: multi-granular tree expansion over persisted data.

These tests verify expansion methods:
1. expand_children: get all children of a node
2. expand_siblings: get all siblings of a node (same parent)
3. expand_adjacent: get nodes adjacent in sequence (page proximity)
4. Edge cases: root node, leaf node, nonexistent node, empty results

Unit tests use a mock cursor and run without a database.
Live tests require FORMAL_RUNTIME_DATABASE_URL to be set.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from okf._e2a_pipeline_testkit import _FakeReconciler

from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.tree.query import TreeRollupQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


# ---------------------------------------------------------------------------
# Mock cursor/connection for unit tests
# ---------------------------------------------------------------------------


class MockCursor:
    """Minimal mock cursor that records execute calls and returns configured rows."""

    def __init__(self) -> None:
        self._rows: list[list[dict[str, Any]]] = []
        self._row_index = 0
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        if self._row_index < len(self._rows):
            batch = self._rows[self._row_index]
            self._row_index += 1
            return batch[0] if batch else None
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        if self._row_index < len(self._rows):
            batch = self._rows[self._row_index]
            self._row_index += 1
            return batch
        return []

    def set_results(self, rows: list[list[dict[str, Any]]]) -> None:
        self._rows = rows
        self._row_index = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockConnection:
    """Minimal mock psycopg connection for unit tests."""

    def __init__(self, cursor: MockCursor | None = None) -> None:
        self._cursor = cursor or MockCursor()

    def cursor(self, row_factory=None):
        return self._cursor


# ===========================================================================
# UNIT TESTS -- mocked database, no PostgreSQL required
# ===========================================================================


class TestExpandChildrenUnit:
    """Unit tests for TreeRollupQuery.expand_children."""

    def test_returns_children_of_parent_node(self) -> None:
        """A parent node must return all its children."""
        parent_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: verify parent exists
            [{
                "node_id": parent_id,
            }],
            # Query 2: fetch children (parent_node_id = parent_id)
            [
                {
                    "node_id": child1_id,
                    "version_id": version_id,
                    "parent_node_id": parent_id,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.1",
                    "heading_path": "Ch 1 > 1.1",
                    "page_start": 1,
                    "page_end": 2,
                    "summary_text": "child1 summary",
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "node_id": child2_id,
                    "version_id": version_id,
                    "parent_node_id": parent_id,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.2",
                    "heading_path": "Ch 1 > 1.2",
                    "page_start": 3,
                    "page_end": 4,
                    "summary_text": "child2 summary",
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        children = query.expand_children(parent_id)

        assert len(children) == 2
        assert children[0]["node_id"] == child1_id
        assert children[1]["node_id"] == child2_id
        assert all(c["parent_node_id"] == parent_id for c in children)

    def test_returns_empty_for_leaf_node(self) -> None:
        """A leaf node (no children) must return an empty list."""
        leaf_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: verify leaf exists
            [{
                "node_id": leaf_id,
            }],
            # Query 2: fetch children (empty result)
            [],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        children = query.expand_children(leaf_id)

        assert children == []

    def test_raises_for_nonexistent_node(self) -> None:
        """Expanding children of a nonexistent node_id must raise ValueError."""
        cur = MockCursor()
        cur.set_results([
            # Query: node not found
            [],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        with pytest.raises(ValueError, match="not found"):
            query.expand_children(uuid.uuid4())


class TestExpandSiblingsUnit:
    """Unit tests for TreeRollupQuery.expand_siblings."""

    def test_returns_all_siblings_including_self(self) -> None:
        """Siblings must include the node itself and all nodes with same parent."""
        parent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        sibling1_id = uuid.uuid4()
        sibling2_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: find parent_node_id for the node
            [{"parent_node_id": parent_id}],
            # Query 2: fetch all siblings with same parent
            [
                {
                    "node_id": sibling1_id,
                    "version_id": version_id,
                    "parent_node_id": parent_id,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.1",
                    "heading_path": "Ch 1 > 1.1",
                    "page_start": 1,
                    "page_end": 2,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "node_id": node_id,
                    "version_id": version_id,
                    "parent_node_id": parent_id,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.2",
                    "heading_path": "Ch 1 > 1.2",
                    "page_start": 3,
                    "page_end": 4,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "node_id": sibling2_id,
                    "version_id": version_id,
                    "parent_node_id": parent_id,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.3",
                    "heading_path": "Ch 1 > 1.3",
                    "page_start": 5,
                    "page_end": 6,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        siblings = query.expand_siblings(node_id)

        assert len(siblings) == 3
        sibling_ids = {s["node_id"] for s in siblings}
        assert sibling_ids == {sibling1_id, node_id, sibling2_id}

    def test_returns_only_self_for_root_node(self) -> None:
        """A root node (parent_node_id=None) has no siblings except itself."""
        root_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: parent_node_id is None (root)
            [{"parent_node_id": None}],
            # Query 2: siblings are nodes with parent_node_id=None
            [
                {
                    "node_id": root_id,
                    "version_id": version_id,
                    "parent_node_id": None,
                    "node_type": "chapter",
                    "level_no": 0,
                    "title": "Ch 1",
                    "heading_path": "Ch 1",
                    "page_start": 1,
                    "page_end": 10,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        siblings = query.expand_siblings(root_id)

        assert len(siblings) == 1
        assert siblings[0]["node_id"] == root_id

    def test_raises_for_nonexistent_node(self) -> None:
        """Expanding siblings of a nonexistent node_id must raise ValueError."""
        cur = MockCursor()
        cur.set_results([[]])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        with pytest.raises(ValueError, match="not found"):
            query.expand_siblings(uuid.uuid4())


class TestExpandAdjacentUnit:
    """Unit tests for TreeRollupQuery.expand_adjacent."""

    def test_returns_adjacent_nodes_by_page_proximity(self) -> None:
        """expand_adjacent must return nodes within page_range threshold."""
        node_id = uuid.uuid4()
        adjacent1_id = uuid.uuid4()
        adjacent2_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: fetch the target node to get page_start/page_end
            [{
                "node_id": node_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "section",
                "level_no": 1,
                "title": "1.1",
                "heading_path": "Ch 1 > 1.1",
                "page_start": 5,
                "page_end": 7,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
            # Query 2: fetch adjacent nodes within page threshold
            [
                {
                    "node_id": adjacent1_id,
                    "version_id": version_id,
                    "parent_node_id": None,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.2",
                    "heading_path": "Ch 1 > 1.2",
                    "page_start": 8,
                    "page_end": 9,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "node_id": adjacent2_id,
                    "version_id": version_id,
                    "parent_node_id": None,
                    "node_type": "section",
                    "level_no": 1,
                    "title": "1.3",
                    "heading_path": "Ch 1 > 1.3",
                    "page_start": 10,
                    "page_end": 11,
                    "summary_text": None,
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        adjacent = query.expand_adjacent(node_id, page_threshold=5)

        assert len(adjacent) == 2
        assert adjacent[0]["node_id"] == adjacent1_id
        assert adjacent[1]["node_id"] == adjacent2_id

    def test_returns_empty_for_isolated_node(self) -> None:
        """A node with no nearby pages must return an empty list."""
        node_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: fetch target node
            [{
                "node_id": node_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "section",
                "level_no": 1,
                "title": "1.1",
                "heading_path": "Ch 1 > 1.1",
                "page_start": 100,
                "page_end": 105,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
            # Query 2: no adjacent nodes within threshold
            [],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        adjacent = query.expand_adjacent(node_id, page_threshold=3)

        assert adjacent == []

    def test_raises_for_nonexistent_node(self) -> None:
        """Expanding adjacent nodes for nonexistent node_id must raise ValueError."""
        cur = MockCursor()
        cur.set_results([[]])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        with pytest.raises(ValueError, match="not found"):
            query.expand_adjacent(uuid.uuid4(), page_threshold=5)


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveExpandChildren:
    """Live tests for child expansion over persisted tree data."""

    def test_parent_node_has_children(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A parent node must expand to its children."""
        sample_pdf = tmp_path / "expand-children.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Expand children test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a parent node (one that appears as parent_node_id in other nodes)
        parent_ids = {n["parent_node_id"] for n in tree["nodes"] if n["parent_node_id"] is not None}
        if parent_ids:
            parent_id = list(parent_ids)[0]
            children = query.expand_children(parent_id)

            assert len(children) > 0, "Parent must have at least one child"
            assert all(c["parent_node_id"] == parent_id for c in children), (
                "All children must have the same parent"
            )

    def test_leaf_node_has_no_children(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A leaf node (with spans) must expand to an empty children list."""
        sample_pdf = tmp_path / "expand-leaf.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Expand leaf test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a leaf node (one in node_spans)
        leaf_node_id = tree["node_spans"][0]["node_id"]
        children = query.expand_children(leaf_node_id)

        # Leaf nodes have no children by definition
        assert children == [], f"Leaf node {leaf_node_id} should have no children"


class TestLiveExpandSiblings:
    """Live tests for sibling expansion over persisted tree data."""

    def test_node_has_siblings_including_self(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Siblings must include the node itself and all nodes with the same parent."""
        sample_pdf = tmp_path / "expand-siblings.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Expand siblings test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a non-root node
        non_root_nodes = [n for n in tree["nodes"] if n["parent_node_id"] is not None]
        if non_root_nodes:
            target_node = non_root_nodes[0]
            siblings = query.expand_siblings(target_node["node_id"])

            # Must include itself
            sibling_ids = {s["node_id"] for s in siblings}
            assert target_node["node_id"] in sibling_ids, "Siblings must include self"

            # All must have same parent
            assert all(s["parent_node_id"] == target_node["parent_node_id"] for s in siblings), (
                "All siblings must have the same parent"
            )


class TestLiveExpandAdjacent:
    """Live tests for adjacent expansion over persisted tree data."""

    def test_adjacent_nodes_by_page(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Adjacent nodes must be within page threshold."""
        sample_pdf = tmp_path / "expand-adjacent.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Expand adjacent test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a node with page info
        nodes_with_pages = [n for n in tree["nodes"] if n.get("page_start") is not None]
        if nodes_with_pages:
            target_node = nodes_with_pages[0]
            adjacent = query.expand_adjacent(target_node["node_id"], page_threshold=5)

            # All adjacent nodes must be within threshold
            target_page = target_node.get("page_start", 0)
            for adj_node in adjacent:
                adj_page = adj_node.get("page_start")
                if adj_page is not None:
                    assert abs(adj_page - target_page) <= 5, (
                        f"Adjacent node page {adj_page} not within threshold of {target_page}"
                    )