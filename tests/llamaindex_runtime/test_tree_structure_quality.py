"""QUAL-02: Tree structure quality validation tests.

Diagnoses PageIndex tree generation to distinguish donor-output
depth issues from flattening-level computation issues.

Thresholds (from Phase 2 research):
- Minimum tree depth: 3 levels
- Must distinguish: donor_issue vs flattening_issue vs config_issue vs pass
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

# --- Thresholds (from Phase 2 research, frozen) ---

MIN_TREE_DEPTH = 3

# --- Diagnosis categories ---
DIAGNOSIS_DONOR_ISSUE = "donor_issue"
DIAGNOSIS_FLATTENING_ISSUE = "flattening_issue"
DIAGNOSIS_CONFIG_ISSUE = "config_issue"
DIAGNOSIS_PASS = "pass"

# --- Donor output fixtures ---

DONOR_OUTPUT_HIERARCHICAL: list[dict[str, Any]] = [
    {
        "title": "# 第一章 概述",
        "start_index": 1,
        "end_index": 10,
        "nodes": [
            {
                "title": "## 市场概况",
                "start_index": 2,
                "end_index": 5,
                "nodes": [
                    {
                        "title": "### 核心算法原理",
                        "start_index": 3,
                        "end_index": 4,
                        "nodes": [],
                    },
                ],
            },
            {
                "title": "## 技术架构设计",
                "start_index": 6,
                "end_index": 10,
                "nodes": [],
            },
        ],
    },
    {
        "title": "# 第二章 实现",
        "start_index": 11,
        "end_index": 20,
        "nodes": [
            {
                "title": "## 数据流程",
                "start_index": 12,
                "end_index": 15,
                "nodes": [],
            },
        ],
    },
]

DONOR_OUTPUT_FLAT: list[dict[str, Any]] = [
    {
        "title": "Root Chapter",
        "start_index": 1,
        "end_index": 20,
        "nodes": [],
    },
]

DONOR_OUTPUT_TWO_LEVEL: list[dict[str, Any]] = [
    {
        "title": "# Chapter",
        "start_index": 1,
        "end_index": 10,
        "nodes": [
            {
                "title": "## Section",
                "start_index": 2,
                "end_index": 5,
                "nodes": [],
            },
        ],
    },
]


def _compute_max_depth(embedded_tree: list[dict[str, Any]], level: int = 0) -> int:
    """Compute maximum depth of embedded tree structure."""
    max_depth = level
    for node in embedded_tree:
        children = node.get("nodes", [])
        if children:
            child_depth = _compute_max_depth(children, level + 1)
            max_depth = max(max_depth, child_depth)
    return max_depth


def _compute_level_distribution(flat_nodes: list[dict[str, Any]]) -> dict[int, int]:
    """Compute level_no distribution from flattened nodes."""
    dist: dict[int, int] = {}
    for node in flat_nodes:
        lvl = node.get("level_no", 0)
        dist[lvl] = dist.get(lvl, 0) + 1
    return dist


def _diagnose_tree(
    donor_output: list[dict[str, Any]],
    flat_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diagnose tree structure issue category.

    Returns:
        {
            "diagnosis": "donor_issue" | "flattening_issue" | "config_issue" | "pass",
            "donor_depth": int,
            "flat_level_distribution": dict,
            "flat_max_level": int,
        }
    """
    donor_depth = _compute_max_depth(donor_output)
    level_dist = _compute_level_distribution(flat_nodes)
    flat_max_level = max(level_dist.keys()) if level_dist else 0

    if donor_depth + 1 < MIN_TREE_DEPTH:
        diagnosis = DIAGNOSIS_DONOR_ISSUE
    elif len(level_dist) == 1 and flat_max_level < MIN_TREE_DEPTH:
        diagnosis = DIAGNOSIS_FLATTENING_ISSUE
    elif flat_max_level >= MIN_TREE_DEPTH and donor_depth + 1 >= MIN_TREE_DEPTH:
        diagnosis = DIAGNOSIS_PASS
    else:
        diagnosis = DIAGNOSIS_CONFIG_ISSUE

    return {
        "diagnosis": diagnosis,
        "donor_depth": donor_depth,
        "flat_level_distribution": level_dist,
        "flat_max_level": flat_max_level,
    }


