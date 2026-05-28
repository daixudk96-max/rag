"""QUAL-03: Evidence-chain completeness validation tests.

Computes node-chunk mapping rate and heading_path completeness
against Phase 2 thresholds.

Thresholds (from Phase 2 research):
- Minimum node-chunk mapping rate: 0.80
- Minimum heading_path completeness (non-None): 0.95

Evidence from 2026-05-27 white-box verification:
- 326 vector_chunks (all embeddings generated)
- 70 chunks mapped to nodes (21.5%) — far below 0.80 threshold
- 64 heading_path None (20%) — far below 0.95 threshold
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

# --- Thresholds (from Phase 2 research, frozen) ---

MIN_NODE_CHUNK_MAPPING_RATE = 0.80
MIN_HEADING_PATH_COMPLETENESS = 0.95

# --- Fixture: Current white-box state (Level 2) ---

WHITEBOX_TOTAL_CHUNKS = 326
WHITEBOX_MAPPED_CHUNKS = 70
WHITEBOX_TOTAL_SPANS = 326
WHITEBOX_NONE_HEADING_PATHS = 64


def _make_mock_registry_with_evidence(
    version_id: uuid.UUID,
    chunks: list[dict[str, Any]] | None = None,
    nodes: list[dict[str, Any]] | None = None,
    spans: list[dict[str, Any]] | None = None,
    node_spans: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create mock registry with evidence-chain data."""
    registry = MagicMock()
    registry.query_vector_chunks_by_version = MagicMock(return_value=chunks or [])
    registry.query_tree_nodes_by_version = MagicMock(return_value=nodes or [])
    registry.query_spans_by_version = MagicMock(return_value=spans or [])
    registry.query_tree_node_spans_by_version = MagicMock(return_value=node_spans or [])
    registry.query_vector_chunk_spans_by_version = MagicMock(return_value=[])
    return registry


