"""Tests for Phase 3 Slice 2: leaf->parent rollup query over persisted tree data.

These tests verify:
1. Single-step rollup: leaf node -> parent node
2. Full chain rollup: leaf -> ... -> root (all ancestors)
3. Node-to-span resolution: given a node, retrieve its linked canonical spans
4. Span provenance tracing: given a span, trace back to its tree node and parent chain
5. Edge cases: root node has no parent, nonexistent node, node with no spans

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


class TestRollupToParentUnit:
    """Unit tests for TreeRollupQuery.rollup_to_parent."""

    def test_returns_parent_node_when_parent_exists(self) -> None:
        """A child node must return its parent node dict."""
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # First query: find parent_node_id for the child
            [{"parent_node_id": parent_id}],
            # Second query: fetch the parent node
            [{
                "node_id": parent_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Ch 1",
                "heading_path": "Ch 1",
                "page_start": 1,
                "page_end": 3,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        result = query.rollup_to_parent(child_id)

        assert result is not None
        assert result["node_id"] == parent_id
        assert result["title"] == "Ch 1"

    def test_returns_none_for_root_node(self) -> None:
        """A root node (parent_node_id is None) must return None."""
        root_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # First query: parent_node_id is None
            [{"parent_node_id": None}],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        result = query.rollup_to_parent(root_id)

        assert result is None

    def test_raises_for_nonexistent_node(self) -> None:
        """Querying a node_id that does not exist must raise ValueError."""
        cur = MockCursor()
        cur.set_results([
            # First query: node not found
            [],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        with pytest.raises(ValueError, match="not found"):
            query.rollup_to_parent(uuid.uuid4())


class TestRollupChainUnit:
    """Unit tests for TreeRollupQuery.rollup_chain."""

    def test_returns_leaf_to_root_chain(self) -> None:
        """rollup_chain must return [leaf, parent, ..., root]."""
        root_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        leaf_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        # The implementation will query nodes one at a time walking up.
        # leaf -> parent -> root (parent_node_id=None, stops)
        cur.set_results([
            # Query 1: fetch leaf node
            [{
                "node_id": leaf_id,
                "version_id": version_id,
                "parent_node_id": parent_id,
                "node_type": "section",
                "level_no": 2,
                "title": "1.1.1 Deep",
                "heading_path": "Ch 1 > 1.1 > 1.1.1 Deep",
                "page_start": 1,
                "page_end": 1,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
            # Query 2: fetch parent node
            [{
                "node_id": parent_id,
                "version_id": version_id,
                "parent_node_id": root_id,
                "node_type": "section",
                "level_no": 1,
                "title": "1.1",
                "heading_path": "Ch 1 > 1.1",
                "page_start": 1,
                "page_end": 2,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
            # Query 3: fetch root node
            [{
                "node_id": root_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Ch 1",
                "heading_path": "Ch 1",
                "page_start": 1,
                "page_end": 3,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        chain = query.rollup_chain(leaf_id)

        assert len(chain) == 3
        assert chain[0]["node_id"] == leaf_id
        assert chain[1]["node_id"] == parent_id
        assert chain[2]["node_id"] == root_id

    def test_single_node_chain_for_root(self) -> None:
        """rollup_chain for a root node returns [root] only."""
        root_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            [{
                "node_id": root_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Ch 1",
                "heading_path": "Ch 1",
                "page_start": 1,
                "page_end": 3,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        chain = query.rollup_chain(root_id)

        assert len(chain) == 1
        assert chain[0]["node_id"] == root_id

    def test_raises_for_nonexistent_node(self) -> None:
        """rollup_chain for a node_id that does not exist must raise ValueError."""
        cur = MockCursor()
        cur.set_results([[]])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        with pytest.raises(ValueError, match="not found"):
            query.rollup_chain(uuid.uuid4())

    def test_chain_levels_are_monotonically_decreasing(self) -> None:
        """level_no must decrease (or stay same) as we go from leaf to root."""
        root_id = uuid.uuid4()
        mid_id = uuid.uuid4()
        leaf_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            [{"node_id": leaf_id, "version_id": version_id, "parent_node_id": mid_id, "node_type": "section", "level_no": 2, "title": "L2", "heading_path": "A > B > C", "page_start": None, "page_end": None, "summary_text": None, "created_at": "2025-01-01T00:00:00Z"}],
            [{"node_id": mid_id, "version_id": version_id, "parent_node_id": root_id, "node_type": "section", "level_no": 1, "title": "L1", "heading_path": "A > B", "page_start": None, "page_end": None, "summary_text": None, "created_at": "2025-01-01T00:00:00Z"}],
            [{"node_id": root_id, "version_id": version_id, "parent_node_id": None, "node_type": "chapter", "level_no": 0, "title": "L0", "heading_path": "A", "page_start": None, "page_end": None, "summary_text": None, "created_at": "2025-01-01T00:00:00Z"}],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        chain = query.rollup_chain(leaf_id)

        levels = [node["level_no"] for node in chain]
        assert levels == sorted(levels, reverse=True), "level_no must decrease from leaf to root"


class TestGetNodeSpansUnit:
    """Unit tests for TreeRollupQuery.get_node_spans."""

    def test_returns_spans_linked_to_node(self) -> None:
        """get_node_spans must return canonical spans linked to a tree node."""
        node_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query: get spans for the node
            [
                {
                    "span_id": span_id_1,
                    "span_kind": "paragraph",
                    "start_offset": 0,
                    "end_offset": 10,
                    "page_no": 1,
                    "heading_path": "Ch 1 > 1.1 Intro",
                    "raw_text": "Intro text",
                },
                {
                    "span_id": span_id_2,
                    "span_kind": "paragraph",
                    "start_offset": 11,
                    "end_offset": 20,
                    "page_no": 1,
                    "heading_path": "Ch 1 > 1.1 Intro",
                    "raw_text": "More text",
                },
            ],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        spans = query.get_node_spans(node_id)

        assert len(spans) == 2
        assert spans[0]["span_id"] == span_id_1
        assert spans[1]["span_id"] == span_id_2

    def test_returns_empty_for_node_with_no_spans(self) -> None:
        """A non-leaf node (no spans directly linked) must return an empty list."""
        node_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([[]])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        spans = query.get_node_spans(node_id)

        assert spans == []


class TestResolveSpanProvenanceUnit:
    """Unit tests for TreeRollupQuery.resolve_span_provenance."""

    def test_returns_node_and_chain_for_span(self) -> None:
        """resolve_span_provenance must return the span's tree node and parent chain."""
        root_id = uuid.uuid4()
        leaf_id = uuid.uuid4()
        span_id = uuid.uuid4()
        version_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([
            # Query 1: find the tree_node_spans row for this span
            [{
                "node_id": leaf_id,
                "span_id": span_id,
                "ordinal_no": 0,
            }],
            # Query 2: fetch the leaf node
            [{
                "node_id": leaf_id,
                "version_id": version_id,
                "parent_node_id": root_id,
                "node_type": "section",
                "level_no": 1,
                "title": "1.1 Intro",
                "heading_path": "Ch 1 > 1.1 Intro",
                "page_start": 1,
                "page_end": 1,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
            # Query 3: fetch root node (parent of leaf)
            [{
                "node_id": root_id,
                "version_id": version_id,
                "parent_node_id": None,
                "node_type": "chapter",
                "level_no": 0,
                "title": "Ch 1",
                "heading_path": "Ch 1",
                "page_start": 1,
                "page_end": 3,
                "summary_text": None,
                "created_at": "2025-01-01T00:00:00Z",
            }],
        ])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        provenance = query.resolve_span_provenance(span_id)

        assert provenance is not None
        assert provenance["node"]["node_id"] == leaf_id
        assert len(provenance["chain"]) == 2
        assert provenance["chain"][0]["node_id"] == leaf_id
        assert provenance["chain"][1]["node_id"] == root_id

    def test_returns_none_for_unlinked_span(self) -> None:
        """A span not linked to any tree node must return None."""
        span_id = uuid.uuid4()

        cur = MockCursor()
        cur.set_results([[]])

        conn = MockConnection(cur)
        query = TreeRollupQuery(conn)
        provenance = query.resolve_span_provenance(span_id)

        assert provenance is None


# ===========================================================================
# LIVE TESTS -- require FORMAL_RUNTIME_DATABASE_URL
# ===========================================================================


class TestLiveRollupToParent:
    """Live tests for leaf->parent rollup over persisted tree data."""

    def test_leaf_rollup_to_parent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A leaf node must roll up to its parent with correct heading_path."""
        sample_pdf = tmp_path / "rollup-leaf.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Rollup leaf test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a leaf node (one that has spans linked to it)
        node_spans = tree["node_spans"]
        leaf_node_id = node_spans[0]["node_id"]

        parent = query.rollup_to_parent(leaf_node_id)
        # If the leaf has a parent, it must be a valid node
        # If there is only one level, parent may be None
        if parent is not None:
            assert isinstance(parent["node_id"], uuid.UUID)
            assert parent["heading_path"] is not None

    def test_root_node_rollup_returns_none(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A root node (level 0) must return None from rollup_to_parent."""
        sample_pdf = tmp_path / "rollup-root.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Rollup root test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find a root node
        root_nodes = [n for n in tree["nodes"] if n["parent_node_id"] is None]
        assert len(root_nodes) > 0, "Must have at least one root node"

        for root_node in root_nodes:
            parent = query.rollup_to_parent(root_node["node_id"])
            assert parent is None, f"Root node {root_node['title']} must have no parent"

    def test_nonexistent_node_raises(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Querying a nonexistent node_id must raise ValueError."""
        query = TreeRollupQuery(live_db_connection)
        with pytest.raises(ValueError, match="not found"):
            query.rollup_to_parent(uuid.uuid4())


class TestLiveRollupChain:
    """Live tests for full chain rollup from leaf to root."""

    def test_full_chain_from_leaf_to_root(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """rollup_chain must return the complete path from leaf to root."""
        sample_pdf = tmp_path / "rollup-chain.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Rollup chain test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find the deepest leaf node
        node_spans = tree["node_spans"]
        leaf_node_id = node_spans[0]["node_id"]

        chain = query.rollup_chain(leaf_node_id)
        assert len(chain) >= 1, "Chain must have at least the starting node"

        # First element must be the leaf
        assert chain[0]["node_id"] == leaf_node_id

        # Last element must be a root (parent_node_id is None)
        assert chain[-1]["parent_node_id"] is None, "Last element must be a root node"

        # Chain must be ordered by decreasing level_no
        levels = [node["level_no"] for node in chain]
        assert levels == sorted(levels, reverse=True), "Chain must be ordered leaf-to-root"

    def test_chain_with_deep_hierarchy(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A tree with multiple levels must produce a chain that traverses all of them.

        We seed a tree with a known deep hierarchy by manually inserting
        tree_nodes with a 4-level path.
        """
        version_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        contract_id = uuid.uuid4()

        with live_db_connection.transaction(), live_db_connection.cursor() as cur:
            # Insert minimal document/version scaffolding
            cur.execute(
                "INSERT INTO documents (doc_id, source_uri, title, doc_type) VALUES (%s, %s, %s, %s)",
                (str(doc_id), "file:///rollup-deep.pdf", "Deep tree test", "document"),
            )
            cur.execute(
                "INSERT INTO normalization_contracts (normalization_contract_id, parser_name, parser_version, offset_basis, notes) VALUES (%s, %s, %s, %s, %s)",
                (str(contract_id), "Test", "1.0", "char", "test"),
            )
            cur.execute(
                "INSERT INTO document_versions (version_id, doc_id, content_hash, version_no, normalization_contract_id, is_active, status, activated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, now())",
                (str(version_id), str(doc_id), "deep-tree-hash", 1, str(contract_id), True, "active"),
            )

            # Create a 4-level hierarchy: L0 -> L1 -> L2 -> L3
            root_id = uuid.uuid4()
            l1_id = uuid.uuid4()
            l2_id = uuid.uuid4()
            l3_id = uuid.uuid4()

            nodes_data = [
                (str(root_id), str(version_id), None, "chapter", 0, "Root", "Root", None, None, None),
                (str(l1_id), str(version_id), str(root_id), "section", 1, "L1", "Root > L1", None, None, None),
                (str(l2_id), str(version_id), str(l1_id), "section", 2, "L2", "Root > L1 > L2", None, None, None),
                (str(l3_id), str(version_id), str(l2_id), "section", 3, "L3", "Root > L1 > L2 > L3", None, None, None),
            ]
            for node_data in nodes_data:
                cur.execute(
                    "INSERT INTO tree_nodes (node_id, version_id, parent_node_id, node_type, level_no, title, heading_path, page_start, page_end, summary_text) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    node_data,
                )

        query = TreeRollupQuery(live_db_connection)
        chain = query.rollup_chain(l3_id)

        assert len(chain) == 4, f"Expected 4 nodes in chain, got {len(chain)}"
        assert chain[0]["title"] == "L3"
        assert chain[1]["title"] == "L2"
        assert chain[2]["title"] == "L1"
        assert chain[3]["title"] == "Root"

        # Verify parent chain integrity
        for i in range(len(chain) - 1):
            child = chain[i]
            parent = chain[i + 1]
            assert child["parent_node_id"] == parent["node_id"], (
                f"Chain broken at index {i}: child parent_node_id={child['parent_node_id']} "
                f"!= parent node_id={parent['node_id']}"
            )


class TestLiveNodeSpans:
    """Live tests for retrieving canonical spans linked to a tree node."""

    def test_leaf_node_spans_match_canonical_spans(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Spans retrieved via get_node_spans must match the canonical spans."""
        sample_pdf = tmp_path / "node-spans.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Node spans test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # For each leaf node, verify its spans
        node_spans = tree["node_spans"]
        # Group by node_id
        from collections import defaultdict
        node_to_span_ids = defaultdict(set)
        for ns in node_spans:
            node_to_span_ids[ns["node_id"]].add(ns["span_id"])

        for node_id, expected_span_ids in node_to_span_ids.items():
            retrieved_spans = query.get_node_spans(node_id)
            retrieved_span_ids = {s["span_id"] for s in retrieved_spans}
            assert retrieved_span_ids == expected_span_ids, (
                f"Node {node_id}: expected span_ids {expected_span_ids}, "
                f"got {retrieved_span_ids}"
            )

    def test_nonleaf_node_has_no_direct_spans(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A non-leaf node (parent only) should have no direct span links in tree_node_spans."""
        sample_pdf = tmp_path / "nonleaf-spans.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Nonleaf spans test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Find nodes that appear as parents but NOT in node_spans
        leaf_node_ids = {ns["node_id"] for ns in tree["node_spans"]}
        parent_only_nodes = [
            n for n in tree["nodes"]
            if n["parent_node_id"] is not None and n["node_id"] not in leaf_node_ids
        ]

        # If there are parent-only nodes, verify they have no direct spans
        for node in parent_only_nodes:
            retrieved_spans = query.get_node_spans(node["node_id"])
            assert retrieved_spans == [], (
                f"Non-leaf node {node['title']} should have no direct spans"
            )


class TestLiveSpanProvenance:
    """Live tests for span provenance tracing back to tree hierarchy."""

    def test_span_provenance_includes_node_and_chain(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """resolve_span_provenance must return the node and full parent chain."""
        sample_pdf = tmp_path / "provenance-chain.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Provenance chain test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Pick a span and trace its provenance
        first_span = spans[0]
        provenance = query.resolve_span_provenance(first_span["span_id"])

        assert provenance is not None, "Span must have provenance"

        # The node must match the leaf node this span is linked to
        node = provenance["node"]
        assert isinstance(node["node_id"], uuid.UUID)

        # The chain must include the node and its ancestors
        chain = provenance["chain"]
        assert len(chain) >= 1
        assert chain[0]["node_id"] == node["node_id"]

        # The last element must be a root
        assert chain[-1]["parent_node_id"] is None

    def test_span_provenance_heading_path_matches(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """The heading_path of the provenance node must match the span's heading_path."""
        sample_pdf = tmp_path / "provenance-heading.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Provenance heading test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # For each span, verify the provenance node's heading_path matches
        for span in spans:
            span_heading = span.get("heading_path") or "(root)"
            provenance = query.resolve_span_provenance(span["span_id"])
            if provenance is not None:
                node_heading = provenance["node"]["heading_path"]
                assert node_heading == span_heading, (
                    f"Span heading_path '{span_heading}' does not match "
                    f"node heading_path '{node_heading}'"
                )

    def test_unlinked_span_returns_none(
        self, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """A span_id not in tree_node_spans must return None from resolve_span_provenance."""
        query = TreeRollupQuery(live_db_connection)
        result = query.resolve_span_provenance(uuid.uuid4())
        assert result is None

    def test_provenance_chain_heading_paths_are_prefixes(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Each ancestor's heading_path must be a prefix of the leaf's heading_path."""
        sample_pdf = tmp_path / "provenance-prefix.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Provenance prefix test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        for span in spans:
            provenance = query.resolve_span_provenance(span["span_id"])
            if provenance is not None and len(provenance["chain"]) > 1:
                leaf_heading = provenance["chain"][0]["heading_path"]
                for ancestor in provenance["chain"][1:]:
                    # Each ancestor's heading_path must be a prefix of the leaf
                    assert leaf_heading.startswith(ancestor["heading_path"]), (
                        f"Ancestor heading_path '{ancestor['heading_path']}' "
                        f"is not a prefix of leaf heading_path '{leaf_heading}'"
                    )