@pytest.mark.integration
class TestTreeStructureQuality:
    """QUAL-02: Tree structure diagnosis and quality checks."""

    def test_hierarchical_donor_output_produces_multi_level_tree(self) -> None:
        """Verify that hierarchical donor output produces 3+ level flat nodes."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_HIERARCHICAL, version_id=version_id
        )

        level_dist = _compute_level_distribution(flat_nodes)
        max_level = max(level_dist.keys()) if level_dist else 0

        assert max_level >= MIN_TREE_DEPTH, (
            f"Hierarchical donor output only produced max level {max_level}, "
            f"expected >= {MIN_TREE_DEPTH}. "
            f"Level distribution: {level_dist}"
        )

    def test_flat_donor_output_diagnosed_as_donor_issue(self) -> None:
        """Verify that flat donor output (no children) is diagnosed as donor_issue."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_FLAT, version_id=version_id
        )

        diagnosis = _diagnose_tree(DONOR_OUTPUT_FLAT, flat_nodes)
        assert diagnosis["diagnosis"] == DIAGNOSIS_DONOR_ISSUE, (
            f"Flat donor output should be diagnosed as donor_issue, "
            f"got {diagnosis['diagnosis']}"
        )

    def test_two_level_donor_output_diagnosed_correctly(self) -> None:
        """Verify that 2-level donor output (below threshold) is diagnosed."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_TWO_LEVEL, version_id=version_id
        )

        diagnosis = _diagnose_tree(DONOR_OUTPUT_TWO_LEVEL, flat_nodes)
        # 2 levels (depth=1, max_level=2) is below MIN_TREE_DEPTH=3
        assert diagnosis["diagnosis"] in (DIAGNOSIS_DONOR_ISSUE, DIAGNOSIS_FLATTENING_ISSUE), (
            f"2-level tree should not pass quality gate, "
            f"got {diagnosis['diagnosis']}"
        )

    def test_flattening_preserves_donor_depth(self) -> None:
        """Verify _flatten_embedded_tree preserves hierarchy depth from donor output."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_HIERARCHICAL, version_id=version_id
        )

        donor_depth = _compute_max_depth(DONOR_OUTPUT_HIERARCHICAL)
        level_dist = _compute_level_distribution(flat_nodes)

        # Donor depth 2 (0-indexed) → should produce levels 1,2,3 (1-indexed)
        # flat_max_level should be at least donor_depth + 1
        flat_max_level = max(level_dist.keys()) if level_dist else 0
        assert flat_max_level >= donor_depth + 1, (
            f"Flattening lost depth: donor_depth={donor_depth}, "
            f"flat_max_level={flat_max_level}"
        )

    def test_heading_path_reflects_hierarchy(self) -> None:
        """Verify heading_path shows parent chain for hierarchical nodes."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_HIERARCHICAL, version_id=version_id
        )

        # Check that at least one node has multi-segment heading_path
        multi_segment_paths = [
            n for n in flat_nodes
            if "/" in n.get("heading_path", "")
        ]
        assert len(multi_segment_paths) > 0, (
            "No nodes with hierarchical heading_path found — "
            "flattening may be losing parent chain"
        )

    def test_level_no_computed_from_heading_depth(self) -> None:
        """Verify level_no is computed from # symbols in headings."""
        adapter = PageIndexTreeAdapter()

        # Directly test _compute_level_from_heading
        assert adapter._compute_level_from_heading("# Title") == 1
        assert adapter._compute_level_from_heading("## Section") == 2
        assert adapter._compute_level_from_heading("### Subsection") == 3
        assert adapter._compute_level_from_heading("Plain text") == 1  # default

    def test_parent_node_id_set_for_child_nodes(self) -> None:
        """Verify child nodes have parent_node_id referencing their parent."""
        adapter = PageIndexTreeAdapter()
        version_id = uuid.uuid4()

        flat_nodes = adapter._flatten_embedded_tree(
            DONOR_OUTPUT_HIERARCHICAL, version_id=version_id
        )

        root_nodes = [n for n in flat_nodes if n["parent_node_id"] is None]
        child_nodes = [n for n in flat_nodes if n["parent_node_id"] is not None]

        assert len(root_nodes) >= 1, "Must have at least 1 root node"
        assert len(child_nodes) >= 1, "Must have at least 1 child node"

        # All parent_node_ids in child nodes must reference an existing node
        node_ids = {n["node_id"] for n in flat_nodes}
        for child in child_nodes:
            assert child["parent_node_id"] in node_ids, (
                f"Child node has orphan parent_node_id: {child['parent_node_id']}"
            )

    def test_current_whitebox_state_diagnosed_as_issue(self) -> None:
        """Verify that current white-box verification state (Level 0 only) is diagnosed.

        The 2026-05-27 white-box verification found:
        - tree_nodes_count: 10, but active_version_nodes: 2
        - max_level: 0 (only root nodes)
        - has_hierarchy: false
        """
        # Simulate the current white-box state
        flat_nodes = [
            {
                "node_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "parent_node_id": None,
                "level_no": 0,
                "title": "Root Node 1",
                "heading_path": "Root Node 1",
            },
            {
                "node_id": uuid.uuid4(),
                "version_id": uuid.uuid4(),
                "parent_node_id": None,
                "level_no": 0,
                "title": "Root Node 2",
                "heading_path": "Root Node 2",
            },
        ]

        level_dist = _compute_level_distribution(flat_nodes)
        assert level_dist == {0: 2}, f"Expected only level-0 nodes, got {level_dist}"
        assert max(level_dist.keys()) < MIN_TREE_DEPTH, (
            "Current white-box state should fail tree depth threshold"
        )
