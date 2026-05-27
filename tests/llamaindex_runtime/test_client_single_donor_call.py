"""Test PageIndex client layer single donor call verification.

Tests verify that PageIndexClient.index() markdown path:
1. Only calls md_to_tree once (no double LLM invocation)
2. Exception handler doesn't trigger second donor call via adapter
3. Adapter layer unified LLM seam is NOT modified (already fixed in f1cf3d0)

This is CLIENT layer test, not adapter layer test.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Any

import pytest


@pytest.mark.integration
class TestPageIndexClientSingleDonorCall:
    """Tests for client layer single md_to_tree call verification."""

    def test_client_markdown_path_calls_md_to_tree_only_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that client markdown path only calls md_to_tree once, even on exception.

        Root cause: Exception handler (ImportError) calls adapter.index_tree(),
        which triggers second md_to_tree call via _call_pageindex_md_to_tree().
        Target: Exception handler should use stub directly, not call adapter.index_tree().
        """
        # Setup: Mock OPENAI_API_KEY
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient
        from llamaindex_runtime.registry import PostgresRegistryWriter

        # Create test markdown file
        test_md = tmp_path / "test.md"
        test_md.write_text("# Test Heading\n\nTest content.\n")

        # Mock registry (must be a valid mock even if write_to_registry=False)
        registry = MagicMock(spec=PostgresRegistryWriter)

        # Mock md_to_tree to track call count
        md_to_tree_call_count = 0

        def mock_md_to_tree(*args, **kwargs):
            nonlocal md_to_tree_call_count
            md_to_tree_call_count += 1
            # Simulate ImportError on first call to trigger exception handler
            if md_to_tree_call_count == 1:
                raise ImportError("Mock: PageIndex donor not installed")
            # Should never reach second call
            return {
                "structure": [{"title": "Test", "line_num": 1, "level": 1, "nodes": []}],
                "doc_name": "Test",
            }

        # Patch md_to_tree import
        with patch("pageindex.page_index_md.md_to_tree", side_effect=mock_md_to_tree):
            # Mock adapter.index_tree to prevent AttributeError and track calls
            adapter_index_tree_call_count = 0

            def mock_adapter_index_tree(*args, **kwargs):
                nonlocal adapter_index_tree_call_count
                adapter_index_tree_call_count += 1

            with patch(
                "llamaindex_runtime.tree.pageindex_adapter.PageIndexTreeAdapter.index_tree",
                side_effect=mock_adapter_index_tree,
            ):
                client = EnhancedPageIndexClient(registry=registry)
                # Exception handler should use stub, not call adapter.index_tree()
                doc_id = client.index(str(test_md), mode="md", write_to_registry=False)

        # RED EXPECTATION: Should only call md_to_tree ONCE
        # Current implementation: calls twice (first in try block, second in exception handler)
        assert md_to_tree_call_count == 1, (
            f"Client should only call md_to_tree once, but called {md_to_tree_call_count} times. "
            "Exception handler triggers second call via adapter.index_tree()."
        )

        # RED EXPECTATION: Exception handler should NOT call adapter.index_tree()
        # Current implementation: calls adapter.index_tree() in exception handler
        assert adapter_index_tree_call_count == 0, (
            f"Exception handler should not call adapter.index_tree(), but called {adapter_index_tree_call_count} times. "
            "Should use stub data directly instead."
        )

    def test_client_markdown_path_success_case_no_double_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GREEN: Test that successful markdown path doesn't call adapter.index_tree().

        Verify: When md_to_tree succeeds, client should:
        1. Call md_to_tree once
        2. Directly flatten and write to registry (no adapter.index_tree())
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient
        from llamaindex_runtime.registry import PostgresRegistryWriter

        test_md = tmp_path / "test_success.md"
        test_md.write_text("# Success Test\n\nContent.\n")

        registry = MagicMock(spec=PostgresRegistryWriter)
        registry.register_document = MagicMock(
            return_value=MagicMock(version_id=uuid.uuid4())
        )

        md_to_tree_call_count = 0
        adapter_index_tree_call_count = 0

        def mock_md_to_tree(*args, **kwargs):
            nonlocal md_to_tree_call_count
            md_to_tree_call_count += 1
            return {
                "structure": [{"title": "Success", "line_num": 1, "level": 1, "nodes": []}],
                "doc_name": "Success Doc",
                "doc_description": "Test",
                "line_count": 3,
            }

        # Mock adapter.index_tree to detect if it's called
        def mock_adapter_index_tree(*args, **kwargs):
            nonlocal adapter_index_tree_call_count
            adapter_index_tree_call_count += 1

        with patch("pageindex.page_index_md.md_to_tree", side_effect=mock_md_to_tree):
            with patch(
                "llamaindex_runtime.tree.pageindex_adapter.PageIndexTreeAdapter.index_tree",
                side_effect=mock_adapter_index_tree,
            ):
                client = EnhancedPageIndexClient(registry=registry)
                doc_id = client.index(str(test_md), mode="md", write_to_registry=True)

        # GREEN: Success case should not call adapter.index_tree()
        assert md_to_tree_call_count == 1, "Should call md_to_tree once"
        assert adapter_index_tree_call_count == 0, (
            "Success case should NOT call adapter.index_tree() - "
            "client directly flattens tree_structure"
        )

        # Verify registry.write_tree was called with flattened nodes
        assert registry.write_tree.called, "Should write to registry"

    def test_client_markdown_exception_handler_uses_stub_not_donor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: Test that exception handler uses stub data, not calls adapter.index_tree().

        Current behavior: ImportError → adapter.index_tree() → second md_to_tree call.
        Target behavior: ImportError → use stub tree_structure directly.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")

        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient
        from llamaindex_runtime.registry import PostgresRegistryWriter

        test_md = tmp_path / "test_exception.md"
        test_md.write_text("# Exception Test\n\nContent.\n")

        registry = MagicMock(spec=PostgresRegistryWriter)

        md_to_tree_call_count = 0

        def mock_md_to_tree(*args, **kwargs):
            nonlocal md_to_tree_call_count
            md_to_tree_call_count += 1
            # Always raise ImportError to trigger exception handler
            raise ImportError("Mock: PageIndex donor not installed")

        with patch("pageindex.page_index_md.md_to_tree", side_effect=mock_md_to_tree):
            # Pass workspace=None to disable lazy-load optimization (preserve structure)
            client = EnhancedPageIndexClient(registry=registry, workspace=None)
            # Should NOT raise exception - should use stub gracefully
            doc_id = client.index(str(test_md), mode="md", write_to_registry=False)

        # RED: Current implementation calls md_to_tree again in exception handler
        # Target: Should only call once, then use stub
        assert md_to_tree_call_count == 1, (
            f"Exception handler should not trigger second md_to_tree call. "
            f"Called {md_to_tree_call_count} times."
        )

        # Verify document was created with stub structure
        assert doc_id in client.documents
        doc = client.documents[doc_id]
        assert doc["type"] == "md"
        # Stub structure should be empty list (when workspace=None, structure is preserved)
        assert isinstance(doc.get("structure", []), list)
        assert doc.get("structure", []) == []  # Empty stub


