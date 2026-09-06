"""PageIndex-style evaluation slice for tree_nodes / tree_node_spans / rollup/query behavior.

This test-only comparison evaluates whether the current tree implementation satisfies
PageIndex-style database catalog-tree expectations. It does NOT modify runtime code
unless a minimal bug fix is absolutely required.

Focus areas:
1. Page-level coverage completeness across page_start/page_end and span page_no
2. Tree depth integrity vs heading_path nesting
3. Span-to-node bidirectional integrity
4. Rollup chain heading_path prefix consistency

Evaluation-first, not a new runtime module.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from okf._e2a_pipeline_testkit import _FakeReconciler

from llamaindex_runtime.registry.contracts import TreeNode, TreeNodeSpan
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter
from llamaindex_runtime.registry.tree_generator import TreeGenerator
from llamaindex_runtime.tree.query import TreeRollupQuery


# ---------------------------------------------------------------------------
# Mock cursor/connection for unit tests (no database required)
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


def _build_rich_pdf(pdf_path: Path, text_body: str = "default body") -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Formal Runtime Heading", fill="black")
    draw.text((80, 180), text_body, fill="black")
    draw.text((80, 260), "Second paragraph for the formal runtime live ingestion test.", fill="black")
    image.save(pdf_path, "PDF")


# ===========================================================================
# UNIT TESTS (NO DATABASE REQUIRED) - TreeGenerator behavior validation
# ===========================================================================


class TestPageIndexUnit:
    """Unit tests for PageIndex-style expectations using TreeGenerator only."""

    def test_level_no_matches_heading_path_depth_unit(self) -> None:
        """level_no must equal heading_path component count minus 1.

        PageIndex expectation: catalog depth is derived from heading hierarchy.
        """
        version_id = uuid.uuid4()
        spans = [
            {"span_id": uuid.uuid4(), "heading_path": "Chapter 1 > Section 1.1 > Subsection 1.1.1", "page_no": 1, "raw_text": "text 1"},
            {"span_id": uuid.uuid4(), "heading_path": "Chapter 1", "page_no": 1, "raw_text": "text 2"},
        ]

        generator = TreeGenerator()
        # Note: TreeGenerator.generate_tree expects spans as list of dict
        tree = generator.generate_tree(spans, version_id=version_id)

        for node in tree["nodes"]:
            parts = [p.strip() for p in node["heading_path"].split(" > ") if p.strip()]
            if not parts:
                parts = ["(root)"]
            expected_level = len(parts) - 1
            assert node["level_no"] == expected_level, (
                f"Node {node['title']} heading_path='{node['heading_path']}' "
                f"has {len(parts)} parts, expected level_no={expected_level}, "
                f"got level_no={node['level_no']}"
            )

    def test_node_page_range_contains_span_pages_unit(self) -> None:
        """Node page_start/page_end must contain all span page_no values.

        PageIndex expectation: catalog nodes accurately reflect page coverage.
        """
        version_id = uuid.uuid4()
        spans = [
            {"span_id": uuid.uuid4(), "heading_path": "Section A", "page_no": 5, "raw_text": "text"},
            {"span_id": uuid.uuid4(), "heading_path": "Section A", "page_no": 7, "raw_text": "text"},
            {"span_id": uuid.uuid4(), "heading_path": "Section A", "page_no": 6, "raw_text": "text"},
        ]

        generator = TreeGenerator()
        tree = generator.generate_tree(spans, version_id=version_id)

        # Find the "Section A" node
        section_a_nodes = [n for n in tree["nodes"] if n["title"] == "Section A"]
        assert len(section_a_nodes) > 0, "Must find Section A node"

        node = section_a_nodes[0]
        assert node["page_start"] == 5, f"Expected page_start=5, got {node['page_start']}"
        assert node["page_end"] == 7, f"Expected page_end=7, got {node['page_end']}"

    def test_all_spans_linked_to_nodes_unit(self) -> None:
        """Every span must be linked to at least one tree node.

        PageIndex expectation: catalog completeness - no orphan spans.
        """
        version_id = uuid.uuid4()
        span_id_1 = uuid.uuid4()
        span_id_2 = uuid.uuid4()
        span_id_3 = uuid.uuid4()

        spans = [
            {"span_id": span_id_1, "heading_path": "A > B", "page_no": 1, "raw_text": "text 1"},
            {"span_id": span_id_2, "heading_path": "A > C", "page_no": 2, "raw_text": "text 2"},
            {"span_id": span_id_3, "heading_path": "D", "page_no": 3, "raw_text": "text 3"},
        ]

        generator = TreeGenerator()
        tree = generator.generate_tree(spans, version_id=version_id)

        linked_span_ids = {ns["span_id"] for ns in tree["node_spans"]}
        original_span_ids = {s["span_id"] for s in spans}

        assert linked_span_ids == original_span_ids, (
            f"Not all spans are linked to nodes. "
            f"Expected {original_span_ids}, got {linked_span_ids}"
        )

    def test_heading_path_components_match_title_chain_unit(self) -> None:
        """heading_path must be formed by concatenating ancestor titles.

        PageIndex expectation: catalog hierarchy is well-formed.
        """
        version_id = uuid.uuid4()
        spans = [
            {"span_id": uuid.uuid4(), "heading_path": "Root > Parent > Child", "page_no": 1, "raw_text": "text"},
        ]

        generator = TreeGenerator()
        tree = generator.generate_tree(spans, version_id=version_id)

        # For each node, heading_path should match title at that depth
        for node in tree["nodes"]:
            parts = [p.strip() for p in node["heading_path"].split(" > ") if p.strip()]
            if not parts:
                parts = ["(root)"]

            # The title should be the last component
            assert node["title"] == parts[-1], (
                f"Node title '{node['title']}' does not match "
                f"last heading_path component '{parts[-1]}'"
            )

    def test_page_range_none_when_no_page_info_unit(self) -> None:
        """Nodes with spans lacking page_no must have page_start/page_end=None.

        PageIndex expectation: catalog accurately reflects missing metadata.
        """
        version_id = uuid.uuid4()
        spans = [
            {"span_id": uuid.uuid4(), "heading_path": "Test Section", "page_no": None, "raw_text": "text"},
        ]

        generator = TreeGenerator()
        tree = generator.generate_tree(spans, version_id=version_id)

        test_nodes = [n for n in tree["nodes"] if n["title"] == "Test Section"]
        assert len(test_nodes) > 0

        node = test_nodes[0]
        assert node["page_start"] is None, (
            f"Node with no page_no spans should have page_start=None, "
            f"got {node['page_start']}"
        )
        assert node["page_end"] is None, (
            f"Node with no page_no spans should have page_end=None, "
            f"got {node['page_end']}"
        )

    def test_parent_nodes_have_no_direct_span_links_unit(self) -> None:
        """Parent-only nodes must not have direct span links in tree_node_spans.

        PageIndex expectation: parent catalog entries aggregate children,
        not duplicate content.
        """
        version_id = uuid.uuid4()
        # Create spans with a 3-level hierarchy: Root > Parent > Leaf
        spans = [
            {
                "span_id": uuid.uuid4(),
                "heading_path": "Root > Parent > Leaf",
                "page_no": 1,
                "raw_text": "leaf content",
            },
        ]

        generator = TreeGenerator()
        tree = generator.generate_tree(spans, version_id=version_id)

        # Identify which nodes have span links (leaf nodes)
        nodes_with_spans = {ns["node_id"] for ns in tree["node_spans"]}

        # Find parent nodes (nodes that appear in parent_node_id but not in node_spans)
        parent_node_ids = {n["parent_node_id"] for n in tree["nodes"] if n["parent_node_id"] is not None}

        # Parent nodes should NOT have direct span links
        for parent_id in parent_node_ids:
            assert parent_id not in nodes_with_spans, (
                f"Parent node {parent_id} has direct span links, "
                f"but should only aggregate children"
            )

        # Verify leaf node DOES have span links
        leaf_nodes = [n for n in tree["nodes"] if n["title"] == "Leaf"]
        assert len(leaf_nodes) > 0, "Must have a Leaf node"
        assert leaf_nodes[0]["node_id"] in nodes_with_spans, (
            "Leaf node must have direct span links"
        )


# ===========================================================================
# LIVE TESTS (REQUIRE DATABASE)
# ===========================================================================


# ===========================================================================
# PAGE COVERAGE COMPLETENESS
# ===========================================================================


class TestPageCoverageCompleteness:
    """Evaluate whether page_start/page_end covers all span page_no values."""

    def test_node_page_range_contains_all_span_pages(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Each node's page_start/page_end must contain all page_no from its spans.

        PageIndex expectation: catalog nodes must accurately reflect the page range
        of their constituent spans, enabling accurate page-level retrieval.
        """
        sample_pdf = tmp_path / "page-range.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Page range test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Group spans by node_id
        node_to_spans: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
        for ns in tree["node_spans"]:
            span_id = ns["span_id"]
            matching_spans = [s for s in spans if s["span_id"] == span_id]
            if matching_spans:
                node_to_spans[ns["node_id"]].append(matching_spans[0])

        # For each node, verify page range contains all span page_no values
        for node_id, node_spans_list in node_to_spans.items():
            node_info = [n for n in tree["nodes"] if n["node_id"] == node_id][0]

            span_pages = [s.get("page_no") for s in node_spans_list if s.get("page_no") is not None]

            if span_pages:
                assert node_info["page_start"] is not None, (
                    f"Node {node_info['title']} has spans with page_no but page_start is None"
                )
                assert node_info["page_end"] is not None, (
                    f"Node {node_info['title']} has spans with page_no but page_end is None"
                )

                min_span_page = min(span_pages)
                max_span_page = max(span_pages)

                assert node_info["page_start"] <= min_span_page, (
                    f"Node {node_info['title']} page_start={node_info['page_start']} "
                    f"> min span page_no={min_span_page}"
                )
                assert node_info["page_end"] >= max_span_page, (
                    f"Node {node_info['title']} page_end={node_info['page_end']} "
                    f"< max span page_no={max_span_page}"
                )

    def test_all_pages_covered_by_some_node(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every page_no present in canonical_spans must appear in at least one node.

        PageIndex expectation: the catalog must be complete - no page should be
        orphaned without a catalog entry.
        """
        sample_pdf = tmp_path / "all-pages-covered.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="All pages covered test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Collect all unique page_no values from spans
        all_span_pages = set(
            s.get("page_no") for s in spans if s.get("page_no") is not None
        )

        # Collect all pages covered by nodes (page_start to page_end inclusive)
        all_node_pages = set()
        for node in tree["nodes"]:
            if node["page_start"] is not None and node["page_end"] is not None:
                for page in range(node["page_start"], node["page_end"] + 1):
                    all_node_pages.add(page)

        # Every span page must be covered by some node
        for span_page in all_span_pages:
            assert span_page in all_node_pages, (
                f"Page {span_page} appears in spans but is not covered by any node's page range"
            )


# ===========================================================================
# TREE DEPTH INTEGRITY
# ===========================================================================


class TestTreeDepthIntegrity:
    """Evaluate whether level_no matches heading_path nesting depth."""

    def test_level_no_matches_heading_path_depth(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """level_no must equal the number of heading components minus 1.

        PageIndex expectation: catalog depth is derived from heading hierarchy,
        not arbitrary. A heading_path "A > B > C" must have level_no=2.
        """
        sample_pdf = tmp_path / "depth-integrity.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Depth integrity test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        for node in tree["nodes"]:
            heading_path = node["heading_path"]
            parts = [p.strip() for p in heading_path.split(" > ") if p.strip()]
            if not parts:
                parts = ["(root)"]

            expected_level = len(parts) - 1
            assert node["level_no"] == expected_level, (
                f"Node {node['title']} heading_path='{heading_path}' "
                f"has {len(parts)} parts, expected level_no={expected_level}, "
                f"got level_no={node['level_no']}"
            )

    def test_rollup_chain_depth_is_monotonic(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Rollup chain must have monotonically decreasing level_no (leaf to root).

        PageIndex expectation: catalog hierarchy is well-formed, each level
        corresponds to a heading component, no cycles or depth jumps.
        """
        sample_pdf = tmp_path / "chain-depth.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Chain depth test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # Test chain depth for each leaf node
        for ns in tree["node_spans"]:
            leaf_node_id = ns["node_id"]
            chain = query.rollup_chain(leaf_node_id)

            levels = [node["level_no"] for node in chain]
            assert levels == sorted(levels, reverse=True), (
                f"Chain from node {leaf_node_id} has non-monotonic levels: {levels}"
            )


# ===========================================================================
# SPAN-TO-NODE BIDIRECTIONAL INTEGRITY
# ===========================================================================


class TestSpanToNodeBidirectionalIntegrity:
    """Evaluate span-to-node linking completeness and correctness."""

    def test_all_spans_linked_to_leaf_nodes(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every canonical span must be linked to a tree node via tree_node_spans.

        PageIndex expectation: catalog entries cover all content - no orphan spans.
        """
        sample_pdf = tmp_path / "all-spans-linked.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="All spans linked test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Collect all span_ids from tree_node_spans
        linked_span_ids = {ns["span_id"] for ns in tree["node_spans"]}

        # Every span must appear in tree_node_spans
        for span in spans:
            assert span["span_id"] in linked_span_ids, (
                f"Span {span['span_id']} is not linked to any tree node"
            )

    def test_leaf_nodes_have_span_links(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every leaf node (lowest depth) must have at least one span link.

        PageIndex expectation: leaf catalog entries represent actual content,
        not empty placeholders.
        """
        sample_pdf = tmp_path / "leaf-has-spans.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Leaf has spans test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Identify leaf nodes (nodes that appear in tree_node_spans)
        leaf_node_ids = {ns["node_id"] for ns in tree["node_spans"]}

        # Nodes NOT in tree_node_spans are parent-only nodes
        # Nodes in tree_node_spans must have at least one span
        for leaf_node_id in leaf_node_ids:
            span_links = [ns for ns in tree["node_spans"] if ns["node_id"] == leaf_node_id]
            assert len(span_links) > 0, (
                f"Leaf node {leaf_node_id} appears in tree_node_spans but has no span links"
            )

    def test_parent_nodes_have_no_direct_spans(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Parent-only nodes must not have direct span links in tree_node_spans.

        PageIndex expectation: parent catalog entries aggregate child entries,
        not duplicate content.
        """
        sample_pdf = tmp_path / "parent-no-spans.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Parent no spans test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Identify leaf nodes
        leaf_node_ids = {ns["node_id"] for ns in tree["node_spans"]}

        # Find parent-only nodes
        parent_only_nodes = [
            n for n in tree["nodes"]
            if n["node_id"] not in leaf_node_ids
        ]

        # Parent-only nodes must not have span links
        for parent_node in parent_only_nodes:
            span_links = [ns for ns in tree["node_spans"] if ns["node_id"] == parent_node["node_id"]]
            assert len(span_links) == 0, (
                f"Parent-only node {parent_node['title']} has direct span links, "
                f"expected 0, got {len(span_links)}"
            )


# ===========================================================================
# HEADING_PATH PREFIX CONSISTENCY
# ===========================================================================


class TestHeadingPathPrefixConsistency:
    """Evaluate whether heading_paths form a prefix-consistent catalog hierarchy."""

    def test_heading_path_components_match_title_chain(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """heading_path must be formed by concatenating ancestor titles.

        PageIndex expectation: catalog hierarchy is well-formed, heading_path
        reflects the actual title chain, not arbitrary strings.
        """
        sample_pdf = tmp_path / "heading-chain.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Heading chain test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        query = TreeRollupQuery(live_db_connection)

        # For each leaf node, verify heading_path matches title chain
        for ns in tree["node_spans"]:
            leaf_node_id = ns["node_id"]
            chain = query.rollup_chain(leaf_node_id)

            # Extract titles from chain (leaf to root)
            titles = [node["title"] for node in chain]
            # Reverse to get root to leaf
            titles_reversed = list(reversed(titles))

            # Construct expected heading_path
            expected_heading = " > ".join(titles_reversed)

            actual_heading = chain[0]["heading_path"]

            assert actual_heading == expected_heading, (
                f"Node {chain[0]['title']} heading_path='{actual_heading}' "
                f"does not match title chain '{expected_heading}'"
            )

    def test_all_unique_heading_paths_get_nodes(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Every unique heading_path in spans must produce at least one tree node.

        PageIndex expectation: catalog completeness - no heading is orphaned.
        """
        sample_pdf = tmp_path / "all-headings-covered.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="All headings covered test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Collect all unique heading_paths from spans
        span_heading_paths = set(
            s.get("heading_path") or "(root)" for s in spans
        )

        # Collect all heading_paths from nodes
        node_heading_paths = set(n["heading_path"] for n in tree["nodes"])

        # Every span heading must appear in some node
        for span_heading in span_heading_paths:
            assert span_heading in node_heading_paths, (
                f"Heading '{span_heading}' appears in spans but has no corresponding tree node"
            )


# ===========================================================================
# EDGE CASES
# ===========================================================================


class TestPageIndexEdgeCases:
    """Edge case tests for PageIndex-style expectations."""

    def test_root_node_level_zero_and_no_parent(
        self, tmp_path: Path, live_db_connection, live_applied_schema, clean_live_db
    ) -> None:
        """Root nodes must have level_no=0 and parent_node_id=None.

        PageIndex expectation: catalog root is clearly marked.
        """
        sample_pdf = tmp_path / "root-node.pdf"
        _build_rich_pdf(sample_pdf)

        registry = PostgresRegistryWriter(live_db_connection)
        from llamaindex_runtime.ingestion import IngestionPipeline

        pipeline = IngestionPipeline(
            registry=registry,
            bundle_root=tmp_path,
            connection_factory=lambda: live_db_connection,
            reconciler=_FakeReconciler(),
        )
        result = pipeline.ingest(sample_pdf, title="Root node test")

        spans = registry.query_spans_by_version(result.version_id)
        tree = TreeGenerator().generate_tree(spans, version_id=result.version_id)
        registry.write_tree(
            version_id=result.version_id,
            nodes=tree["nodes"],
            node_spans=tree["node_spans"],
        )

        # Find root nodes
        root_nodes = [n for n in tree["nodes"] if n["parent_node_id"] is None]

        assert len(root_nodes) > 0, "Must have at least one root node"

        for root_node in root_nodes:
            assert root_node["level_no"] == 0, (
                f"Root node {root_node['title']} must have level_no=0, "
                f"got level_no={root_node['level_no']}"
            )
            assert root_node["parent_node_id"] is None, (
                f"Root node {root_node['title']} must have parent_node_id=None"
            )

