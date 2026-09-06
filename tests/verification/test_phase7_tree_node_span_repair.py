"""Tests for Phase 7 tree-node span repair helpers."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "verification"
    / "phase7-db-backed-evidence-chain-rerun"
    / "repair_tree_node_spans.py"
)


def load_repair_module() -> ModuleType:
    """Load the repair script from its hyphenated directory."""
    spec = importlib.util.spec_from_file_location("repair_tree_node_spans", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_heading_path_accepts_tree_and_span_separators() -> None:
    module = load_repair_module()

    assert module.normalize_heading_path("Root > Section > Leaf") == (
        "Root",
        "Section",
        "Leaf",
    )
    assert module.normalize_heading_path("Root/Section/Leaf") == (
        "Root",
        "Section",
        "Leaf",
    )
    assert module.normalize_heading_path(None) == ("(root)",)


def test_build_span_node_mappings_uses_normalized_leaf_paths() -> None:
    module = load_repair_module()
    node_id = uuid.uuid4()
    span_a = uuid.uuid4()
    span_b = uuid.uuid4()
    unmatched_span = uuid.uuid4()

    nodes = [
        {
            "node_id": node_id,
            "heading_path": "Root/Section/Leaf",
        }
    ]
    spans = [
        {
            "span_id": span_a,
            "heading_path": "Root > Section > Leaf",
            "start_offset": 10,
        },
        {
            "span_id": unmatched_span,
            "heading_path": "Root > Other",
            "start_offset": 15,
        },
        {
            "span_id": span_b,
            "heading_path": "Root > Section > Leaf",
            "start_offset": 20,
        },
    ]

    result = module.build_span_node_mappings(spans=spans, nodes=nodes)

    assert result["unmatched_span_ids"] == [unmatched_span]


def test_build_span_node_mappings_falls_back_to_nearest_parent_node() -> None:
    module = load_repair_module()
    parent_node_id = uuid.uuid4()
    span_id = uuid.uuid4()

    nodes = [
        {
            "node_id": parent_node_id,
            "heading_path": "Root/Section",
        }
    ]
    spans = [
        {
            "span_id": span_id,
            "heading_path": "Root > Section > Missing Leaf",
            "start_offset": 10,
        }
    ]

    result = module.build_span_node_mappings(spans=spans, nodes=nodes)

    # Parent node should match via nearest-parent fallback, so no spans remain unmatched.
    assert result["unmatched_span_ids"] == []
    assert result["mappings"] == [
        {"node_id": parent_node_id, "span_id": span_id, "ordinal_no": 0}
    ]