@pytest.mark.integration
class TestAdapterLayerUnifiedSeamNotModified:
    """Verify adapter layer unified LLM seam is NOT touched during client layer fix.

    Commit f1cf3d0 already fixed adapter layer. This test ensures client layer fix
    doesn't revert or modify adapter layer changes.
    """

    def test_adapter_layer_md_to_tree_unified_seam_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GREEN: Verify adapter layer still uses RuntimeSettings.from_env_llm_only().

        Adapter layer fix (f1cf3d0): _call_pageindex_md_to_tree uses unified seam.
        Client layer fix should NOT change this.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-tdd")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        test_md = tmp_path / "test_adapter_seam.md"
        test_md.write_text("# Adapter Seam Test\n\nContent.\n")

        version_id = uuid.uuid4()
        registry = MagicMock()

        adapter = PageIndexTreeAdapter()

        # Mock RuntimeSettings.from_env_llm_only to verify it's called
        with patch(
            "llamaindex_runtime.config.RuntimeSettings.from_env_llm_only"
        ) as mock_unified_seam:
            mock_unified_seam.return_value = {"llm_model": "gpt-4o-mini"}

            # Mock md_to_tree to prevent real LLM call
            with patch("pageindex.page_index_md.md_to_tree") as mock_md_to_tree:
                mock_md_to_tree.return_value = {
                    "structure": [
                        {"title": "Adapter Test", "line_num": 1, "level": 1, "nodes": []}
                    ]
                }

                # This should fail gracefully or succeed
                try:
                    adapter.index_tree(
                        source_path=str(test_md),
                        version_id=version_id,
                        registry=registry,
                    )
                except Exception:
                    pass  # Expected in test environment

        # GREEN: Adapter layer should call unified seam
        # This verifies adapter layer fix is NOT reverted
        assert mock_unified_seam.called, (
            "Adapter layer must use RuntimeSettings.from_env_llm_only() - "
            "commit f1cf3d0 unified LLM seam must be preserved"
        )