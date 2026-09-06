"""Test content extraction implementation for Task 1.3.

Tests verify:
1. Content extracted from tree_nodes table
2. Uses Registry seam (query_tree_nodes_by_version)
3. Returns real content (not stub placeholders)
4. Preserves frozen contracts (Registry seam used)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock


# Import implementation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.tree.reasoning_backend import ReasoningTreeBackend


def test_content_extracted_from_tree_nodes():
    """Test content extracted from tree_nodes table."""
    print("=== Content Extraction from tree_nodes ===\n")

    backend = ReasoningTreeBackend()

    version_id = uuid.uuid4()

    # Mock Registry with tree_nodes
    mock_registry = MagicMock()
    mock_registry.query_tree_nodes_by_version.return_value = [
        {
            "node_id": str(uuid.uuid4()),
            "title": "Introduction",
            "heading_path": "# Introduction",
            "page_start": 1,
            "page_end": 1,
            "summary_text": "This is the introduction section content.",
        },
        {
            "node_id": str(uuid.uuid4()),
            "title": "SWOT Analysis",
            "heading_path": "## SWOT Analysis",
            "page_start": 5,
            "page_end": 5,
            "summary_text": "SWOT analysis covers strengths, weaknesses, opportunities, and threats.",
        },
    ]

    # Extract content for pages "1,5"
    content_list = backend._extract_content_from_registry_nodes(
        registry=mock_registry,
        version_id=version_id,
        pages="1,5"
    )

    # Verify content extracted
    assert len(content_list) == 2, "Should return content for 2 pages"
    print(f"[OK] Extracted {len(content_list)} content items")

    # Verify content is real (not stub)
    item1 = content_list[0]
    assert item1.get("page") == 1, "First item should be page 1"
    assert "introduction" in item1.get("content", "").lower(), \
        "Content should contain real text (not stub)"
    print(f"[OK] Page 1 content: {item1.get('content')[:50]}...")

    item2 = content_list[1]
    assert item2.get("page") == 5, "Second item should be page 5"
    assert "SWOT" in item2.get("content", ""), \
        "Content should contain real text (not stub)"
    print(f"[OK] Page 5 content: {item2.get('content')[:50]}...")


def test_registry_seam_used():
    """Test that Registry seam is used (not direct SQL)."""
    print("\n=== Registry Seam Usage ===\n")

    backend = ReasoningTreeBackend()

    version_id = uuid.uuid4()

    # Mock Registry to verify seam call
    mock_registry = MagicMock()
    mock_registry.query_tree_nodes_by_version.return_value = []

    # Call extraction
    backend._extract_content_from_registry_nodes(
        registry=mock_registry,
        version_id=version_id,
        pages="1"
    )

    # Verify Registry seam called
    mock_registry.query_tree_nodes_by_version.assert_called_once_with(version_id)
    print("[OK] Registry seam used (query_tree_nodes_by_version called)")


def test_summary_text_or_title_used():
    """Test that summary_text or title is used as content."""
    print("\n=== Content Field Selection ===\n")

    backend = ReasoningTreeBackend()

    version_id = uuid.uuid4()

    # Mock Registry with nodes having different content fields
    mock_registry = MagicMock()

    # Node 1: Has summary_text
    node1 = {
        "node_id": str(uuid.uuid4()),
        "title": "Node 1 Title",
        "page_start": 1,
        "summary_text": "Rich summary text content",
    }

    # Node 2: No summary_text, use title
    node2 = {
        "node_id": str(uuid.uuid4()),
        "title": "Node 2 Title",
        "page_start": 2,
        "summary_text": None,
    }

    mock_registry.query_tree_nodes_by_version.return_value = [node1, node2]

    content_list = backend._extract_content_from_registry_nodes(
        registry=mock_registry,
        version_id=version_id,
        pages="1,2"
    )

    # Verify summary_text used when available
    item1 = content_list[0]
    assert item1.get("content") == "Rich summary text content", \
        "Should use summary_text when available"
    print(f"[OK] Node 1 used summary_text: {item1.get('content')}")

    # Verify title used when summary_text unavailable
    item2 = content_list[1]
    assert item2.get("content") == "Node 2 Title", \
        "Should use title when summary_text unavailable"
    print(f"[OK] Node 2 used title: {item2.get('content')}")


def test_no_stub_content_returned():
    """Test that no stub placeholder content is returned."""
    print("\n=== No Stub Content ===\n")

    backend = ReasoningTreeBackend()

    version_id = uuid.uuid4()

    # Mock Registry with real content
    mock_registry = MagicMock()
    mock_registry.query_tree_nodes_by_version.return_value = [
        {
            "node_id": str(uuid.uuid4()),
            "title": "Real Title",
            "page_start": 1,
            "summary_text": "Real content text",
        },
    ]

    content_list = backend._extract_content_from_registry_nodes(
        registry=mock_registry,
        version_id=version_id,
        pages="1"
    )

    # Verify no stub text
    content = content_list[0].get("content", "")
    assert "stub" not in content.lower(), \
        "Content should not contain stub placeholder text"
    print("[OK] No stub content returned")
    print(f"  Content: {content}")


if __name__ == "__main__":
    print("=== RED Phase: Content Extraction Tests ===\n")

    # Run tests (will fail because stub implementation)
    try:
        test_content_extracted_from_tree_nodes()
    except AssertionError as e:
        print(f"[EXPECTED FAILURE] content extraction: {e}")

    try:
        test_registry_seam_used()
    except Exception as e:
        print(f"[EXPECTED FAILURE] Registry seam: {e}")

    try:
        test_summary_text_or_title_used()
    except AssertionError as e:
        print(f"[EXPECTED FAILURE] content field selection: {e}")

    try:
        test_no_stub_content_returned()
    except AssertionError as e:
        print(f"[EXPECTED FAILURE] no stub content: {e}")

    print("\n=== RED phase complete ===")
    print("Task 1.3: Tests written, awaiting GREEN implementation")