def _build_complete_evidence_chain(version_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Build fixture with complete evidence chain (passing state)."""
    nodes = [
        {
            "node_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1",
            "level_no": 1,
            "title": "Chapter 1",
        },
        {
            "node_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1/## Section 1.1",
            "level_no": 2,
            "title": "Section 1.1",
        },
    ]

    # All chunks mapped to nodes (100% mapping rate)
    chunks = [
        {
            "chunk_id": uuid.uuid4(),
            "version_id": version_id,
            "node_id": nodes[0]["node_id"],
        },
        {
            "chunk_id": uuid.uuid4(),
            "version_id": version_id,
            "node_id": nodes[1]["node_id"],
        },
    ]

    # All spans have heading_path (100% completeness)
    spans = [
        {
            "span_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1",
        },
        {
            "span_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": "# Chapter 1/## Section 1.1",
        },
    ]

    node_spans = [
        {"node_id": nodes[0]["node_id"], "span_id": spans[0]["span_id"]},
        {"node_id": nodes[1]["node_id"], "span_id": spans[1]["span_id"]},
    ]

    return {
        "nodes": nodes,
        "chunks": chunks,
        "spans": spans,
        "node_spans": node_spans,
    }


def _build_partial_evidence_chain(version_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Build fixture matching white-box state (failing state)."""
    # Simulate: 21.5% mapping rate, 80% heading_path completeness
    chunks = []
    mapped_node_ids = set()

    for i in range(100):
        chunk_id = uuid.uuid4()
        node_id = None
        if i < 22:  # ~22% mapped (close to 21.5%)
            node_id = uuid.uuid4()
            mapped_node_ids.add(node_id)
        chunks.append({
            "chunk_id": chunk_id,
            "version_id": version_id,
            "node_id": node_id,
        })

    spans = []
    for i in range(100):
        heading_path = f"# Section {i}" if i < 80 else None  # 80% non-None
        spans.append({
            "span_id": uuid.uuid4(),
            "version_id": version_id,
            "heading_path": heading_path,
        })

    return {
        "nodes": [],
        "chunks": chunks,
        "spans": spans,
        "node_spans": [],
    }


def _compute_node_chunk_mapping_rate(
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute node-chunk mapping rate from chunk data."""
    total = len(chunks)
    if total == 0:
        return {"mapped": 0, "total": 0, "rate": 0.0, "pass": False}

    mapped = sum(1 for c in chunks if c.get("node_id") is not None)
    rate = mapped / total
    return {
        "mapped": mapped,
        "total": total,
        "rate": rate,
        "threshold": MIN_NODE_CHUNK_MAPPING_RATE,
        "pass": rate >= MIN_NODE_CHUNK_MAPPING_RATE,
    }


def _compute_heading_path_completeness(
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute heading_path completeness from span data."""
    total = len(spans)
    if total == 0:
        return {"non_none": 0, "total": 0, "rate": 0.0, "pass": False}

    non_none = sum(1 for s in spans if s.get("heading_path") is not None)
    rate = non_none / total
    return {
        "non_none": non_none,
        "total": total,
        "rate": rate,
        "threshold": MIN_HEADING_PATH_COMPLETENESS,
        "pass": rate >= MIN_HEADING_PATH_COMPLETENESS,
    }


@pytest.mark.integration
class TestEvidenceChainCompleteness:
    """QUAL-03: Evidence-chain completeness checks."""

    def test_complete_evidence_chain_passes_node_chunk_mapping(self) -> None:
        """Verify that 100% mapping rate passes the 0.80 threshold."""
        version_id = uuid.uuid4()
        chain = _build_complete_evidence_chain(version_id)

        result = _compute_node_chunk_mapping_rate(chain["chunks"])
        assert result["pass"], (
            f"Complete chain should pass: rate={result['rate']:.2%}, "
            f"threshold={result['threshold']:.2%}"
        )

    def test_complete_evidence_chain_passes_heading_path(self) -> None:
        """Verify that 100% heading_path completeness passes the 0.95 threshold."""
        version_id = uuid.uuid4()
        chain = _build_complete_evidence_chain(version_id)

        result = _compute_heading_path_completeness(chain["spans"])
        assert result["pass"], (
            f"Complete chain should pass: rate={result['rate']:.2%}, "
            f"threshold={result['threshold']:.2%}"
        )

    def test_partial_evidence_chain_fails_node_chunk_mapping(self) -> None:
        """Verify that ~22% mapping rate fails the 0.80 threshold.

        This matches the 2026-05-27 white-box state: 21.5% mapping.
        """
        version_id = uuid.uuid4()
        chain = _build_partial_evidence_chain(version_id)

        result = _compute_node_chunk_mapping_rate(chain["chunks"])
        assert not result["pass"], (
            f"Partial chain should fail: rate={result['rate']:.2%}, "
            f"threshold={result['threshold']:.2%}"
        )

    def test_partial_evidence_chain_fails_heading_path(self) -> None:
        """Verify that 80% heading_path completeness fails the 0.95 threshold.

        This matches the 2026-05-27 white-box state: 20% None.
        """
        version_id = uuid.uuid4()
        chain = _build_partial_evidence_chain(version_id)

        result = _compute_heading_path_completeness(chain["spans"])
        assert not result["pass"], (
            f"Partial chain should fail: rate={result['rate']:.2%}, "
            f"threshold={result['threshold']:.2%}"
        )

    def test_whitebox_state_metrics_match_known_gaps(self) -> None:
        """Verify that white-box known metrics compute correctly.

        Known state: 70/326 chunks mapped, 64/326 heading_path None.
        """
        # Reconstruct from known counts
        chunks = [{"node_id": uuid.uuid4() if i < 70 else None} for i in range(326)]
        spans = [{"heading_path": f"h{i}" if i < 262 else None} for i in range(326)]

        mapping = _compute_node_chunk_mapping_rate(chunks)
        heading = _compute_heading_path_completeness(spans)

        assert mapping["mapped"] == 70
        assert mapping["total"] == 326
        assert abs(mapping["rate"] - 70 / 326) < 0.01

        assert heading["non_none"] == 262
        assert heading["total"] == 326
        assert abs(heading["rate"] - 262 / 326) < 0.01

    def test_node_chunk_mapping_rate_boundary(self) -> None:
        """Verify exact boundary: 80% mapping rate should pass."""
        version_id = uuid.uuid4()
        # Exactly 80% mapped
        chunks = [{"node_id": uuid.uuid4() if i < 80 else None} for i in range(100)]

        result = _compute_node_chunk_mapping_rate(chunks)
        assert result["rate"] == 0.80
        assert result["pass"], "Exact 80% should pass >= 0.80 threshold"

    def test_heading_path_completeness_boundary(self) -> None:
        """Verify exact boundary: 95% completeness should pass."""
        spans = [{"heading_path": f"h{i}" if i < 95 else None} for i in range(100)]

        result = _compute_heading_path_completeness(spans)
        assert result["rate"] == 0.95
        assert result["pass"], "Exact 95% should pass >= 0.95 threshold"

    def test_evidence_chain_report_structure(self) -> None:
        """Verify evidence chain report has all required fields."""
        version_id = uuid.uuid4()
        chain = _build_complete_evidence_chain(version_id)

        mapping = _compute_node_chunk_mapping_rate(chain["chunks"])
        heading = _compute_heading_path_completeness(chain["spans"])

        report = {
            "node_chunk_mapping": mapping,
            "heading_path_completeness": heading,
            "overall_pass": mapping["pass"] and heading["pass"],
        }

        assert "node_chunk_mapping" in report
        assert "heading_path_completeness" in report
        assert "overall_pass" in report
        assert "rate" in report["node_chunk_mapping"]
        assert "rate" in report["heading_path_completeness"]
        assert "threshold" in report["node_chunk_mapping"]
        assert "threshold" in report["heading_path_completeness"]
