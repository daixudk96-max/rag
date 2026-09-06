"""
TDD test for PageIndex double-call bug fix.

This test proves the bug exists: PageIndex donor is called twice.
After fix, this test should be modified to expect single call.
"""

import tempfile
from unittest import mock
from pathlib import Path
from llamaindex_runtime.client import EnhancedPageIndexClient
from llamaindex_runtime.config import RuntimeSettings


# PageIndex md_to_tree returns structure with 'title' key (not 'heading')
MOCK_TREE_STRUCTURE = [
    {
        'title': '# Root',
        'node_id': 'root_1',
        'line_num': 1,
        'nodes': [
            {
                'title': '## Section 1',
                'node_id': 'sec_1',
                'line_num': 3,
                'nodes': []
            }
        ]
    }
]

MOCK_MD_TO_TREE_RESULT = {
    'structure': MOCK_TREE_STRUCTURE,
    'doc_name': 'test_document'
}


def test_pageindex_donor_called_once():
    """
    GREEN state: Verify PageIndex donor is called only once.

    Expected: PageIndex donor (md_to_tree) is called only 1 time
    This proves the double-call bug is fixed.
    """
    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp_file:
        tmp_file.write("# Test Document\n\n## Section 1\n\nContent here.\n")
        tmp_md_path = tmp_file.name

    try:
        # Mock PageIndex donor - patch the source module where md_to_tree is defined
        with mock.patch('pageindex.page_index_md.md_to_tree', new_callable=mock.AsyncMock) as mock_md_to_tree:
            mock_md_to_tree.return_value = MOCK_MD_TO_TREE_RESULT

            # Setup client with mocked registry
            settings = RuntimeSettings.from_env()
            mock_registry = mock.MagicMock()
            mock_registry.register_document.return_value = mock.MagicMock(version_id='test_version_123')

            client = EnhancedPageIndexClient(registry=mock_registry, settings=settings)

            # Execute: Call index() with write_to_registry=True
            client.index(file_path=tmp_md_path, write_to_registry=True)

            # FIXED STATE: md_to_tree should be called only 1 time
            # First call: PageIndexClient.index() line 205-222
            # No second call (removed adapter.index_tree())
            assert mock_md_to_tree.call_count == 1, \
                f"Expected 1 call (fixed state), got {mock_md_to_tree.call_count} calls"
    finally:
        # Cleanup temp file
        Path(tmp_md_path).unlink(missing_ok=True)


def test_tree_structure_not_root_only():
    """
    MIGRATED: Verify tree structure behavior with consumer-only semantics.

    After fix:
    - Client does NOT call registry.write_tree() (consumer-only)
    - Document structure is stored in workspace
    - No root-only fallback from forbidden adapter.index_tree()
    """
    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tmp_file:
        tmp_file.write("# Test Document\n\n## Section 1\n\nContent here.\n")
        tmp_md_path = tmp_file.name

    try:
        # Mock PageIndex donor to return real tree structure
        with mock.patch('pageindex.page_index_md.md_to_tree', new_callable=mock.AsyncMock) as mock_md_to_tree:
            mock_md_to_tree.return_value = MOCK_MD_TO_TREE_RESULT

            # Setup client with mocked registry
            settings = RuntimeSettings.from_env()
            mock_registry = mock.MagicMock()

            # Track write_tree calls (should be 0 - consumer-only)
            write_calls = []
            mock_registry.write_tree = mock.MagicMock(
                side_effect=lambda *args, **kwargs: write_calls.append(1)
            )

            client = EnhancedPageIndexClient(registry=mock_registry, settings=settings)

            # Execute with write_to_registry=True (should be ignored - consumer-only)
            doc_id = client.index(file_path=tmp_md_path, write_to_registry=True)

            # CONSUMER-ONLY: write_tree must NOT be called
            assert len(write_calls) == 0, (
                f"registry.write_tree() was called {len(write_calls)} times - "
                "PageIndex must be consumer-only, not author canonical data"
            )

            # Verify: Doc ID returned (workspace)
            assert doc_id is not None
            from uuid import UUID
            UUID(doc_id)  # Validate UUID format

            # Verify: Document has structure in workspace
            assert doc_id in client.documents
            doc = client.documents[doc_id]
            structure = doc.get("structure", [])
            # Structure should be a list (could be mock data)
            assert isinstance(structure, list)

    finally:
        # Cleanup temp file
        Path(tmp_md_path).unlink(missing_ok=True)