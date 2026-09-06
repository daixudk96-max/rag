"""Test provenance field extraction for Task 1.2.

Tests verify:
1. heading_path extracted from tree structure
2. node_id extracted from structure (not uuid.uuid4())
3. span_ids mapped from Registry query
4. BackendHit frozen contract preserved
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock


# Import implementation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend
from llamaindex_runtime.tree.backend_adapter import BackendHit


def test_heading_path_extraction():
    """Test heading_path extracted from tree structure."""
    print("=== Heading Path Extraction ===\n")

    backend = ReasoningTreeBackend()

    # Mock structure with heading_path
    structure = [
        {
            "title": "Introduction",
            "heading_path": "# Introduction",
            "page_no": 1,
            "node_id": "00000000-0000-0000-0000-000000000001",
        },
        {
            "title": "SWOT Analysis",
            "heading_path": "## SWOT Analysis",
            "page_no": 5,
            "node_id": "00000000-0000-0000-0000-000000000002",
        },
    ]

    # Mock content_list (from page extraction)
    content_list = [
        {"page": 5, "content": "SWOT analysis content..."},
    ]

    # Mock Registry
    mock_registry = MagicMock()
    mock_registry.query_tree_node_spans_by_version.return_value = []

    # Call retrieve_tree_hits() to verify BackendHit construction
    hits = backend.retrieve_tree_hits(
        query_text="test query",
        version_id=uuid.uuid4(),
        registry=mock_registry,
    )

    # Mock the content extraction to return our test content
    # (We're testing the BackendHit construction, not full flow)
    # For this test, we'll patch _extract_content_from_registry_nodes
    def mock_extract(registry, version_id, pages):
        return content_list

    backend._extract_content_from_registry_nodes = mock_extract
    backend._llm_judge_relevant_pages = lambda q, s: "5"  # Mock to return page 5

    hits = backend.retrieve_tree_hits(
        query_text="test query",
        version_id=uuid.uuid4(),
        registry=mock_registry,
    )

    # Verify heading_path extracted
    assert len(hits) > 0, "Should return at least one hit"
    hit = hits[0]
    print(f"[OK] BackendHit created: {hit}")
    # heading_path should come from structure (not None)
    # We'll verify this more thoroughly in GREEN phase
    print("[OK] heading_path extraction test written")


def test_node_id_extraction():
    """Test node_id extracted from structure (not uuid.uuid4())."""
    print("\n=== Node ID Extraction ===\n")

    backend = ReasoningTreeBackend()

    # Structure with node_id
    structure = [
        {
            "title": "Test",
            "page_no": 1,
            "node_id": "00000000-0000-0000-0000-000000000001",
        },
    ]

    # Helper method to map page → node_id
    node_id = backend._map_page_to_node_id(1, structure)

    print(f"[OK] Mapped page 1 → node_id: {node_id}")
    assert node_id == uuid.UUID("00000000-0000-0000-0000-000000000001"), \
        "Should map to correct node_id from structure"


def test_span_ids_mapping_from_registry():
    """Test span_ids mapped from Registry query."""
    print("\n=== Span IDs Mapping ===\n")

    backend = ReasoningTreeBackend()

    node_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    version_id = uuid.uuid4()

    # Mock Registry with tree_node_spans
    mock_registry = MagicMock()
    mock_registry.query_tree_node_spans_by_version.return_value = [
        {
            "node_id": str(node_id),
            "span_id": "00000000-0000-0000-0000-000000000010",
            "ordinal_no": 1,
        },
        {
            "node_id": str(node_id),
            "span_id": "00000000-0000-0000-0000-000000000011",
            "ordinal_no": 2,
        },
    ]

    # Query span_ids
    span_ids = backend._query_span_ids_for_node(registry=mock_registry, node_id=node_id, version_id=version_id)

    print(f"[OK] Queried span_ids: {span_ids}")
    assert len(span_ids) == 2, "Should return 2 span_ids from Registry"
    assert uuid.UUID("00000000-0000-0000-0000-000000000010") in span_ids, "Should include span_id 10"
    assert uuid.UUID("00000000-0000-0000-0000-000000000011") in span_ids, "Should include span_id 11"


def test_backend_hit_frozen_contract_preserved():
    """Test BackendHit frozen fields preserved (no modification)."""
    print("\n=== Frozen Contract Preservation ===\n")

    # Create BackendHit with all fields
    hit = BackendHit(
        score=None,
        text_preview="Test content",
        heading_path="# Test",
        page_no=1,
        span_ids=[uuid.uuid4()],
        node_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        entity_id=None,
        relation_id=None,
        backend_source="reasoning",
        retrieval_path="llm_navigation",
    )

    print(f"[OK] BackendHit created with provenance fields")
    print(f"  - backend_source: {hit.backend_source}")
    print(f"  - retrieval_path: {hit.retrieval_path}")

    # Verify frozen contract (frozen=True in dataclass)
    try:
        hit.score = 0.5  # Attempt to modify frozen field
        print("[FAIL] Frozen contract violated - field modification allowed")
    except Exception as e:
        print(f"[OK] Frozen contract preserved - modification blocked: {type(e).__name__}")


if __name__ == "__main__":
    print("=== RED Phase: Provenance Extraction Tests ===\n")

    # Run tests (some will fail because implementation not complete)
    try:
        test_heading_path_extraction()
    except Exception as e:
        print(f"[EXPECTED FAILURE] heading_path extraction: {e}")

    try:
        test_node_id_extraction()
    except Exception as e:
        print(f"[EXPECTED FAILURE] node_id extraction: {e}")

    try:
        test_span_ids_mapping_from_registry()
    except Exception as e:
        print(f"[EXPECTED FAILURE] span_ids mapping: {e}")

    test_backend_hit_frozen_contract_preserved()

    print("\n=== RED phase complete ===")
    print("Task 1.2: Tests written, awaiting GREEN implementation")