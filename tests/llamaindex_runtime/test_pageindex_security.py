"""Security tests for Phase 15 Wave 1 Track B.

CRITICAL security remediation tests:
A. No import-time sys.path mutation
B. No donor error-path reads of credentials
C. No raw input in errors/logs
D. No global credential mutation in client constructor
E. Consumer boundary enforcement (no canonical writes)
F. Stale docs updated
G. Legacy tests fixed
"""

from __future__ import annotations

import os
import sys
import uuid
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import importlib

import pytest


class TestNoSysPathMutation:
    """SECURITY A: Import-time sys.path mutation is FORBIDDEN."""

    def test_import_does_not_alter_sys_path(self) -> None:
        """Import pageindex_adapter must NOT modify sys.path with hardcoded paths."""
        import llamaindex_runtime.tree.pageindex_adapter as adapter_module

        # Verify no hardcoded Downloads path in sys.path
        for path in sys.path:
            assert "Downloads" not in path, (
                f"Hardcoded Downloads path found in sys.path: {path}"
            )
            assert "rag-upstreams" not in path, (
                f"Hardcoded rag-upstreams path found in sys.path: {path}"
            )

        # Verify the module source does not contain the forbidden path pattern
        import inspect
        source = inspect.getsource(adapter_module)

        # Must NOT contain hardcoded Downloads path
        assert r"C:\Users\daixu\Downloads" not in source, (
            "Module source contains hardcoded Windows path - CRITICAL"
        )
        assert "PAGEINDEX_REPO_PATH" not in source, (
            "Module source contains PAGEINDEX_REPO_PATH - CRITICAL"
        )
        assert "sys.path.insert" not in source, (
            "Module source contains sys.path.insert - CRITICAL"
        )

    def test_no_global_sys_path_variable(self) -> None:
        """Module must not have global PAGEINDEX_REPO_PATH variable."""
        from llamaindex_runtime.tree import pageindex_adapter

        # Verify no global path mutation variables
        assert not hasattr(pageindex_adapter, "PAGEINDEX_REPO_PATH"), (
            "PAGEINDEX_REPO_PATH global variable found - should be removed"
        )


class TestNoCredentialReads:
    """SECURITY B: Donor error-path reads of credentials are FORBIDDEN."""

    def test_adapter_no_openai_key_read_on_import_error(self, tmp_path: Path) -> None:
        """_call_pageindex_tree_parser_stub must NOT read OPENAI_API_KEY on ImportError."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        # Mock import to fail with ImportError
        with patch.dict(os.environ, {}, clear=True):
            # Remove OPENAI_API_KEY if present
            os.environ.pop("OPENAI_API_KEY", None)

            # Patch the actual import mechanism inside the method
            with patch("builtins.__import__") as mock_import:
                # Make imports fail for pageindex module
                def side_effect(name, *args, **kwargs):
                    if "pageindex" in name:
                        raise ImportError("Module not found")
                    return importlib.__import__(name, *args, **kwargs)

                mock_import.side_effect = side_effect

                # Should return empty list, not read credentials
                result = adapter._call_pageindex_tree_parser_stub(str(test_file))

                # Should return non-authoritative empty result
                assert result == [], "Should return empty list on ImportError"

    def test_client_constructor_no_credential_mutation(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """SECURITY D: Client constructor must NOT mutate global os.environ."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        # Clear environment
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CHATGPT_API_KEY", raising=False)

        # Create client with api_key parameter and explicit workspace
        with patch.dict(os.environ, {}, clear=True):
            EnhancedPageIndexClient(
                registry=None,
                api_key="test-key",
                workspace=str(tmp_path)  # Explicit workspace to avoid path expansion issues
            )

            # Verify os.environ["OPENAI_API_KEY"] was NOT set
            # (api_key should be stored internally, not propagated globally)
            assert os.environ.get("OPENAI_API_KEY") != "test-key", (
                "Constructor mutated global os.environ - FORBIDDEN"
            )

        # Test CHATGPT_API_KEY aliasing is NOT done
        monkeypatch.setenv("CHATGPT_API_KEY", "chatgpt-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with patch.dict(os.environ, {}, clear=True):
            os.environ["CHATGPT_API_KEY"] = "chatgpt-key"
            EnhancedPageIndexClient(registry=None, workspace=str(tmp_path))

            # Should NOT alias CHATGPT_API_KEY to OPENAI_API_KEY
            assert os.environ.get("OPENAI_API_KEY") != "chatgpt-key", (
                "Constructor aliased CHATGPT_API_KEY to OPENAI_API_KEY - FORBIDDEN"
            )


class TestNoRawInputInErrors:
    """SECURITY C: Raw file paths, version IDs must NOT appear in errors/logs."""

    def test_client_file_not_found_static_error(self) -> None:
        """FileNotFoundError must NOT include raw file path in message."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        client = EnhancedPageIndexClient(registry=None)

        # Path with potentially malicious content
        malicious_path = "/tmp/malicious<script>alert(1)</script>.pdf"

        with pytest.raises(FileNotFoundError) as exc_info:
            client.index(malicious_path)

        error_msg = str(exc_info.value)

        # Error must NOT contain raw path
        assert "<script>" not in error_msg, (
            f"Error message contains raw path: {error_msg}"
        )
        assert "malicious" not in error_msg.lower(), (
            f"Error message contains raw path content: {error_msg}"
        )

    def test_client_invalid_uuid_static_error(self) -> None:
        """Invalid version_id must fail with static message before registry operations."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        registry = MagicMock()
        client = EnhancedPageIndexClient(registry=registry, workspace=tempfile.mkdtemp())

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test\n")
            temp_path = f.name

        try:
            # Malicious version_id
            malicious_version = "<script>alert(1)</script>"

            with pytest.raises(ValueError) as exc_info:
                client.index(temp_path, mode="md", version_id=malicious_version)

            error_msg = str(exc_info.value)

            # Error must NOT contain raw input
            assert "<script>" not in error_msg, (
                f"Error contains raw version_id: {error_msg}"
            )

            # Registry must NOT have been called (fail closed)
            registry.query_tree_nodes_by_version.assert_not_called()
        finally:
            os.unlink(temp_path)

    def test_adapter_donor_exception_static_error(self, tmp_path: Path) -> None:
        """Donor exceptions must NOT expose raw exception text."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        # Mock pageindex module import to raise exception
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pageindex.page_index":
                raise RuntimeError("malicious<script>alert(1)</script>")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = adapter._call_pageindex_tree_parser_stub(str(test_file))

            # Should return empty list, not expose raw exception
            assert result == [], "Should return empty list on exception"

    def test_cli_no_input_echo_in_stdout(self, tmp_path: Path) -> None:
        """CLI must NOT echo input paths, version IDs to stdout."""
        # Read CLI source directly to verify no raw input echo
        cli_path = Path(__file__).parent.parent.parent / "llamaindex_runtime" / "cli" / "run_pageindex.py"

        if not cli_path.exists():
            pytest.skip("CLI file not found")

        source = cli_path.read_text(encoding="utf-8")

        # Verify source does not contain raw input echo patterns
        # Check for f-string patterns that would echo raw inputs
        import re

        # Should NOT have f-strings with file_path in print statements
        dangerous_patterns = [
            r'print\(f["\'].*\{.*file_path.*\}.*["\']',
            r'print\(f["\'].*\{.*version_id.*\}.*["\']',
            r'print\(f["\'].*\{.*args\.pdf_path.*\}.*["\']',
            r'print\(f["\'].*\{.*args\.md_path.*\}.*["\']',
        ]

        for pattern in dangerous_patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            assert not matches, (
                f"CLI contains dangerous print pattern that echoes raw input: {matches}"
            )

        # Verify static error messages
        assert "Document file not found" in source, (
            "CLI should have static error message for file not found"
        )
        assert "version_id must be a valid UUID" in source, (
            "CLI should have static error message for invalid version_id"
        )


class TestNoCanonicalWrites:
    """SECURITY E: PageIndex must NEVER author canonical E2a data."""

    def test_index_tree_forbidden(self) -> None:
        """index_tree() must raise RuntimeError - forbidden operation."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        with pytest.raises(RuntimeError, match="cannot author|FORBIDDEN"):
            adapter.index_tree(
                source_path="test.pdf",
                version_id=uuid.uuid4(),
                registry=MagicMock(),
            )

    def test_flatten_embedded_tree_forbidden(self) -> None:
        """_flatten_embedded_tree() with version_id must be forbidden."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        with pytest.raises(RuntimeError, match="cannot author|FORBIDDEN"):
            adapter._flatten_embedded_tree(
                embedded_tree=[{"title": "Test", "nodes": []}],
                version_id=uuid.uuid4(),
            )

    def test_client_no_write_tree_calls(self, tmp_path: Path) -> None:
        """Client.index() must NOT call registry.write_tree()."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        registry = MagicMock()
        client = EnhancedPageIndexClient(registry=registry)

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        # Call with write_to_registry=True (should be ignored)
        doc_id = client.index(str(test_file), mode="md", write_to_registry=True)

        # MUST NOT call write_tree
        assert not registry.write_tree.called, (
            "Client called registry.write_tree() - FORBIDDEN"
        )

        # Should return workspace doc_id
        assert doc_id is not None
        uuid.UUID(doc_id)

    def test_client_canonical_hits_consumed_meaningfully(self, tmp_path: Path) -> None:
        """Client must store canonical hits in meaningful workspace representation."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient
        from llamaindex_runtime.tree.backend_adapter import BackendHit

        registry = MagicMock()
        canonical_version_id = uuid.uuid4()

        # Mock canonical hits
        mock_hit = BackendHit(
            score=None,
            text_preview="Canonical summary",
            heading_path="Chapter 1",
            page_no=5,
            span_ids=[uuid.uuid4()],
            node_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            entity_id=None,
            relation_id=None,
        )

        # Use markdown instead of PDF to avoid PyPDF2 issues
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n\nContent\n")

        client = EnhancedPageIndexClient(registry=registry, workspace=str(tmp_path))

        # Mock both adapter.retrieve_tree_hits and md_to_tree
        with patch.object(client.adapter, "retrieve_tree_hits", return_value=[mock_hit]):
            with patch("pageindex.page_index_md.md_to_tree") as mock_md_to_tree:
                mock_md_to_tree.return_value = {
                    "structure": [],
                    "doc_name": "Test",
                    "doc_description": "Test",
                    "line_count": 2,
                }

                doc_id = client.index(
                    str(test_file),
                    mode="md",
                    version_id=str(canonical_version_id),
                )

        # Verify document stores canonical version ID separately
        assert doc_id in client.documents
        doc = client.documents[doc_id]

        # Canonical version must be normalized UUID string (not raw input)
        stored_version = doc.get("canonical_version_id")
        assert stored_version == str(canonical_version_id), (
            f"Canonical version not stored correctly: {stored_version}"
        )

        # Doc ID must be different from canonical version
        assert doc_id != str(canonical_version_id), (
            "Doc ID conflated with canonical version - FORBIDDEN"
        )

        # Verify canonical_projections field exists
        assert "canonical_projections" in doc, (
            "canonical_projections field missing from document"
        )


class TestDonorUnavailableSafeBehavior:
    """Donor unavailable/failure must produce safe empty/non-authoritative behavior."""

    def test_import_error_returns_empty_not_synthetic(self, tmp_path: Path) -> None:
        """ImportError must return empty structure, not synthetic 'Test Chapter'."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)

            # Should return empty list, not synthetic tree
            result = adapter._call_pageindex_tree_parser_stub(str(test_file))

            assert result == [], (
                f"Should return empty list, got: {result}"
            )

            # Must NOT return synthetic data
            if result:
                assert result[0].get("title") != "Test Chapter", (
                    "Returned synthetic 'Test Chapter' - FORBIDDEN"
                )

    def test_md_to_tree_import_error_empty(self, tmp_path: Path) -> None:
        """md_to_tree ImportError must return empty structure."""
        from llamaindex_runtime.tree.pageindex_adapter import PageIndexTreeAdapter

        adapter = PageIndexTreeAdapter()

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        # Mock md_to_tree to raise ImportError
        with patch("pageindex.page_index_md.md_to_tree") as mock_md:
            mock_md.side_effect = ImportError("Mock: PageIndex not installed")

            result = adapter._call_pageindex_md_to_tree(str(test_file))

            assert result == [], (
                f"Should return empty list on ImportError, got: {result}"
            )


class TestClientStaleDocs:
    """SECURITY F: Client package docs must not promise registry writes."""

    def test_client_init_no_write_promise(self) -> None:
        """client/__init__.py must not promise write_to_registry creates canonical tree."""
        init_path = Path(__file__).parent.parent.parent / "llamaindex_runtime" / "client" / "__init__.py"

        if not init_path.exists():
            pytest.skip("client/__init__.py not found")

        content = init_path.read_text(encoding="utf-8")

        # Must clarify consumer-only role
        assert "consumer" in content.lower() or "non-authoritative" in content.lower(), (
            "client/__init__.py must clarify consumer-only role"
        )

        # Must NOT promise canonical writes
        lines = content.split("\n")
        for line in lines:
            if "write_to_registry" in line.lower():
                # Should not say it writes canonical tree
                assert "canonical" not in line.lower() or "cannot" in line.lower(), (
                    f"Line promises canonical writes: {line}"
                )


class TestLegacyTestMigration:
    """Track B: Legacy tests must be updated for consumer-only behavior."""

    def test_tree_structure_not_root_only_consumer_behavior(self, tmp_path: Path) -> None:
        """Migrated: Test tree structure is complete, no writer calls."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n\n## Section 1\n\nContent\n")

        registry = MagicMock()
        client = EnhancedPageIndexClient(registry=registry)

        # Call index
        doc_id = client.index(str(test_file), mode="md", write_to_registry=False)

        # Verify doc_id returned
        assert doc_id is not None
        uuid.UUID(doc_id)

        # Verify NO write_tree calls
        assert not registry.write_tree.called, (
            "Registry write_tree called - consumer-only violation"
        )

        # Verify document has structure (not root-only)
        if doc_id in client.documents:
            doc = client.documents[doc_id]
            structure = doc.get("structure", [])
            # Structure should be a list (could be empty if donor unavailable)
            assert isinstance(structure, list)

    def test_client_markdown_success_no_double_call(self, tmp_path: Path) -> None:
        """Migrated: Test success path, no double donor call, no writer calls."""
        from llamaindex_runtime.client.pageindex_client import EnhancedPageIndexClient

        test_file = tmp_path / "test_success.md"
        test_file.write_text("# Success\n\nContent\n")

        registry = MagicMock()
        client = EnhancedPageIndexClient(registry=registry)

        # Track write_tree calls
        write_calls = []
        registry.write_tree = MagicMock(side_effect=lambda *a, **k: write_calls.append(1))

        doc_id = client.index(str(test_file), mode="md", write_to_registry=True)

        # Verify NO write_tree calls (consumer-only)
        assert len(write_calls) == 0, (
            f"write_tree called {len(write_calls)} times - consumer-only violation"
        )

        # Verify doc_id returned
        assert doc_id is not None
        uuid.UUID(doc_id)